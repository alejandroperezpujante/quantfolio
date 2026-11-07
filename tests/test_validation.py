"""Tests for the shared input validators."""

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
    """Build a return series directly: pct_change would drop the invalid entries under test."""
    return pd.Series(values, index=pd.bdate_range("2025-01-02", periods=len(values)), dtype=float)


@pytest.mark.parametrize("periods_per_year", [1, 12, 252])
def test_validate_periods_per_year_accepts_positive_factors(periods_per_year: int) -> None:
    """Any positive annualization factor is valid."""
    validate_periods_per_year(periods_per_year)


@pytest.mark.parametrize("periods_per_year", [0, -1])
def test_validate_periods_per_year_rejects_non_positive_factors(periods_per_year: int) -> None:
    """A non-positive annualization factor cannot annualize a return."""
    with pytest.raises(ValueError, match="periods_per_year debe ser al menos uno"):
        validate_periods_per_year(periods_per_year)


@pytest.mark.parametrize("confidence", [0.01, 0.5, 0.99])
def test_validate_confidence_accepts_interior_values(confidence: float) -> None:
    """Any confidence strictly inside (0, 1) is valid."""
    validate_confidence(confidence)


@pytest.mark.parametrize("confidence", [0.0, 1.0, -0.1, 1.1])
def test_validate_confidence_rejects_out_of_range_values(confidence: float) -> None:
    """Confidence must be strictly between zero and one."""
    with pytest.raises(ValueError, match="confidence debe estar entre 0 y 1"):
        validate_confidence(confidence)


@pytest.mark.parametrize("risk_free_rate", [0.0, 0.02, -0.01])
def test_validate_risk_free_rate_accepts_finite_rates(risk_free_rate: float) -> None:
    """Any finite annual rate is valid, including zero and negatives."""
    validate_risk_free_rate(risk_free_rate)


@pytest.mark.parametrize("risk_free_rate", [float("nan"), float("inf"), float("-inf")])
def test_validate_risk_free_rate_rejects_non_finite_rates(risk_free_rate: float) -> None:
    """A non-finite rate cannot annualize an excess return."""
    with pytest.raises(ValueError, match="risk_free_rate debe ser un número finito"):
        validate_risk_free_rate(risk_free_rate)


def test_validate_returns_accepts_a_valid_series() -> None:
    """A normal sample passes both the length and the finiteness checks."""
    validate_returns(returns_of([0.01, -0.02]))


def test_validate_returns_rejects_a_single_observation() -> None:
    """Dispersion statistics need at least two returns."""
    returns = returns_of([0.01])

    with pytest.raises(ValueError, match="dos observaciones de rentabilidad"):
        validate_returns(returns)


@pytest.mark.parametrize("values", [[float("nan"), 0.01], [0.01, -1.0]])
def test_validate_returns_rejects_invalid_returns(values: list[float]) -> None:
    """Non-finite returns and total losses are rejected."""
    returns = returns_of(values)

    with pytest.raises(ValueError, match="finitas y mayores que -100 %"):
        validate_returns(returns)


def test_validate_finite_returns_skips_the_sample_length_check() -> None:
    """Only validate_returns enforces the two-observation minimum."""
    validate_finite_returns(returns_of([0.01]))


@pytest.mark.parametrize("values", [[float("inf"), 0.01], [0.01, -1.5]])
def test_validate_finite_returns_rejects_invalid_returns(values: list[float]) -> None:
    """The finiteness branch shares the validate_returns message."""
    returns = returns_of(values)

    with pytest.raises(ValueError, match="finitas y mayores que -100 %"):
        validate_finite_returns(returns)
