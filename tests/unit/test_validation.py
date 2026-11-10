"""Behaviour of shared validation rules."""

import math

import pandas as pd
import pytest

from quantfolio.validation import (
    validate_confidence,
    validate_finite_returns,
    validate_periods_per_year,
    validate_returns,
    validate_risk_free_rate,
)


def returns_of(values: list[float]) -> pd.Series[float]:
    """Build a return series without dropping the invalid entries under test."""
    return pd.Series(values, index=pd.bdate_range("2025-01-02", periods=len(values)), dtype=float)


def test_valid_annualization_factors_are_accepted_before_an_invalid_one_is_rejected() -> None:
    """Any positive number of periods is valid; non-positive factors are not."""
    for periods_per_year in (1, 12, 252):
        validate_periods_per_year(periods_per_year)
    for periods_per_year in (0, -1):
        with pytest.raises(ValueError, match="periods_per_year"):
            validate_periods_per_year(periods_per_year)


def test_confidence_and_finite_rates_share_their_documented_domains() -> None:
    """Finite rates and interior confidences pass; boundary or non-finite values fail."""
    for confidence in (0.01, 0.5, 0.99):
        validate_confidence(confidence)
    for confidence in (0.0, 1.0, -0.1, 1.1):
        with pytest.raises(ValueError, match="confidence"):
            validate_confidence(confidence)
    for risk_free_rate in (0.0, 0.02, -0.01):
        validate_risk_free_rate(risk_free_rate)
    for risk_free_rate in (math.nan, math.inf, -math.inf):
        with pytest.raises(ValueError, match="risk_free_rate"):
            validate_risk_free_rate(risk_free_rate)


def test_return_validation_enforces_length_finiteness_and_total_loss() -> None:
    """Aggregate validation rejects short, non-finite and total-loss samples."""
    validate_returns(returns_of([0.01, -0.02]))
    validate_finite_returns(returns_of([0.01]))

    short_returns = returns_of([0.01])
    with pytest.raises(ValueError, match="dos observaciones"):
        validate_returns(short_returns)
    for values in ([math.nan, 0.01], [math.inf, 0.01], [0.01, -1.0], [0.01, -1.5]):
        invalid_returns = returns_of(values)
        with pytest.raises(ValueError, match="-100"):
            validate_returns(invalid_returns)
        with pytest.raises(ValueError, match="-100"):
            validate_finite_returns(invalid_returns)
