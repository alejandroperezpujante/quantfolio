"""Price-series model with automatic descriptive statistics."""

from dataclasses import dataclass, field
from typing import cast

import numpy as np
import pandas as pd

from quantfolio.constants import MIN_OBSERVATIONS
from quantfolio.reporting import plot_simulation_paths
from quantfolio.simulation import (
    MonteCarloParameters,
    annualized_log_assumptions,
    paths_to_frame,
    simulate_gbm_paths,
)


def clean_numeric_series(
    values: pd.Series[float],
    *,
    require_positive: bool = False,
) -> pd.Series[float]:
    """Return a sorted, duplicate-free copy of a series with invalid entries removed.

    Non-numeric entries, missing values and, when ``require_positive`` is true, non-positive
    values are dropped. A timezone-aware index is converted to timezone-naive timestamps.

    Args:
        values: Series indexed by observation date.
        require_positive: Whether strictly positive values are required.

    Returns:
        A numeric, chronologically sorted copy of the input series.

    Raises:
        TypeError: If the index is not a ``DatetimeIndex``.

    """
    if not isinstance(values.index, pd.DatetimeIndex):
        msg = "El índice de la serie debe ser un DatetimeIndex."
        raise TypeError(msg)
    cleaned = pd.to_numeric(values, errors="coerce").dropna()
    cleaned = cleaned[np.isfinite(cleaned)]
    if require_positive:
        cleaned = cleaned[cleaned > 0]
    if cleaned.index.tz is not None:
        cleaned = cleaned.copy()
        cleaned.index = cleaned.index.tz_localize(None)
    cleaned = cleaned[~cleaned.index.duplicated(keep="last")]
    cleaned = cleaned.sort_index()
    cleaned.index = cleaned.index.rename(None)
    return cast("pd.Series[float]", cleaned.astype(float))


@dataclass
class PriceSeries:
    """Historical close prices for a single instrument.

    Attributes:
        ticker: Instrument identifier, for example ``"AAPL"`` or ``"^GSPC"``.
        prices: Close prices indexed by observation date.
        source: Human-readable name of the provider the data came from.
        mean_price: Mean close price, computed automatically on instantiation.
        std_price: Sample standard deviation of close prices, computed automatically on
            instantiation (zero for a single observation).

    """

    ticker: str
    prices: pd.Series[float]
    source: str = "unknown"
    mean_price: float = field(init=False)
    std_price: float = field(init=False)

    def __post_init__(self) -> None:
        """Validate the input and compute the automatic descriptive statistics.

        Raises:
            TypeError: If ``prices`` is not a ``pandas.Series``.
            ValueError: If the ticker is empty or the series has no valid positive prices.

        """
        if not isinstance(self.ticker, str) or not self.ticker.strip():
            msg = "El ticker debe ser un texto no vacío."
            raise ValueError(msg)
        if not isinstance(cast("object", self.prices), pd.Series):
            msg = "prices debe ser una pandas.Series."
            raise TypeError(msg)
        if self.prices.empty:
            msg = "La serie de precios no puede estar vacía."
            raise ValueError(msg)
        cleaned = clean_numeric_series(self.prices, require_positive=True)
        if cleaned.empty:
            msg = "La serie debe contener precios positivos válidos."
            raise ValueError(msg)
        self.prices = cleaned
        self.prices.name = self.ticker
        self.mean_price = float(cleaned.mean())
        self.std_price = float(cleaned.std(ddof=1)) if len(cleaned) >= MIN_OBSERVATIONS else 0.0

    def simulate_monte_carlo(
        self,
        parameters: MonteCarloParameters | None = None,
    ) -> pd.DataFrame:
        """Simulate future prices with a geometric Brownian motion.

        The annual drift and volatility are estimated from the historical series unless
        ``parameters.return_assumption`` or ``parameters.volatility_assumption`` are given.
        The initial value defaults to the last observed price.

        Args:
            parameters: Simulation settings; defaults to :class:`MonteCarloParameters`.

        Returns:
            DataFrame of shape ``(horizon + 1, n_paths)``; row 0 is the initial value.

        Raises:
            ValueError: If the series is too short or a parameter is invalid.

        """
        settings = parameters if parameters is not None else MonteCarloParameters()
        if len(self.prices) < MIN_OBSERVATIONS:
            msg = "Se necesitan al menos dos precios para estimar la simulación."
            raise ValueError(msg)
        returns = self.prices.pct_change().dropna()
        annual_return, annual_volatility = annualized_log_assumptions(returns)
        if settings.return_assumption is not None:
            annual_return = settings.return_assumption
        if settings.volatility_assumption is not None:
            annual_volatility = settings.volatility_assumption
        spot = (
            settings.initial_value
            if settings.initial_value is not None
            else float(self.prices.iloc[-1])
        )
        paths = simulate_gbm_paths(
            initial_value=spot,
            annual_return=annual_return,
            annual_volatility=annual_volatility,
            parameters=settings,
        )
        return paths_to_frame(paths)

    def plot_simulation(self, simulations: pd.DataFrame, *, max_paths: int = 100) -> None:
        """Display simulated trajectories and the distribution of final values.

        Args:
            simulations: Path matrix returned by :meth:`simulate_monte_carlo`.
            max_paths: Maximum number of trajectories to draw.

        """
        plot_simulation_paths(simulations, max_paths=max_paths)
