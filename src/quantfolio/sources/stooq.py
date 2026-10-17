"""Stooq price source using its keyless CSV endpoint."""

from datetime import UTC, datetime
from urllib.parse import urlencode

import pandas as pd

from quantfolio.models import PriceSeries
from quantfolio.sources.base import DateLike, PriceSource, validate_ticker

STOOQ_CSV_URL = "https://stooq.com/q/d/l/"


def _format_day(value: DateLike) -> str:
    """Return a date formatted as ``YYYYMMDD`` for the Stooq endpoint."""
    return pd.Timestamp(value).strftime("%Y%m%d")


class StooqSource(PriceSource):
    """Historical close prices from Stooq.

    Stooq exposes a keyless CSV endpoint, so this provider complements Yahoo Finance and
    demonstrates that both APIs produce identical internal objects.
    """

    @property
    def name(self) -> str:
        """Return the provider name."""
        return "Stooq"

    def get_prices(
        self,
        ticker: str,
        start: DateLike,
        end: DateLike | None = None,
    ) -> PriceSeries:
        """Download the close-price history of one instrument.

        Args:
            ticker: Stooq symbol, for example ``"aapl.us"`` or ``"^spx"``.
            start: First observation date (inclusive).
            end: Last observation date (inclusive); defaults to today.

        Returns:
            The normalized price series.

        Raises:
            ValueError: If the symbol is empty or the endpoint returns no usable data.

        """
        symbol = validate_ticker(ticker)
        params = {
            "s": symbol,
            "d1": _format_day(start),
            "d2": _format_day(end if end is not None else datetime.now(tz=UTC).date()),
            "i": "d",
        }
        try:
            data = pd.read_csv(f"{STOOQ_CSV_URL}?{urlencode(params)}")
        except (OSError, ValueError) as exc:
            msg = f"No se pudo descargar la serie {symbol} de Stooq: {exc}"
            raise ValueError(msg) from exc
        if data.empty or "Close" not in data.columns:
            msg = f"No se han encontrado datos para {symbol} en Stooq."
            raise ValueError(msg)
        dates = pd.to_datetime(data["Date"], errors="coerce")
        prices = pd.Series(
            pd.to_numeric(data["Close"], errors="coerce").to_numpy(),
            index=pd.DatetimeIndex(dates),
            name=symbol,
        )
        prices = prices[prices.index.notna()]
        return PriceSeries(ticker=symbol, prices=prices, source=self.name)
