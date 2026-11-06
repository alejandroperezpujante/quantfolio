"""Constants shared across the toolkit."""

#: Minimum number of observations required by descriptive statistics and simulations.
MIN_OBSERVATIONS = 2

#: Number of trading sessions in a year used to annualize daily statistics.
TRADING_DAYS_PER_YEAR = 252

#: Alignment coverage below which the portfolio report warns about discarded dates.
ALIGNMENT_COVERAGE_WARNING_THRESHOLD = 0.9

#: Share of returns spanning more than one calendar day above which the report warns that the
#: annualization of a mixed-calendar portfolio is approximate.
MULTI_DAY_RETURNS_WARNING_THRESHOLD = 0.05

#: Number of portfolio returns below which the report warns about a short sample.
SHORT_HISTORY_WARNING_THRESHOLD = 30

#: Annualized volatility at or above which the report warns about high risk.
HIGH_VOLATILITY_WARNING_THRESHOLD = 0.25

#: Maximum drawdown at or below which the report warns about a deep loss.
DRAWDOWN_WARNING_THRESHOLD = -0.20

#: Largest portfolio weight above which the report warns about concentration.
CONCENTRATION_WARNING_THRESHOLD = 0.50

#: Base value used to normalize portfolio evolution charts.
PERFORMANCE_BASE = 100.0

#: Default starting value used by the portfolio Monte Carlo simulation.
DEFAULT_PORTFOLIO_VALUE = 10_000.0
