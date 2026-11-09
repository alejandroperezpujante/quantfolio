"""Offline tests for portfolio purchasing-power analysis."""

import math

import numpy as np
import pandas as pd
import pytest

from quantfolio.currency import ExchangeRates
from quantfolio.macro import MacroSeries
from quantfolio.models import PriceSeries
from quantfolio.portfolio import Portfolio
from quantfolio.simulation import MonteCarloParameters


def _portfolio(*, reporting_currency: str | None = "USD") -> Portfolio:
    """Build a portfolio with a return in each of four reference months."""
    dates = pd.DatetimeIndex(
        ["2024-12-31", "2025-01-15", "2025-01-31", "2025-02-28", "2025-03-31", "2025-04-30"]
    )
    asset = PriceSeries(
        ticker="AAA",
        prices=pd.Series([100.0, 105.0, 110.0, 99.0, 108.9, 119.79], index=dates),
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
    dates = dates or ["2024-12-01", "2025-01-01", "2025-02-01", "2025-03-01"]
    return MacroSeries(
        series_id="CPIAUCNS",
        values=pd.Series(values, index=pd.DatetimeIndex(dates)),
        vintage_date=pd.Timestamp(vintage_date) if vintage_date else None,
    )


def test_real_monthly_returns_compound_then_deflate_and_truncate() -> None:
    """The first-month daily returns compound before exact CPI deflation."""
    result = _portfolio().real_monthly_returns(_index([100.0, 102.0, 101.0, 103.0]))

    expected = pd.Series(
        [1.1 / 1.02 - 1.0, 0.9 / (101.0 / 102.0) - 1.0, 1.1 / (103.0 / 101.0) - 1.0],
        index=pd.date_range("2025-01-31", periods=3, freq="ME"),
        name="real_monthly_return",
    )
    pd.testing.assert_series_equal(result, expected)


def test_real_monthly_returns_use_converted_asset_prices() -> None:
    """The nominal input is calculated after historical FX conversion."""
    dates = pd.DatetimeIndex(["2024-12-31", "2025-01-31", "2025-02-28"])
    asset = PriceSeries(
        ticker="EUR_ASSET",
        prices=pd.Series([100.0, 110.0, 100.0], index=dates),
        quote_currency="EUR",
    )
    rates = PriceSeries(
        ticker="FX:EUR/USD",
        prices=pd.Series([1.0, 1.1, 1.2], index=dates),
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


def test_real_monthly_returns_requires_reporting_currency() -> None:
    """Purchasing-power analysis needs an explicit currency context."""
    portfolio = _portfolio(reporting_currency=None)
    inflation_index = _index([100, 101, 102, 103])
    with pytest.raises(ValueError, match="divisa de reporte"):
        portfolio.real_monthly_returns(inflation_index)


@pytest.mark.parametrize(
    ("values", "dates", "message"),
    [
        ([100, 0, 102, 103], None, "positivos"),
        ([100, -1, 102, 103], None, "positivos"),
        (
            [100, 101, 102, 103],
            ["2024-12-01", "2025-01-01", "2025-01-15", "2025-03-01"],
            "duplicad",
        ),
        (
            [100, 101, 102, 103],
            ["2024-12-01", "2025-01-01", "2025-01-01", "2025-03-01"],
            "duplicad",
        ),
        ([100, 101, 103], ["2024-12-01", "2025-01-01", "2025-03-01"], "faltan meses"),
    ],
)
def test_real_monthly_returns_rejects_invalid_cpi(
    values: list[float], dates: list[str] | None, message: str
) -> None:
    """CPI must contain one positive index level per consecutive month."""
    portfolio = _portfolio()
    inflation_index = _index(values, dates)
    with pytest.raises(ValueError, match=message):
        portfolio.real_monthly_returns(inflation_index)


def test_real_monthly_returns_rejects_insufficient_overlap() -> None:
    """A CPI observation without its previous reference month cannot deflate a return."""
    portfolio = _portfolio()
    inflation_index = _index([100, 101], ["2023-01-01", "2023-02-01"])
    with pytest.raises(ValueError, match="coincidencia"):
        portfolio.real_monthly_returns(inflation_index)


def test_real_monthly_returns_rejects_missing_portfolio_month() -> None:
    """A gap in the matched portfolio months cannot be annualized as consecutive months."""
    asset = PriceSeries(
        ticker="AAA",
        prices=pd.Series(
            [100.0, 110.0, 121.0],
            index=pd.DatetimeIndex(["2024-12-31", "2025-01-31", "2025-03-31"]),
        ),
        quote_currency="USD",
    )
    portfolio = Portfolio(assets={"AAA": asset}, weights={"AAA": 1.0}, reporting_currency="USD")
    inflation_index = _index([100, 101, 102, 103])

    with pytest.raises(ValueError, match="cartera faltan meses"):
        portfolio.real_monthly_returns(inflation_index)


def test_real_monthly_returns_rejects_gap_before_first_cpi_month() -> None:
    """CPI overlap cannot hide a portfolio return spanning an absent month."""
    asset = PriceSeries(
        ticker="AAA",
        prices=pd.Series(
            [100.0, 110.0, 121.0],
            index=pd.DatetimeIndex(["2024-12-31", "2025-01-31", "2025-03-31"]),
        ),
        quote_currency="USD",
    )
    portfolio = Portfolio(assets={"AAA": asset}, weights={"AAA": 1.0}, reporting_currency="USD")
    inflation_index = _index([102, 104], ["2025-02-01", "2025-03-01"])

    with pytest.raises(ValueError, match="cartera faltan meses"):
        portfolio.real_monthly_returns(inflation_index)


def test_real_monthly_returns_omit_partial_first_month() -> None:
    """Returns beginning mid-month cannot use a full month of CPI deflation."""
    dates = pd.DatetimeIndex(["2025-01-15", "2025-01-31", "2025-02-28", "2025-03-31"])
    asset = PriceSeries(
        ticker="AAA",
        prices=pd.Series([100.0, 100.0, 110.0, 121.0], index=dates),
        quote_currency="USD",
    )
    portfolio = Portfolio(assets={"AAA": asset}, weights={"AAA": 1.0}, reporting_currency="USD")
    inflation_index = _index([100, 102, 104, 106])

    result = portfolio.real_monthly_returns(inflation_index)

    assert list(result.index) == [pd.Timestamp("2025-02-28"), pd.Timestamp("2025-03-31")]
    assert result.tolist() == pytest.approx([1.1 / (104 / 102) - 1, 1.1 / (106 / 104) - 1])


def test_real_monthly_returns_omit_partial_last_month() -> None:
    """A price history ending before the last trading day omits that month."""
    dates = pd.DatetimeIndex(["2024-12-31", "2025-01-31", "2025-02-28", "2025-03-14"])
    asset = PriceSeries(
        ticker="AAA",
        prices=pd.Series([100.0, 110.0, 121.0, 133.1], index=dates),
        quote_currency="USD",
    )
    portfolio = Portfolio(assets={"AAA": asset}, weights={"AAA": 1.0}, reporting_currency="USD")
    inflation_index = _index([100, 102, 104, 106])

    result = portfolio.real_monthly_returns(inflation_index)

    assert list(result.index) == [pd.Timestamp("2025-01-31"), pd.Timestamp("2025-02-28")]


def test_real_monthly_returns_require_complete_prior_month_close() -> None:
    """A partial price base month cannot anchor the next month's full return."""
    dates = pd.DatetimeIndex(["2024-12-15", "2025-01-31", "2025-02-28"])
    asset = PriceSeries(
        ticker="AAA",
        prices=pd.Series([100.0, 110.0, 121.0], index=dates),
        quote_currency="USD",
    )
    portfolio = Portfolio(assets={"AAA": asset}, weights={"AAA": 1.0}, reporting_currency="USD")
    inflation_index = _index([100, 102, 104], ["2024-12-01", "2025-01-01", "2025-02-01"])

    result = portfolio.real_monthly_returns(inflation_index)

    assert list(result.index) == [pd.Timestamp("2025-02-28")]


def test_real_monthly_returns_accept_last_weekday_of_month() -> None:
    """A Friday close may finish a month whose final calendar day is Sunday."""
    dates = pd.DatetimeIndex(["2025-07-31", "2025-08-29", "2025-09-30"])
    asset = PriceSeries(
        ticker="AAA",
        prices=pd.Series([100.0, 110.0, 121.0], index=dates),
        quote_currency="USD",
    )
    portfolio = Portfolio(assets={"AAA": asset}, weights={"AAA": 1.0}, reporting_currency="USD")
    inflation_index = _index([100, 102, 104], ["2025-07-01", "2025-08-01", "2025-09-01"])

    result = portfolio.real_monthly_returns(inflation_index)

    assert list(result.index) == [pd.Timestamp("2025-08-31"), pd.Timestamp("2025-09-30")]


def test_real_monthly_returns_use_calendar_end_for_weekend_prices() -> None:
    """A weekend-traded portfolio requires the actual last calendar day."""
    dates = pd.DatetimeIndex(["2025-07-31", "2025-08-31", "2025-09-30"])
    asset = PriceSeries(
        ticker="AAA",
        prices=pd.Series([100.0, 110.0, 121.0], index=dates),
        quote_currency="USD",
    )
    portfolio = Portfolio(assets={"AAA": asset}, weights={"AAA": 1.0}, reporting_currency="USD")
    inflation_index = _index([100, 102, 104], ["2025-07-01", "2025-08-01", "2025-09-01"])

    result = portfolio.real_monthly_returns(inflation_index)

    assert list(result.index) == [pd.Timestamp("2025-08-31"), pd.Timestamp("2025-09-30")]


def test_real_monthly_returns_rejects_incomplete_interior_month() -> None:
    """An incomplete interior close would contaminate adjacent monthly returns."""
    dates = pd.DatetimeIndex(["2024-12-31", "2025-01-15", "2025-02-28", "2025-03-31"])
    asset = PriceSeries(
        ticker="AAA",
        prices=pd.Series([100.0, 110.0, 121.0, 133.1], index=dates),
        quote_currency="USD",
    )
    portfolio = Portfolio(assets={"AAA": asset}, weights={"AAA": 1.0}, reporting_currency="USD")
    inflation_index = _index([100, 102, 104, 106])

    with pytest.raises(ValueError, match="meses interiores incompletos"):
        portfolio.real_monthly_returns(inflation_index)


def test_report_pairs_metrics_on_cpi_covered_months() -> None:
    """Nominal and real metrics use the same months and show CPI provenance."""
    report = _portfolio().report(
        inflation_index=_index([100, 102, 101, 103], vintage_date="2025-04-15"),
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


def test_report_marks_short_real_history_metrics_unavailable() -> None:
    """One covered return permits cumulative return but not sample risk metrics."""
    report = _portfolio().report(
        inflation_index=_index([100, 102], ["2024-12-01", "2025-01-01"]),
        include_quality=False,
        include_warnings=False,
    )

    assert "| CAGR | No disponible | No disponible |" in report
    assert "| Volatilidad anualizada mensual | No disponible | No disponible |" in report
    assert "| Máxima caída | No disponible | No disponible |" in report
    assert "Vintage: no especificado" in report


@pytest.mark.parametrize("rate", [0.0, 0.04, -0.02])
def test_real_simulation_deflates_identical_nominal_paths(rate: float) -> None:
    """Fixed inflation changes units while retaining every nominal random draw."""
    portfolio = _portfolio()
    settings = MonteCarloParameters(n_paths=3, horizon=4, periods_per_year=12, seed=8)
    nominal = portfolio.simulate_monte_carlo(settings)
    real = portfolio.simulate_real_monte_carlo(settings, annual_inflation_rate=rate)

    factors = (1.0 + rate) ** (np.arange(5) / 12)
    np.testing.assert_allclose(real.to_numpy(), nominal.to_numpy() / factors[:, None])
    assert real.shape == nominal.shape
    assert real.iloc[0].tolist() == nominal.iloc[0].tolist()
    assert "inflación fija" in real.attrs["scenario"]


@pytest.mark.parametrize("rate", [-1.0, -1.1, math.nan, math.inf, -math.inf])
def test_real_simulation_rejects_invalid_inflation(rate: float) -> None:
    """The assumed annual inflation rate must be finite and above minus 100%."""
    portfolio = _portfolio()
    with pytest.raises(ValueError, match="inflación"):
        portfolio.simulate_real_monte_carlo(annual_inflation_rate=rate)
