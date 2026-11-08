"""Portfolio model aggregating price series with weights."""

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

import pandas as pd

from quantfolio.constants import (
    DEFAULT_PORTFOLIO_VALUE,
    MIN_OBSERVATIONS,
    TRADING_DAYS_PER_YEAR,
)
from quantfolio.currency import ExchangeRateObservation, ExchangeRates
from quantfolio.models import _normalize_currency_code
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
from quantfolio.validation import validate_periods_per_year, validate_returns

if TYPE_CHECKING:
    from quantfolio.models import PriceSeries


def _calendar_gaps(dates: pd.DatetimeIndex) -> pd.Series[int]:
    """Return the calendar-day gaps between consecutive dates."""
    return dates.to_series().diff().dt.days.dropna().astype(int)


_CURRENCY_DIAGNOSTIC_COLUMNS = (
    "asset",
    "asset_date",
    "source_currency",
    "reporting_currency",
    "pair",
    "source",
    "rate_date",
    "age_days",
    "rate",
    "applied_rate",
    "inverted",
    "carried_forward",
)


@dataclass
class Portfolio:
    """Weighted collection of price series.

    A portfolio aggregates several :class:`quantfolio.models.PriceSeries` objects and the
    fraction of the invested capital assigned to each one. Weights are validated (non-negative
    and finite) and normalized to sum to one on instantiation.

    Attributes:
        assets: Mapping from ticker to the corresponding price series.
        weights: Mapping from ticker to its portfolio weight; normalized on instantiation.
        reporting_currency: Optional target currency used by portfolio analysis.
        exchange_rates: Historical rates available for converting asset prices.

    """

    assets: dict[str, PriceSeries]
    weights: dict[str, float]
    reporting_currency: str | None = None
    exchange_rates: ExchangeRates = field(default_factory=ExchangeRates)

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
        self._validate_currency_configuration()

    def _validate_currency_configuration(self) -> None:
        """Validate explicit reporting currency and asset quote-currency metadata."""
        exchange_rates: object = self.exchange_rates
        if not isinstance(exchange_rates, ExchangeRates):
            msg = "exchange_rates debe ser una colección ExchangeRates."
            raise TypeError(msg)
        if self.reporting_currency is not None:
            self.reporting_currency = _normalize_currency_code(
                self.reporting_currency,
                "La divisa de reporte",
            )
            unknown = [
                ticker for ticker, asset in self.assets.items() if asset.quote_currency is None
            ]
            if unknown:
                tickers = ", ".join(unknown)
                msg = f"Cada activo necesita una divisa de cotización conocida: {tickers}."
                raise ValueError(msg)
            return

        currencies = {
            asset.quote_currency for asset in self.assets.values() if asset.quote_currency
        }
        unknown_count = sum(asset.quote_currency is None for asset in self.assets.values())
        if len(currencies) > 1:
            msg = (
                "La cartera mezcla divisas; indica una divisa de reporte "
                "para convertir los activos."
            )
            raise ValueError(msg)
        if currencies and unknown_count:
            msg = (
                "No se pueden combinar divisas conocidas y desconocidas sin una divisa de reporte."
            )
            raise ValueError(msg)
        if self.exchange_rates.rates:
            msg = "Debes indicar una divisa de reporte para usar tipos de cambio."
            raise ValueError(msg)

    def get_prices(self) -> pd.DataFrame:
        """Return local-currency close prices on the union of asset calendars.

        Missing observations are kept as ``NaN`` so that the raw calendars remain visible;
        use :meth:`get_returns` for the aligned analysis view.
        """
        return pd.concat(
            {ticker: asset.prices for ticker, asset in self.assets.items()},
            axis=1,
        ).sort_index()

    def get_reporting_prices(self) -> pd.DataFrame:
        """Return asset close prices converted to the portfolio reporting currency.

        Each rate observation is selected on or before the asset date. The returned frame
        keeps the union of the original asset calendars, and rate trace data is available
        through :meth:`_reporting_prices_and_rate_uses` for diagnostics.

        Raises:
            ValueError: If no reporting currency is set or a conversion rate is missing,
                stale, invalid or future-dated.

        """
        return self._reporting_prices_and_rate_uses()[0]

    def _reporting_prices_and_rate_uses(
        self,
    ) -> tuple[pd.DataFrame, list[tuple[str, pd.Timestamp, ExchangeRateObservation]]]:
        """Build converted prices and retain the rate legs used for each observation."""
        if self.reporting_currency is None:
            msg = "Debes indicar una divisa de reporte para obtener precios convertidos."
            raise ValueError(msg)
        prices: dict[str, pd.Series[float]] = {}
        rate_uses: list[tuple[str, pd.Timestamp, ExchangeRateObservation]] = []
        for ticker, asset in self.assets.items():
            source_currency = asset.quote_currency
            if source_currency is None:
                msg = f"El activo {ticker} no tiene divisa de cotización conocida."
                raise ValueError(msg)
            if source_currency == self.reporting_currency:
                prices[ticker] = asset.prices.copy()
                continue
            converted_values: list[float] = []
            for date, price in asset.prices.items():
                asset_date = cast("pd.Timestamp", date)
                factor, observations = self.exchange_rates.resolve_rate(
                    source_currency,
                    self.reporting_currency,
                    asset_date,
                )
                converted_values.append(float(price) * factor)
                rate_uses.extend((ticker, asset_date, row) for row in observations)
            prices[ticker] = pd.Series(
                converted_values,
                index=asset.prices.index,
                dtype=float,
                name=ticker,
            )
        return pd.concat(prices, axis=1).sort_index(), rate_uses

    def _get_analysis_prices(self) -> pd.DataFrame:
        """Return the local or reporting-currency view used by portfolio analytics."""
        if self.reporting_currency is None:
            return self.get_prices()
        return self.get_reporting_prices()

    def currency_conversion_diagnostics(self) -> pd.DataFrame:
        """Return one trace row per asset date and selected FX rate leg.

        The trace includes pair orientation, provider provenance, the source observation
        date, calendar age, rate direction and whether the rate was carried forward. Identity
        conversions are included with a ``-`` pair and ``No requerida`` source.

        Returns:
            DataFrame containing rate-use trace rows. Currency-free portfolios return an
            empty frame with the same columns.

        """
        if self.reporting_currency is None:
            return pd.DataFrame(columns=list(_CURRENCY_DIAGNOSTIC_COLUMNS))
        _, rate_uses = self._reporting_prices_and_rate_uses()
        rows: list[dict[str, object]] = []
        for ticker, date, observation in rate_uses:
            rows.append(
                {
                    "asset": ticker,
                    "asset_date": date,
                    "source_currency": self.assets[ticker].quote_currency,
                    "reporting_currency": self.reporting_currency,
                    "pair": observation.pair,
                    "source": observation.source,
                    "rate_date": observation.observation_date,
                    "age_days": observation.age_days,
                    "rate": observation.rate,
                    "applied_rate": observation.applied_rate,
                    "inverted": observation.inverted,
                    "carried_forward": observation.age_days > 0,
                }
            )
        for ticker, asset in self.assets.items():
            if asset.quote_currency != self.reporting_currency:
                continue
            rows.extend(
                {
                    "asset": ticker,
                    "asset_date": date,
                    "source_currency": asset.quote_currency,
                    "reporting_currency": self.reporting_currency,
                    "pair": "-",
                    "source": "No requerida",
                    "rate_date": date,
                    "age_days": 0,
                    "rate": 1.0,
                    "applied_rate": 1.0,
                    "inverted": False,
                    "carried_forward": False,
                }
                for date in asset.prices.index
            )
        diagnostics = pd.DataFrame(rows, columns=list(_CURRENCY_DIAGNOSTIC_COLUMNS))
        return diagnostics.sort_values(
            ["asset", "asset_date", "pair"],
            ignore_index=True,
        )

    def get_returns(self) -> pd.DataFrame:
        """Return daily simple returns on the dates shared by every asset.

        Dates are aligned by intersection (inner join), so each return is computed from prices
        observed on the same trading day for all assets. Use :meth:`alignment_summary` to
        quantify how many dates are discarded by the alignment.

        Raises:
            ValueError: If the assets share fewer than two observation dates.

        """
        prices = self._get_analysis_prices().dropna(how="any")
        if len(prices) < MIN_OBSERVATIONS:
            msg = (
                "Los activos no comparten al menos dos fechas de negociación; "
                "no se pueden calcular rentabilidades."
            )
            raise ValueError(msg)
        return prices.pct_change().dropna()

    def return_gaps(self) -> pd.Series[int]:
        """Return the calendar-day gaps between consecutive return dates.

        A return computed from a Friday close to the following Monday close spans three
        calendar days. Weekends, holidays or a mixed calendar therefore make some gaps larger
        than one day, and the annualization with a fixed number of periods per year is
        approximate. The first return has no predecessor, so it has no gap.

        Returns:
            Series of positive integers indexed by the later date of each pair, with one
            entry per portfolio return after the first.

        Raises:
            ValueError: If the assets share fewer than two observation dates.

        """
        return _calendar_gaps(pd.DatetimeIndex(self.get_returns().index))

    def alignment_summary(self) -> dict[str, float | int]:
        """Summarize the temporal alignment of the portfolio assets.

        The calendar-day gaps come from the dates shared by every asset; a sample with a
        single shared date has no gap, so the multi-day statistics fall back to zero.
        Disjoint calendars report a zero coverage instead of raising.

        Returns:
            Mapping with the number of dates in the union of calendars, the number of dates
            shared by every asset, the resulting coverage ratio, the number of return
            intervals that span more than one calendar day, their share of the sample and
            the largest gap.

        """
        prices = self._get_analysis_prices()
        union_dates = len(prices)
        common = prices.dropna(how="any")
        common_dates = len(common)
        coverage = common_dates / union_dates if union_dates else 0.0
        # The first shared date is the base of the first return, so the return intervals start
        # on the second one; this mirrors ``return_gaps()`` without requiring two returns.
        gaps = _calendar_gaps(pd.DatetimeIndex(common.index[1:]))
        multi_day_returns = int((gaps > 1).sum())
        multi_day_share = float(multi_day_returns / len(gaps)) if len(gaps) else 0.0
        max_gap_days = int(gaps.max()) if len(gaps) else 0
        return {
            "union_dates": union_dates,
            "common_dates": common_dates,
            "coverage": coverage,
            "multi_day_returns": multi_day_returns,
            "multi_day_share": multi_day_share,
            "max_gap_days": max_gap_days,
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
        validate_periods_per_year(periods_per_year)
        returns = self.portfolio_returns()
        validate_returns(returns)
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

    def sharpe_ratio(
        self,
        *,
        risk_free_rate: float = 0.0,
        periods_per_year: int = TRADING_DAYS_PER_YEAR,
    ) -> float:
        """Return the annualized Sharpe ratio with an annual risk-free rate.

        Args:
            risk_free_rate: Annual risk-free rate used to compute the excess return.
            periods_per_year: Number of trading periods per year used to annualize.

        Returns:
            Annualized mean excess return divided by the annualized volatility.

        Raises:
            ValueError: If ``periods_per_year`` is not positive, ``risk_free_rate`` is not
                finite, or there are fewer than two return observations.

        """
        return sharpe_ratio_of_returns(
            self.portfolio_returns(),
            risk_free_rate=risk_free_rate,
            periods_per_year=periods_per_year,
        )

    def value_at_risk(self, *, confidence: float = 0.95) -> float:
        """Return the historical VaR of a portfolio return period at the confidence."""
        return historical_var(self.portfolio_returns(), confidence=confidence)

    def conditional_value_at_risk(self, *, confidence: float = 0.95) -> float:
        """Return the historical CVaR of a portfolio return period at the confidence."""
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
        validate_returns(returns)
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
            periods_per_year: Number of trading periods per year used to annualize the mean
                return, the volatility and the Sharpe ratio; the VaR and the CVaR are expressed
                per return period and their label follows this factor (252 or 365 read "diario",
                52 "semanal", 12 "mensual", 4 "trimestral", 1 "anual", anything else
                "por periodo"). It must match the sampling frequency of the price data.
            include_quality: Whether to include the data-quality diagnostics section.
            include_warnings: Whether to include the risk-warnings section.
            risk_free_rate: Annual risk-free rate used by the Sharpe ratio.
            confidence: Confidence level of the value-at-risk measures.

        Returns:
            Markdown text with composition, metrics, diagnostics and risk warnings.

        Raises:
            ValueError: If ``periods_per_year`` is not positive, ``confidence`` is not
                strictly between zero and one, ``risk_free_rate`` is not finite, or the
                assets share fewer than two dates (disjoint calendars).

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
