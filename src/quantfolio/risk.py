"""Pure risk and performance measures computed from return series.

Every function in this module is a pure transformation of a return series: it does not fetch
data, mutate its input or depend on the portfolio model, which keeps the measures reusable by
the portfolio report, the notebooks and any future backtest.
"""

import math
from typing import TYPE_CHECKING, cast

from quantfolio.constants import TRADING_DAYS_PER_YEAR
from quantfolio.validation import (
    validate_confidence,
    validate_periods_per_year,
    validate_returns,
    validate_risk_free_rate,
)

if TYPE_CHECKING:
    import pandas as pd

#: Annualized volatility below which a return series is treated as riskless. The sample
#: standard deviation of a constant series is not exactly zero in floating point, so an
#: absolute tolerance is required to recognize a constant path as having no risk.
_ZERO_VOLATILITY_TOLERANCE = 1e-12


def drawdown_series(returns: pd.Series[float]) -> pd.Series[float]:
    """Return the underwater curve of a return series.

    The curve compares the compounded wealth of the series with its running peak, so each
    value is the percentage decline from the best wealth observed up to that period.

    Args:
        returns: Simple period returns.

    Returns:
        Series named ``"drawdown"`` with the decline from the running peak at each period.

    Raises:
        ValueError: If the series has fewer than two observations or an invalid return.

    """
    validate_returns(returns)
    wealth = (1.0 + returns).cumprod()
    drawdowns = wealth / wealth.cummax() - 1.0
    drawdowns.name = "drawdown"
    return drawdowns


def max_drawdown(returns: pd.Series[float]) -> float:
    """Return the deepest peak-to-trough decline of a return series.

    Args:
        returns: Simple period returns.

    Returns:
        Most negative drawdown of the series, as a fraction of the running peak.

    Raises:
        ValueError: If the series has fewer than two observations or an invalid return.

    """
    return float(drawdown_series(returns).min())


def compound_annual_growth(
    returns: pd.Series[float],
    *,
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
) -> float:
    """Return the compound annual growth rate implied by the series.

    Args:
        returns: Simple period returns.
        periods_per_year: Number of periods in a year used to annualize.

    Returns:
        Annualized compound growth rate of the series.

    Raises:
        ValueError: If ``periods_per_year`` is lower than one or the series is invalid.

    """
    validate_periods_per_year(periods_per_year)
    validate_returns(returns)
    growth = cast("float", (1.0 + returns).prod())
    return float(growth ** (periods_per_year / len(returns))) - 1.0


def sharpe_ratio(
    returns: pd.Series[float],
    *,
    risk_free_rate: float = 0.0,
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
) -> float:
    """Return the annualized Sharpe ratio of a return series.

    Args:
        returns: Simple period returns.
        risk_free_rate: Annual risk-free rate used to compute the excess return.
        periods_per_year: Number of periods in a year used to annualize.

    Returns:
        Annualized mean excess return divided by the annualized volatility, or ``0.0`` when
        the volatility is numerically zero.

    Raises:
        ValueError: If ``periods_per_year`` is lower than one, ``risk_free_rate`` is not
            finite, or the series is invalid.

    """
    validate_periods_per_year(periods_per_year)
    validate_risk_free_rate(risk_free_rate)
    validate_returns(returns)
    period_risk_free = risk_free_rate / periods_per_year
    annual_excess = float((returns - period_risk_free).mean()) * periods_per_year
    annual_volatility = float(returns.std(ddof=1)) * math.sqrt(periods_per_year)
    if annual_volatility < _ZERO_VOLATILITY_TOLERANCE:
        return 0.0
    return annual_excess / annual_volatility


def drift_standard_error(
    returns: pd.Series[float],
    *,
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
) -> float:
    """Return the standard error of the annualized mean return.

    Args:
        returns: Simple period returns.
        periods_per_year: Number of periods in a year used to annualize.

    Returns:
        Annualized volatility divided by the square root of the sample length in years.

    Raises:
        ValueError: If ``periods_per_year`` is lower than one or the series is invalid.

    """
    validate_periods_per_year(periods_per_year)
    validate_returns(returns)
    annual_volatility = float(returns.std(ddof=1)) * math.sqrt(periods_per_year)
    years = len(returns) / periods_per_year
    return annual_volatility / math.sqrt(years)


def historical_var(returns: pd.Series[float], *, confidence: float = 0.95) -> float:
    """Return the historical value at risk of a return series.

    Args:
        returns: Simple period returns.
        confidence: Confidence level of the measure; the tail probability is ``1 - confidence``.

    Returns:
        Loss (positive number) at the requested confidence, as the negated empirical quantile.

    Raises:
        ValueError: If ``confidence`` is not strictly between zero and one, or the series is
            invalid.

    """
    validate_confidence(confidence)
    validate_returns(returns)
    return -float(returns.quantile(1.0 - confidence))


def historical_cvar(returns: pd.Series[float], *, confidence: float = 0.95) -> float:
    """Return the historical conditional value at risk of a return series.

    Args:
        returns: Simple period returns.
        confidence: Confidence level of the measure; the tail probability is ``1 - confidence``.

    Returns:
        Mean loss (positive number) of the observations in the tail.

    Raises:
        ValueError: If ``confidence`` is not strictly between zero and one, or the series is
            invalid.

    """
    validate_confidence(confidence)
    validate_returns(returns)
    threshold = returns.quantile(1.0 - confidence)
    tail = returns[returns <= threshold]
    return -float(tail.mean())
