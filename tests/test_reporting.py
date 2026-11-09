"""Tests for the reporting and plotting helpers."""

from typing import TYPE_CHECKING

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from quantfolio.currency import ExchangeRates
from quantfolio.models import PriceSeries
from quantfolio.portfolio import Portfolio
from quantfolio.reporting import plot_portfolio_report, plot_simulation_paths
from quantfolio.risk import max_drawdown
from quantfolio.simulation import MonteCarloParameters
from tests.helpers import make_series

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(autouse=True)
def _close_figures() -> Iterator[None]:
    """Close every figure after each test to keep the suite headless."""
    yield
    plt.close("all")


def _build_portfolio() -> Portfolio:
    """Return a two-asset portfolio suitable for plotting."""
    return Portfolio(
        assets={
            "AAA": make_series("AAA", [10.0 + position for position in range(10)]),
            "BBB": make_series("BBB", [20.0 + position for position in range(10)]),
        },
        weights={"AAA": 0.5, "BBB": 0.5},
    )


def _build_reporting_currency_portfolio() -> Portfolio:
    """Return a USD series converted by manually supplied USD/EUR rates."""
    dates = pd.DatetimeIndex(["2025-01-02", "2025-01-03", "2025-01-06"])
    asset = PriceSeries(
        ticker="US_ASSET",
        prices=pd.Series([100.0, 110.0, 105.0], index=dates),
        source="Manual asset input",
        quote_currency="USD",
    )
    rate = PriceSeries(
        ticker="FX:USD/EUR",
        prices=pd.Series([0.9, 0.95], index=dates[:2]),
        source="Manual FX input",
        quote_currency="EUR",
    )
    return Portfolio(
        assets={asset.ticker: asset},
        weights={asset.ticker: 1.0},
        reporting_currency="EUR",
        exchange_rates=ExchangeRates([rate]),
    )


def _build_golden_conversion_portfolio() -> Portfolio:
    """Return the four-date currency-conversion consumer fixture."""
    dates = pd.DatetimeIndex(["2025-01-02", "2025-01-03", "2025-01-06", "2025-01-07"])
    usd_asset = PriceSeries(
        ticker="US_ASSET",
        prices=pd.Series([100.0, 110.0, 100.0, 120.0], index=dates),
        quote_currency="USD",
    )
    eur_asset = PriceSeries(
        ticker="EU_ASSET",
        prices=pd.Series([100.0, 101.0, 99.0, 104.0], index=dates),
        quote_currency="EUR",
    )
    usd_eur = PriceSeries(
        ticker="FX:USD/EUR",
        prices=pd.Series([0.90, 0.95, 0.92, 0.91], index=dates),
        source="Manual FX input",
        quote_currency="EUR",
    )
    return Portfolio(
        assets={usd_asset.ticker: usd_asset, eur_asset.ticker: eur_asset},
        weights={usd_asset.ticker: 0.5, eur_asset.ticker: 0.5},
        reporting_currency="EUR",
        exchange_rates=ExchangeRates([usd_eur]),
    )


def test_report_aligns_the_returns_twice(monkeypatch: pytest.MonkeyPatch) -> None:
    """The report computes the aligned returns once for the series and once inside summary."""
    calls: list[int] = []
    original = Portfolio.portfolio_returns

    def counting(self: Portfolio) -> pd.Series[float]:
        calls.append(1)
        return original(self)

    monkeypatch.setattr(Portfolio, "portfolio_returns", counting)

    _build_portfolio().report()

    assert len(calls) == 2


def test_report_does_not_recompute_the_drawdown_through_the_portfolio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The drawdown is computed once from the aligned returns, not through the portfolio."""

    def forbidden(_self: Portfolio) -> float:
        msg = "the report must reuse the aligned returns"
        raise AssertionError(msg)

    monkeypatch.setattr(Portfolio, "max_drawdown", forbidden)

    _build_portfolio().report()


def test_report_computes_the_drawdown_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """The report derives the drawdown once from the aligned returns."""
    calls: list[int] = []

    def counting(returns: pd.Series[float]) -> float:
        calls.append(1)
        return max_drawdown(returns)

    monkeypatch.setattr("quantfolio.reporting.max_drawdown_of_returns", counting)

    _build_portfolio().report()

    assert len(calls) == 1


@pytest.mark.parametrize(
    ("periods_per_year", "label"),
    [
        (252, "diario"),
        (365, "diario"),
        (52, "semanal"),
        (12, "mensual"),
        (4, "trimestral"),
        (1, "anual"),
        (6, "por periodo"),
    ],
)
def test_report_labels_the_var_period(periods_per_year: int, label: str) -> None:
    """The VaR row names the return period instead of hardcoding 'diario'."""
    report = _build_portfolio().report(periods_per_year=periods_per_year, confidence=0.9)

    assert f"VaR histórico {label} (90%)" in report
    assert f"CVaR histórico {label} (90%)" in report


def test_plot_portfolio_report_runs_headless(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The analytical dashboard renders without a display."""
    monkeypatch.setattr(plt, "show", lambda: None)

    plot_portfolio_report(_build_portfolio())

    assert plt.get_fignums()


def test_plot_portfolio_report_rebases_prices_to_100(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every asset starts at the common base on the price panel."""
    monkeypatch.setattr(plt, "show", lambda: None)

    plot_portfolio_report(_build_portfolio())

    price_axis = plt.gcf().axes[0]
    first_values = [float(np.asarray(line.get_ydata())[0]) for line in price_axis.lines]
    assert first_values == pytest.approx([100.0, 100.0])
    assert price_axis.get_title() == "Evolución de precios (base 100)"
    assert price_axis.get_ylabel() == "Precio relativo (base 100)"


def test_plot_portfolio_report_rebases_staggered_prices(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A shorter series still starts at 100 on the common dates."""
    monkeypatch.setattr(plt, "show", lambda: None)
    portfolio = Portfolio(
        assets={
            "AAA": make_series("AAA", [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0]),
            "BBB": make_series("BBB", [20.0, 21.0, 22.0, 23.0], start=3),
        },
        weights={"AAA": 0.5, "BBB": 0.5},
    )

    plot_portfolio_report(portfolio)

    price_axis = plt.gcf().axes[0]
    lines = price_axis.lines
    assert len(lines) == 2
    for line in lines:
        values = np.asarray(line.get_ydata())
        assert not np.isnan(values).any()
        assert float(values[0]) == pytest.approx(100.0)
    assert float(np.asarray(lines[0].get_xdata())[0]) == pytest.approx(
        float(np.asarray(lines[1].get_xdata())[0])
    )


def test_plot_portfolio_report_uses_reporting_currency_prices(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The price panel reflects both local price changes and FX movements."""
    monkeypatch.setattr(plt, "show", lambda: None)

    plot_portfolio_report(_build_reporting_currency_portfolio())

    price_axis = plt.gcf().axes[0]
    values = np.asarray(price_axis.lines[0].get_ydata())
    assert values == pytest.approx([100.0, 104.5 / 90.0 * 100.0, 99.75 / 90.0 * 100.0])


def test_converted_series_drives_all_consumers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Converted prices feed returns, report metrics, simulation and every plot panel."""
    monkeypatch.setattr(plt, "show", lambda: None)
    portfolio = _build_golden_conversion_portfolio()
    expected_asset_returns = np.array(
        [
            [104.5 / 90.0 - 1.0, 101.0 / 100.0 - 1.0],
            [92.0 / 104.5 - 1.0, 99.0 / 101.0 - 1.0],
            [109.2 / 92.0 - 1.0, 104.0 / 99.0 - 1.0],
        ]
    )
    expected_returns = expected_asset_returns.mean(axis=1)
    actual_returns = portfolio.get_returns()

    assert actual_returns.iloc[0, 0] == pytest.approx(0.1611111111111111)
    np.testing.assert_allclose(actual_returns.to_numpy(), expected_asset_returns)
    np.testing.assert_allclose(portfolio.portfolio_returns().to_numpy(), expected_returns)

    expected_sharpe = expected_returns.mean() * 252 / (expected_returns.std(ddof=1) * np.sqrt(252))
    threshold = np.quantile(expected_returns, 0.05)
    expected_var = -threshold
    expected_cvar = -expected_returns[expected_returns <= threshold].mean()
    log_drift = float(np.log1p(expected_returns).mean() * 252)
    report = portfolio.report()

    assert f"| Rentabilidad media diaria | {expected_returns.mean():.4%} |" in report
    assert f"| Ratio de Sharpe (rf=0.00%) | {expected_sharpe:.2f} |" in report
    assert f"| VaR histórico diario (95%) | {expected_var:.2%} |" in report
    assert f"| CVaR histórico diario (95%) | {expected_cvar:.2%} |" in report
    assert f"| Deriva del logaritmo usada por Monte Carlo | {log_drift:.2%} |" in report
    assert "| Primera observación | Última observación | Observaciones | Arrastres |" in report
    assert "| US_ASSET | FX:USD/EUR | Manual FX input | 2025-01-02 | 2025-01-07 | 4 | 0 |" in report
    assert "2025-01-02, 2025-01-03" not in report

    simulation = portfolio.simulate_monte_carlo(
        MonteCarloParameters(
            n_paths=1,
            horizon=252,
            initial_value=100.0,
            volatility_assumption=0.0,
            seed=42,
        )
    )
    assert simulation.iloc[-1, 0] == pytest.approx(100.0 * np.exp(log_drift))

    portfolio.plots_report()
    axes = {axis.get_title(): axis for axis in plt.gcf().axes}
    prices_axis = axes["Evolución de precios en EUR (base 100)"]
    price_lines = {line.get_label(): line for line in prices_axis.lines}
    np.testing.assert_allclose(
        np.asarray(price_lines["US_ASSET"].get_ydata(), dtype=float),
        np.array([100.0, 104.5 / 90.0 * 100.0, 92.0 / 90.0 * 100.0, 109.2 / 90.0 * 100.0]),
    )
    np.testing.assert_allclose(
        np.asarray(price_lines["EU_ASSET"].get_ydata(), dtype=float),
        np.array([100.0, 101.0, 99.0, 104.0]),
    )

    cumulative_axis = axes["Rentabilidad acumulada por activo"]
    cumulative_lines = {line.get_label(): line for line in cumulative_axis.lines}
    np.testing.assert_allclose(
        np.asarray(cumulative_lines["US_ASSET"].get_ydata(), dtype=float),
        np.array([104.5, 92.0, 109.2]) / 90.0 - 1.0,
    )
    np.testing.assert_allclose(
        np.asarray(cumulative_lines["EU_ASSET"].get_ydata(), dtype=float),
        np.array([101.0, 99.0, 104.0]) / 100.0 - 1.0,
    )

    correlation_axis = axes["Correlación entre activos"]
    np.testing.assert_allclose(
        np.asarray(correlation_axis.images[0].get_array()),
        np.corrcoef(expected_asset_returns.T),
    )
    value_axis = axes["Evolución del valor de la cartera (base 100)"]
    np.testing.assert_allclose(
        np.asarray(value_axis.lines[0].get_ydata(), dtype=float),
        100.0 * np.cumprod(1.0 + expected_returns),
    )
    plt.close("all")


def test_report_summarizes_manual_and_ecb_sources() -> None:
    """Large rate traces are summarized by source without enumerating every date."""
    dates = pd.date_range("2024-01-01", periods=600, freq="D")
    rate_dates = dates[::2]
    assets = {
        "US_ASSET": PriceSeries(
            ticker="US_ASSET",
            prices=pd.Series(100.0 + np.arange(len(dates)) / 100.0, index=dates),
            quote_currency="USD",
        ),
        "GB_ASSET": PriceSeries(
            ticker="GB_ASSET",
            prices=pd.Series(50.0 + np.arange(len(dates)) / 200.0, index=dates),
            quote_currency="GBP",
        ),
        "EU_ASSET": PriceSeries(
            ticker="EU_ASSET",
            prices=pd.Series(10.0 + np.arange(len(dates)) / 10.0, index=dates),
            quote_currency="EUR",
        ),
    }
    manual_rate = PriceSeries(
        ticker="FX:USD/EUR",
        prices=pd.Series(0.9, index=rate_dates),
        source="Manual rates",
        quote_currency="EUR",
    )
    ecb_rate = PriceSeries(
        ticker="FX:GBP/EUR",
        prices=pd.Series(1.2, index=rate_dates),
        source="ECB reference rates",
        quote_currency="EUR",
    )
    portfolio = Portfolio(
        assets=assets,
        weights=dict.fromkeys(assets, 1.0),
        reporting_currency="EUR",
        exchange_rates=ExchangeRates([manual_rate, ecb_rate]),
    )

    report = portfolio.report()
    manual_row = next(line for line in report.splitlines() if "Manual rates" in line)
    ecb_row = next(line for line in report.splitlines() if "ECB reference rates" in line)
    identity_row = next(
        line for line in report.splitlines() if line.startswith("| EU_ASSET | - | No requerida |")
    )

    assert "| Primera observación | Última observación | Observaciones | Arrastres |" in report
    assert f"| {rate_dates[0]:%Y-%m-%d} | {rate_dates[-1]:%Y-%m-%d} | 300 | 300 |" in manual_row
    assert f"| {rate_dates[0]:%Y-%m-%d} | {rate_dates[-1]:%Y-%m-%d} | 300 | 300 |" in ecb_row
    assert "ECB" not in manual_row
    assert f"| {dates[0]:%Y-%m-%d} | {dates[-1]:%Y-%m-%d} | 600 | 0 |" in identity_row


def test_legacy_report_discloses_unassessed_currency_conversion() -> None:
    """Currency-free portfolios state that conversion was not assessed."""
    report = _build_portfolio().report()

    assert "La conversión de divisas no se ha evaluado" in report
    assert "desconocida" in report


def test_report_preserves_the_original_quote_unit() -> None:
    """A normalized minor unit remains visible beside its canonical currency."""
    asset = PriceSeries(
        ticker="VOD.L",
        prices=pd.Series([120.0, 125.0], index=pd.DatetimeIndex(["2025-01-02", "2025-01-03"])),
        quote_unit="GBX",
    )
    portfolio = Portfolio(assets={asset.ticker: asset}, weights={asset.ticker: 1.0})

    assert "| VOD.L | GBP (GBX) | 100.00% |" in portfolio.report()


def test_legacy_currency_diagnostics_are_empty_with_stable_columns() -> None:
    """Legacy portfolios expose an empty trace instead of implying FX use."""
    diagnostics = _build_portfolio().currency_conversion_diagnostics()

    assert diagnostics.empty
    assert list(diagnostics.columns) == [
        "asset",
        "asset_date",
        "source_currency",
        "reporting_currency",
        "pair",
        "source",
        "rate_date",
        "age_days",
        "rate",
        "applied_rate",
        "inverted",
        "carried_forward",
        "from_currency",
        "to_currency",
        "leg_index",
    ]


def test_currency_report_includes_rate_trace_and_daily_cutoff_limit() -> None:
    """Currency-aware reports identify rate provenance, dates and carried values."""
    report = _build_reporting_currency_portfolio().report()

    assert "Divisa de reporte: EUR" in report
    assert "FX:USD/EUR" in report
    assert "Manual FX input" in report
    assert "| Primera observación | Última observación | Observaciones | Arrastres |" in report
    assert (
        "| US_ASSET | FX:USD/EUR | Manual FX input | 2025-01-02 | 2025-01-03 | 2 | 1 |"
    ) in report
    assert "corte intradía" in report


def test_currency_conversion_diagnostics_list_each_rate_use() -> None:
    """Diagnostics retain asset dates, provider dates and carry-forward age."""
    diagnostics = _build_reporting_currency_portfolio().currency_conversion_diagnostics()

    assert list(diagnostics["pair"].unique()) == ["FX:USD/EUR"]
    assert list(diagnostics["rate_date"].unique()) == list(
        pd.DatetimeIndex(["2025-01-02", "2025-01-03"])
    )
    assert diagnostics["carried_forward"].tolist() == [False, False, True]
    assert diagnostics["age_days"].tolist() == [0, 0, 3]


def test_plot_simulation_paths_runs_headless(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Simulation charts render without a display."""
    monkeypatch.setattr(plt, "show", lambda: None)
    simulations = pd.DataFrame(np.linspace(100.0, 120.0, 30).reshape(6, 5))

    plot_simulation_paths(simulations, max_paths=3)

    assert plt.get_fignums()


def test_plot_simulation_paths_defaults_to_the_portfolio_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The default trajectory label names a portfolio value."""
    monkeypatch.setattr(plt, "show", lambda: None)
    simulations = pd.DataFrame(np.linspace(100.0, 120.0, 30).reshape(6, 5))

    plot_simulation_paths(simulations, max_paths=1)

    assert plt.gcf().axes[0].get_ylabel() == "Valor de la cartera"
    distribution_axis = plt.gcf().axes[1]
    assert distribution_axis.get_title() == "Distribución del valor final"
    assert distribution_axis.get_xlabel() == "Valor final"


def test_plot_simulation_paths_rejects_empty_frames() -> None:
    """An empty simulation matrix cannot be plotted."""
    empty = pd.DataFrame()

    with pytest.raises(ValueError, match="simulaciones"):
        plot_simulation_paths(empty)


def test_plot_simulation_paths_rejects_non_positive_max_paths() -> None:
    """The number of drawn trajectories must be positive."""
    simulations = pd.DataFrame(np.ones((3, 2)))

    with pytest.raises(ValueError, match="max_paths"):
        plot_simulation_paths(simulations, max_paths=0)


def test_portfolio_and_series_plot_delegates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The public plot methods delegate to the reporting helpers."""
    monkeypatch.setattr(plt, "show", lambda: None)
    portfolio = _build_portfolio()
    simulations = portfolio.simulate_monte_carlo(
        MonteCarloParameters(n_paths=4, horizon=5, seed=42)
    )

    portfolio.plots_report()
    portfolio.plot_simulation(simulations, max_paths=2)
    portfolio.assets["AAA"].plot_simulation(simulations, max_paths=2)

    assert len(plt.get_fignums()) == 3


def test_series_simulation_uses_the_price_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A single-asset simulation is labelled as a price, not a portfolio."""
    monkeypatch.setattr(plt, "show", lambda: None)
    asset = make_series("AAA", [10.0, 11.0, 12.0, 13.0])
    simulations = asset.simulate_monte_carlo(MonteCarloParameters(n_paths=2, horizon=5, seed=1))

    asset.plot_simulation(simulations, max_paths=1)

    assert plt.gcf().axes[0].get_ylabel() == "Precio"


def test_series_simulation_labels_the_distribution_as_final_price(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A single-asset distribution panel speaks of prices, not portfolio values."""
    monkeypatch.setattr(plt, "show", lambda: None)
    asset = make_series("AAA", [10.0, 11.0, 12.0, 13.0])
    simulations = asset.simulate_monte_carlo(MonteCarloParameters(n_paths=2, horizon=5, seed=1))

    asset.plot_simulation(simulations, max_paths=1)

    distribution_axis = plt.gcf().axes[1]
    assert distribution_axis.get_title() == "Distribución del precio final"
    assert distribution_axis.get_xlabel() == "Precio final"
