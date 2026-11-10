"""Inflation alignment, real monthly returns, reporting and purchasing-power simulation."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from quantfolio.currency import ExchangeRates
from quantfolio.macro import MacroSeries
from quantfolio.models import PriceSeries
from quantfolio.portfolio import Portfolio
from quantfolio.simulation import MonteCarloParameters
from tests.support.builders import make_prices, make_series


def _portfolio(*, reporting_currency: str | None = "USD") -> Portfolio:
    """Build a portfolio with complete monthly closes and returns in four reference months."""
    dates = pd.DatetimeIndex(
        ["2024-12-31", "2025-01-15", "2025-01-31", "2025-02-28", "2025-03-31", "2025-04-30"]
    )
    asset = PriceSeries(
        "AAA",
        pd.Series([100.0, 105.0, 110.0, 99.0, 108.9, 119.79], index=dates),
        quote_currency="USD",
    )
    return Portfolio(
        assets={"AAA": asset},
        weights={"AAA": 1.0},
        reporting_currency=reporting_currency,
    )


def _index(
    values: list[float],
    dates: list[str] | None = None,
    *,
    vintage_date: str | None = None,
) -> MacroSeries:
    """Build a CPI index with first-of-month reference dates."""
    reference_dates = dates or ["2024-12-01", "2025-01-01", "2025-02-01", "2025-03-01"]
    return MacroSeries(
        series_id="CPIAUCNS",
        values=make_prices(values, dates=reference_dates),
        vintage_date=pd.Timestamp(vintage_date) if vintage_date is not None else None,
    )


def _monthly_portfolio(
    dates: list[str],
    values: list[float],
    *,
    reporting_currency: str | None = "USD",
) -> Portfolio:
    asset = make_series(
        "AAA",
        values,
        dates=dates,
        quote_currency=reporting_currency,
    )
    return Portfolio(
        assets={"AAA": asset},
        weights={"AAA": 1.0},
        reporting_currency=reporting_currency,
    )


def test_real_monthly_returns_compound_daily_returns_then_deflate() -> None:
    """Nominal returns are compounded within each complete month before CPI deflation."""
    result = _portfolio().real_monthly_returns(_index([100.0, 102.0, 101.0, 103.0]))

    expected = pd.Series(
        [1.1 / 1.02 - 1.0, 0.9 / (101.0 / 102.0) - 1.0, 1.1 / (103.0 / 101.0) - 1.0],
        index=pd.date_range("2025-01-31", periods=3, freq="ME"),
        name="real_monthly_return",
    )
    pd.testing.assert_series_equal(result, expected)


def test_real_returns_use_reporting_currency_prices_before_inflation() -> None:
    """Historical FX conversion happens before monthly nominal returns are measured."""
    dates = pd.DatetimeIndex(["2024-12-31", "2025-01-31", "2025-02-28"])
    asset = PriceSeries(
        "EUR_ASSET",
        pd.Series([100.0, 110.0, 100.0], index=dates),
        quote_currency="EUR",
    )
    rates = PriceSeries(
        "FX:EUR/USD",
        pd.Series([1.0, 1.1, 1.2], index=dates),
        quote_currency="USD",
    )
    portfolio = Portfolio(
        assets={"EUR_ASSET": asset},
        weights={"EUR_ASSET": 1.0},
        reporting_currency="USD",
        exchange_rates=ExchangeRates([rates]),
    )

    result = portfolio.real_monthly_returns(
        _index([100.0, 110.0, 110.0], ["2024-12-01", "2025-01-01", "2025-02-01"])
    )

    assert result.tolist() == pytest.approx([0.1, 120.0 / 121.0 - 1.0])


def test_real_returns_require_a_reporting_currency() -> None:
    """Purchasing-power analysis has no meaning without a currency context."""
    portfolio = _portfolio(reporting_currency=None)
    cpi = _index([100.0, 101.0, 102.0, 103.0])
    with pytest.raises(ValueError, match="divisa de reporte"):
        portfolio.real_monthly_returns(cpi)


@pytest.mark.parametrize(
    ("values", "dates", "message"),
    [
        ([100.0, 0.0, 102.0, 103.0], None, "positivos"),
        ([100.0, -1.0, 102.0, 103.0], None, "positivos"),
        (
            [100.0, 101.0, 102.0, 103.0],
            ["2024-12-01", "2025-01-01", "2025-01-15", "2025-03-01"],
            "duplicad",
        ),
        (
            [100.0, 101.0, 102.0, 103.0],
            ["2024-12-01", "2025-01-01", "2025-01-01", "2025-03-01"],
            "duplicad",
        ),
        (
            [100.0, 101.0, 103.0],
            ["2024-12-01", "2025-01-01", "2025-03-01"],
            "faltan meses",
        ),
    ],
)
def test_real_returns_reject_duplicate_negative_or_nonconsecutive_cpi(
    values: list[float],
    dates: list[str] | None,
    message: str,
) -> None:
    """CPI inputs need one positive level for each consecutive reference month."""
    portfolio = _portfolio()
    cpi = _index(values, dates)
    with pytest.raises(ValueError, match=message):
        portfolio.real_monthly_returns(cpi)


def test_real_returns_reject_insufficient_cpi_overlap() -> None:
    """A CPI sample outside the portfolio months cannot deflate any return."""
    portfolio = _portfolio()
    cpi = _index([100.0, 101.0], ["2023-01-01", "2023-02-01"])
    with pytest.raises(ValueError, match="coincidencia"):
        portfolio.real_monthly_returns(cpi)


@pytest.mark.parametrize(
    ("price_dates", "cpi_dates"),
    [
        (
            ["2024-12-31", "2025-01-31", "2025-03-31"],
            ["2024-12-01", "2025-01-01", "2025-02-01", "2025-03-01"],
        ),
        (
            ["2024-12-31", "2025-01-31", "2025-03-31"],
            ["2025-02-01", "2025-03-01"],
        ),
    ],
)
def test_real_returns_reject_a_gap_in_portfolio_months(
    price_dates: list[str],
    cpi_dates: list[str],
) -> None:
    """A return cannot span an absent interior month, even when CPI overlap exists."""
    portfolio = _monthly_portfolio(price_dates, [100.0, 110.0, 121.0])
    cpi = _index([102.0, 104.0, 106.0, 108.0][-len(cpi_dates) :], cpi_dates)

    with pytest.raises(ValueError, match="cartera faltan meses"):
        portfolio.real_monthly_returns(cpi)


def test_partial_boundary_months_are_omitted() -> None:
    """A mid-month first close and a mid-month final close do not anchor full months."""
    first = _monthly_portfolio(
        ["2025-01-15", "2025-01-31", "2025-02-28", "2025-03-31"],
        [100.0, 100.0, 110.0, 121.0],
    ).real_monthly_returns(_index([100.0, 102.0, 104.0, 106.0]))
    last = _monthly_portfolio(
        ["2024-12-31", "2025-01-31", "2025-02-28", "2025-03-14"],
        [100.0, 110.0, 121.0, 133.1],
    ).real_monthly_returns(_index([100.0, 102.0, 104.0, 106.0]))

    assert list(first.index) == [pd.Timestamp("2025-02-28"), pd.Timestamp("2025-03-31")]
    assert first.tolist() == pytest.approx([1.1 / (104 / 102) - 1, 1.1 / (106 / 104) - 1])
    assert list(last.index) == [pd.Timestamp("2025-01-31"), pd.Timestamp("2025-02-28")]


def test_partial_prior_month_is_not_used_as_a_full_month_base() -> None:
    """A mid-December base cannot represent the full December-to-January return."""
    portfolio = _monthly_portfolio(
        ["2024-12-15", "2025-01-31", "2025-02-28"],
        [100.0, 110.0, 121.0],
    )
    result = portfolio.real_monthly_returns(
        _index([100.0, 102.0, 104.0], ["2024-12-01", "2025-01-01", "2025-02-01"])
    )

    assert list(result.index) == [pd.Timestamp("2025-02-28")]


@pytest.mark.parametrize(
    ("dates", "message"),
    [
        (
            ["2025-07-31", "2025-08-29", "2025-09-30"],
            "weekday",
        ),
        (
            ["2025-07-31", "2025-08-31", "2025-09-30"],
            "weekend",
        ),
    ],
)
def test_month_completeness_accepts_business_and_calendar_end_dates(
    dates: list[str],
    message: str,
) -> None:
    """Regular portfolios accept the last business day; weekend data require calendar ends."""
    del message
    portfolio = _monthly_portfolio(dates, [100.0, 110.0, 121.0])
    result = portfolio.real_monthly_returns(
        _index([100.0, 102.0, 104.0], ["2025-07-01", "2025-08-01", "2025-09-01"])
    )

    assert list(result.index) == [pd.Timestamp("2025-08-31"), pd.Timestamp("2025-09-30")]


def test_incomplete_interior_month_is_rejected() -> None:
    """A partial interior close contaminates both adjacent monthly returns."""
    portfolio = _monthly_portfolio(
        ["2024-12-31", "2025-01-15", "2025-02-28", "2025-03-31"],
        [100.0, 110.0, 121.0, 133.1],
    )
    cpi = _index([100.0, 102.0, 104.0, 106.0])
    with pytest.raises(ValueError, match="meses interiores incompletos"):
        portfolio.real_monthly_returns(cpi)


def test_report_pairs_nominal_and_real_metrics_on_cpi_covered_months() -> None:
    """The report shows CPI provenance, the shared period and paired growth metrics."""
    report = _portfolio().report(
        inflation_index=_index([100.0, 102.0, 101.0, 103.0], vintage_date="2025-04-15"),
        include_quality=False,
        include_warnings=False,
    )

    assert "CPIAUCNS" in report
    assert "2025-04-15" in report
    assert "2025-01-31 → 2025-03-31" in report
    assert "| Rentabilidad acumulada | 8.90% | 5.73% |" in report
    assert "| Volatilidad anualizada mensual |" in report
    assert "| Máxima caída |" in report
    assert "| Rentabilidad media diaria |" in report


def test_report_marks_unavailable_metrics_for_a_single_real_return() -> None:
    """One covered month supports cumulative growth but not sample risk measures."""
    report = _portfolio().report(
        inflation_index=_index([100.0, 102.0], ["2024-12-01", "2025-01-01"]),
        include_quality=False,
        include_warnings=False,
    )

    assert "| CAGR | No disponible | No disponible |" in report
    assert "| Volatilidad anualizada mensual | No disponible | No disponible |" in report
    assert "| Máxima caída | No disponible | No disponible |" in report
    assert "Vintage: no especificado" in report


@pytest.mark.parametrize("rate", [0.0, 0.04, -0.02])
def test_real_simulation_deflates_nominal_paths_without_changing_random_draws(rate: float) -> None:
    """Fixed inflation preserves path shape and converts each step consistently."""
    portfolio = _portfolio()
    settings = MonteCarloParameters(n_paths=3, horizon=4, periods_per_year=12, seed=8)
    nominal = portfolio.simulate_monte_carlo(settings)
    real = portfolio.simulate_real_monte_carlo(settings, annual_inflation_rate=rate)

    factors = (1.0 + rate) ** (np.arange(5) / 12)
    np.testing.assert_allclose(real.to_numpy(), nominal.to_numpy() / factors[:, None])
    assert real.shape == nominal.shape
    assert real.iloc[0].tolist() == nominal.iloc[0].tolist()
    assert real.attrs["scenario"] == (f"Poder adquisitivo con inflación fija anual de {rate:.2%}")


@pytest.mark.parametrize("rate", [-1.0, -1.1, math.nan, math.inf, -math.inf])
def test_real_simulation_rejects_invalid_inflation(rate: float) -> None:
    """Fixed inflation must be finite and greater than minus one hundred percent."""
    portfolio = _portfolio()
    with pytest.raises(ValueError, match="inflación"):
        portfolio.simulate_real_monte_carlo(annual_inflation_rate=rate)
