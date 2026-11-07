"""Shared input validation for the analysis entry points.

Every public function that annualizes or summarizes a return series validates its arguments
through this module, so the same invalid input raises the same Spanish message from the report,
the portfolio, the price series, the simulation engine and the pure risk measures.
"""

import math
from typing import TYPE_CHECKING

import numpy as np

from quantfolio.constants import MIN_OBSERVATIONS

if TYPE_CHECKING:
    import pandas as pd


def validate_periods_per_year(periods_per_year: int) -> None:
    """Check that the annualization factor is positive.

    Args:
        periods_per_year: Number of periods in a year.

    Raises:
        ValueError: If ``periods_per_year`` is lower than one.

    """
    if periods_per_year < 1:
        msg = "periods_per_year debe ser al menos uno."
        raise ValueError(msg)


def validate_confidence(confidence: float) -> None:
    """Check that a tail probability is a valid confidence level.

    Args:
        confidence: Confidence level of the risk measure.

    Raises:
        ValueError: If ``confidence`` is not strictly between zero and one.

    """
    if not 0.0 < confidence < 1.0:
        msg = "confidence debe estar entre 0 y 1."
        raise ValueError(msg)


def validate_risk_free_rate(risk_free_rate: float) -> None:
    """Check that the annual risk-free rate is a finite number.

    Args:
        risk_free_rate: Annual risk-free rate used by the Sharpe ratio.

    Raises:
        ValueError: If ``risk_free_rate`` is not finite.

    """
    if not math.isfinite(risk_free_rate):
        msg = "risk_free_rate debe ser un número finito."
        raise ValueError(msg)


def validate_finite_returns(returns: pd.Series[float]) -> None:
    """Check that a return series holds only finite returns above a total loss.

    Args:
        returns: Simple period returns.

    Raises:
        ValueError: If a return is not finite or is less than or equal to -100 %.

    """
    values = returns.to_numpy()
    if not np.all(np.isfinite(values)) or np.any(values <= -1.0):
        msg = "Las rentabilidades deben ser finitas y mayores que -100 %."
        raise ValueError(msg)


def validate_returns(returns: pd.Series[float]) -> None:
    """Check that a return series can be aggregated.

    Args:
        returns: Simple period returns.

    Raises:
        ValueError: If there are fewer than two observations or a return is not finite or is
            less than or equal to a total loss (-100 %).

    """
    if len(returns) < MIN_OBSERVATIONS:
        msg = "Se necesitan al menos dos observaciones de rentabilidad."
        raise ValueError(msg)
    validate_finite_returns(returns)
