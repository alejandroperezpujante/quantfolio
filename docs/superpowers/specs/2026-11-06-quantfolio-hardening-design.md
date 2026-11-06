# Quantfolio Hardening Design

**Date:** 2026-11-06
**Status:** Implemented
**Source:** evaluation of the B1-T1 deliverable and independent audit (2026-11-06)

## Intent

Close the P0/P1 gaps found in the evaluation without destabilizing the passing suite. The
engineering baseline is strong (294 tests, 100 % branch coverage, strict typing, CI and Sonar
green); the work is therefore additive and test-first, one commit per problem.

## Goals

1. Make `.report()` carry the risk metrics the assignment and the repository's own
   `docs/portfolio-risk-measures.md` expect: maximum drawdown, Sharpe ratio, historical VaR and
   CVaR.
2. Make the report honest about the sample: start/end dates, per-asset coverage, annualized-return
   standard error and 95 % interval.
3. Make the report reconcile the three return measures that currently diverge: arithmetic
   annualized return, geometric CAGR, and the log drift used by the Monte Carlo (with its implied
   median growth).
4. Add risk warnings for high volatility, deep drawdown and concentration (not only the
   single-asset case).
5. Make `.report()` degrade gracefully when there are too few observations to compute metrics.
6. Make mixed-calendar return gaps visible: count return intervals that span more than one calendar
   day and document the annualization approximation.
7. Harden the CSV cache path for tickers containing `/`, `\` or `..`.
8. Pin the notebook end date and re-run all notebooks so their outputs are deterministic.
9. Fix the single-asset simulation label and the stale README claims.
10. Keep every quality gate green after every task.

## Non-goals

- A full calendar-aware return engine (per-asset returns aligned on a common frequency, or weekly
  resampling). This is documented as a follow-up; the plan makes the approximation visible.
- Multivariate, Student-t or bootstrap Monte Carlo. Separate enhancement.
- Rewriting git history, inventing commits or resolving the group composition. Human action.
- Presentation slides or a demo script.

## Decisions

### Risk metrics (`src/quantfolio/risk.py`)

Pure functions over a `pd.Series[float]` of simple returns, with at least two finite observations
and no return at or below −100 %:

| Function | Definition |
|---|---|
| `drawdown_series(returns)` | `wealth = (1 + returns).cumprod()`; `wealth / wealth.cummax() - 1` |
| `max_drawdown(returns)` | minimum of `drawdown_series` (≤ 0) |
| `compound_annual_growth(returns, periods_per_year)` | `(1 + returns).prod() ** (periods_per_year / len(returns)) - 1` |
| `sharpe_ratio(returns, risk_free_rate=0.0, periods_per_year)` | annualized mean excess return / annualized volatility; 0.0 when volatility is 0 |
| `drift_standard_error(returns, periods_per_year)` | annualized volatility / `sqrt(len(returns) / periods_per_year)` |
| `historical_var(returns, confidence=0.95)` | `-quantile(1 - confidence)` (positive number = loss) |
| `historical_cvar(returns, confidence=0.95)` | `-mean(returns <= quantile(1 - confidence))` |

`Portfolio.sharpe_ratio` takes the report's `periods_per_year` so the annualized return, volatility
and Sharpe ratio use the same factor.

`risk_free_rate` is an annual rate converted to a per-period rate by dividing by
`periods_per_year`. Invalid confidence (`≤ 0` or `≥ 1`), fewer than two returns, non-finite returns
and returns `≤ -1` raise `ValueError` with Spanish messages.

### Report layout

The existing section order stays unchanged, so the current section-number assertions keep passing:

1. Composición
2. Métricas históricas — the four existing rows plus the new ones, in the rendered order:
   1. Rentabilidad media diaria
   2. Volatilidad diaria
   3. Rentabilidad anualizada aproximada
   4. Volatilidad anualizada
   5. Error estándar de la rentabilidad anualizada
   6. IC 95% de la rentabilidad anualizada
   7. Rentabilidad geométrica (CAGR)
   8. Deriva del logaritmo usada por Monte Carlo
   9. Crecimiento mediano implícito (exp(m)-1)
   10. Máxima caída histórica
   11. Ratio de Sharpe (rf = …)
   12. VaR histórico diario (95%)
   13. CVaR histórico diario (95%)
3. Calidad de los datos — existing counts plus sample period, years of history, per-asset coverage
   table, and the share of return intervals spanning more than one calendar day.
4. Advertencias de riesgo — existing warnings plus high volatility, deep drawdown, concentration
   and multi-day-interval warnings.

After the metrics table the report renders
`_Un VaR o CVaR negativo indica que el cuantil de la cola es una ganancia._`, because a negative VaR
or CVaR means the tail quantile is a gain.

`Portfolio.report()` and `render_portfolio_report()` gain keyword-only `risk_free_rate: float = 0.0`
and `confidence: float = 0.95`. Existing calls remain valid.

### Thresholds

| Constant | Value | Warning |
|---|---:|---|
| `HIGH_VOLATILITY_WARNING_THRESHOLD` | 0.25 | annualized volatility ≥ 25 % |
| `DRAWDOWN_WARNING_THRESHOLD` | -0.20 | maximum drawdown ≤ −20 % |
| `CONCENTRATION_WARNING_THRESHOLD` | 0.50 | largest weight > 50 % |
| multi-day-interval warning | 0.05 | > 5 % of return intervals span more than one calendar day |

`SHORT_HISTORY_WARNING_THRESHOLD = 30` is retained as the "can compute" guard. The new
annualized-return standard error is the informative signal; a 1.8-year sample will show a wide
interval without changing the existing warning.

### Mixed calendars

`Portfolio.return_gaps()` returns the calendar-day differences between consecutive return dates.
`alignment_summary()` adds `multi_day_returns`, `multi_day_share` and `max_gap_days`. For disjoint
calendars it returns zero coverage and zero gap statistics instead of raising. The report warns when
more than 5 % of return intervals span more than one calendar day; the warning describes that
measured share (weekends included) without claiming that the portfolio mixes calendars. The full
return engine is out of scope; the README explains the approximation.

R29 keeps the approved calendar-day share and the `> 5 %` warning, so a weekday-only portfolio can
exceed 5 %; a union-calendar discriminator is a future enhancement, and the README documents the
caveat.

### Cache

`CachedPriceSource` keeps safe tickers unchanged (`AAA.csv`) and replaces `/`, `\` and `..` with
`-` (`BTC/USD` → `BTC-USD.csv`; `../escape` → `escape.csv`). An empty stem raises `ValueError`.
The cache file always stays inside the provider directory. The CSV stores the requested ticker in a
`ticker` column, so a file whose column does not match the requested ticker is a cache miss. Legacy
files without the column are trusted only when the ticker needed no sanitization
(`_cache_stem(ticker) == ticker`).

### Notebooks

Every notebook defines `END = "2026-11-06"` (exclusive for price sources) and passes `end=END` to
every price and macro call. Every notebook keeps stored outputs from a single top-to-bottom run after
the change. A new offline test parses the notebook JSON and asserts the pinned constant, that every
provider call passes `end=END`, the absence of `pd.Timestamp.now()`, `datetime.now(` and
`date.today(` in code cells, at least one code cell with stored outputs per notebook, and the absence
of error outputs.

## Constraints

- Python 3.14 managed with `uv`; never pip, conda or poetry.
- Before every commit: `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src tests`,
  `uv run pytest`, `uv run pre-commit run --all-files`.
- 100 % line and branch coverage; every new branch has a test.
- `tests/` never hits the network; notebook execution is a manual verification step.
- Docstrings and comments in English; user-facing report text, exception messages and plot labels
  in Spanish.
- `main` is protected: every task is implemented on its own descriptive branch and reaches `main`
  through a pull request. The plan's Branching Protocol lists the exact branch names and bases.
- Do not commit `notebooks/data/`, `coverage.xml`, `junit.xml` or scratch scripts.

## Non-code actions (before submission)

- Confirm the group composition with the instructor. If the group has three members, add the third
  member to `README.md` and `pyproject.toml` and have them make genuine commits. If the group is two,
  document the exception.
- Prepare the five-minute presentation narrative; the code plan does not cover it. The clone URL and
  the stale README claims are handled by Task 12.
