"""Yahoo Finance price source."""

from typing import TYPE_CHECKING, cast

import pandas as pd
import yfinance as yf  # type: ignore[import-untyped]

from quantfolio.models import PriceSeries
from quantfolio.sources.base import PriceSource, validate_ticker

if TYPE_CHECKING:
    from quantfolio.sources.base import DateLike


def _first_column(selection: pd.Series[float] | pd.DataFrame) -> pd.Series[float]:
    """Return a series unchanged or the first column of a frame.

    ``DataFrame.xs`` keeps a frame when it leaves at least one column behind, so multi-level
    yfinance responses are reduced to the first ticker column.
    """
    if isinstance(selection, pd.DataFrame):
        return cast("pd.Series[float]", selection.iloc[:, 0])
    return selection


def _extract_close(data: pd.DataFrame) -> pd.Series[float]:
    """Return the close-price column of a yfinance response.

    Args:
        data: Frame returned by ``yfinance.download``.

    Returns:
        Close prices indexed by date.

    Raises:
        ValueError: If the response does not contain a close-price column.

    """
    if isinstance(data.columns, pd.MultiIndex):
        return _first_column(data.xs("Close", axis=1, level=0))
    if "Close" not in data.columns:
        msg = "La descarga no contiene la columna Close."
        raise ValueError(msg)
    return cast("pd.Series[float]", data["Close"])


class YahooFinanceSource(PriceSource):
    """Historical close prices from Yahoo Finance through ``yfinance``."""

    @property
    def name(self) -> str:
        """Return the provider name."""
        return "Yahoo Finance"

    def get_prices(
        self,
        ticker: str,
        start: DateLike,
        end: DateLike | None = None,
    ) -> PriceSeries:
        """Download the adjusted close-price history of one instrument.

        Args:
            ticker: Yahoo Finance symbol, for example ``"AAPL"`` or ``"^GSPC"``.
            start: First observation date (inclusive).
            end: Last observation date (exclusive); defaults to the present.

        Returns:
            The normalized price series.

        Raises:
            ValueError: If the symbol is empty or the download returns no usable data.

        """
        symbol = validate_ticker(ticker)
        data = cast(
            "pd.DataFrame",
            yf.download(
                symbol,
                start=start,
                end=end,
                auto_adjust=True,
                progress=False,
                threads=False,
            ),
        )
        if data.empty:
            msg = f"No se han encontrado datos para {symbol}."
            raise ValueError(msg)
        prices = _extract_close(data).rename(symbol)
        prices.index = pd.DatetimeIndex(prices.index)
        return PriceSeries(ticker=symbol, prices=prices, source=self.name)
