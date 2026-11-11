"""Deterministic mechanics of the Monte Carlo engine."""

import numpy as np
import pandas as pd
import pytest

from quantfolio.simulation import (
    MonteCarloParameters,
    annualized_log_assumptions,
    paths_to_frame,
    simulate_gbm_paths,
)


def test_parameter_defaults_describe_one_trading_year() -> None:
    """The default simulation uses one year and one thousand paths."""
    parameters = MonteCarloParameters()

    assert parameters.n_paths == 1_000
    assert parameters.horizon == 252
    assert parameters.periods_per_year == 252
    assert parameters.initial_value is None
    assert parameters.return_assumption is None
    assert parameters.volatility_assumption is None
    assert parameters.seed is None


def test_paths_have_an_initial_row_are_positive_and_reproducible() -> None:
    """A seed controls identical paths while a different seed changes the sample."""
    parameters = MonteCarloParameters(n_paths=7, horizon=5, seed=42)
    arguments = {"initial_value": 100.0, "annual_return": 0.1, "annual_volatility": 0.2}

    paths = simulate_gbm_paths(parameters=parameters, **arguments)
    same = simulate_gbm_paths(parameters=parameters, **arguments)
    other = simulate_gbm_paths(
        parameters=MonteCarloParameters(n_paths=7, horizon=5, seed=43),
        **arguments,
    )

    assert paths.shape == (6, 7)
    np.testing.assert_allclose(paths[0], 100.0)
    assert np.all(paths > 0)
    np.testing.assert_array_equal(paths, same)
    assert not np.array_equal(paths, other)


def test_zero_volatility_compounds_exactly_on_any_annual_calendar() -> None:
    """The configured periods-per-year controls both drift and time step."""
    for periods_per_year in (252, 365):
        parameters = MonteCarloParameters(
            n_paths=2,
            horizon=periods_per_year,
            periods_per_year=periods_per_year,
            seed=1,
        )
        paths = simulate_gbm_paths(
            initial_value=100.0,
            annual_return=0.05,
            annual_volatility=0.0,
            parameters=parameters,
        )
        expected = 100.0 * np.exp(0.05 * np.arange(periods_per_year + 1) / periods_per_year)
        np.testing.assert_allclose(paths[:, 0], expected, rtol=1e-12)
        np.testing.assert_allclose(paths[:, 1], expected, rtol=1e-12)


def test_simulated_log_growth_reproduces_the_estimated_drift() -> None:
    """The seeded sample mean log path tracks the annualized historical drift."""
    rng = np.random.default_rng(3)
    log_returns = rng.normal(0.0004, 0.012, 1_000)
    annual_return, annual_volatility = annualized_log_assumptions(pd.Series(np.expm1(log_returns)))

    paths = simulate_gbm_paths(
        initial_value=100.0,
        annual_return=annual_return,
        annual_volatility=annual_volatility,
        parameters=MonteCarloParameters(n_paths=10_000, horizon=252, seed=5),
    )

    mean_log_growth = float(np.log(paths[-1] / paths[0]).mean())
    assert mean_log_growth == pytest.approx(annual_return, abs=0.005)


def test_invalid_simulation_parameters_are_rejected() -> None:
    """Each out-of-range dimension raises a Spanish error that names the parameter."""
    cases = (
        (0.0, 0.1, MonteCarloParameters(), "valor inicial"),
        (100.0, -0.1, MonteCarloParameters(), "volatilidad"),
        (100.0, 0.1, MonteCarloParameters(horizon=0), "horizonte"),
        (100.0, 0.1, MonteCarloParameters(n_paths=0), "trayectorias"),
        (100.0, 0.1, MonteCarloParameters(periods_per_year=0), "periods_per_year"),
    )
    for initial_value, volatility, parameters, message in cases:
        with pytest.raises(ValueError, match=message):
            simulate_gbm_paths(
                initial_value=initial_value,
                annual_return=0.1,
                annual_volatility=volatility,
                parameters=parameters,
            )


def test_log_assumptions_annualize_constant_returns() -> None:
    """Constant returns have the log drift scaled by the chosen calendar."""
    for periods_per_year in (252, 365):
        annual_return, annual_volatility = annualized_log_assumptions(
            pd.Series([0.01] * 10, dtype=float),
            periods_per_year=periods_per_year,
        )
        assert annual_return == pytest.approx(float(np.log1p(0.01)) * periods_per_year)
        assert annual_volatility == pytest.approx(0.0)


def test_log_assumptions_reject_invalid_returns_or_calendars() -> None:
    """The estimator validates the calendar, sample length and log domain."""
    two_returns = pd.Series([0.01, 0.02])
    one_return = pd.Series([0.01])
    total_loss = pd.Series([0.01, -1.5])
    with pytest.raises(ValueError, match="periods_per_year"):
        annualized_log_assumptions(two_returns, periods_per_year=0)
    with pytest.raises(ValueError, match="dos rentabilidades"):
        annualized_log_assumptions(one_return)
    with pytest.raises(ValueError, match="finitas"):
        annualized_log_assumptions(total_loss)


def test_path_matrix_is_labelled_by_scenario() -> None:
    """The frame exposes one Spanish column per simulated path."""
    frame = paths_to_frame(np.ones((4, 2)))

    assert list(frame.columns) == ["Simulación 1", "Simulación 2"]
    assert frame.index[0] == 0
    assert frame.shape == (4, 2)
