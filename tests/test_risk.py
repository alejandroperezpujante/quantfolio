"""Tests for the pure risk functions."""

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


def test_max_drawdown_known_path() -> None:
    """A 50 % fall from the peak is the maximum drawdown."""
    assert max_drawdown(pd.Series([0.10, -0.50, 0.25])) == pytest.approx(-0.50)


def test_max_drawdown_is_zero_for_monotonic_gains() -> None:
    """A series that never falls has no drawdown."""
    assert max_drawdown(pd.Series([0.01, 0.02, 0.03])) == pytest.approx(0.0)


def test_drawdown_series_returns_the_underwater_curve() -> None:
    """The drawdown path is measured against the running peak."""
    drawdowns = drawdown_series(pd.Series([0.10, -0.50, 0.25]))

    assert drawdowns.iloc[0] == pytest.approx(0.0)
    assert drawdowns.iloc[1] == pytest.approx(-0.50)
    assert drawdowns.iloc[2] == pytest.approx(-0.375)


def test_compound_annual_growth_matches_manual() -> None:
    """A constant 1 % per period compounds to 1.01**252 - 1."""
    assert compound_annual_growth(pd.Series([0.01] * 252)) == pytest.approx(1.01**252 - 1)


def test_sharpe_ratio_matches_manual() -> None:
    """Sharpe is annualized mean excess return over annualized volatility."""
    returns = pd.Series([0.01, 0.02, -0.01, 0.03])
    expected = float(returns.mean() * 252) / float(returns.std(ddof=1) * np.sqrt(252))

    assert sharpe_ratio(returns) == pytest.approx(expected)


def test_sharpe_ratio_is_zero_when_volatility_is_zero() -> None:
    """A constant return has no risk to divide by."""
    assert sharpe_ratio(pd.Series([0.01] * 10)) == pytest.approx(0.0)


def test_drift_standard_error_matches_manual() -> None:
    """The standard error scales with the annualized volatility and the sample length."""
    returns = pd.Series([0.01, -0.01, 0.02, -0.02])
    expected = float(returns.std(ddof=1) * np.sqrt(252)) / np.sqrt(len(returns) / 252)

    assert drift_standard_error(returns) == pytest.approx(expected)


def test_historical_var_and_cvar_known_tail() -> None:
    """The 25 % tail of five observations is the two worst returns."""
    returns = pd.Series([-0.10, -0.05, 0.0, 0.05, 0.10])

    assert historical_var(returns, confidence=0.75) == pytest.approx(0.05)
    assert historical_cvar(returns, confidence=0.75) == pytest.approx(0.075)


@pytest.mark.parametrize("confidence", [0.0, 1.0, -0.1, 1.1])
def test_risk_measures_reject_invalid_confidence(confidence: float) -> None:
    """Confidence must be strictly between zero and one."""
    returns = pd.Series([0.01, -0.01])

    with pytest.raises(ValueError, match="confidence"):
        historical_var(returns, confidence=confidence)


def test_risk_measures_require_two_returns() -> None:
    """A single return cannot describe a distribution."""
    returns = pd.Series([0.01])

    with pytest.raises(ValueError, match="dos rentabilidades"):
        max_drawdown(returns)


def test_risk_measures_reject_returns_at_or_below_minus_one() -> None:
    """A total loss breaks the log and growth calculations."""
    returns = pd.Series([0.01, -1.0])

    with pytest.raises(ValueError, match="-100"):
        max_drawdown(returns)


def test_drawdown_series_is_named_drawdown() -> None:
    """The underwater curve carries a descriptive series name."""
    assert drawdown_series(pd.Series([0.10, -0.50, 0.25])).name == "drawdown"


def test_sharpe_ratio_subtracts_the_risk_free_rate() -> None:
    """The annual risk-free rate is converted to a per-period rate first."""
    returns = pd.Series([0.01, 0.02, -0.01, 0.03])
    period_risk_free = 0.02 / 252
    expected = float((returns - period_risk_free).mean() * 252) / float(
        returns.std(ddof=1) * np.sqrt(252)
    )

    assert sharpe_ratio(returns, risk_free_rate=0.02) == pytest.approx(expected)


def test_compound_annual_growth_rejects_invalid_periods_per_year() -> None:
    """The annualization period must be a positive number of periods."""
    returns = pd.Series([0.01, -0.01])

    with pytest.raises(ValueError, match="periods_per_year"):
        compound_annual_growth(returns, periods_per_year=0)


def test_sharpe_ratio_rejects_invalid_periods_per_year() -> None:
    """The annualization period must be a positive number of periods."""
    returns = pd.Series([0.01, -0.01])

    with pytest.raises(ValueError, match="periods_per_year"):
        sharpe_ratio(returns, periods_per_year=-1)


def test_drift_standard_error_rejects_invalid_periods_per_year() -> None:
    """The annualization period must be a positive number of periods."""
    returns = pd.Series([0.01, -0.01])

    with pytest.raises(ValueError, match="periods_per_year"):
        drift_standard_error(returns, periods_per_year=0)


@pytest.mark.parametrize("value", [np.nan, np.inf, -np.inf])
def test_risk_measures_reject_non_finite_returns(value: float) -> None:
    """Non-finite returns cannot be aggregated."""
    returns = pd.Series([0.01, value])

    with pytest.raises(ValueError, match="finitas"):
        historical_var(returns, confidence=0.95)


def test_historical_cvar_requires_two_returns() -> None:
    """The CVaR validates the sample before looking at the tail."""
    returns = pd.Series([0.01])

    with pytest.raises(ValueError, match="dos rentabilidades"):
        historical_cvar(returns, confidence=0.95)
