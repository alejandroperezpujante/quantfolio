"""End-to-end FRED inflation ingestion, purchasing-power analysis and real simulation."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quantfolio import FredMacroSource, MonteCarloParameters, Portfolio
from quantfolio.models import PriceSeries
from tests.support.transports import install_fred


def _daily_portfolio() -> Portfolio:
    """Return a USD portfolio with complete monthly closes over eight months."""
    dates = pd.bdate_range("2024-12-31", "2025-07-31")
    prices = [100.0 * (1.004**position) for position in range(len(dates))]
    asset = PriceSeries(
        "US_ASSET",
        pd.Series(prices, index=dates),
        source="Manual",
        quote_currency="USD",
    )
    return Portfolio(
        assets={asset.ticker: asset},
        weights={asset.ticker: 1.0},
        reporting_currency="USD",
    )


def test_fred_cpi_drives_real_returns_report_and_real_simulation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The public CPI series feeds aligned real returns, the report and deflated paths."""
    cpi_dates = pd.date_range("2024-12-01", "2025-07-01", freq="MS")
    cpi = pd.Series(
        [300.0 * (1.002**position) for position in range(len(cpi_dates))],
        index=cpi_dates,
        dtype=float,
    )
    install_fred(
        monkeypatch,
        {"CPIAUCNS": cpi},
        vintages={"CPIAUCNS": pd.Timestamp("2025-09-15").date()},
    )
    inflation = FredMacroSource().get_series(
        "CPIAUCNS",
        start="2024-12-01",
        end="2025-08-01",
        as_of="2025-09-15",
    )

    portfolio = _daily_portfolio()
    real = portfolio.real_monthly_returns(inflation)

    assert len(real) == 7
    assert real.index.min() == pd.Timestamp("2025-01-31")
    assert real.index.max() == pd.Timestamp("2025-07-31")
    nominal_returns = portfolio.portfolio_returns()
    january_mask = pd.DatetimeIndex(nominal_returns.index).month == 1
    january = pd.Series(nominal_returns.to_numpy()[january_mask], dtype=float)
    january_nominal = float(np.prod(1.0 + january.to_numpy(dtype=float)) - 1.0)
    january_inflation = float(cpi.loc["2025-01-01"] / cpi.loc["2024-12-01"] - 1.0)
    assert real.loc["2025-01-31"] == pytest.approx(
        (1.0 + january_nominal) / (1.0 + january_inflation) - 1.0
    )

    report = portfolio.report(inflation_index=inflation)
    assert "Poder adquisitivo e inflación" in report
    assert "CPIAUCNS" in report
    assert "Vintage: 2025-09-15" in report
    assert "| Rentabilidad acumulada |" in report
    assert "| Métrica | Nominal | Real (poder adquisitivo) |" in report

    settings = MonteCarloParameters(n_paths=3, horizon=12, seed=7)
    first = portfolio.simulate_real_monte_carlo(settings, annual_inflation_rate=0.03)
    second = portfolio.simulate_real_monte_carlo(settings, annual_inflation_rate=0.03)
    pd.testing.assert_frame_equal(first, second)
    assert first.attrs["scenario"] == "Poder adquisitivo con inflación fija anual de 3.00%"
    assert first.iloc[0, 0] == pytest.approx(10_000.0)
    assert float(first.iloc[-1].median()) < float(
        portfolio.simulate_monte_carlo(settings).iloc[-1].median()
    )
