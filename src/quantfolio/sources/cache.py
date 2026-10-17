"""CSV cache decorator for price sources."""

from pathlib import Path
from typing import cast

import pandas as pd

from quantfolio.constants import MIN_OBSERVATIONS
from quantfolio.models import PriceSeries
from quantfolio.sources.base import DateLike, PriceSource, validate_ticker


def _slug(value: str) -> str:
    """Return a filesystem-friendly slug for a provider name."""
    slug = "".join(character if character.isalnum() else "-" for character in value.lower())
    return slug.strip("-")


def _naive_timestamp(value: DateLike) -> pd.Timestamp:
    """Convert a date-like value to a timezone-naive timestamp."""
    stamp = pd.Timestamp(value)
    if stamp.tz is not None:
        return stamp.tz_localize(None)
    return stamp


class CachedPriceSource(PriceSource):
    """Wrap a price source and reuse local CSV files while they are valid.

    Files are stored under a provider-specific subdirectory of ``cache_dir``. A cached file is
    reused only when it starts before the requested start date and its last observation is
    recent enough for the requested end date.

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
            ValueError: If the ticker is empty or the upstream source returns no data.

        """
        symbol = validate_ticker(ticker)
        path = self._cache_dir / _slug(self._source.name) / f"{symbol}.csv"
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
        try:
            frame = pd.read_csv(path, index_col="Date", parse_dates=True)
            raw = cast("pd.Series[float]", frame["Close"])
            cached = PriceSeries(ticker=ticker, prices=raw, source=self.name)
        except OSError, KeyError, TypeError, ValueError:
            return None

        requested_start = _naive_timestamp(start)
        if cached.prices.index.min() > requested_start:
            return None
        requested_end = _naive_timestamp(end) if end is not None else None
        reference = requested_end if requested_end is not None else pd.Timestamp.now().normalize()
        if cached.prices.index.max() < reference - pd.Timedelta(days=self._ttl_days):
            return None

        window = cached.prices[cached.prices.index >= requested_start]
        if requested_end is not None:
            window = window[window.index < requested_end]
        if len(window) < MIN_OBSERVATIONS:
            return None
        return PriceSeries(ticker=ticker, prices=window, source=self.name)

    @staticmethod
    def _write_cache(path: Path, asset: PriceSeries) -> None:
        """Write the close prices of a series to the CSV cache."""
        path.parent.mkdir(parents=True, exist_ok=True)
        asset.prices.rename("Close").to_csv(path, index_label="Date")
