"""CSV cache decorator for price sources."""

from pathlib import Path
from typing import cast

import pandas as pd

from quantfolio.constants import MIN_OBSERVATIONS
from quantfolio.models import PriceSeries
from quantfolio.sources.base import DateLike, PriceSource, naive_timestamp, validate_ticker


def _slug(value: str) -> str:
    """Return a filesystem-friendly slug for a provider name."""
    slug = "".join(character if character.isalnum() else "-" for character in value.lower())
    return slug.strip("-")


def _cache_stem(ticker: str) -> str:
    """Return a safe cache filename stem for a ticker."""
    stem = ticker.replace("/", "-").replace("\\", "-").replace("..", "-").strip("-")
    if not stem:
        msg = "El ticker no produce un nombre de caché válido."
        raise ValueError(msg)
    return stem


class CachedPriceSource(PriceSource):
    """Wrap a price source and reuse local CSV files while they are valid.

    Files are stored under a provider-specific subdirectory of ``cache_dir``. A cached file is
    reused only when it starts before the requested start date, its last observation is
    recent enough for the requested end date, and the ticker stored inside the file matches
    the requested ticker, so two tickers that sanitize to the same filename never share data.

    Args:
        source: Upstream price source used on cache misses.
        cache_dir: Directory that holds the CSV cache.
        ttl_days: Maximum accepted age of cached data, in calendar days.
        refresh: When true, always download and overwrite the cached files.

    """

    def __init__(
        self,
        source: PriceSource,
        *,
        cache_dir: str | Path = "data",
        ttl_days: int = 7,
        refresh: bool = False,
    ) -> None:
        """Validate the cache configuration and create the cache directory."""
        if ttl_days < 0:
            msg = "ttl_days no puede ser negativo."
            raise ValueError(msg)
        self._source = source
        self._cache_dir = Path(cache_dir)
        self._ttl_days = ttl_days
        self._refresh = refresh
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    @property
    def name(self) -> str:
        """Return the provider name with a cache marker."""
        return f"{self._source.name} (cache)"

    def get_prices(
        self,
        ticker: str,
        start: DateLike,
        end: DateLike | None = None,
    ) -> PriceSeries:
        """Return a price series from the cache when valid, or download and cache it.

        Args:
            ticker: Instrument identifier understood by the wrapped source.
            start: First observation date (inclusive).
            end: Last observation date (exclusive); defaults to the present.

        Returns:
            The normalized price series, labelled with its provenance.

        Raises:
            ValueError: If the ticker is empty, does not produce a safe cache filename, or
                the upstream source returns no data.

        """
        symbol = validate_ticker(ticker)
        path = self._cache_dir / _slug(self._source.name) / f"{_cache_stem(symbol)}.csv"
        if path.exists() and not self._refresh:
            cached = self._read_cache(path, symbol, start, end)
            if cached is not None:
                return cached
        asset = self._source.get_prices(symbol, start, end)
        self._write_cache(path, asset)
        return asset

    def _read_cache(
        self,
        path: Path,
        ticker: str,
        start: DateLike,
        end: DateLike | None,
    ) -> PriceSeries | None:
        """Return a cached series when it covers the requested window, else ``None``."""
        cached = self._read_cached_series(path, ticker)
        if cached is None:
            return None
        window = self._covered_window(cached, start, end)
        if len(window) < MIN_OBSERVATIONS:
            return None
        return PriceSeries(ticker=ticker, prices=window, source=self.name)

    def _read_cached_series(self, path: Path, ticker: str) -> PriceSeries | None:
        """Return the cached series when the file belongs to the requested ticker."""
        try:
            frame = pd.read_csv(
                path,
                index_col="Date",
                parse_dates=True,
                dtype={"Close": float, "ticker": str},
            )
            if frame.empty or not self._matches_ticker(frame, ticker):
                return None
            raw = cast("pd.Series[float]", frame["Close"])
            return PriceSeries(ticker=ticker, prices=raw, source=self.name)
        except OSError, KeyError, TypeError, ValueError:
            return None

    @staticmethod
    def _matches_ticker(frame: pd.DataFrame, ticker: str) -> bool:
        """Return whether the cached file was written for the requested ticker."""
        if "ticker" in frame.columns:
            return bool(frame["ticker"].iloc[0] == ticker)
        return _cache_stem(ticker) == ticker

    def _covered_window(
        self,
        cached: PriceSeries,
        start: DateLike,
        end: DateLike | None,
    ) -> pd.Series[float]:
        """Return the cached observations that fall inside the requested window.

        The window is empty when the file starts after ``start`` or is older than ``ttl_days``
        for the requested ``end``, so a short window always means a cache miss.
        """
        requested_start = naive_timestamp(start)
        requested_end = naive_timestamp(end) if end is not None else None
        reference = requested_end if requested_end is not None else pd.Timestamp.now().normalize()
        starts_late = cached.prices.index.min() > requested_start
        too_stale = cached.prices.index.max() < reference - pd.Timedelta(days=self._ttl_days)
        if starts_late or too_stale:
            return pd.Series(dtype=float)

        window = cached.prices[cached.prices.index >= requested_start]
        if requested_end is not None:
            window = window[window.index < requested_end]
        return window

    @staticmethod
    def _write_cache(path: Path, asset: PriceSeries) -> None:
        """Write the close prices and the ticker identity of a series to the CSV cache."""
        path.parent.mkdir(parents=True, exist_ok=True)
        asset.prices.rename("Close").to_frame().assign(ticker=asset.ticker).to_csv(
            path, index_label="Date"
        )
