# Dedicated asset-class notebooks and a diversified reference portfolio

- **Date**: 2026-11-06
- **Status**: approved (2026-11-06), ready for a plan
- **Scope**: project — four new notebooks, one rewritten notebook, two small library extensions, README and
  architecture updates

## Intent

The assignment asks for a toolkit that ingests several market-data sources and manages portfolios. The
single entry point, `notebooks/quantfolio_demo.ipynb`, currently demonstrates that toolkit with four
large-cap equities (`META`, `GOOGL`, `IAG.MC`, `MC.PA`). That example mixes euros and dollars and does
not show how an asset class behaves on its own or how the classes combine.

The change adds four **dedicated portfolios**, one per asset class — stocks, index ETFs, fixed income and
crypto — each running the existing ingest → `Portfolio` → `report()` → `plots_report()` → Monte Carlo
pipeline. The main notebook becomes the **cross-class comparison**, built around a diversified portfolio
that mixes all four classes. Each dedicated notebook is a self-contained entry point; the main notebook
answers the question the individual ones cannot: what happens when the classes are combined.

## Goals

- Four new notebooks under `notebooks/`, one per asset class, each self-contained and reproducible.
- `notebooks/quantfolio_demo.ipynb` uses a diversified portfolio spanning stocks, index ETFs, fixed
  income and crypto instead of the current four-equity example.
- Every example is USD-denominated, so the documented lack of FX conversion cannot distort the results.
- All five notebooks share the same start date, the same public API and the same report/simulation
  structure, so their outputs are comparable.
- Add `periods_per_year` to the Monte Carlo engine so each asset class can annualize on its own calendar:
  crypto uses 365, the rest use 252. The existing default stays 252.
- Rebase the dashboard's price panel to 100 so assets with very different nominal prices remain
  comparable on one chart.
- Cover both library extensions with tests and keep every existing default and public signature
  backward compatible.
- `README.md` and `docs/architecture.md` describe the new entry points and the constraints they rely on.

## Non-goals

- Changing any other library behavior. The annualization parameter and the rebased price panel are the
  only `src/` edits; if a notebook exposes another defect, stop and re-plan.
- Adding FX conversion or currency hedging.
- Adding new data providers, new metrics or new simulation engines.
- A fifth comparison notebook: the main notebook already plays that role.
- Changing the CI workflows.

## Anti-goals

- A notebook that reimplements analysis in cells instead of calling the `quantfolio` public API.
- A portfolio that mixes currencies and silently compares nominal prices.
- Treating raw index levels as investable assets: index exposure is implemented with ETFs.
- Committing generated CSV caches or scratch scripts.

## Constraints

- **Kraken retention.** Kraken serves at most 720 daily candles (about two years). `2025-01-02` is inside
  that window today; if a run falls outside it, `KrakenSource` raises a clear error rather than silently
  truncating. The README will state the limitation.
- **Trading calendars.** Crypto trades seven days a week; the Yahoo assets trade on weekdays. `Portfolio`
  aligns by intersection, so the main portfolio discards weekend crypto observations and its coverage
  warning will fire (about 69 % in the review run, 463 common dates out of 674; the exact figure varies
  with the download date). This is expected, is explained in the main notebook, and is one of the reasons
  the crypto notebook exists as a single-class view.
- **Annualization.** `Portfolio.summary()` and `Portfolio.report()` already accept `periods_per_year`, but
  the Monte Carlo engine hard-codes 252. Crypto needs 365-day annualization and a 365-step horizon to
  represent one calendar year; the weekday-aligned main portfolio keeps 252. The library change below
  removes the inconsistency instead of documenting an understated volatility.
- **Plot scale.** Absolute prices on one axis hide low-priced assets (BTC near 76,000 USD against ADA
  near 0.19 USD, or against an 82 USD bond ETF). The price panel must be rebased to a common base; the
  library change below does it once for every portfolio.
- **Distributions.** Yahoo bond and equity ETFs are downloaded with `auto_adjust=True`, so their closes
  include distributions; the notebooks say so.
- **Working directory.** Notebooks run with `notebooks/` as the working directory, so `cache_dir="data"`
  keeps the existing convention.
- **Quality gates.** The strict IPython SonarQube profile and `ruff` cover notebooks. Cells follow the
  style of the current notebook: one import/setup cell, Spanish markdown and user-facing text, no
  analysis logic in cells.

## Approaches considered

**A. Four independent notebooks, with the main notebook as the cross-class comparison — chosen.** Each
class gets a short, readable notebook that can be studied on its own; the main notebook keeps the full
toolkit walkthrough and adds the diversified portfolio. The duplication is limited to setup and pipeline
calls, which is exactly what makes the notebooks self-contained.

**B. One parameterized notebook that selects the asset class — rejected.** A single notebook driven by a
`CLASS` variable hides four different stories behind conditionals, makes the rendered outputs depend on
run order, and is harder to read on GitHub than four short notebooks.

**C. Four dedicated notebooks plus a fifth comparison notebook — rejected.** It duplicates the main
notebook's role, adds a fifth artifact to maintain, and leaves the main notebook's old example in place
or turns it into yet another walkthrough with no clear audience.

## Composition

All series start on `2025-01-02`. Weights are equal inside each dedicated notebook; the main portfolio
uses sleeve weights and equal weights inside each sleeve.

### Dedicated portfolios

| Notebook | Assets (equal weight) | Class note |
|---|---|---|
| `portfolio_stocks.ipynb` | `AAPL`, `JPM`, `JNJ`, `XOM`, `WMT` — 20 % each | Five sectors, USD large caps. |
| `portfolio_indices.ipynb` | `SPY`, `QQQ`, `IWM`, `EFA`, `EEM` — 20 % each | Investable ETF proxies for US large/mid/small cap, developed ex-US and emerging markets. |
| `portfolio_fixed_income.ipynb` | `SHY`, `IEF`, `TLT`, `LQD`, `HYG` — 20 % each | Treasury duration ladder plus investment-grade and high-yield credit. |
| `portfolio_crypto.ipynb` | `BTC/USD`, `ETH/USD`, `SOL/USD`, `ADA/USD` — 25 % each | Kraken pairs, seven-day calendar. |

### Diversified main portfolio

| Sleeve | Weight | Assets (equal weight inside the sleeve) |
|---|---:|---|
| Stocks | 30 % | `AAPL`, `JPM`, `XOM` — 10 % each |
| Index ETFs | 30 % | `SPY`, `EFA`, `EEM` — 10 % each |
| Fixed income | 30 % | `SHY`, `IEF`, `HYG` — 10 % each |
| Crypto | 10 % | `BTC/USD`, `ETH/USD` — 5 % each |

The result is 60 % equity (half single names, half index ETFs), 30 % fixed income and a 10 % crypto
satellite: a classic 60/40 skeleton with a small satellite, expressed in one currency and built from the
same instruments as the dedicated notebooks. The main portfolio deliberately uses a subset of each
dedicated portfolio so the reader can map every holding back to its class notebook.

## Library changes

Both changes were approved during the design review. They keep every default and existing caller working;
they only add a parameter and change one presentation panel.

### 1. `periods_per_year` in the Monte Carlo engine

- `MonteCarloParameters` gains `periods_per_year: int = TRADING_DAYS_PER_YEAR`, appended after `seed` so
  existing positional construction keeps its meaning. The `horizon` docstring becomes "number of periods
  to simulate", not "trading sessions".
- `simulate_gbm_paths` computes `dt = 1 / parameters.periods_per_year` and rejects values below one with
  a Spanish `ValueError`.
- `annualized_log_assumptions(returns, *, periods_per_year=TRADING_DAYS_PER_YEAR)` uses the same
  parameter for the drift and volatility scaling and validates it.
- `Portfolio.simulate_monte_carlo` and `PriceSeries.simulate_monte_carlo` pass
  `settings.periods_per_year` to `annualized_log_assumptions`, so the estimate and the simulated steps
  always share one calendar convention.
- Defaults preserve today's behavior: 252 for every existing caller. The crypto notebook uses
  `periods_per_year=365` with `horizon=365`; the stocks, indices, fixed-income and main notebooks use
  252 with a 252-step horizon.
- Tests: default remains 252; a 365-period deterministic path grows at the expected rate; the
  annualized assumptions scale with 365; zero or negative values are rejected.

### 2. Rebased price panel

- `plot_portfolio_report` uses the common-date aligned prices (`get_prices().dropna(how="any")`) and
  divides each column by its first value, multiplied by `PERFORMANCE_BASE` (100).
- The panel title becomes `Evolución de precios (base 100)` and the y-axis label `Precio relativo (base
  100)`. The other three panels are unchanged.
- This is a presentation change, not a calculation: `report()`, `summary()` and the Monte Carlo engine
  keep using the same returns.
- Tests: the dashboard still renders headless, and the first plotted value of every asset is 100.

## Notebook design

### Common structure for the four dedicated notebooks

1. **Title and scope** — what the class is, why it is isolated, the USD-only and date-window decisions.
2. **Imports and constants** — `START`, tickers, equal weights, `CACHE_DIR`.
3. **Ingestion** — `CachedPriceSource(YahooFinanceSource(), cache_dir="data")` for stocks, index ETFs and
   bonds; `KrakenSource()` for crypto. A short printout shows provider, date range and observation count.
4. **Portfolio** — `Portfolio(assets=..., weights=...)`, normalized weights and `alignment_summary()`.
5. **Report** — `Markdown(portfolio.report(periods_per_year=...))`, with a sentence on how to read the
   warnings.
6. **Dashboard** — `portfolio.plots_report()`; the price panel is already rebased to 100 by the library.
7. **Monte Carlo** — `portfolio.simulate_monte_carlo(MonteCarloParameters(periods_per_year=...,
   horizon=..., seed=...))` and `portfolio.plot_simulation(...)`, with a short interpretation of the
   final-value distribution.
8. **Takeaway** — one markdown cell on the class's volatility, correlation and role in a diversified
   portfolio.

Annualization by notebook: stocks, indices and fixed income use 252 periods and a 252-step horizon; the
crypto notebook uses 365 and a 365-step horizon because its calendar is daily, not a trading calendar.
The main notebook uses 252 because the inner join with the weekday assets makes its return series a
weekday series, even though the crypto sleeve internally spans weekends.

The fixed-income notebook may add a single `FredMacroSource().get_series("DGS10", start=START)` cell as
macro context (yield vs bond price), provided it stays a context cell and does not enter the portfolio.
The crypto notebook uses the raw `KrakenSource` rather than the CSV cache, so its retention note replaces
the cache demo; the cache would otherwise sanitize `BTC/USD` to a `BTC-USD.csv` file.

### Main notebook changes

- Replace the old `EQUITIES` and `WEIGHTS` with the four sleeve mappings and the 11-asset weight map.
- Keep the pedagogical order: Yahoo stocks and reference indices → Kraken crypto → FRED rates → cache →
  diversified portfolio → report → dashboard → Monte Carlo. Add the bond ETFs to the Yahoo ingestion.
- Keep `^GSPC` and `^IBEX` as **reference series** for the index section and the individual Monte Carlo
  example; they are not portfolio holdings.
- Add a short markdown table with the sleeve weights and a note explaining why the alignment coverage is
  lower than in the single-class notebooks (crypto weekends) and why the main simulation keeps the
  252-period convention.
- Rename the notebook to `quantfolio_demo.ipynb` (already done) so its name describes the walkthrough
  rather than the assignment container.

## Documentation

- `README.md`: point the usage section at `quantfolio_demo.ipynb`, list the four dedicated notebooks,
  replace the four-equity minimal example with a compact four-class example, update the project tree, and
  rewrite the currency limitation as "the library does not convert currencies; the examples use USD
  assets".
- `docs/architecture.md`: show the five notebooks in the entry-point subgraph and mention the dedicated
  class views in the flow paragraph.
- `docs/README.md` needs no new background document; the notebooks are project documentation, not
  research material.

## Verification

- Add and run the library tests first: default 252, 365-period paths and assumptions, invalid period
  counts, and a rebased price panel whose first value is 100.
- Execute all five notebooks end to end with
  `uv run jupyter nbconvert --to notebook --execute --inplace <notebook>` and confirm there are no
  exceptions and the plots render.
- Run the five local gates: `ruff check`, `ruff format`, `mypy src`, `pytest`, `pre-commit`.
- Inspect the executed notebooks for stale outputs, empty cells and warnings that contradict the
  markdown.
- SonarQube analysis is left to CI; the notebooks and the two library changes follow the existing style
  that passes the strict IPython/Python profiles and the 100 % coverage gate.

## Risks

- **Library changes.** The Monte Carlo parameter touches `simulation.py`, both simulation entry points
  and the tests; the price panel touches `reporting.py` and its test. The defaults stay identical, so no
  existing caller changes behavior, but the strict coverage gate means every new branch needs a test.
- **Dashboard appearance.** Rebasing the price panel changes the look of the existing walkthrough (for
  the better), and any screenshot or prose that describes the old absolute-price panel must be updated.
- **Yahoo availability.** The new tickers are not in the local cache yet; the first execution needs
  network access and may hit rate limits. Re-running with the cache should be cheap.
- **Kraken retention.** The shared start date will eventually fall outside the 720-candle window; the
  documented error is preferable to silent truncation. The README will say how to adjust `START`.

## Decisions left to the builder

- Exact prose, cell boundaries and plot sizes inside the established style.
- Whether the fixed-income notebook includes the optional FRED context cell.
- Whether the main notebook keeps the individual `^GSPC` Monte Carlo section; it is useful and cheap, so
  the default is to keep it.
- Whether the new library tests live in the existing `test_simulation.py`/`test_reporting.py` or in a
  new module; the existing files are the natural home.
