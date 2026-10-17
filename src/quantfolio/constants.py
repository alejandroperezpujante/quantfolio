"""Constants shared across the toolkit."""

#: Minimum number of observations required by descriptive statistics and simulations.
MIN_OBSERVATIONS = 2

#: Number of trading sessions in a year used to annualize daily statistics.
TRADING_DAYS_PER_YEAR = 252

#: Alignment coverage below which the portfolio report warns about discarded dates.
ALIGNMENT_COVERAGE_WARNING_THRESHOLD = 0.9

#: Number of portfolio returns below which the report warns about a short sample.
SHORT_HISTORY_WARNING_THRESHOLD = 30

#: Base value used to normalize portfolio evolution charts.
PERFORMANCE_BASE = 100.0

#: Default starting value used by the portfolio Monte Carlo simulation.
DEFAULT_PORTFOLIO_VALUE = 10_000.0
