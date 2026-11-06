# Dedicated Asset-Class Portfolios Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add four dedicated single-asset-class notebooks and turn `notebooks/quantfolio_demo.ipynb` into a cross-class walkthrough built on a diversified 11-asset portfolio, with two small library extensions for correct crypto annualization and readable price charts.

**Architecture:** Each dedicated notebook is a self-contained entry point that calls the public `quantfolio` API: ingest with `CachedPriceSource`/`KrakenSource`, build a `Portfolio`, render its report and dashboard, then run the Monte Carlo engine. The main notebook keeps the full multi-source walkthrough and uses a 60/30/10 portfolio (equity/fixed income/crypto) whose holdings are a subset of the four class universes. Two library changes support the notebooks: `periods_per_year` on `MonteCarloParameters` (365 for crypto, 252 elsewhere) and a price panel rebased to 100.

**Tech Stack:** Python 3.14, uv, pandas, matplotlib, Jupyter/nbformat, ruff, mypy, pytest.

**Spec:** `docs/superpowers/specs/2026-11-06-dedicated-portfolios-design.md`

## Global Constraints

- Python 3.14 managed with `uv`; never use pip, conda or poetry.
- All example assets are USD-denominated; the library does not convert currencies.
- Every notebook uses `START = "2025-01-02"` and runs with `notebooks/` as the working directory; the CSV cache lives in `notebooks/data/` via `cache_dir="data"`.
- Kraken only serves the last 720 daily candles; the crypto notebook must explain that limit.
- Notebooks use the public `quantfolio` API only; no analysis logic duplicated in cells.
- Docstrings and code comments in English; notebook markdown, plot labels, printed output and exception messages in Spanish.
- `main` is protected: work on `feat/dedicated-portfolios` and open a pull request; never push to `main`.
- Before any commit: `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src`, `uv run pytest`, `uv run pre-commit run --all-files`.
- Do not commit `notebooks/data/`, `coverage.xml`, `junit.xml` or scratch generator scripts.

## Review Focus

- **Crypto annualization must agree end to end.** A 365-period notebook whose report says 365 while the simulation still uses 252 is the most likely silent error; the tests must cover the pass-through in both `Portfolio` and `PriceSeries`, not only the engine.
- **Mixed calendars must not pretend to be complete.** The main portfolio joins weekday assets with a seven-day crypto calendar; coverage must be reported honestly (about 69 %), the warning must remain visible, and the markdown must explain why.
- **The rebased price panel must start every asset at 100.** Assets with different first available dates must not produce NaNs, zeros or a misleading first point; the test asserts the first plotted value of each line.
- **Kraken retention must fail loudly.** A start date outside the 720-candle window must raise the existing clear error, not silently return a shorter series; the notebook must state how to adjust `START`.
- **Running a notebook twice must be safe.** The second run must reuse the cache without changing shapes, tickers or results; the final verification executes every notebook after its first run.

---

### Task 1: Branch and record the approved design

**Files:**
- Create: `docs/superpowers/specs/2026-11-06-dedicated-portfolios-design.md` (already written)
- Create: `docs/superpowers/plans/2026-11-06-dedicated-portfolios.md` (this plan)
- Rename: `notebooks/assignment.ipynb` → `notebooks/quantfolio_demo.ipynb` (already done)
- Modify: `README.md`, `docs/architecture.md` (already updated for the rename)

**Interfaces:**
- Consumes: nothing.
- Produces: branch `feat/dedicated-portfolios` with the approved spec and the renamed notebook.

- [ ] **Step 1: Create the feature branch**

```bash
git switch -c feat/dedicated-portfolios
```

- [ ] **Step 2: Confirm the working tree contains only the design record and the rename**

Run: `git status --short`
Expected: `README.md`, `docs/architecture.md`, the renamed notebook, and the new spec. No cache files.

- [ ] **Step 3: Commit the design record**

```bash
git add README.md docs/architecture.md docs/superpowers/specs/2026-11-06-dedicated-portfolios-design.md docs/superpowers/plans/2026-11-06-dedicated-portfolios.md notebooks/quantfolio_demo.ipynb
git commit -m "docs: design dedicated asset-class portfolios"
```

---

### Task 2: Add `periods_per_year` to the Monte Carlo engine

**Files:**
- Modify: `src/quantfolio/simulation.py`
- Modify: `src/quantfolio/models.py` (`PriceSeries.simulate_monte_carlo`)
- Modify: `src/quantfolio/portfolio.py` (`Portfolio.simulate_monte_carlo`)
- Test: `tests/test_simulation.py`
- Test: `tests/test_models.py`
- Test: `tests/test_portfolio.py`

**Interfaces:**
- Consumes: existing `TRADING_DAYS_PER_YEAR = 252`, `MIN_OBSERVATIONS = 2`.
- Produces:
  - `MonteCarloParameters(..., seed: int | None = None, periods_per_year: int = 252)`
  - `simulate_gbm_paths(*, initial_value: float, annual_return: float, annual_volatility: float, parameters: MonteCarloParameters) -> npt.NDArray[np.float64]` (same signature; uses `parameters.periods_per_year`)
  - `annualized_log_assumptions(returns: pd.Series[float], *, periods_per_year: int = 252) -> tuple[float, float]`
  - `Portfolio.simulate_monte_carlo` and `PriceSeries.simulate_monte_carlo` keep their signatures and pass `settings.periods_per_year` through.

- [ ] **Step 1: Write the failing engine tests**

In `tests/test_simulation.py`, extend the defaults test and add these tests:

```python
def test_monte_carlo_parameters_defaults() -> None:
    """The default simulation runs one 252-period year with 1,000 paths."""
    parameters = MonteCarloParameters()

    assert parameters.n_paths == 1_000
    assert parameters.horizon == 252
    assert parameters.periods_per_year == 252
    assert parameters.initial_value is None
    assert parameters.return_assumption is None
    assert parameters.volatility_assumption is None
    assert parameters.seed is None


def test_simulate_gbm_paths_uses_the_configured_periods_per_year() -> None:
    """A 365-period year grows at the annual rate over 365 steps."""
    parameters = MonteCarloParameters(
        n_paths=2,
        horizon=365,
        periods_per_year=365,
        seed=1,
    )

    paths = simulate_gbm_paths(
        initial_value=100.0,
        annual_return=0.05,
        annual_volatility=0.0,
        parameters=parameters,
    )

    expected = 100.0 * np.exp(0.05 * np.arange(366) / 365)
    np.testing.assert_allclose(paths[:, 0], expected, rtol=1e-12)
    np.testing.assert_allclose(paths[:, 1], expected, rtol=1e-12)


def test_annualized_log_assumptions_accepts_a_custom_annualization_factor() -> None:
    """The drift scales with the configured number of periods per year."""
    returns = pd.Series([0.01] * 10, dtype=float)

    annual_return, annual_volatility = annualized_log_assumptions(
        returns,
        periods_per_year=365,
    )

    assert annual_return == pytest.approx(float(np.log1p(0.01)) * 365)
    assert annual_volatility == pytest.approx(0.0)


def test_annualized_log_assumptions_rejects_non_positive_periods_per_year() -> None:
    """The annualization factor must be positive."""
    with pytest.raises(ValueError, match="periods_per_year"):
        annualized_log_assumptions(pd.Series([0.01, 0.02]), periods_per_year=0)
```

Add the invalid-period case to the existing `test_simulate_gbm_paths_rejects_invalid_parameters` parametrization:

```python
((100.0, 0.1, MonteCarloParameters(periods_per_year=0), "periods_per_year"),)
```

- [ ] **Step 2: Run the engine tests to verify they fail**

Run: `uv run pytest tests/test_simulation.py -v`
Expected: FAIL because `MonteCarloParameters` has no `periods_per_year` and `annualized_log_assumptions` does not accept the keyword.

- [ ] **Step 3: Implement the engine change**

In `src/quantfolio/simulation.py`:

```python
@dataclass(frozen=True)
class MonteCarloParameters:
    """Parameters shared by the Monte Carlo simulations.

    Attributes:
        n_paths: Number of independent trajectories.
        horizon: Number of periods to simulate.
        initial_value: Starting value; when ``None``, each caller applies its own default.
        return_assumption: Annualized drift of the log process; ``None`` estimates it from the
            historical returns.
        volatility_assumption: Annualized volatility of the log process; ``None`` estimates it
            from the historical returns.
        seed: Seed for the random generator; use it for reproducible results.
        periods_per_year: Number of periods per year used to annualize and to set the time step.

    """

    n_paths: int = 1_000
    horizon: int = TRADING_DAYS_PER_YEAR
    initial_value: float | None = None
    return_assumption: float | None = None
    volatility_assumption: float | None = None
    seed: int | None = None
    periods_per_year: int = TRADING_DAYS_PER_YEAR
```

In `simulate_gbm_paths`, validate the new field with the other parameters and replace the fixed step:

```python
    if parameters.periods_per_year < 1:
        msg = "periods_per_year debe ser al menos uno."
        raise ValueError(msg)
    ...
    dt = 1.0 / parameters.periods_per_year
```

Update the docstring from "trading sessions" to "periods of `1 / periods_per_year` years".

In `annualized_log_assumptions`, add the keyword argument and validate it before estimating:

```python
def annualized_log_assumptions(
    returns: pd.Series[float],
    *,
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
) -> tuple[float, float]:
    ...
    if periods_per_year < 1:
        msg = "periods_per_year debe ser al menos uno."
        raise ValueError(msg)
    ...
    annual_return = float(np.mean(log_returns) * periods_per_year)
    annual_volatility = float(np.std(log_returns, ddof=1) * math.sqrt(periods_per_year))
```

- [ ] **Step 4: Write the failing pass-through tests**

In `tests/test_portfolio.py`:

```python
def test_simulation_uses_the_configured_periods_per_year() -> None:
    """The historical estimate follows the simulation calendar."""
    prices = [100.0, 101.0, 102.01, 103.0301]
    portfolio = Portfolio(
        assets={
            "AAA": make_series("AAA", prices),
            "BBB": make_series("BBB", prices),
        },
        weights={"AAA": 0.5, "BBB": 0.5},
    )

    simulations = portfolio.simulate_monte_carlo(
        MonteCarloParameters(
            n_paths=1,
            horizon=365,
            periods_per_year=365,
            seed=1,
        )
    )

    expected = 10_000.0 * np.exp(float(np.log1p(0.01)) * 365)
    assert simulations.iloc[-1, 0] == pytest.approx(expected)
```

In `tests/test_models.py`:

```python
def test_price_series_simulation_uses_the_configured_periods_per_year() -> None:
    """The historical estimate follows the simulation calendar."""
    asset = make_series("TEST", [100.0, 101.0, 102.01, 103.0301])

    simulations = asset.simulate_monte_carlo(
        MonteCarloParameters(
            n_paths=1,
            horizon=365,
            periods_per_year=365,
            seed=1,
        )
    )

    expected = 103.0301 * np.exp(float(np.log1p(0.01)) * 365)
    assert simulations.iloc[-1, 0] == pytest.approx(expected)
```

- [ ] **Step 5: Run the pass-through tests to verify they fail**

Run: `uv run pytest tests/test_portfolio.py::test_simulation_uses_the_configured_periods_per_year tests/test_models.py::test_price_series_simulation_uses_the_configured_periods_per_year -v`
Expected: FAIL because both callers still call `annualized_log_assumptions(returns)` with the default 252.

- [ ] **Step 6: Implement the pass-through**

In `src/quantfolio/portfolio.py`:

```python
        annual_return, annual_volatility = annualized_log_assumptions(
            returns,
            periods_per_year=settings.periods_per_year,
        )
```

In `src/quantfolio/models.py`, the same change in `PriceSeries.simulate_monte_carlo`:

```python
        annual_return, annual_volatility = annualized_log_assumptions(
            returns,
            periods_per_year=settings.periods_per_year,
        )
```

Update both docstrings to mention that `parameters.periods_per_year` drives the annualization.

- [ ] **Step 7: Run the full simulation, model and portfolio tests**

Run: `uv run pytest tests/test_simulation.py tests/test_models.py tests/test_portfolio.py -v`
Expected: PASS, including all pre-existing tests.

- [ ] **Step 8: Commit**

```bash
git add src/quantfolio/simulation.py src/quantfolio/models.py src/quantfolio/portfolio.py tests/test_simulation.py tests/test_models.py tests/test_portfolio.py
git commit -m "feat: add periods_per_year to Monte Carlo"
```

---

### Task 3: Rebase the price panel to 100

**Files:**
- Modify: `src/quantfolio/reporting.py` (`plot_portfolio_report`)
- Test: `tests/test_reporting.py`

**Interfaces:**
- Consumes: `PERFORMANCE_BASE = 100.0`, `Portfolio.get_prices()`, `Portfolio.get_returns()`.
- Produces: `plot_portfolio_report(portfolio: Portfolio) -> None` with the same signature; the first panel now plots `price / first_price * 100` on the common-date aligned frame.

- [ ] **Step 1: Write the failing test**

In `tests/test_reporting.py`:

```python
def test_plot_portfolio_report_rebases_prices_to_100(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every asset starts at the common base on the price panel."""
    monkeypatch.setattr(plt, "show", lambda: None)

    plot_portfolio_report(_build_portfolio())

    price_axis = plt.gcf().axes[0]
    first_values = [line.get_ydata()[0] for line in price_axis.lines]
    assert first_values == pytest.approx([100.0, 100.0])
    assert price_axis.get_title() == "Evolución de precios (base 100)"
    assert price_axis.get_ylabel() == "Precio relativo (base 100)"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_reporting.py::test_plot_portfolio_report_rebases_prices_to_100 -v`
Expected: FAIL because the first plotted values are 10 and 20, and the title is `Evolución de precios`.

- [ ] **Step 3: Implement the rebased panel**

In `plot_portfolio_report`, replace the price block:

```python
    prices = portfolio.get_prices().dropna(how="any")
    returns = portfolio.get_returns()
    ...
    normalized_prices = prices.divide(prices.iloc[0]).multiply(PERFORMANCE_BASE)
    normalized_prices.plot(ax=prices_axis)
    prices_axis.set_title(f"Evolución de precios (base {PERFORMANCE_BASE:.0f})")
    prices_axis.set_xlabel("Fecha")
    prices_axis.set_ylabel(f"Precio relativo (base {PERFORMANCE_BASE:.0f})")
```

Update the function docstring to say the prices are aligned and rebased to 100.

- [ ] **Step 4: Run the reporting tests**

Run: `uv run pytest tests/test_reporting.py -v`
Expected: PASS, including the headless-render test.

- [ ] **Step 5: Commit**

```bash
git add src/quantfolio/reporting.py tests/test_reporting.py
git commit -m "feat: rebase portfolio price panel to 100"
```

---

### Task 4: Add the dedicated stocks notebook

**Files:**
- Create: `notebooks/portfolio_stocks.ipynb`

**Interfaces:**
- Consumes: `CachedPriceSource`, `YahooFinanceSource`, `Portfolio`, `MonteCarloParameters`, `Markdown`.
- Produces: the notebook template the next three dedicated notebooks follow.

- [ ] **Step 1: Generate the notebook with `nbformat`**

Use a temporary script (delete it afterwards; never commit it) with `nbformat.v4` and this cell sequence:

1. **Markdown — title and scope.** Title `# Cartera dedicada · Acciones`. State that the portfolio contains only USD equities, lists the five tickers and sectors, fixes `2025-01-02` as the start date, and says annualization uses 252 sessions.
2. **Code — imports and constants.**

```python
"""Cartera dedicada de acciones: ingesta, informe y simulación."""

from IPython.display import Markdown

from quantfolio import (
    CachedPriceSource,
    MonteCarloParameters,
    Portfolio,
    YahooFinanceSource,
)

START = "2025-01-02"
TICKERS = ["AAPL", "JPM", "JNJ", "XOM", "WMT"]
WEIGHTS = {"AAPL": 0.20, "JPM": 0.20, "JNJ": 0.20, "XOM": 0.20, "WMT": 0.20}
PERIODS_PER_YEAR = 252
```

3. **Markdown — ingestion.** Explain that `get_many()` downloads the five series in one batch and that each becomes a `PriceSeries`.
4. **Code — ingestion.**

```python
source = CachedPriceSource(YahooFinanceSource(), cache_dir="data")
assets = source.get_many(TICKERS, start=START)

for ticker, asset in assets.items():
    print(
        f"{ticker:>5} | {asset.source:<18} | "
        f"{asset.prices.index.min().date()} → {asset.prices.index.max().date()} | "
        f"{len(asset.prices)} observaciones"
    )
```

5. **Markdown — portfolio.** Explain that `Portfolio` validates the weights, normalizes them and aligns the calendars.
6. **Code — portfolio.**

```python
portfolio = Portfolio(assets=assets, weights=WEIGHTS)

print("Pesos normalizados:")
for ticker, weight in portfolio.weights.items():
    print(f"  {ticker}: {weight:.2%}")

print("\nDiagnóstico de alineación temporal:", portfolio.alignment_summary())
```

7. **Markdown — report.** Say the report includes composition, metrics, quality and risk warnings.
8. **Code — report.**

```python
Markdown(portfolio.report(periods_per_year=PERIODS_PER_YEAR))
```

9. **Markdown — dashboard.** Say the price panel is rebased to 100 and the other panels compare returns, correlation and portfolio value.
10. **Code — dashboard.**

```python
portfolio.plots_report()
```

11. **Markdown — Monte Carlo.** Explain that the simulation uses the historical log drift and volatility and that 252 steps represent one trading year.
12. **Code — Monte Carlo.**

```python
simulations = portfolio.simulate_monte_carlo(
    MonteCarloParameters(
        n_paths=2_000,
        horizon=PERIODS_PER_YEAR,
        periods_per_year=PERIODS_PER_YEAR,
        seed=42,
    )
)

final_values = simulations.iloc[-1]
print(final_values.describe(percentiles=[0.05, 0.5, 0.95]).round(2))
portfolio.plot_simulation(simulations, max_paths=200)
```

13. **Markdown — takeaway.** One paragraph on the role of single stocks in a diversified portfolio: higher idiosyncratic risk than index ETFs, sector dispersion and correlation below 1.

Set the notebook metadata to the `python3` kernelspec and `language_info.name = "python"`.

- [ ] **Step 2: Execute the notebook**

Run:

```bash
uv run jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.timeout=600 notebooks/portfolio_stocks.ipynb
```

Expected: exit code 0, all cells executed, no traceback, plots embedded.

- [ ] **Step 3: Verify the output**

Run a short check:

```bash
uv run python -c "import nbformat as nbf; nb=nbf.read('notebooks/portfolio_stocks.ipynb', as_version=4); code=[c for c in nb.cells if c.cell_type=='code']; assert any(c.get('outputs') for c in code); assert not any(o.output_type=='error' for c in code for o in c.get('outputs', [])); print('ok')"
```

Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add notebooks/portfolio_stocks.ipynb
git commit -m "feat: add dedicated stocks portfolio notebook"
```

---

### Task 5: Add the dedicated indices notebook

**Files:**
- Create: `notebooks/portfolio_indices.ipynb`

**Interfaces:**
- Consumes: the Task 4 notebook structure and the same public API.
- Produces: the index-ETF class view.

- [ ] **Step 1: Generate the notebook from the Task 4 template**

Keep every cell and change only:

- Title: `# Cartera dedicada · Índices`.
- Scope markdown: explain that raw index levels are not investable, so the portfolio uses five liquid ETFs as investable proxies: `SPY` (S&P 500), `QQQ` (Nasdaq 100), `IWM` (Russell 2000), `EFA` (developed ex-US) and `EEM` (emerging markets). All USD, 252 sessions.
- Constants:

```python
START = "2025-01-02"
TICKERS = ["SPY", "QQQ", "IWM", "EFA", "EEM"]
WEIGHTS = {"SPY": 0.20, "QQQ": 0.20, "IWM": 0.20, "EFA": 0.20, "EEM": 0.20}
PERIODS_PER_YEAR = 252
```

- Docstring: `"""Cartera dedicada de índices: ingesta, informe y simulación."""`
- Takeaway: index ETFs remove single-name risk but keep market, size and regional risk; correlation between equity ETFs is high, so the class does not replace fixed income or crypto as a diversifier.

- [ ] **Step 2: Execute the notebook**

```bash
uv run jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.timeout=600 notebooks/portfolio_indices.ipynb
```

Expected: exit code 0, no traceback, plots embedded.

- [ ] **Step 3: Verify the output**

Run the same no-error check as Task 4 with the new filename. Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add notebooks/portfolio_indices.ipynb
git commit -m "feat: add dedicated indices portfolio notebook"
```

---

### Task 6: Add the dedicated fixed-income notebook

**Files:**
- Create: `notebooks/portfolio_fixed_income.ipynb`

**Interfaces:**
- Consumes: the Task 4 notebook structure, `FredMacroSource` for the optional context cell.
- Produces: the fixed-income class view.

- [ ] **Step 1: Generate the notebook from the Task 4 template**

Keep every cell and change only:

- Title: `# Cartera dedicada · Renta fija`.
- Scope markdown: five USD bond ETFs spanning the Treasury curve and credit: `SHY` (1–3 years), `IEF` (7–10 years), `TLT` (20+ years), `LQD` (investment grade) and `HYG` (high yield). Note that `auto_adjust=True` includes distributions. 252 sessions.
- Constants:

```python
START = "2025-01-02"
TICKERS = ["SHY", "IEF", "TLT", "LQD", "HYG"]
WEIGHTS = {"SHY": 0.20, "IEF": 0.20, "TLT": 0.20, "LQD": 0.20, "HYG": 0.20}
PERIODS_PER_YEAR = 252
```

- Docstring: `"""Cartera dedicada de renta fija: ingesta, informe y simulación."""`.
- Add one context section after the dashboard and before the Monte Carlo:

```python
from quantfolio import FredMacroSource

fred = FredMacroSource()
rates = fred.get_series("DGS10", start=START)
print(f"Tipo del Treasury a 10 años (%): {rates.values.tail(3).round(2).to_list()}")
```

The markdown around it must say that `DGS10` is macro context and does not enter the portfolio.
- Takeaway: duration and credit are different risks; Treasuries usually diversify equities in risk-off episodes, while high yield behaves more like equity.

- [ ] **Step 2: Execute the notebook**

```bash
uv run jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.timeout=600 notebooks/portfolio_fixed_income.ipynb
```

Expected: exit code 0, no traceback, plots embedded.

- [ ] **Step 3: Verify the output**

Run the no-error check with the new filename. Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add notebooks/portfolio_fixed_income.ipynb
git commit -m "feat: add dedicated fixed-income portfolio notebook"
```

---

### Task 7: Add the dedicated crypto notebook

**Files:**
- Create: `notebooks/portfolio_crypto.ipynb`

**Interfaces:**
- Consumes: `KrakenSource`, `Portfolio`, `MonteCarloParameters`, `Markdown`.
- Produces: the crypto class view with 365-period annualization.

- [ ] **Step 1: Generate the notebook from the Task 4 template**

Keep the same section order and change:

- Title: `# Cartera dedicada · Criptomonedas`.
- Scope markdown: Kraken pairs `BTC/USD`, `ETH/USD`, `SOL/USD`, `ADA/USD`, equal weight. Explain the seven-day calendar, the 720-daily-candle retention limit and that `START = "2025-01-02"` is inside the current window.
- Constants:

```python
START = "2025-01-02"
TICKERS = ["BTC/USD", "ETH/USD", "SOL/USD", "ADA/USD"]
WEIGHTS = {"BTC/USD": 0.25, "ETH/USD": 0.25, "SOL/USD": 0.25, "ADA/USD": 0.25}
PERIODS_PER_YEAR = 365
```

- Docstring: `"""Cartera dedicada de criptomonedas: ingesta, informe y simulación."""`.
- Imports: `KrakenSource` instead of `CachedPriceSource`/`YahooFinanceSource`.
- Ingestion:

```python
source = KrakenSource()
assets = source.get_many(TICKERS, start=START)
```

- Report: `portfolio.report(periods_per_year=PERIODS_PER_YEAR)`.
- Monte Carlo: `horizon=PERIODS_PER_YEAR` and `periods_per_year=PERIODS_PER_YEAR`, so 365 steps equal one calendar year.
- Takeaway: crypto has the highest volatility and a different calendar; it is a satellite, not a core holding, and its weekend returns disappear when it is mixed with weekday assets.

- [ ] **Step 2: Execute the notebook**

```bash
uv run jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.timeout=600 notebooks/portfolio_crypto.ipynb
```

Expected: exit code 0, no traceback, plots embedded, 674 observations per pair for the current window.

- [ ] **Step 3: Verify the output**

Run the no-error check with the new filename. Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add notebooks/portfolio_crypto.ipynb
git commit -m "feat: add dedicated crypto portfolio notebook"
```

---

### Task 8: Diversify the main walkthrough notebook

**Files:**
- Modify: `notebooks/quantfolio_demo.ipynb`

**Interfaces:**
- Consumes: all providers, the library changes from Tasks 2–3, and the universes from Tasks 4–7.
- Produces: the cross-class walkthrough with the 11-asset portfolio.

- [ ] **Step 1: Replace the constants cell**

Use:

```python
"""Cuaderno de demostración: recorrido reproducible del toolkit Quantfolio."""

from quantfolio import (
    CachedPriceSource,
    FredMacroSource,
    KrakenSource,
    MonteCarloParameters,
    Portfolio,
    YahooFinanceSource,
)

START = "2025-01-02"

STOCKS = ["AAPL", "JPM", "XOM"]
INDEX_ETFS = ["SPY", "EFA", "EEM"]
BONDS = ["SHY", "IEF", "HYG"]
CRYPTO = ["BTC/USD", "ETH/USD"]

#: Cartera diversificada: 60 % renta variable, 30 % renta fija y 10 % cripto.
WEIGHTS = {
    "AAPL": 0.10,
    "JPM": 0.10,
    "XOM": 0.10,
    "SPY": 0.10,
    "EFA": 0.10,
    "EEM": 0.10,
    "SHY": 0.10,
    "IEF": 0.10,
    "HYG": 0.10,
    "BTC/USD": 0.05,
    "ETH/USD": 0.05,
}

SP500 = "^GSPC"
IBEX = "^IBEX"
INDEXES = [SP500, IBEX]
CACHE_SAMPLE = STOCKS[0]
PERIODS_PER_YEAR = 252
```

- [ ] **Step 2: Update the Yahoo section**

Keep the raw-provider demonstration for the three stocks and the reference index levels:

```python
yahoo = YahooFinanceSource()

stocks = yahoo.get_many(STOCKS, start=START)
indices = yahoo.get_many(INDEXES, start=START)

for ticker, asset in {**stocks, **indices}.items():
    print(
        f"{ticker:>8} | {asset.source:<13} | "
        f"{asset.prices.index.min().date()} → {asset.prices.index.max().date()} | "
        f"{len(asset.prices)} observaciones"
    )
```

Update the surrounding markdown to say that the index levels (`^GSPC`, `^IBEX`) are reference series and that the portfolio uses investable ETFs instead.

- [ ] **Step 3: Update the Kraken section**

```python
kraken = KrakenSource()
crypto = kraken.get_many(CRYPTO, start=START)

btc = crypto["BTC/USD"]
print(f"{type(btc).__name__}: {btc.ticker} | {btc.source} | {len(btc.prices)} observaciones")
print(f"Media: {btc.mean_price:,.0f} USD | Desviación típica: {btc.std_price:,.0f} USD")
print(f"¿Mismo objeto interno que las acciones? {type(btc) is type(stocks['AAPL'])}")
```

- [ ] **Step 4: Keep the FRED and cache sections**

Leave the `DGS10` section and the `CachedPriceSource` demo unchanged, except `CACHE_SAMPLE` now resolves to `AAPL`.

- [ ] **Step 5: Build the diversified portfolio**

Replace the old portfolio cell with:

```python
portfolio = Portfolio(
    assets={
        **cached.get_many(STOCKS + INDEX_ETFS + BONDS, start=START),
        **crypto,
    },
    weights=WEIGHTS,
)

print("Pesos normalizados:")
for ticker, weight in portfolio.weights.items():
    print(f"  {ticker}: {weight:.2%}")

print("\nDiagnóstico de alineación temporal:", portfolio.alignment_summary())

print("\nEstadísticos anualizados:")
for name, value in portfolio.summary(periods_per_year=PERIODS_PER_YEAR).items():
    print(f"  {name}: {value:.6f}")
```

Add a markdown cell before it with the sleeve table:

```markdown
| Bloque | Peso | Activos |
|---|---:|---|
| Acciones | 30 % | AAPL, JPM, XOM |
| ETF de índices | 30 % | SPY, EFA, EEM |
| Renta fija | 30 % | SHY, IEF, HYG |
| Cripto | 10 % | BTC/USD, ETH/USD |
```

Add a note after the alignment output explaining that the coverage is about 69 % because crypto trades on weekends and the inner join keeps only common weekday dates.

- [ ] **Step 6: Keep the report, dashboard and Monte Carlo sections**

Update the report call only if needed; the default 252 is correct for the main portfolio:

```python
Markdown(portfolio.report())
```

Keep `portfolio.report(include_warnings=False)`, `portfolio.plots_report()`, the 2,000-path Monte Carlo with `periods_per_year=PERIODS_PER_YEAR` and `horizon=252`, and the individual `^GSPC` simulation. Update the markdown around the Monte Carlo to say that 252 steps represent one trading year and that the crypto sleeve is a satellite.

- [ ] **Step 7: Add the closing section**

Add a final markdown cell listing the four dedicated notebooks and what each one isolates:

```markdown
## Carteras por clase de activo

- `portfolio_stocks.ipynb` — cinco acciones de sectores distintos.
- `portfolio_indices.ipynb` — cinco ETF de índices.
- `portfolio_fixed_income.ipynb` — cinco ETF de bonos.
- `portfolio_crypto.ipynb` — cuatro pares de Kraken con calendario de 365 días.
```

- [ ] **Step 8: Execute the notebook**

```bash
uv run jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.timeout=600 notebooks/quantfolio_demo.ipynb
```

Expected: exit code 0, no traceback, plots embedded, 11 assets in the report.

- [ ] **Step 9: Verify the output**

Run the no-error check with `notebooks/quantfolio_demo.ipynb`. Expected: `ok`.

- [ ] **Step 10: Commit**

```bash
git add notebooks/quantfolio_demo.ipynb
git commit -m "feat: diversify the main walkthrough portfolio"
```

---

### Task 9: Document the new notebooks

**Files:**
- Modify: `README.md`
- Modify: `docs/architecture.md`

**Interfaces:**
- Consumes: the five notebook names and the annualization rules.
- Produces: user-facing documentation that matches the executed notebooks.

- [ ] **Step 1: Update the README usage section**

After the `uv run jupyter lab notebooks/quantfolio_demo.ipynb` block, add:

```markdown
### Carteras por clase de activo

Cada clase tiene su propio cuaderno reproducible, con la misma estructura de ingesta, informe,
gráficos y Monte Carlo:

| Cuaderno | Universo | Anualización |
|---|---|---|
| [`portfolio_stocks.ipynb`](notebooks/portfolio_stocks.ipynb) | AAPL, JPM, JNJ, XOM, WMT | 252 sesiones |
| [`portfolio_indices.ipynb`](notebooks/portfolio_indices.ipynb) | SPY, QQQ, IWM, EFA, EEM | 252 sesiones |
| [`portfolio_fixed_income.ipynb`](notebooks/portfolio_fixed_income.ipynb) | SHY, IEF, TLT, LQD, HYG | 252 sesiones |
| [`portfolio_crypto.ipynb`](notebooks/portfolio_crypto.ipynb) | BTC/USD, ETH/USD, SOL/USD, ADA/USD | 365 días |

Todos los ejemplos están denominados en USD para no mezclar divisas. El cuaderno de cripto usa 365
periodos porque su calendario cotiza todos los días; el resto usa 252 sesiones.
```

- [ ] **Step 2: Replace the minimal example**

Use a compact four-class example:

```python
from quantfolio import (
    CachedPriceSource,
    KrakenSource,
    MonteCarloParameters,
    Portfolio,
    YahooFinanceSource,
)

yahoo = CachedPriceSource(YahooFinanceSource(), cache_dir="data")
kraken = KrakenSource()
assets = {
    **yahoo.get_many(["AAPL", "SPY", "IEF"], start="2025-01-02"),
    **kraken.get_many(["BTC/USD"], start="2025-01-02"),
}
portfolio = Portfolio(
    assets=assets,
    weights={"AAPL": 0.35, "SPY": 0.30, "IEF": 0.25, "BTC/USD": 0.10},
)

print(portfolio.report())  # informe Markdown
portfolio.plots_report()  # panel analítico de gráficos

simulations = portfolio.simulate_monte_carlo(
    MonteCarloParameters(n_paths=1_000, horizon=252, seed=42)
)
portfolio.plot_simulation(simulations)
```

- [ ] **Step 3: Update the project tree**

Replace the single `notebooks/` line with:

```text
├── notebooks/               # entry point and dedicated class portfolios
│   ├── quantfolio_demo.ipynb
│   ├── portfolio_stocks.ipynb
│   ├── portfolio_indices.ipynb
│   ├── portfolio_fixed_income.ipynb
│   └── portfolio_crypto.ipynb
```

- [ ] **Step 4: Update the limitations bullet**

Replace the currency bullet with:

```markdown
- La biblioteca **no convierte divisas**: los ejemplos usan activos denominados en USD para que las
  comparaciones sean monetariamente homogéneas. Mezclar activos en otras monedas sigue siendo
  responsabilidad de quien construye la cartera.
```

Add a bullet about Kraken retention:

```markdown
- Kraken solo conserva las últimas 720 velas diarias (≈2 años). Si `START` queda fuera de esa ventana,
  `KrakenSource` lanza un error explicativo en lugar de devolver una serie truncada.
```

- [ ] **Step 5: Update the architecture entry-point diagram**

Replace the single `NB["quantfolio_demo.ipynb"]` node with:

```mermaid
    subgraph entrypoint["Punto de entrada (notebooks/)"]
        NB["quantfolio_demo.ipynb<br/>portfolio_stocks.ipynb<br/>portfolio_indices.ipynb<br/>portfolio_fixed_income.ipynb<br/>portfolio_crypto.ipynb"]
    end
```

Update the flow paragraph to mention that the dedicated notebooks isolate each class while the main
notebook compares them.

- [ ] **Step 6: Verify links and consistency**

Run:

```bash
grep -R "assignment.ipynb" README.md docs/architecture.md || true
grep -R "META.*GOOGL.*IAG.MC.*MC.PA" README.md || true
```

Expected: no output from either command. Historical plan files may still mention the old name and must
not be edited.

- [ ] **Step 7: Commit**

```bash
git add README.md docs/architecture.md
git commit -m "docs: describe the dedicated portfolio notebooks"
```

---

### Task 10: Full verification

**Files:**
- No new files; fix anything the gates reveal.

**Interfaces:**
- Consumes: every previous task.
- Produces: a green branch ready for a pull request.

- [ ] **Step 1: Run the local gates**

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest
uv run pre-commit run --all-files
```

Expected: all five commands exit 0.

- [ ] **Step 2: Re-execute every notebook from the cache**

```bash
uv run jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.timeout=600 notebooks/portfolio_stocks.ipynb
uv run jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.timeout=600 notebooks/portfolio_indices.ipynb
uv run jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.timeout=600 notebooks/portfolio_fixed_income.ipynb
uv run jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.timeout=600 notebooks/portfolio_crypto.ipynb
uv run jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.timeout=600 notebooks/quantfolio_demo.ipynb
```

Expected: every command exits 0; the second runs exercise the cache.

- [ ] **Step 3: Check the executed notebooks for errors and stale outputs**

```bash
uv run python - <<'PY'
import nbformat as nbf

for path in [
    "notebooks/portfolio_stocks.ipynb",
    "notebooks/portfolio_indices.ipynb",
    "notebooks/portfolio_fixed_income.ipynb",
    "notebooks/portfolio_crypto.ipynb",
    "notebooks/quantfolio_demo.ipynb",
]:
    notebook = nbf.read(path, as_version=4)
    code_cells = [cell for cell in notebook.cells if cell.cell_type == "code"]
    assert any(cell.get("outputs") for cell in code_cells), f"no rendered output in {path}"
    assert not any(
        output.output_type == "error"
        for cell in code_cells
        for output in cell.get("outputs", [])
    ), f"error output in {path}"
    print(f"{path}: ok")
PY
```

Expected: five `ok` lines.

- [ ] **Step 4: Check the working tree**

Run: `git status --short`
Expected: only the intended notebook and documentation changes; no `notebooks/data/`, `coverage.xml`, `junit.xml` or scratch scripts.

- [ ] **Step 5: Commit any verification fixes**

If a gate required a change:

```bash
git add <changed files>
git commit -m "test: verify dedicated portfolios end to end"
```

If nothing changed, skip this commit.

- [ ] **Step 6: Open the pull request**

```bash
git push -u origin feat/dedicated-portfolios
gh pr create --title "feat: dedicated asset-class portfolios" --body "Adds four dedicated single-class notebooks, a diversified 11-asset main walkthrough, and the two small library extensions required for correct crypto annualization and readable price charts."
```

Expected: a pull request whose `Quality gates` and `Strict analysis` checks run on the branch.
