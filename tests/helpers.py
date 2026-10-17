"""Builders and fakes shared by the test suite."""

import pandas as pd

from quantfolio.models import PriceSeries
from quantfolio.sources.base import DateLike, PriceSource

#: Deterministic business-day calendar used to build price series.
TRADING_DATES = pd.bdate_range("2025-01-02", periods=40)


def make_prices(values: list[float], *, start: int = 0) -> pd.Series[float]:
    """Return a float price series on the shared business-day calendar."""
    index = TRADING_DATES[start : start + len(values)]
    return pd.Series(values, index=index, dtype=float)


def make_series(ticker: str, values: list[float], *, start: int = 0) -> PriceSeries:
    """Return a price series built on the shared business-day calendar."""
    return PriceSeries(ticker=ticker, prices=make_prices(values, start=start))


class StubSource(PriceSource):
    """Deterministic in-memory price source used by the source tests."""

    def __init__(self, dates: pd.DatetimeIndex, name: str = "Stub") -> None:
        """Store the calendar served by the source."""
        self.dates = dates
        self._name = name
        self.calls = 0

    @property
    def name(self) -> str:
        """Return the provider name."""
        return self._name

    def get_prices(
        self,
        ticker: str,
        start: DateLike,
        end: DateLike | None = None,
    ) -> PriceSeries:
        """Return a deterministic slice of the configured calendar."""
        self.calls += 1
        start_stamp = pd.Timestamp(start)
        end_stamp = pd.Timestamp(end) if end is not None else None
        mask = self.dates >= start_stamp
        if end_stamp is not None:
            mask = mask & (self.dates < end_stamp)
        window = self.dates[mask]
        prices = pd.Series(
            [10.0 + position for position in range(len(window))],
            index=window,
            dtype=float,
        )
        return PriceSeries(ticker=ticker, prices=prices, source=self.name)
