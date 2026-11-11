"""Portfolio composition, calendar alignment, analytics and simulation behavior."""

from __future__ import annotations

import math

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from quantfolio.currency import ExchangeRates
from quantfolio.models import PriceSeries
from quantfolio.portfolio import Portfolio
from quantfolio.risk import historical_cvar, historical_var, max_drawdown, sharpe_ratio
from quantfolio.simulation import MonteCarloParameters
from tests.support.builders import make_series


def _overlapping_portfolio() -> Portfolio:
    return Portfolio(
        assets={
            "AAA": make_series("AAA", [10.0, 11.0, 12.0, 13.0, 14.0]),
            "BBB": make_series("BBB", [20.0, 19.0, 21.0, 22.0, 23.0]),
        },
        weights={"AAA": 0.5, "BBB": 0.5},
    )


def _mixed_calendar_portfolio() -> Portfolio:
    return Portfolio(
        assets={
            "AAA": make_series("AAA", [10.0, 11.0, 12.0, 13.0, 14.0]),
            "BBB": make_series("BBB", [20.0, 19.0, 21.0], start=2),
        },
        weights={"AAA": 0.5, "BBB": 0.5},
    )


def test_portfolio_normalizes_weights_and_validates_the_composition() -> None:
    """Valid weights sum to one; missing, negative, non-finite and zero totals fail."""
    portfolio = Portfolio(
        assets={
            "AAA": make_series("AAA", [10.0, 11.0]),
            "BBB": make_series("BBB", [20.0, 19.0]),
        },
        weights={"AAA": 2.0, "BBB": 2.0},
    )
    assert portfolio.weights == {"AAA": 0.5, "BBB": 0.5}

    asset = make_series("AAA", [10.0, 11.0])
    failures: tuple[tuple[dict[str, PriceSeries], dict[str, float], str], ...] = (
        ({}, {}, "al menos un activo"),
        ({"AAA": asset}, {"BBB": 1.0}, "ponderación para cada activo"),
        ({"AAA": asset}, {"AAA": -1.0}, "negativas"),
        ({"AAA": asset}, {"AAA": float("nan")}, "finitos"),
        ({"AAA": asset}, {"AAA": 0.0}, "positiva"),
    )
    for assets, weights, message in failures:
        with pytest.raises(ValueError, match=message):
            Portfolio(assets=assets, weights=weights)


def test_asset_key_must_match_the_series_ticker() -> None:
    """A mapping key cannot relabel an asset inside the portfolio."""
    asset = make_series("BBB", [10.0, 11.0])
    with pytest.raises(ValueError, match="no coincide con el ticker"):
        Portfolio(assets={"AAA": asset}, weights={"AAA": 1.0})


def test_raw_prices_keep_the_union_while_returns_use_shared_dates() -> None:
    """Missing observations stay visible locally but never enter aligned returns."""
    portfolio = _mixed_calendar_portfolio()
    prices = portfolio.get_prices()
    returns = portfolio.get_returns()

    assert len(prices) == 5
    assert int(prices["BBB"].isna().sum()) == 2
    assert len(returns) == 2
    assert not returns.isna().to_numpy().any()


def test_alignment_summary_quantifies_coverage_and_discarded_dates() -> None:
    """The public summary exposes union size, shared dates, coverage and gaps."""
    summary = _mixed_calendar_portfolio().alignment_summary()

    assert summary["union_dates"] == 5
    assert summary["common_dates"] == 3
    assert summary["coverage"] == pytest.approx(0.6)


def test_disjoint_calendars_fail_returns_but_report_zero_alignment_coverage() -> None:
    """Alignment diagnostics degrade gracefully while return analysis rejects no overlap."""
    first = make_series("AAA", [10.0, 11.0])
    second = make_series("BBB", [20.0, 21.0], dates=["2026-01-02", "2026-01-05"])
    portfolio = Portfolio(
        assets={"AAA": first, "BBB": second},
        weights={"AAA": 0.5, "BBB": 0.5},
    )

    with pytest.raises(ValueError, match="no comparten"):
        portfolio.get_returns()
    summary = portfolio.alignment_summary()
    assert summary["coverage"] == 0.0
    assert summary["multi_day_returns"] == 0
    assert summary["multi_day_share"] == 0.0
    assert summary["max_gap_days"] == 0


def test_portfolio_returns_are_the_weighted_mean_of_aligned_asset_returns() -> None:
    """Equal weights make each portfolio return the cross-sectional mean."""
    portfolio = _overlapping_portfolio()
    pd.testing.assert_series_equal(
        portfolio.portfolio_returns(),
        portfolio.get_returns().mean(axis=1),
        check_names=False,
    )


def test_summary_matches_manual_annualization_and_custom_periods() -> None:
    """Summary statistics expose the documented arithmetic annualization."""
    portfolio = _overlapping_portfolio()
    returns = portfolio.portfolio_returns()
    summary = portfolio.summary()

    assert summary["mean_daily_return"] == pytest.approx(float(returns.mean()))
    assert summary["daily_volatility"] == pytest.approx(float(returns.std(ddof=1)))
    assert summary["annualized_return_approx"] == pytest.approx(float(returns.mean()) * 252)
    assert summary["annualized_volatility"] == pytest.approx(
        float(returns.std(ddof=1)) * math.sqrt(252)
    )
    assert portfolio.summary(periods_per_year=12)["annualized_return_approx"] == pytest.approx(
        float(returns.mean()) * 12
    )


@pytest.mark.parametrize("periods_per_year", [0, -1])
def test_summary_rejects_non_positive_annualization(periods_per_year: int) -> None:
    """The annualization factor is shared with PriceSeries validation."""
    portfolio = _overlapping_portfolio()
    with pytest.raises(ValueError, match="periods_per_year"):
        portfolio.summary(periods_per_year=periods_per_year)


def test_summary_and_simulation_require_at_least_two_returns() -> None:
    """One aligned return is insufficient for portfolio dispersion or simulation."""
    portfolio = Portfolio(
        assets={
            "AAA": make_series("AAA", [10.0, 11.0]),
            "BBB": make_series("BBB", [20.0, 19.0]),
        },
        weights={"AAA": 0.5, "BBB": 0.5},
    )
    with pytest.raises(ValueError, match="dos observaciones"):
        portfolio.summary()
    with pytest.raises(ValueError, match="dos observaciones"):
        portfolio.simulate_monte_carlo()


def test_portfolio_risk_methods_match_the_shared_risk_formulas() -> None:
    """Drawdown, Sharpe, VaR and CVaR use the same portfolio-return sample."""
    portfolio = _overlapping_portfolio()
    returns = portfolio.portfolio_returns()

    assert portfolio.max_drawdown() == pytest.approx(max_drawdown(returns))
    assert portfolio.sharpe_ratio() == pytest.approx(sharpe_ratio(returns))
    assert portfolio.value_at_risk(confidence=0.95) == pytest.approx(
        historical_var(returns, confidence=0.95)
    )
    assert portfolio.conditional_value_at_risk(confidence=0.95) == pytest.approx(
        historical_cvar(returns, confidence=0.95)
    )


@pytest.mark.parametrize("risk_free_rate", [float("nan"), float("inf"), float("-inf")])
def test_portfolio_sharpe_rejects_non_finite_risk_free_rates(risk_free_rate: float) -> None:
    """The portfolio entry point inherits finite-rate validation."""
    portfolio = _overlapping_portfolio()
    with pytest.raises(ValueError, match="finito"):
        portfolio.sharpe_ratio(risk_free_rate=risk_free_rate)


def test_portfolio_simulation_defaults_to_the_documented_value_and_shape() -> None:
    """A simulation has horizon plus one rows and starts at the default portfolio value."""
    simulations = _overlapping_portfolio().simulate_monte_carlo(
        MonteCarloParameters(n_paths=5, horizon=10, seed=42)
    )

    assert simulations.shape == (11, 5)
    assert (simulations.iloc[0] == 10_000.0).all()


def test_portfolio_simulation_uses_calendar_drift_and_explicit_assumptions() -> None:
    """The configured periods-per-year and zero-volatility assumptions drive terminal values."""
    prices = [100.0, 101.0, 102.01, 103.0301]
    portfolio = Portfolio(
        assets={
            "AAA": make_series("AAA", prices),
            "BBB": make_series("BBB", prices),
        },
        weights={"AAA": 0.5, "BBB": 0.5},
    )
    annual = portfolio.simulate_monte_carlo(
        MonteCarloParameters(n_paths=1, horizon=365, periods_per_year=365, seed=1)
    )
    assumed = portfolio.simulate_monte_carlo(
        MonteCarloParameters(
            n_paths=2,
            horizon=252,
            initial_value=100.0,
            return_assumption=0.1,
            volatility_assumption=0.0,
            seed=1,
        )
    )

    assert annual.iloc[-1, 0] == pytest.approx(10_000.0 * np.exp(float(np.log1p(0.01)) * 365))
    assert assumed.iloc[-1].tolist() == pytest.approx([100.0 * np.exp(0.1)] * 2)


def test_portfolio_simulation_is_reproducible_for_the_same_seed() -> None:
    """Identical public parameters produce byte-for-byte identical frames."""
    portfolio = _overlapping_portfolio()
    parameters = MonteCarloParameters(n_paths=3, horizon=5, seed=11)
    pd.testing.assert_frame_equal(
        portfolio.simulate_monte_carlo(parameters),
        portfolio.simulate_monte_carlo(parameters),
    )


def test_return_gaps_and_multi_day_alignment_statistics() -> None:
    """Weekend intervals contribute calendar-day gaps and their share of the sample."""
    prices = make_series(
        "AAA",
        [10.0, 11.0, 12.0, 13.0],
        dates=["2025-01-02", "2025-01-03", "2025-01-06", "2025-01-07"],
    )
    portfolio = Portfolio(
        assets={"AAA": prices, "BBB": make_series("BBB", list(prices.prices * 2.0))},
        weights={"AAA": 0.5, "BBB": 0.5},
    )

    assert list(portfolio.return_gaps()) == [3, 1]
    summary = portfolio.alignment_summary()
    assert summary["multi_day_returns"] == 1
    assert summary["multi_day_share"] == pytest.approx(0.5)
    assert summary["max_gap_days"] == 3


def test_report_renders_composition_risk_and_optional_sections() -> None:
    """Portfolio.report delegates content to the public Markdown renderer."""
    portfolio = _mixed_calendar_portfolio()
    report = portfolio.report()
    compact = portfolio.report(include_quality=False, include_warnings=False)

    assert report.startswith("# Informe de la cartera")
    assert "## 1. Composición" in report
    assert "## 2. Métricas históricas" in report
    assert "## 3. Calidad de los datos" in report
    assert "## 4. Advertencias de riesgo" in report
    assert "descarta el 40.0%" in report
    assert "Calidad de los datos" not in compact
    assert "Advertencias de riesgo" not in compact


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"periods_per_year": 0}, "periods_per_year"),
        ({"confidence": 1.5}, "confidence"),
        ({"risk_free_rate": float("nan")}, "finito"),
    ],
)
def test_report_rejects_invalid_analysis_parameters(
    kwargs: dict[str, object], message: str
) -> None:
    """Invalid report settings fail before rendering misleading metrics."""
    portfolio = _overlapping_portfolio()
    with pytest.raises(ValueError, match=message):
        portfolio.report(**kwargs)  # type: ignore[arg-type]


def test_report_degrades_gracefully_with_one_return() -> None:
    """A short sample still receives a structural report and a quality warning."""
    portfolio = Portfolio(
        assets={
            "AAA": make_series("AAA", [10.0, 11.0]),
            "BBB": make_series("BBB", [20.0, 19.0]),
        },
        weights={"AAA": 0.5, "BBB": 0.5},
    )
    report = portfolio.report()

    assert "No hay suficientes observaciones" in report
    assert "solo hay 1 observación de rentabilidad" in report


def test_plotting_entry_points_render_without_leaving_ui_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The public plot methods create figures without an interactive backend."""
    monkeypatch.setattr(plt, "show", lambda: None)
    portfolio = _overlapping_portfolio()
    simulations = portfolio.simulate_monte_carlo(MonteCarloParameters(n_paths=2, horizon=3, seed=1))
    portfolio.plot_simulation(simulations, max_paths=1)
    portfolio.plots_report()
    assert plt.get_fignums()
    plt.close("all")


def test_cross_currency_diagnostics_are_ordered_and_traceable() -> None:
    """EUR-pivot diagnostics retain leg order and trace metadata for every converted date."""
    dates = pd.DatetimeIndex(["2025-01-02", "2025-01-03"])
    usd = PriceSeries(
        "US",
        pd.Series([100.0, 100.0], index=dates),
        quote_currency="USD",
    )
    gbp = PriceSeries(
        "GB",
        pd.Series([10.0, 11.0], index=dates),
        quote_currency="GBP",
    )
    rates = ExchangeRates(
        [
            make_series(
                "FX:EUR/USD",
                [1.25, 1.25],
                dates=dates,
                source="ECB",
                quote_currency="USD",
            ),
            make_series(
                "FX:EUR/GBP",
                [0.8, 0.8],
                dates=dates,
                source="ECB",
                quote_currency="GBP",
            ),
        ]
    )
    portfolio = Portfolio(
        assets={"US": usd, "GB": gbp},
        weights={"US": 0.5, "GB": 0.5},
        reporting_currency="GBP",
        exchange_rates=rates,
    )

    diagnostics = portfolio.currency_conversion_diagnostics()
    usd_rows = diagnostics[diagnostics["asset"] == "US"]
    gbp_rows = diagnostics[diagnostics["asset"] == "GB"]
    assert portfolio.get_reporting_prices()["US"].tolist() == pytest.approx([64.0, 64.0])
    assert usd_rows["leg_index"].tolist() == [1, 2, 1, 2]
    assert usd_rows["from_currency"].tolist() == ["USD", "EUR", "USD", "EUR"]
    assert usd_rows["to_currency"].tolist() == ["EUR", "GBP", "EUR", "GBP"]
    assert gbp_rows["leg_index"].tolist() == [0, 0]
    assert gbp_rows["source"].tolist() == ["No requerida", "No requerida"]
