"""Pure risk and performance formulas."""

import math

import numpy as np
import pandas as pd
import pytest

from quantfolio.risk import (
    compound_annual_growth,
    drawdown_series,
    drift_standard_error,
    historical_cvar,
    historical_var,
    max_drawdown,
    sharpe_ratio,
)


def test_drawdown_path_and_maximum_are_measured_from_the_running_peak() -> None:
    """A 50 % fall defines both the underwater path and its minimum."""
    returns = pd.Series([0.10, -0.50, 0.25], dtype=float)
    underwater = drawdown_series(returns)

    assert underwater.name == "drawdown"
    assert underwater.iloc[0] == pytest.approx(0.0)
    assert underwater.iloc[1] == pytest.approx(-0.50)
    assert underwater.iloc[2] == pytest.approx(-0.375)
    assert max_drawdown(returns) == pytest.approx(-0.50)
    assert max_drawdown(pd.Series([0.01, 0.02, 0.03])) == pytest.approx(0.0)


def test_growth_sharpe_and_drift_match_their_formulas() -> None:
    """Compounding, excess return and standard error match direct calculations."""
    constant = pd.Series([0.01] * 252, dtype=float)
    returns = pd.Series([0.01, 0.02, -0.01, 0.03], dtype=float)
    expected_sharpe = float(returns.mean() * 252) / float(returns.std(ddof=1) * np.sqrt(252))
    expected_drift = float(returns.std(ddof=1) * np.sqrt(252)) / math.sqrt(len(returns) / 252)

    assert compound_annual_growth(constant) == pytest.approx(1.01**252 - 1.0)
    assert sharpe_ratio(returns) == pytest.approx(expected_sharpe)
    assert sharpe_ratio(pd.Series([0.01] * 10)) == pytest.approx(0.0)
    assert drift_standard_error(returns) == pytest.approx(expected_drift)


def test_sharpe_subtracts_the_annual_risk_free_rate_per_period() -> None:
    """The risk-free rate is de-annualized before forming excess returns."""
    returns = pd.Series([0.01, 0.02, -0.01, 0.03], dtype=float)
    period_rate = 0.02 / 252
    expected = float((returns - period_rate).mean() * 252) / float(
        returns.std(ddof=1) * np.sqrt(252)
    )

    assert sharpe_ratio(returns, risk_free_rate=0.02) == pytest.approx(expected)


def test_historical_tail_measures_use_the_documented_sign_convention() -> None:
    """VaR and CVaR are positive loss magnitudes over the requested tail."""
    returns = pd.Series([-0.10, -0.05, 0.0, 0.05, 0.10], dtype=float)

    assert historical_var(returns, confidence=0.75) == pytest.approx(0.05)
    assert historical_cvar(returns, confidence=0.75) == pytest.approx(0.075)


def test_risk_functions_reject_invalid_common_inputs() -> None:
    """Confidence, sample length, returns, rates and annualization share validation."""
    returns = pd.Series([0.01, -0.01], dtype=float)
    for confidence in (0.0, 1.0, -0.1, 1.1):
        with pytest.raises(ValueError, match="confidence"):
            historical_var(returns, confidence=confidence)
    one_return = pd.Series([0.01])
    with pytest.raises(ValueError, match="dos observaciones"):
        historical_cvar(one_return, confidence=0.95)
    for value in (math.nan, math.inf, -math.inf, -1.0):
        returns_with_invalid_value = pd.Series([0.01, value])
        with pytest.raises(ValueError, match="rentabilidades"):
            max_drawdown(returns_with_invalid_value)
    for rate in (math.nan, math.inf, -math.inf):
        with pytest.raises(ValueError, match="risk_free_rate"):
            sharpe_ratio(returns, risk_free_rate=rate)
    with pytest.raises(ValueError, match="periods_per_year"):
        compound_annual_growth(returns, periods_per_year=0)
    with pytest.raises(ValueError, match="periods_per_year"):
        sharpe_ratio(returns, periods_per_year=0)
    with pytest.raises(ValueError, match="periods_per_year"):
        drift_standard_error(returns, periods_per_year=0)
