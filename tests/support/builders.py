"""Deterministic data builders shared across test layers."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

from quantfolio.macro import MacroSeries
from quantfolio.models import PriceSeries

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import date

#: Shared business-day calendar used by unit, contract and integration fixtures.
TRADING_DATES = pd.bdate_range("2025-01-02", periods=80)


def make_prices(
    values: Sequence[float],
    *,
    dates: Sequence[str | date | pd.Timestamp] | pd.DatetimeIndex | None = None,
    start: int = 0,
) -> pd.Series[float]:
    """Build a float price series on explicit dates or the shared trading calendar."""
    index = (
        TRADING_DATES[start : start + len(values)]
        if dates is None
        else pd.DatetimeIndex([pd.Timestamp(observation) for observation in dates])
    )
    return pd.Series(values, index=index, dtype=float)


def make_series(  # noqa: PLR0913
    ticker: str,
    values: Sequence[float],
    *,
    dates: Sequence[str | date | pd.Timestamp] | pd.DatetimeIndex | None = None,
    start: int = 0,
    source: str = "Stub",
    quote_currency: str | None = None,
    quote_unit: str | None = None,
) -> PriceSeries:
    """Build a fully labelled price series."""
    return PriceSeries(
        ticker=ticker,
        prices=make_prices(values, dates=dates, start=start),
        source=source,
        quote_currency=quote_currency,
        quote_unit=quote_unit,
    )


def make_macro_series(  # noqa: PLR0913
    series_id: str,
    values: Sequence[float],
    *,
    dates: Sequence[str | date | pd.Timestamp] | pd.DatetimeIndex | None = None,
    start: int = 0,
    source: str = "FRED",
    vintage_date: pd.Timestamp | None = None,
) -> MacroSeries:
    """Build a normalized macro series on explicit dates or the shared trading calendar."""
    return MacroSeries(
        series_id=series_id,
        values=make_prices(values, dates=dates, start=start),
        source=source,
        vintage_date=vintage_date,
    )


def month_end_index(*, start: str = "2024-12-31", periods: int = 25) -> pd.DatetimeIndex:
    """Return deterministic month-end observations."""
    return pd.date_range(start=start, periods=periods, freq="ME")


def make_cpi_series(*, periods: int = 25, monthly_rate: float = 0.002) -> pd.Series[float]:
    """Return a strictly increasing CPI level series ending in late 2026."""
    index = month_end_index(periods=periods)
    values = [300.0 * (1.0 + monthly_rate) ** position for position in range(periods)]
    return pd.Series(values, index=index, dtype=float)
