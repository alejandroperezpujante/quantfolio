"""Tests for the Monte Carlo engine."""

import numpy as np
import pandas as pd
import pytest

from quantfolio.simulation import (
    MonteCarloParameters,
    annualized_log_assumptions,
    paths_to_frame,
    simulate_gbm_paths,
)


def test_monte_carlo_parameters_defaults() -> None:
    """The default simulation runs one year with 1,000 paths."""
    parameters = MonteCarloParameters()

    assert parameters.n_paths == 1_000
    assert parameters.horizon == 252
    assert parameters.initial_value is None
    assert parameters.return_assumption is None
    assert parameters.volatility_assumption is None
    assert parameters.seed is None


def test_simulate_gbm_paths_has_expected_shape_and_initial_row() -> None:
    """Paths have one extra row for the initial value and stay positive."""
    parameters = MonteCarloParameters(n_paths=7, horizon=5, seed=42)

    paths = simulate_gbm_paths(
        initial_value=100.0,
        annual_return=0.1,
        annual_volatility=0.2,
        parameters=parameters,
    )

    assert paths.shape == (6, 7)
    np.testing.assert_allclose(paths[0], 100.0)
    assert np.all(paths > 0)


def test_simulate_gbm_paths_is_reproducible_with_a_seed() -> None:
    """The same seed yields identical outcomes."""
    parameters = MonteCarloParameters(n_paths=4, horizon=3, seed=7)
    arguments = {
        "initial_value": 100.0,
        "annual_return": 0.08,
        "annual_volatility": 0.15,
    }

    first = simulate_gbm_paths(parameters=parameters, **arguments)
    second = simulate_gbm_paths(parameters=parameters, **arguments)
    other_seed = simulate_gbm_paths(
        parameters=MonteCarloParameters(n_paths=4, horizon=3, seed=8),
        **arguments,
    )

    np.testing.assert_array_equal(first, second)
    assert not np.array_equal(first, other_seed)


def test_zero_volatility_grows_at_the_assumed_return() -> None:
    """Without volatility the process is deterministic."""
    parameters = MonteCarloParameters(n_paths=2, horizon=252, seed=1)

    paths = simulate_gbm_paths(
        initial_value=100.0,
        annual_return=0.05,
        annual_volatility=0.0,
        parameters=parameters,
    )

    expected = 100.0 * np.exp(0.05 * np.arange(253) / 252)
    np.testing.assert_allclose(paths[:, 0], expected, rtol=1e-12)
    np.testing.assert_allclose(paths[:, 1], expected, rtol=1e-12)


@pytest.mark.parametrize(
    ("initial_value", "annual_volatility", "parameters", "message"),
    [
        (0.0, 0.1, MonteCarloParameters(), "valor inicial"),
        (100.0, -0.1, MonteCarloParameters(), "volatilidad"),
        (100.0, 0.1, MonteCarloParameters(horizon=0), "horizonte"),
        (100.0, 0.1, MonteCarloParameters(n_paths=0), "trayectorias"),
    ],
)
def test_simulate_gbm_paths_rejects_invalid_parameters(
    initial_value: float,
    annual_volatility: float,
    parameters: MonteCarloParameters,
    message: str,
) -> None:
    """Out-of-range parameters are rejected with a clear message."""
    with pytest.raises(ValueError, match=message):
        simulate_gbm_paths(
            initial_value=initial_value,
            annual_return=0.1,
            annual_volatility=annual_volatility,
            parameters=parameters,
        )


def test_annualized_log_assumptions_of_constant_returns() -> None:
    """Constant returns have the expected drift and zero volatility."""
    returns = pd.Series([0.01] * 10, dtype=float)

    annual_return, annual_volatility = annualized_log_assumptions(returns)

    assert annual_return == pytest.approx(float(np.log1p(0.01)) * 252)
    assert annual_volatility == pytest.approx(0.0)


def test_annualized_log_assumptions_requires_two_observations() -> None:
    """A single return is not enough to estimate the assumptions."""
    with pytest.raises(ValueError, match="dos rentabilidades"):
        annualized_log_assumptions(pd.Series([0.01], dtype=float))


def test_annualized_log_assumptions_rejects_returns_below_minus_one() -> None:
    """Returns below -100 % make the log transformation undefined."""
    with pytest.raises(ValueError, match="finitas"):
        annualized_log_assumptions(pd.Series([0.01, -1.5], dtype=float))


def test_paths_to_frame_labels_columns() -> None:
    """The path matrix is wrapped with one Spanish-labelled column per scenario."""
    frame = paths_to_frame(np.ones((4, 2)))

    assert list(frame.columns) == ["Simulación 1", "Simulación 2"]
    assert frame.index[0] == 0
    assert frame.shape == (4, 2)
