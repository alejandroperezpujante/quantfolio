"""Portfolio model aggregating price series with weights."""

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

import pandas as pd

from quantfolio.constants import (
    DEFAULT_PORTFOLIO_VALUE,
    MIN_OBSERVATIONS,
    TRADING_DAYS_PER_YEAR,
)
from quantfolio.reporting import (
    plot_portfolio_report,
    plot_simulation_paths,
    render_portfolio_report,
)
from quantfolio.risk import historical_cvar, historical_var
from quantfolio.risk import max_drawdown as max_drawdown_of_returns
from quantfolio.risk import sharpe_ratio as sharpe_ratio_of_returns
from quantfolio.simulation import (
    MonteCarloParameters,
    annualized_log_assumptions,
    paths_to_frame,
    simulate_gbm_paths,
)

if TYPE_CHECKING:
    from quantfolio.models import PriceSeries


@dataclass
class Portfolio:
    """Weighted collection of price series.

    A portfolio aggregates several :class:`quantfolio.models.PriceSeries` objects and the
    fraction of the invested capital assigned to each one. Weights are validated (non-negative
    and finite) and normalized to sum to one on instantiation.

    Attributes:
        assets: Mapping from ticker to the corresponding price series.
        weights: Mapping from ticker to its portfolio weight; normalized on instantiation.

    """

    assets: dict[str, PriceSeries]
    weights: dict[str, float]

    def __post_init__(self) -> None:
        """Validate the composition and normalize the weights to sum to one.

        Raises:
            ValueError: If the portfolio has no assets, a key does not match its asset ticker,
                a weight is missing, negative or not finite, or the weights sum to zero.

        """
        if not self.assets:
            msg = "La cartera debe contener al menos un activo."
            raise ValueError(msg)
        for ticker, asset in self.assets.items():
            if ticker != asset.ticker:
                msg = f"La clave {ticker!r} no coincide con el ticker del activo {asset.ticker!r}."
                raise ValueError(msg)
        if set(self.assets) != set(self.weights):
            msg = "Debe existir una ponderación para cada activo."
            raise ValueError(msg)
        if not all(math.isfinite(weight) for weight in self.weights.values()):
            msg = "Las ponderaciones deben ser valores numéricos finitos."
            raise ValueError(msg)
        if any(weight < 0 for weight in self.weights.values()):
            msg = "Las ponderaciones no pueden ser negativas."
            raise ValueError(msg)
        total_weight = sum(self.weights.values())
        if total_weight <= 0:
            msg = "La suma de las ponderaciones debe ser positiva."
            raise ValueError(msg)
        self.weights = {ticker: weight / total_weight for ticker, weight in self.weights.items()}

    def get_prices(self) -> pd.DataFrame:
        """Return the close prices of every asset aligned on their date union.

        Missing observations are kept as ``NaN`` so that the raw calendars remain visible;
        use :meth:`get_returns` for the aligned analysis view.
        """
        return pd.concat(
            {ticker: asset.prices for ticker, asset in self.assets.items()},
            axis=1,
        ).sort_index()

    def get_returns(self) -> pd.DataFrame:
        """Return daily simple returns on the dates shared by every asset.

        Dates are aligned by intersection (inner join), so each return is computed from prices
        observed on the same trading day for all assets. Use :meth:`alignment_summary` to
        quantify how many dates are discarded by the alignment.

        Raises:
            ValueError: If the assets share fewer than two observation dates.

        """
        prices = self.get_prices().dropna(how="any")
        if len(prices) < MIN_OBSERVATIONS:
            msg = (
                "Los activos no comparten al menos dos fechas de negociación; "
                "no se pueden calcular rentabilidades."
            )
            raise ValueError(msg)
        return prices.pct_change().dropna()

    def alignment_summary(self) -> dict[str, float | int]:
        """Summarize the temporal alignment of the portfolio assets.

        Returns:
            Mapping with the number of dates in the union of calendars, the number of dates
            shared by every asset and the resulting coverage ratio.

        """
        prices = self.get_prices()
        union_dates = len(prices)
        common_dates = len(prices.dropna(how="any"))
        coverage = common_dates / union_dates if union_dates else 0.0
        return {
            "union_dates": union_dates,
            "common_dates": common_dates,
            "coverage": coverage,
        }

    def portfolio_returns(self) -> pd.Series[float]:
        """Return the weighted daily return of the portfolio."""
        returns = self.get_returns()
        weights = pd.Series(self.weights, dtype=float)
        weighted = returns.mul(weights, axis=1).sum(axis=1)
        weighted.name = "portfolio"
        return cast("pd.Series[float]", weighted)

    def summary(self, *, periods_per_year: int = TRADING_DAYS_PER_YEAR) -> dict[str, float]:
        """Return the historical return and volatility statistics of the portfolio.

        Args:
            periods_per_year: Number of trading periods per year used to annualize.

        Returns:
            Mapping with the mean daily return, daily volatility, annualized return
            approximation and annualized volatility.

        Raises:
            ValueError: If ``periods_per_year`` is not positive or there are fewer than two
                return observations.

        """
        if periods_per_year < 1:
            msg = "periods_per_year debe ser al menos uno."
            raise ValueError(msg)
        returns = self.portfolio_returns()
        if len(returns) < MIN_OBSERVATIONS:
            msg = "Se necesitan al menos dos observaciones de rentabilidad."
            raise ValueError(msg)
        mean_daily = float(returns.mean())
        std_daily = float(returns.std(ddof=1))
        return {
            "mean_daily_return": mean_daily,
            "daily_volatility": std_daily,
            "annualized_return_approx": mean_daily * periods_per_year,
            "annualized_volatility": std_daily * math.sqrt(periods_per_year),
        }

    def max_drawdown(self) -> float:
        """Return the maximum peak-to-trough decline of the portfolio."""
        return max_drawdown_of_returns(self.portfolio_returns())

    def sharpe_ratio(self, *, risk_free_rate: float = 0.0) -> float:
        """Return the annualized Sharpe ratio with an annual risk-free rate."""
        return sharpe_ratio_of_returns(
            self.portfolio_returns(),
            risk_free_rate=risk_free_rate,
        )

    def value_at_risk(self, *, confidence: float = 0.95) -> float:
        """Return the historical daily VaR at the requested confidence."""
        return historical_var(self.portfolio_returns(), confidence=confidence)

    def conditional_value_at_risk(self, *, confidence: float = 0.95) -> float:
        """Return the historical daily CVaR at the requested confidence."""
        return historical_cvar(self.portfolio_returns(), confidence=confidence)

    def simulate_monte_carlo(
        self,
        parameters: MonteCarloParameters | None = None,
    ) -> pd.DataFrame:
        """Simulate the portfolio value with a geometric Brownian motion.

        The annual drift and volatility of the portfolio log returns are estimated from the
        aligned historical returns unless ``parameters.return_assumption`` or
        ``parameters.volatility_assumption`` are given. The correlation between assets is
        embedded in the estimated portfolio volatility. ``parameters.periods_per_year`` drives
        the annualization of the estimate and the time step of the simulation. The initial
        value defaults to 10,000 units.

        Args:
            parameters: Simulation settings; defaults to :class:`MonteCarloParameters`.

        Returns:
            DataFrame of shape ``(horizon + 1, n_paths)``; row 0 is the initial value.

        Raises:
            ValueError: If the portfolio is too short or a parameter is invalid.

        """
        settings = parameters if parameters is not None else MonteCarloParameters()
        returns = self.portfolio_returns()
        if len(returns) < MIN_OBSERVATIONS:
            msg = "Se necesitan al menos dos observaciones de rentabilidad."
            raise ValueError(msg)
        annual_return, annual_volatility = annualized_log_assumptions(
            returns,
            periods_per_year=settings.periods_per_year,
        )
        if settings.return_assumption is not None:
            annual_return = settings.return_assumption
        if settings.volatility_assumption is not None:
            annual_volatility = settings.volatility_assumption
        spot = (
            settings.initial_value
            if settings.initial_value is not None
            else DEFAULT_PORTFOLIO_VALUE
        )
        paths = simulate_gbm_paths(
            initial_value=spot,
            annual_return=annual_return,
            annual_volatility=annual_volatility,
            parameters=settings,
        )
        return paths_to_frame(paths)

    @staticmethod
    def plot_simulation(simulations: pd.DataFrame, *, max_paths: int = 100) -> None:
        """Display simulated trajectories and the distribution of final values.

        Args:
            simulations: Path matrix returned by :meth:`simulate_monte_carlo`.
            max_paths: Maximum number of trajectories to draw.

        """
        plot_simulation_paths(simulations, max_paths=max_paths)

    def report(
        self,
        *,
        periods_per_year: int = TRADING_DAYS_PER_YEAR,
        include_quality: bool = True,
        include_warnings: bool = True,
        risk_free_rate: float = 0.0,
        confidence: float = 0.95,
    ) -> str:
        """Render the portfolio report as structured Markdown.

        Args:
            periods_per_year: Number of trading periods per year used to annualize statistics.
            include_quality: Whether to include the data-quality diagnostics section.
            include_warnings: Whether to include the risk-warnings section.
            risk_free_rate: Annual risk-free rate used by the Sharpe ratio.
            confidence: Confidence level of the value-at-risk measures.

        Returns:
            Markdown text with composition, metrics, diagnostics and risk warnings.

        """
        return render_portfolio_report(
            self,
            periods_per_year=periods_per_year,
            include_quality=include_quality,
            include_warnings=include_warnings,
            risk_free_rate=risk_free_rate,
            confidence=confidence,
        )

    def plots_report(self) -> None:
        """Display the analytical dashboard of the portfolio."""
        plot_portfolio_report(self)
