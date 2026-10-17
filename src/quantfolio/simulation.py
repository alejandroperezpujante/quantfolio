"""Monte Carlo engine based on geometric Brownian motion."""

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from quantfolio.constants import MIN_OBSERVATIONS, TRADING_DAYS_PER_YEAR

if TYPE_CHECKING:
    import numpy.typing as npt


@dataclass(frozen=True)
class MonteCarloParameters:
    """Parameters shared by the Monte Carlo simulations.

    Attributes:
        n_paths: Number of independent trajectories.
        horizon: Number of trading sessions to simulate.
        initial_value: Starting value; when ``None``, each caller applies its own default.
        return_assumption: Annualized drift of the log process; ``None`` estimates it from the
            historical returns.
        volatility_assumption: Annualized volatility of the log process; ``None`` estimates it
            from the historical returns.
        seed: Seed for the random generator; use it for reproducible results.

    """

    n_paths: int = 1_000
    horizon: int = TRADING_DAYS_PER_YEAR
    initial_value: float | None = None
    return_assumption: float | None = None
    volatility_assumption: float | None = None
    seed: int | None = None


def simulate_gbm_paths(
    *,
    initial_value: float,
    annual_return: float,
    annual_volatility: float,
    parameters: MonteCarloParameters,
) -> npt.NDArray[np.float64]:
    r"""Simulate geometric Brownian motion paths.

    The process is discretized in trading sessions with annualized assumptions:

    $$S_t = S_0 \exp\left(\mu t + \sigma W_t\right)$$

    where ``annual_return`` is the annualized drift of the log process and ``annual_volatility``
    its standard deviation, so the simulated log returns reproduce the estimated log drift. With
    this log-drift parameterization the expected price grows at
    ``annual_return + annual_volatility**2 / 2`` per year, equivalently to the classic
    $S_t = S_0 \exp((\mu - \tfrac{1}{2}\sigma^2)t + \sigma W_t)$ form with $\mu$ the drift of
    $dS = \mu S \, dt + \sigma S \, dW$.

    Args:
        initial_value: Value of the process at the first row of the output.
        annual_return: Annualized drift of the log process.
        annual_volatility: Annualized volatility of the log process.
        parameters: Horizon, number of trajectories and random seed.

    Returns:
        Array of shape ``(horizon + 1, n_paths)``; row 0 holds ``initial_value``.

    Raises:
        ValueError: If any parameter falls outside its valid range.

    """
    if initial_value <= 0:
        msg = "El valor inicial debe ser mayor que cero."
        raise ValueError(msg)
    if annual_volatility < 0:
        msg = "La volatilidad anual no puede ser negativa."
        raise ValueError(msg)
    if parameters.horizon < 1:
        msg = "El horizonte debe ser de al menos una sesión."
        raise ValueError(msg)
    if parameters.n_paths < 1:
        msg = "El número de trayectorias debe ser al menos uno."
        raise ValueError(msg)

    dt = 1.0 / TRADING_DAYS_PER_YEAR
    rng = np.random.default_rng(parameters.seed)
    shocks = rng.standard_normal((parameters.horizon, parameters.n_paths))
    drift = annual_return * dt
    increments = drift + annual_volatility * math.sqrt(dt) * shocks
    log_paths = np.cumsum(increments, axis=0)
    return initial_value * np.exp(np.vstack([np.zeros(parameters.n_paths), log_paths]))


def annualized_log_assumptions(returns: pd.Series[float]) -> tuple[float, float]:
    """Estimate annualized drift and volatility from daily simple returns.

    Args:
        returns: Daily simple returns, for example ``prices.pct_change().dropna()``.

    Returns:
        Tuple ``(annual_return, annual_volatility)`` of the log process: the annualized mean
        log return and its annualized standard deviation, directly usable by
        :func:`simulate_gbm_paths`.

    Raises:
        ValueError: If there are fewer than two observations or a return is not finite.

    """
    if len(returns) < MIN_OBSERVATIONS:
        msg = "Se necesitan al menos dos rentabilidades para estimar los supuestos."
        raise ValueError(msg)
    values = returns.to_numpy()
    if not np.all(np.isfinite(values)) or np.any(values <= -1.0):
        msg = "Las rentabilidades deben ser finitas y mayores que -100 %."
        raise ValueError(msg)
    log_returns = np.log1p(values)
    annual_return = float(np.mean(log_returns) * TRADING_DAYS_PER_YEAR)
    annual_volatility = float(np.std(log_returns, ddof=1) * math.sqrt(TRADING_DAYS_PER_YEAR))
    return annual_return, annual_volatility


def paths_to_frame(paths: npt.NDArray[np.float64]) -> pd.DataFrame:
    """Wrap a matrix of simulated paths in a labelled DataFrame.

    Args:
        paths: Array of shape ``(rows, n_paths)`` as returned by :func:`simulate_gbm_paths`.

    Returns:
        DataFrame with one column per simulated scenario and row 0 as the initial value.

    """
    n_paths = paths.shape[1]
    return pd.DataFrame(
        paths,
        index=pd.RangeIndex(paths.shape[0]),
        columns=[f"Simulación {position + 1}" for position in range(n_paths)],
    )
