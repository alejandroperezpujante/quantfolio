"""Contract shared by every historical market-data provider."""

from abc import ABC, abstractmethod
from datetime import date
from typing import TYPE_CHECKING, cast

import pandas as pd

if TYPE_CHECKING:
    from collections.abc import Sequence

    from quantfolio.models import PriceSeries

DateLike = str | date


def naive_timestamp(value: DateLike) -> pd.Timestamp:
    """Convert a date-like value to a timezone-naive timestamp."""
    stamp = pd.Timestamp(value)
    if stamp.tz is not None:
        return stamp.tz_localize(None)
    return stamp


def validate_ticker(ticker: str) -> str:
    """Return the normalized ticker after validating it is a non-empty string.

    Args:
        ticker: Instrument identifier as provided by the caller.

    Returns:
        The identifier without surrounding whitespace.

    Raises:
        TypeError: If ``ticker`` is not a string.
        ValueError: If ``ticker`` is empty or whitespace.

    """
    if not isinstance(cast("object", ticker), str):
        msg = "El ticker debe ser un texto."
        raise TypeError(msg)
    symbol = ticker.strip()
    if not symbol:
        msg = "El ticker no puede estar vacío."
        raise ValueError(msg)
    return symbol


class PriceSource(ABC):
    """Abstract contract for historical price providers.

    Every provider returns :class:`quantfolio.models.PriceSeries` objects, so the analysis
    layer is independent of the underlying API.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the human-readable provider name."""
        raise NotImplementedError

    @abstractmethod
    def get_prices(
        self,
        ticker: str,
        start: DateLike,
        end: DateLike | None = None,
    ) -> PriceSeries:
        """Return the close-price history of one instrument.

        Args:
            ticker: Instrument identifier understood by the provider.
            start: First observation date (inclusive).
            end: Last observation date (exclusive); defaults to the present.

        Returns:
            The normalized price series.

        """
        raise NotImplementedError

    def get_many(
        self,
        tickers: Sequence[str],
        start: DateLike,
        end: DateLike | None = None,
    ) -> dict[str, PriceSeries]:
        """Return the close-price history of several instruments in batch.

        Args:
            tickers: Instrument identifiers; duplicates are rejected.
            start: First observation date (inclusive).
            end: Last observation date (exclusive); defaults to the present.

        Returns:
            Mapping from ticker to the corresponding normalized price series.

        Raises:
            ValueError: If ``tickers`` is empty or contains duplicates.

        """
        symbols = list(tickers)
        if not symbols:
            msg = "Debes proporcionar al menos un ticker."
            raise ValueError(msg)
        if len(set(symbols)) != len(symbols):
            msg = "La lista de tickers contiene duplicados."
            raise ValueError(msg)
        return {symbol: self.get_prices(symbol, start, end) for symbol in symbols}
