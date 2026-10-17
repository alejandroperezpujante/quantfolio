"""Tests for the portfolio model."""

import numpy as np
import pandas as pd
import pytest

from quantfolio.models import PriceSeries
from quantfolio.portfolio import Portfolio
from quantfolio.simulation import MonteCarloParameters
from tests.helpers import make_series


def build_portfolio() -> Portfolio:
    """Return a fully overlapping two-asset portfolio."""
    return Portfolio(
        assets={
            "AAA": make_series("AAA", [10.0, 11.0, 12.0, 13.0, 14.0]),
            "BBB": make_series("BBB", [20.0, 19.0, 21.0, 22.0, 23.0]),
        },
        weights={"AAA": 0.5, "BBB": 0.5},
    )


def build_mixed_calendar_portfolio() -> Portfolio:
    """Return a portfolio whose second asset starts later in the calendar."""
    return Portfolio(
        assets={
            "AAA": make_series("AAA", [10.0, 11.0, 12.0, 13.0, 14.0]),
            "BBB": make_series("BBB", [20.0, 19.0, 21.0], start=2),
        },
        weights={"AAA": 0.5, "BBB": 0.5},
    )


def test_portfolio_normalizes_weights() -> None:
    """Weights are normalized to sum to one."""
    portfolio = Portfolio(
        assets={
            "AAA": make_series("AAA", [10.0, 11.0]),
            "BBB": make_series("BBB", [20.0, 19.0]),
        },
        weights={"AAA": 2.0, "BBB": 2.0},
    )

    assert sum(portfolio.weights.values()) == pytest.approx(1.0)
    assert portfolio.weights["AAA"] == pytest.approx(0.5)


def test_portfolio_rejects_missing_weights() -> None:
    """Every asset needs a weight."""
    with pytest.raises(ValueError, match="ponderación para cada activo"):
        Portfolio(
            assets={"AAA": make_series("AAA", [10.0, 11.0])},
            weights={"BBB": 1.0},
        )


def test_portfolio_rejects_negative_weights() -> None:
    """Short positions are rejected."""
    with pytest.raises(ValueError, match="negativas"):
        Portfolio(
            assets={"AAA": make_series("AAA", [10.0, 11.0])},
            weights={"AAA": -1.0},
        )


def test_portfolio_rejects_non_finite_weights() -> None:
    """NaN weights are rejected before normalization."""
    with pytest.raises(ValueError, match="finitos"):
        Portfolio(
            assets={"AAA": make_series("AAA", [10.0, 11.0])},
            weights={"AAA": float("nan")},
        )


def test_portfolio_rejects_zero_total_weight() -> None:
    """Weights must sum to a positive amount."""
    with pytest.raises(ValueError, match="positiva"):
        Portfolio(
            assets={"AAA": make_series("AAA", [10.0, 11.0])},
            weights={"AAA": 0.0},
        )


def test_portfolio_rejects_empty_assets() -> None:
    """A portfolio needs at least one asset."""
    with pytest.raises(ValueError, match="al menos un activo"):
        Portfolio(assets={}, weights={})


def test_portfolio_rejects_key_without_matching_ticker() -> None:
    """Asset keys must match the ticker of the series."""
    with pytest.raises(ValueError, match="no coincide con el ticker"):
        Portfolio(
            assets={"AAA": make_series("BBB", [10.0, 11.0])},
            weights={"AAA": 1.0},
        )


def test_get_prices_keeps_the_date_union() -> None:
    """Raw prices keep the union of calendars and expose missing values."""
    prices = build_mixed_calendar_portfolio().get_prices()

    assert len(prices) == 5
    assert prices["BBB"].isna().sum() == 2


def test_get_returns_uses_common_dates() -> None:
    """Returns are computed only on dates shared by every asset."""
    returns = build_mixed_calendar_portfolio().get_returns()

    assert len(returns) == 2
    assert not returns.isna().to_numpy().any()


def test_alignment_summary_reports_coverage() -> None:
    """The alignment summary quantifies discarded dates."""
    summary = build_mixed_calendar_portfolio().alignment_summary()

    assert summary["union_dates"] == 5
    assert summary["common_dates"] == 3
    assert summary["coverage"] == pytest.approx(0.6)


def test_get_returns_rejects_disjoint_calendars() -> None:
    """Assets without a shared calendar cannot produce returns."""
    first = make_series("AAA", [10.0, 11.0, 12.0])
    second = PriceSeries(
        ticker="BBB",
        prices=pd.Series(
            [20.0, 21.0, 22.0],
            index=pd.bdate_range("2026-01-02", periods=3),
            dtype=float,
        ),
    )
    portfolio = Portfolio(
        assets={"AAA": first, "BBB": second},
        weights={"AAA": 0.5, "BBB": 0.5},
    )

    with pytest.raises(ValueError, match="no comparten"):
        portfolio.get_returns()


def test_portfolio_returns_are_weighted() -> None:
    """With equal weights the portfolio return is the cross-sectional mean."""
    portfolio = build_portfolio()
    returns = portfolio.get_returns()

    expected = returns.mean(axis=1)

    pd.testing.assert_series_equal(
        portfolio.portfolio_returns(),
        expected,
        check_names=False,
    )


def test_summary_matches_manual_annualization() -> None:
    """Summary statistics follow the documented annualization formulas."""
    portfolio = build_portfolio()
    returns = portfolio.portfolio_returns()

    summary = portfolio.summary()

    assert summary["mean_daily_return"] == pytest.approx(float(returns.mean()))
    assert summary["daily_volatility"] == pytest.approx(float(returns.std(ddof=1)))
    assert summary["annualized_return_approx"] == pytest.approx(float(returns.mean()) * 252)
    assert summary["annualized_volatility"] == pytest.approx(
        float(returns.std(ddof=1)) * np.sqrt(252)
    )


def test_summary_accepts_a_custom_annualization_factor() -> None:
    """The annualization factor is configurable."""
    portfolio = build_portfolio()
    mean_daily = float(portfolio.portfolio_returns().mean())

    summary = portfolio.summary(periods_per_year=12)

    assert summary["annualized_return_approx"] == pytest.approx(mean_daily * 12)


def test_summary_rejects_non_positive_annualization_factor() -> None:
    """The annualization factor must be positive."""
    with pytest.raises(ValueError, match="periods_per_year"):
        build_portfolio().summary(periods_per_year=0)


def test_summary_requires_two_return_observations() -> None:
    """A single return is not enough for dispersion statistics."""
    portfolio = Portfolio(
        assets={
            "AAA": make_series("AAA", [10.0, 11.0]),
            "BBB": make_series("BBB", [20.0, 19.0]),
        },
        weights={"AAA": 0.5, "BBB": 0.5},
    )

    with pytest.raises(ValueError, match="dos observaciones"):
        portfolio.summary()


def test_monte_carlo_simulation_has_expected_shape() -> None:
    """Simulations start at the default portfolio value."""
    simulations = build_portfolio().simulate_monte_carlo(
        MonteCarloParameters(n_paths=5, horizon=10, seed=42)
    )

    assert simulations.shape == (11, 5)
    assert (simulations.iloc[0] == 10_000.0).all()


def test_monte_carlo_simulation_respects_assumptions_and_initial_value() -> None:
    """Explicit return and volatility assumptions drive the paths."""
    simulations = build_portfolio().simulate_monte_carlo(
        MonteCarloParameters(
            n_paths=2,
            horizon=252,
            initial_value=100.0,
            return_assumption=0.1,
            volatility_assumption=0.0,
            seed=1,
        )
    )

    expected = 100.0 * np.exp(0.1)
    assert simulations.iloc[-1, 0] == pytest.approx(expected)
    assert simulations.iloc[-1, 1] == pytest.approx(expected)


def test_monte_carlo_simulation_is_reproducible() -> None:
    """The same seed produces identical simulations."""
    portfolio = build_portfolio()
    parameters = MonteCarloParameters(n_paths=3, horizon=5, seed=11)

    first = portfolio.simulate_monte_carlo(parameters)
    second = portfolio.simulate_monte_carlo(parameters)

    pd.testing.assert_frame_equal(first, second)


def test_monte_carlo_simulation_requires_two_return_observations() -> None:
    """A one-return portfolio cannot be simulated."""
    portfolio = Portfolio(
        assets={
            "AAA": make_series("AAA", [10.0, 11.0]),
            "BBB": make_series("BBB", [20.0, 19.0]),
        },
        weights={"AAA": 0.5, "BBB": 0.5},
    )

    with pytest.raises(ValueError, match="dos observaciones"):
        portfolio.simulate_monte_carlo()


def test_report_contains_composition_metrics_quality_and_warnings() -> None:
    """The Markdown report includes every default section."""
    report = build_mixed_calendar_portfolio().report()

    assert report.startswith("# Informe de la cartera")
    assert "## 1. Composición" in report
    assert "| AAA | 50.00% |" in report
    assert "## 2. Métricas históricas" in report
    assert "## 3. Calidad de los datos" in report
    assert "## 4. Advertencias de riesgo" in report
    assert "no garantizan resultados futuros" in report


def test_report_warns_about_discarded_dates() -> None:
    """Low alignment coverage produces an explicit warning."""
    report = build_mixed_calendar_portfolio().report()

    assert "descarta el 40.0%" in report


def test_report_warns_about_single_asset_concentration() -> None:
    """A one-asset portfolio is flagged as undiversified."""
    portfolio = Portfolio(
        assets={"AAA": make_series("AAA", [10.0, 11.0, 12.0, 13.0])},
        weights={"AAA": 1.0},
    )

    report = portfolio.report()

    assert "único activo" in report
    assert "muestra histórica es corta" in report


def test_report_omits_quality_and_warnings_when_disabled() -> None:
    """Report sections can be switched off."""
    report = build_portfolio().report(include_quality=False, include_warnings=False)

    assert "Calidad de los datos" not in report
    assert "Advertencias de riesgo" not in report
    assert "## 3." not in report


def test_report_does_not_warn_about_history_with_long_samples() -> None:
    """A long sample does not trigger the short-history warning."""
    portfolio = Portfolio(
        assets={
            "AAA": make_series("AAA", [10.0 + position for position in range(40)]),
            "BBB": make_series("BBB", [20.0 + position for position in range(40)]),
        },
        weights={"AAA": 0.5, "BBB": 0.5},
    )

    report = portfolio.report()

    assert "muestra histórica es corta" not in report
