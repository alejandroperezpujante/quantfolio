# Quantfolio Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the P0/P1 findings of the 2026-11-06 evaluation — risk metrics, report diagnostics, return-measure reconciliation, tiny-sample resilience, mixed-calendar visibility, cache safety and notebook determinism — without breaking the passing 294-test suite.

**Architecture:** A new pure-function `quantfolio.risk` module supplies drawdown, Sharpe, VaR/CVaR, CAGR and drift uncertainty. `Portfolio` exposes thin delegating methods; `reporting.py` renders them into the existing four-section Markdown report, so the section order and the current tests stay intact. The notebook and cache changes are independent of the reporting work.

**Tech Stack:** Python 3.14, uv, pandas, numpy, matplotlib, pytest, ruff, mypy, pre-commit, Jupyter/nbconvert.

**Spec:** `docs/superpowers/specs/2026-11-06-quantfolio-hardening-design.md`

## Global Constraints

- Python 3.14 managed with `uv`; never pip, conda or poetry.
- Before every commit: `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src tests`, `uv run pytest`, `uv run pre-commit run --all-files`.
- 100 % line and branch coverage; every new branch has a test.
- `tests/` never hits the network. Notebook execution is a manual verification step.
- Docstrings and comments in English; report text, exception messages and plot labels in Spanish.
- `main` is protected: every task has its own branch (see **Branching Protocol**), and every change reaches `main` through a pull request; never push to `main`.
- Do not commit `notebooks/data/`, `coverage.xml`, `junit.xml` or scratch scripts.
- One task = one branch + one self-contained commit + one pull request. Task 0 records the design; Tasks 1–2 are the code foundation; Tasks 3–6 consume it. Tasks 7–11 are independent. Task 12 is documentation after the code. Task 13 is optional.
- The existing report section order stays unchanged: 1 Composición, 2 Métricas históricas, 3 Calidad de los datos, 4 Advertencias de riesgo.

## Branching Protocol

Every task is implemented on its own branch. Do not reuse a branch across tasks and do not commit
directly to `main`. Cut each branch from an up-to-date `main` after its prerequisite task has
merged.

| Task | Branch | Cut from | PR title |
|---:|---|---|---|
| 0 | `docs/hardening-design` | `main` | `docs: record the hardening design` |
| 1 | `feat/risk-measures-core` | `main` after Task 0 merges | `feat: add pure portfolio risk measures` |
| 2 | `feat/report-risk-metrics` | `main` after Task 1 merges | `feat: report drawdown, Sharpe, VaR and CVaR` |
| 3 | `feat/report-sample-diagnostics` | `main` after Task 2 merges | `feat: report sample coverage and return uncertainty` |
| 4 | `feat/report-risk-warnings` | `main` after Task 2 merges | `feat: warn about volatility, drawdown and concentration` |
| 5 | `feat/report-return-reconciliation` | `main` after Task 2 merges | `feat: reconcile arithmetic, geometric and log-drift returns` |
| 6 | `fix/report-tiny-samples` | `main` after Task 2 merges | `fix: degrade report gracefully on tiny samples` |
| 7 | `feat/mixed-calendar-diagnostics` | `main` after Task 2 merges | `feat: expose mixed-calendar return gaps` |
| 8 | `fix/cache-path-safety` | `main` | `fix: keep cache files inside the provider directory` |
| 9 | `fix/simulation-price-label` | `main` after Task 2 merges | `fix: label single-asset simulations as prices` |
| 10 | `fix/notebook-end-dates` | `main` after Tasks 2-7 and 9 merge | `fix: pin notebook end dates and re-run all notebooks` |
| 11 | `build/prune-dependencies` | `main` | `build: prune unused runtime dependencies` |
| 12 | `docs/report-and-notebooks` | `main` after Tasks 2-11 merge | `docs: document the hardened report and reproducible notebooks` |
| 13 | `feat/price-series-summary` | `main` after Task 1 merges | `feat: add return statistics to PriceSeries` |
| 14 | `chore/final-verification` (only if a gate requires a change) | `main` after all task PRs merge | `chore: verify the hardening release` |

For every task:

1. `git switch main && git pull --ff-only`
2. `git switch -c <branch>`
3. Implement the task and commit.
4. `git push -u origin <branch>`
5. `gh pr create --fill`
6. Wait for `Quality gates` and `Strict analysis` to be green; merge with the repository's
   configured method and delete the branch.
7. `git switch main && git pull --ff-only` before the next task.

Task 0 records the design and must merge first. Tasks 1 and 2 are the code foundation: merge Task 1
before starting Task 2, and Task 2 before starting Tasks 3–7 and 9. Tasks 8, 11 and 13 are independent and can be done in any order after their base
is available. Task 10 needs Tasks 2–7 and 9 merged because the notebooks render the hardened report
and the single-asset label. Task 12 needs Tasks 2–11 merged because it documents them. Task 14 runs
on `main` after every task PR has merged; it only creates a branch if a gate reveals a fix.

If two tasks touch the same file (`reporting.py` in Tasks 3–7 and 9; `models.py` in Tasks 9 and 13),
merge the earlier one before starting the second. Do not keep two branches open against the same
file.

## Review Focus

- **A two-price portfolio must not crash `.report()`.** `summary()` needs two returns; the report must render an "insufficient observations" message instead of raising.
- **A mixed-calendar portfolio must not hide its approximation.** The report must show how many return intervals span more than one calendar day and warn when the share exceeds 5 %.
- **A 99 %/1 % portfolio must warn about concentration.** The current check only fires for a single asset.
- **A high-volatility or deep-drawdown portfolio must warn.** A 65 %-vol crypto portfolio currently gets only the generic warnings.
- **A ticker containing `/` or `..` must not escape the cache directory.** `BTC/USD` must become a safe filename and `../escape` must stay inside the provider folder.

---

### Task 0: Record the approved design

**Files:**
- Create: `docs/superpowers/specs/2026-11-06-quantfolio-hardening-design.md` (already written)
- Create: `docs/superpowers/plans/2026-11-06-quantfolio-hardening.md` (this plan)
- Modify: `pyproject.toml` — add `docs/superpowers/plans/*.md` to `[tool.ruff] extend-exclude` so the
  plan's illustrative snippets are not reformatted as executable code.

**Interfaces:**
- Consumes: nothing.
- Produces: the approved spec and plan on `main`.

**Branch:** `docs/hardening-design` (cut from `main`).

- [ ] **Step 1: Create the branch**

```bash
git switch main
git pull --ff-only
git switch -c docs/hardening-design
```

- [ ] **Step 2: Exclude plan documents from Ruff formatting**

Add to the `[tool.ruff]` table in `pyproject.toml`:

```toml
extend-exclude = ["docs/superpowers/plans/*.md"]
```

- [ ] **Step 3: Run the five global gates**

Run the five commands in **Global Constraints**.

Expected: all exit 0.

- [ ] **Step 4: Commit the design record**

```bash
git add docs/superpowers/specs/2026-11-06-quantfolio-hardening-design.md docs/superpowers/plans/2026-11-06-quantfolio-hardening.md pyproject.toml
git commit -m "docs: record the hardening design"
```

- [ ] **Step 5: Push and open the pull request**

```bash
git push -u origin docs/hardening-design
gh pr create --fill
```

Expected: the PR's `Quality gates` and `Strict analysis` checks run on the branch. Merge only when both are green.

---

### Task 1: Add the pure risk functions

**Files:**
- Create: `src/quantfolio/risk.py`
- Create: `tests/test_risk.py`

**Interfaces:**
- Consumes: `TRADING_DAYS_PER_YEAR = 252`, `pandas`, `numpy`.
- Produces:
  - `drawdown_series(returns: pd.Series[float]) -> pd.Series[float]`
  - `max_drawdown(returns: pd.Series[float]) -> float`
  - `compound_annual_growth(returns: pd.Series[float], *, periods_per_year: int = 252) -> float`
  - `sharpe_ratio(returns: pd.Series[float], *, risk_free_rate: float = 0.0, periods_per_year: int = 252) -> float`
  - `drift_standard_error(returns: pd.Series[float], *, periods_per_year: int = 252) -> float`
  - `historical_var(returns: pd.Series[float], *, confidence: float = 0.95) -> float`
  - `historical_cvar(returns: pd.Series[float], *, confidence: float = 0.95) -> float`

**Branch:** `feat/risk-measures-core` (cut from `main` after Task 0 merges).

- [ ] **Step 1: Write the failing tests**

In `tests/test_risk.py`:

```python
"""Tests for the pure risk functions."""

import numpy as np
import pandas as pd
import pytest

from quantfolio.risk import (
    compound_annual_growth,
    drawdown_series,
    drift_standard_error,
    historical_cvar,
    historical_var,
    max_drawdown,
    sharpe_ratio,
)


def test_max_drawdown_known_path() -> None:
    """A 50 % fall from the peak is the maximum drawdown."""
    assert max_drawdown(pd.Series([0.10, -0.50, 0.25])) == pytest.approx(-0.50)


def test_max_drawdown_is_zero_for_monotonic_gains() -> None:
    """A series that never falls has no drawdown."""
    assert max_drawdown(pd.Series([0.01, 0.02, 0.03])) == pytest.approx(0.0)


def test_drawdown_series_returns_the_underwater_curve() -> None:
    """The drawdown path is measured against the running peak."""
    drawdowns = drawdown_series(pd.Series([0.10, -0.50, 0.25]))

    assert drawdowns.iloc[0] == pytest.approx(0.0)
    assert drawdowns.iloc[1] == pytest.approx(-0.50)
    assert drawdowns.iloc[2] == pytest.approx(-0.375)


def test_compound_annual_growth_matches_manual() -> None:
    """A constant 1 % per period compounds to 1.01**252 - 1."""
    assert compound_annual_growth(pd.Series([0.01] * 252)) == pytest.approx(1.01**252 - 1)


def test_sharpe_ratio_matches_manual() -> None:
    """Sharpe is annualized mean excess return over annualized volatility."""
    returns = pd.Series([0.01, 0.02, -0.01, 0.03])
    expected = float(returns.mean() * 252) / float(returns.std(ddof=1) * np.sqrt(252))

    assert sharpe_ratio(returns) == pytest.approx(expected)


def test_sharpe_ratio_is_zero_when_volatility_is_zero() -> None:
    """A constant return has no risk to divide by."""
    assert sharpe_ratio(pd.Series([0.01] * 10)) == pytest.approx(0.0)


def test_drift_standard_error_matches_manual() -> None:
    """The standard error scales with the annualized volatility and the sample length."""
    returns = pd.Series([0.01, -0.01, 0.02, -0.02])
    expected = float(returns.std(ddof=1) * np.sqrt(252)) / np.sqrt(len(returns) / 252)

    assert drift_standard_error(returns) == pytest.approx(expected)


def test_historical_var_and_cvar_known_tail() -> None:
    """The 25 % tail of five observations is the two worst returns."""
    returns = pd.Series([-0.10, -0.05, 0.0, 0.05, 0.10])

    assert historical_var(returns, confidence=0.75) == pytest.approx(0.05)
    assert historical_cvar(returns, confidence=0.75) == pytest.approx(0.075)


@pytest.mark.parametrize("confidence", [0.0, 1.0, -0.1, 1.1])
def test_risk_measures_reject_invalid_confidence(confidence: float) -> None:
    """Confidence must be strictly between zero and one."""
    with pytest.raises(ValueError, match="confidence"):
        historical_var(pd.Series([0.01, -0.01]), confidence=confidence)


def test_risk_measures_require_two_returns() -> None:
    """A single return cannot describe a distribution."""
    with pytest.raises(ValueError, match="dos rentabilidades"):
        max_drawdown(pd.Series([0.01]))


def test_risk_measures_reject_returns_at_or_below_minus_one() -> None:
    """A total loss breaks the log and growth calculations."""
    with pytest.raises(ValueError, match="-100"):
        max_drawdown(pd.Series([0.01, -1.0]))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_risk.py -v`

Expected: FAIL because `quantfolio.risk` does not exist.

- [ ] **Step 3: Implement `src/quantfolio/risk.py`**

Create the module with the seven public functions and one private validator. Use this validation contract:

```python
def _validate_returns(returns: pd.Series[float]) -> None:
    if len(returns) < 2:
        msg = "Se necesitan al menos dos rentabilidades."
        raise ValueError(msg)
    values = returns.to_numpy()
    if not np.all(np.isfinite(values)) or np.any(values <= -1.0):
        msg = "Las rentabilidades deben ser finitas y mayores que -100 %."
        raise ValueError(msg)


def _validate_confidence(confidence: float) -> None:
    if not 0.0 < confidence < 1.0:
        msg = "confidence debe estar entre 0 y 1."
        raise ValueError(msg)
```

Definitions to implement (docstrings in English):

- `drawdown_series`: `wealth = (1 + returns).cumprod()`; `wealth / wealth.cummax() - 1`, renamed `"drawdown"`.
- `max_drawdown`: `float(drawdown_series(returns).min())`.
- `compound_annual_growth`: validate `periods_per_year >= 1`; `(1 + returns).prod() ** (periods_per_year / len(returns)) - 1`.
- `sharpe_ratio`: validate `periods_per_year >= 1`; `period_rf = risk_free_rate / periods_per_year`; `annual_excess = (returns - period_rf).mean() * periods_per_year`; `annual_vol = returns.std(ddof=1) * sqrt(periods_per_year)`; return `0.0` when `annual_vol == 0`, else `annual_excess / annual_vol`.
- `drift_standard_error`: validate `periods_per_year >= 1`; `years = len(returns) / periods_per_year`; `annual_vol / sqrt(years)`.
- `historical_var`: validate confidence; `-float(returns.quantile(1.0 - confidence))`.
- `historical_cvar`: validate confidence; `threshold = returns.quantile(1.0 - confidence)`; `tail = returns[returns <= threshold]`; return `-float(tail.mean())`.

- [ ] **Step 4: Run the risk tests**

Run: `uv run pytest tests/test_risk.py -v`

Expected: PASS.

- [ ] **Step 5: Run the five global gates**

Run the five commands in **Global Constraints**.

Expected: all exit 0; coverage stays at 100 %.

- [ ] **Step 6: Commit**

```bash
git add src/quantfolio/risk.py tests/test_risk.py
git commit -m "feat: add pure portfolio risk measures"
```

- [ ] **Step PR: Push and open the pull request**

```bash
git push -u origin feat/risk-measures-core
gh pr create --fill
```

Expected: the PR's `Quality gates` and `Strict analysis` checks run on the branch. Merge only when both are green.

---

### Task 2: Expose risk metrics in `Portfolio` and `.report()`

**Files:**
- Modify: `src/quantfolio/portfolio.py`
- Modify: `src/quantfolio/reporting.py`
- Test: `tests/test_portfolio.py`

**Interfaces:**
- Consumes: the seven functions from Task 1.
- Produces:
  - `Portfolio.max_drawdown() -> float`
  - `Portfolio.sharpe_ratio(*, risk_free_rate: float = 0.0, periods_per_year: int = 252) -> float`
  - `Portfolio.value_at_risk(*, confidence: float = 0.95) -> float`
  - `Portfolio.conditional_value_at_risk(*, confidence: float = 0.95) -> float`
  - `Portfolio.report(*, periods_per_year=252, include_quality=True, include_warnings=True, risk_free_rate=0.0, confidence=0.95) -> str`
  - `render_portfolio_report(..., risk_free_rate: float = 0.0, confidence: float = 0.95) -> str`

**Branch:** `feat/report-risk-metrics` (cut from `main` after Task 1 merges).

- [ ] **Step 1: Write the failing portfolio tests**

Append to `tests/test_portfolio.py`:

```python
def test_portfolio_risk_metrics_match_manual() -> None:
    """The portfolio methods delegate to the pure risk functions."""
    portfolio = build_portfolio()
    returns = portfolio.portfolio_returns()

    assert portfolio.max_drawdown() == pytest.approx(max_drawdown(returns))
    assert portfolio.sharpe_ratio() == pytest.approx(sharpe_ratio(returns))
    assert portfolio.value_at_risk(confidence=0.95) == pytest.approx(
        historical_var(returns, confidence=0.95)
    )
    assert portfolio.conditional_value_at_risk(confidence=0.95) == pytest.approx(
        historical_cvar(returns, confidence=0.95)
    )


def test_report_includes_risk_metrics() -> None:
    """The Markdown report shows drawdown, Sharpe, VaR and CVaR."""
    report = build_portfolio().report()

    assert "Máxima caída histórica" in report
    assert "Ratio de Sharpe" in report
    assert "VaR histórico diario (95%)" in report
    assert "CVaR histórico diario (95%)" in report
```

Add the imports at the top of `tests/test_portfolio.py`:

```python
from quantfolio.risk import historical_cvar, historical_var, max_drawdown, sharpe_ratio
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_portfolio.py::test_portfolio_risk_metrics_match_manual tests/test_portfolio.py::test_report_includes_risk_metrics -v`

Expected: FAIL because the methods and the report rows do not exist.

- [ ] **Step 3: Add the `Portfolio` methods**

In `src/quantfolio/portfolio.py`, import the functions with aliases to avoid the method-name collision:

```python
from quantfolio.risk import (
    historical_cvar,
    historical_var,
    max_drawdown as max_drawdown_of_returns,
    sharpe_ratio as sharpe_ratio_of_returns,
)
```

Add four methods next to `summary()`:

```python
    def max_drawdown(self) -> float:
        """Return the maximum peak-to-trough decline of the portfolio."""
        return max_drawdown_of_returns(self.portfolio_returns())

    def sharpe_ratio(
        self,
        *,
        risk_free_rate: float = 0.0,
        periods_per_year: int = TRADING_DAYS_PER_YEAR,
    ) -> float:
        """Return the annualized Sharpe ratio with an annual risk-free rate."""
        return sharpe_ratio_of_returns(
            self.portfolio_returns(),
            risk_free_rate=risk_free_rate,
            periods_per_year=periods_per_year,
        )

    def value_at_risk(self, *, confidence: float = 0.95) -> float:
        """Return the historical daily VaR at the requested confidence."""
        return historical_var(self.portfolio_returns(), confidence=confidence)

    def conditional_value_at_risk(self, *, confidence: float = 0.95) -> float:
        """Return the historical daily CVaR at the requested confidence."""
        return historical_cvar(self.portfolio_returns(), confidence=confidence)
```

- [ ] **Step 4: Add the report rows**

In `src/quantfolio/reporting.py`, add `risk_free_rate` and `confidence` keyword arguments to `render_portfolio_report` and `Portfolio.report`. In the metrics section, append:

```python
            f"| Máxima caída histórica | {portfolio.max_drawdown():.2%} |",
            f"| Ratio de Sharpe (rf={risk_free_rate:.2%}) | "
            f"{portfolio.sharpe_ratio(risk_free_rate=risk_free_rate, periods_per_year=periods_per_year):.2f} |",
            f"| VaR histórico diario ({confidence:.0%}) | "
            f"{portfolio.value_at_risk(confidence=confidence):.2%} |",
            f"| CVaR histórico diario ({confidence:.0%}) | "
            f"{portfolio.conditional_value_at_risk(confidence=confidence):.2%} |",
```

`render_portfolio_report` reaches six parameters, so `PLR0913` is silenced by the
`"src/quantfolio/reporting.py" = ["PLR0913"]` entry in `[tool.ruff.lint.per-file-ignores]` of
`pyproject.toml` (commented "The report renderer mirrors the public `Portfolio.report` signature."),
not by an inline `# noqa`.

After the table, render the sign note
`_Un VaR o CVaR negativo indica que el cuantil de la cola es una ganancia._`, so a negative VaR or
CVaR is not read as a loss.

Update the `Portfolio.report` docstring and pass the two keywords through.

- [ ] **Step 5: Run the portfolio and reporting tests**

Run: `uv run pytest tests/test_portfolio.py tests/test_reporting.py -v`

Expected: PASS, including the pre-existing report section tests.

- [ ] **Step 6: Run the five global gates and commit**

```bash
git add src/quantfolio/portfolio.py src/quantfolio/reporting.py tests/test_portfolio.py
git commit -m "feat: report drawdown, Sharpe, VaR and CVaR"
```

- [ ] **Step PR: Push and open the pull request**

```bash
git push -u origin feat/report-risk-metrics
gh pr create --fill
```

Expected: the PR's `Quality gates` and `Strict analysis` checks run on the branch. Merge only when both are green.

---

### Task 3: Add sample period, per-asset coverage and return uncertainty

**Files:**
- Modify: `src/quantfolio/reporting.py`
- Test: `tests/test_portfolio.py`

**Interfaces:**
- Consumes: `risk.drift_standard_error`, `Portfolio.summary()`, `Portfolio.get_returns()`, `Portfolio.assets`.
- Produces: two new metric rows (`Error estándar de la rentabilidad anualizada`, `IC 95% de la rentabilidad anualizada`) and a quality-section block with the sample period and a per-asset table.

**Branch:** `feat/report-sample-diagnostics` (cut from `main` after Task 2 merges).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_portfolio.py`:

```python
def test_report_includes_sample_period_and_per_asset_coverage() -> None:
    """The quality section dates the sample and lists every asset."""
    report = build_portfolio().report()

    assert "Periodo de la muestra" in report
    assert "Cobertura por activo" in report
    assert "| AAA | 5 |" in report
    assert "| BBB | 5 |" in report


def test_report_includes_annualized_return_uncertainty() -> None:
    """The report shows the standard error and the 95 % interval."""
    report = build_portfolio().report()

    assert "Error estándar de la rentabilidad anualizada" in report
    assert "IC 95% de la rentabilidad anualizada" in report
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_portfolio.py::test_report_includes_sample_period_and_per_asset_coverage tests/test_portfolio.py::test_report_includes_annualized_return_uncertainty -v`

Expected: FAIL because the labels are absent.

- [ ] **Step 3: Implement the quality block**

In `render_portfolio_report`, after the existing quality bullets, add:

```python
        start = returns.index.min()
        end = returns.index.max()
        years = len(returns) / periods_per_year
        lines.extend(
            [
                f"- Periodo de la muestra: {start:%Y-%m-%d} → {end:%Y-%m-%d}",
                f"- Años de historia: {years:.2f}",
                "",
                "**Cobertura por activo**",
                "",
                "| Activo | Observaciones | Inicio | Fin |",
                "|---|---:|---|---|",
            ]
        )
        lines.extend(
            f"| {ticker} | {len(asset.prices)} | "
            f"{asset.prices.index.min():%Y-%m-%d} | {asset.prices.index.max():%Y-%m-%d} |"
            for ticker, asset in portfolio.assets.items()
        )
```

- [ ] **Step 4: Implement the uncertainty rows**

In the metrics section, after the annualized volatility row, add:

```python
        standard_error = drift_standard_error(returns, periods_per_year=periods_per_year)
        point_estimate = metrics["annualized_return_approx"]
        lower = point_estimate - 1.96 * standard_error
        upper = point_estimate + 1.96 * standard_error
        lines.extend(
            [
                f"| Error estándar de la rentabilidad anualizada | {standard_error:.2%} |",
                f"| IC 95% de la rentabilidad anualizada | {lower:.2%} - {upper:.2%} |",
            ]
        )
```

Import `drift_standard_error` from `quantfolio.risk` at the top of `reporting.py`.

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/test_portfolio.py tests/test_reporting.py -v`

Expected: PASS.

- [ ] **Step 6: Run the five global gates and commit**

```bash
git add src/quantfolio/reporting.py tests/test_portfolio.py
git commit -m "feat: report sample coverage and return uncertainty"
```

- [ ] **Step PR: Push and open the pull request**

```bash
git push -u origin feat/report-sample-diagnostics
gh pr create --fill
```

Expected: the PR's `Quality gates` and `Strict analysis` checks run on the branch. Merge only when both are green.

---

### Task 4: Add high-volatility, drawdown and concentration warnings

**Files:**
- Modify: `src/quantfolio/constants.py`
- Modify: `src/quantfolio/reporting.py`
- Test: `tests/test_portfolio.py`

**Interfaces:**
- Consumes: `Portfolio.summary()`, `Portfolio.max_drawdown()`, `Portfolio.weights`.
- Produces: three new constants and three new warning branches.

**Branch:** `feat/report-risk-warnings` (cut from `main` after Task 2 merges).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_portfolio.py`:

```python
def test_report_warns_about_high_volatility() -> None:
    """A 20 % daily swing is flagged as high volatility."""
    prices = [100.0, 120.0, 100.0, 120.0, 100.0, 120.0]
    portfolio = Portfolio(
        assets={
            "AAA": make_series("AAA", prices),
            "BBB": make_series("BBB", prices),
        },
        weights={"AAA": 0.5, "BBB": 0.5},
    )

    assert "volatilidad anualizada" in portfolio.report()


def test_report_warns_about_deep_drawdown() -> None:
    """A 30 % fall from the peak is flagged."""
    prices = [100.0, 90.0, 80.0, 70.0, 75.0, 80.0]
    portfolio = Portfolio(
        assets={
            "AAA": make_series("AAA", prices),
            "BBB": make_series("BBB", prices),
        },
        weights={"AAA": 0.5, "BBB": 0.5},
    )

    assert "máxima caída" in portfolio.report()


def test_report_warns_about_concentration() -> None:
    """A 99 %/1 % portfolio is concentrated even with two assets."""
    portfolio = Portfolio(
        assets={
            "AAA": make_series("AAA", [10.0, 11.0, 12.0]),
            "BBB": make_series("BBB", [20.0, 19.0, 21.0]),
        },
        weights={"AAA": 0.99, "BBB": 0.01},
    )

    assert "concentra" in portfolio.report()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_portfolio.py::test_report_warns_about_high_volatility tests/test_portfolio.py::test_report_warns_about_deep_drawdown tests/test_portfolio.py::test_report_warns_about_concentration -v`

Expected: FAIL because the warnings are absent.

- [ ] **Step 3: Add the constants**

In `src/quantfolio/constants.py`:

```python
#: Annualized volatility at or above which the report warns about high risk.
HIGH_VOLATILITY_WARNING_THRESHOLD = 0.25

#: Maximum drawdown at or below which the report warns about a deep loss.
DRAWDOWN_WARNING_THRESHOLD = -0.20

#: Largest portfolio weight at or above which the report warns about concentration.
CONCENTRATION_WARNING_THRESHOLD = 0.50
```

- [ ] **Step 4: Add the warning branches**

Pass `metrics` and `max_drawdown` into `_collect_risk_warnings`. After the existing single-asset check, add:

```python
    if metrics["annualized_volatility"] >= HIGH_VOLATILITY_WARNING_THRESHOLD:
        risk_warnings.append(
            f"La volatilidad anualizada es {metrics['annualized_volatility']:.1%}; "
            "la cartera se comporta como un activo de alto riesgo."
        )
    if max_drawdown <= DRAWDOWN_WARNING_THRESHOLD:
        risk_warnings.append(
            f"La máxima caída histórica es {max_drawdown:.1%}; "
            "la simulación puede subestimar episodios de estrés."
        )
    top_ticker, top_weight = max(portfolio.weights.items(), key=lambda item: item[1])
    if len(portfolio.assets) > 1 and top_weight >= CONCENTRATION_WARNING_THRESHOLD:
        risk_warnings.append(
            f"{top_ticker} concentra el {top_weight:.1%} de la cartera; "
            "la diversificación es limitada."
        )
```

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/test_portfolio.py -v`

Expected: PASS, including the existing single-asset and long-history tests.

- [ ] **Step 6: Run the five global gates and commit**

```bash
git add src/quantfolio/constants.py src/quantfolio/reporting.py tests/test_portfolio.py
git commit -m "feat: warn about volatility, drawdown and concentration"
```

- [ ] **Step PR: Push and open the pull request**

```bash
git push -u origin feat/report-risk-warnings
gh pr create --fill
```

Expected: the PR's `Quality gates` and `Strict analysis` checks run on the branch. Merge only when both are green.

---

### Task 5: Reconcile arithmetic return, CAGR and the Monte Carlo log drift

**Files:**
- Modify: `src/quantfolio/reporting.py`
- Test: `tests/test_portfolio.py`

**Interfaces:**
- Consumes: `risk.compound_annual_growth`, `simulation.annualized_log_assumptions`.
- Produces: three new metric rows and an explanatory note.

**Branch:** `feat/report-return-reconciliation` (cut from `main` after Task 2 merges).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_portfolio.py`:

```python
def test_report_includes_geometric_and_log_drift_measures() -> None:
    """The report distinguishes arithmetic, geometric and log-drift growth."""
    prices = [100.0, 101.0, 102.01, 103.0301]
    portfolio = Portfolio(
        assets={
            "AAA": make_series("AAA", prices),
            "BBB": make_series("BBB", prices),
        },
        weights={"AAA": 0.5, "BBB": 0.5},
    )

    report = portfolio.report(periods_per_year=252)
    cagr = 1.01**252 - 1
    log_drift = float(np.log1p(0.01) * 252)

    assert "Rentabilidad geométrica (CAGR)" in report
    assert "Deriva del logaritmo usada por Monte Carlo" in report
    assert "Crecimiento mediano implícito" in report
    assert f"{cagr:.2%}" in report
    assert f"{log_drift:.2%}" in report
    assert f"{np.exp(log_drift) - 1:.2%}" in report
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_portfolio.py::test_report_includes_geometric_and_log_drift_measures -v`

Expected: FAIL because the labels are absent.

- [ ] **Step 3: Implement the three rows**

In `render_portfolio_report`, compute:

```python
    cagr = compound_annual_growth(returns, periods_per_year=periods_per_year)
    log_drift, _ = annualized_log_assumptions(returns, periods_per_year=periods_per_year)
    median_growth = math.exp(log_drift) - 1.0
```

Add to the metrics table:

```python
            f"| Rentabilidad geométrica (CAGR) | {cagr:.2%} |",
            f"| Deriva del logaritmo usada por Monte Carlo | {log_drift:.2%} |",
            f"| Crecimiento mediano implícito (exp(m)-1) | {median_growth:.2%} |",
```

The three rows are inserted after the `IC 95% de la rentabilidad anualizada` row and before the
`Máxima caída histórica` row, which is the order the report renders.

Add a note after the table:

```python
            "",
            "_La simulación usa la deriva del logaritmo; su mediana crece a exp(m)-1, "
            "no a la rentabilidad aritmética._",
```

Import `math`, `compound_annual_growth` and `annualized_log_assumptions`.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_portfolio.py tests/test_reporting.py -v`

Expected: PASS.

- [ ] **Step 5: Run the five global gates and commit**

```bash
git add src/quantfolio/reporting.py tests/test_portfolio.py
git commit -m "feat: reconcile arithmetic, geometric and log-drift returns"
```

- [ ] **Step PR: Push and open the pull request**

```bash
git push -u origin feat/report-return-reconciliation
gh pr create --fill
```

Expected: the PR's `Quality gates` and `Strict analysis` checks run on the branch. Merge only when both are green.

---

### Task 6: Make `.report()` degrade gracefully on tiny samples

**Files:**
- Modify: `src/quantfolio/reporting.py`
- Test: `tests/test_portfolio.py`

**Interfaces:**
- Consumes: `Portfolio.summary()` (which still raises on one return), `Portfolio.alignment_summary()`, `Portfolio.portfolio_returns()`.
- Produces: a report that renders composition, quality and warnings even when metrics are unavailable.

**Branch:** `fix/report-tiny-samples` (cut from `main` after Task 2 merges).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_portfolio.py`:

```python
def test_report_degrades_gracefully_with_one_return() -> None:
    """A two-price portfolio gets a report, not an exception."""
    portfolio = Portfolio(
        assets={
            "AAA": make_series("AAA", [10.0, 11.0]),
            "BBB": make_series("BBB", [20.0, 19.0]),
        },
        weights={"AAA": 0.5, "BBB": 0.5},
    )

    report = portfolio.report()

    assert report.startswith("# Informe de la cartera")
    assert "## 1. Composición" in report
    assert "No hay suficientes observaciones" in report
    assert "## 3. Calidad de los datos" in report
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_portfolio.py::test_report_degrades_gracefully_with_one_return -v`

Expected: FAIL with `ValueError: Se necesitan al menos dos observaciones de rentabilidad.`

- [ ] **Step 3: Guard the metrics section**

In `render_portfolio_report`, validate the arguments upfront, so an invalid call raises before
anything is rendered:

```python
    if periods_per_year < 1:
        msg = "periods_per_year debe ser al menos uno."
        raise ValueError(msg)
    if not 0.0 < confidence < 1.0:
        msg = "confidence debe estar entre 0 y 1."
        raise ValueError(msg)
```

Then wrap the three calls that need at least two returns — `portfolio.summary(...)`,
`portfolio.max_drawdown()` and `_render_metrics_section(...)` — in a single `try`:

```python
    returns = portfolio.portfolio_returns()
    quality = portfolio.alignment_summary()
    metrics: dict[str, float] | None = None
    max_drawdown: float | None = None
    metrics_note = "No hay suficientes observaciones para calcular métricas históricas."
    metrics_lines: list[str] | None = None
    try:
        metrics = portfolio.summary(periods_per_year=periods_per_year)
        max_drawdown = portfolio.max_drawdown()
        metrics_lines = _render_metrics_section(
            portfolio,
            metrics=metrics,
            returns=returns,
            periods_per_year=periods_per_year,
            risk_free_rate=risk_free_rate,
            confidence=confidence,
        )
    except ValueError:
        metrics = None
        max_drawdown = None
    except OverflowError:
        metrics = None
        max_drawdown = None
        metrics_note = "Las métricas no se pueden representar: rentabilidad extrema."
    if metrics_lines is None:
        metrics_lines = ["", "## 2. Métricas históricas", "", metrics_note]
```

`ValueError` covers the short sample (`summary()` needs two returns) and `OverflowError` covers an
extreme return whose CAGR or log drift cannot be represented; both handlers leave the report without
metrics, and the overflow case replaces the default note with the reason. Render `metrics_lines`
where the table used to be, so the `## 3. Calidad de los datos` and `## 4. Advertencias de riesgo`
numbering does not move.

`_collect_risk_warnings` must accept `metrics: dict[str, float] | None` and
`max_drawdown: float | None`; skip the volatility branch when `metrics is None` and the drawdown
branch when `max_drawdown is None`. The short-history warning still fires.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_portfolio.py -v`

Expected: PASS, including `test_summary_requires_two_return_observations` (the `summary()` method still raises).

- [ ] **Step 5: Run the five global gates and commit**

```bash
git add src/quantfolio/reporting.py tests/test_portfolio.py
git commit -m "fix: degrade report gracefully on tiny samples"
```

- [ ] **Step PR: Push and open the pull request**

```bash
git push -u origin fix/report-tiny-samples
gh pr create --fill
```

Expected: the PR's `Quality gates` and `Strict analysis` checks run on the branch. Merge only when both are green.

---

### Task 7: Make mixed-calendar return gaps visible

**Files:**
- Modify: `src/quantfolio/portfolio.py`
- Modify: `src/quantfolio/reporting.py`
- Modify: `README.md`
- Test: `tests/test_portfolio.py`

**Interfaces:**
- Consumes: `Portfolio.get_returns()`.
- Produces:
  - `Portfolio.return_gaps() -> pd.Series[int]`
  - `alignment_summary()` gains `multi_day_returns`, `multi_day_share`, `max_gap_days`.
  - A quality-section line and a warning when `multi_day_share > 0.05`.

**Branch:** `feat/mixed-calendar-diagnostics` (cut from `main` after Task 2 merges).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_portfolio.py`:

```python
def test_return_gaps_reports_calendar_days() -> None:
    """A Friday-to-Monday return spans three calendar days."""
    dates = pd.DatetimeIndex(["2025-01-02", "2025-01-03", "2025-01-06", "2025-01-07"])
    prices = pd.Series([10.0, 11.0, 12.0, 13.0], index=dates)
    portfolio = Portfolio(
        assets={
            "AAA": PriceSeries(ticker="AAA", prices=prices),
            "BBB": PriceSeries(ticker="BBB", prices=prices * 2.0),
        },
        weights={"AAA": 0.5, "BBB": 0.5},
    )

    assert list(portfolio.return_gaps()) == [3, 1]


def test_alignment_summary_reports_multi_day_returns() -> None:
    """The summary counts returns that span more than one calendar day."""
    dates = pd.DatetimeIndex(["2025-01-02", "2025-01-03", "2025-01-06", "2025-01-07"])
    prices = pd.Series([10.0, 11.0, 12.0, 13.0], index=dates)
    portfolio = Portfolio(
        assets={
            "AAA": PriceSeries(ticker="AAA", prices=prices),
            "BBB": PriceSeries(ticker="BBB", prices=prices * 2.0),
        },
        weights={"AAA": 0.5, "BBB": 0.5},
    )

    summary = portfolio.alignment_summary()

    assert summary["multi_day_returns"] == 1
    assert summary["multi_day_share"] == pytest.approx(0.5)
    assert summary["max_gap_days"] == 3


def test_report_warns_about_multi_day_return_intervals() -> None:
    """A portfolio with multi-day return intervals gets an approximation warning."""
    dates = pd.DatetimeIndex(["2025-01-02", "2025-01-03", "2025-01-06", "2025-01-07"])
    prices = pd.Series([10.0, 11.0, 12.0, 13.0], index=dates)
    portfolio = Portfolio(
        assets={
            "AAA": PriceSeries(ticker="AAA", prices=prices),
            "BBB": PriceSeries(ticker="BBB", prices=prices * 2.0),
        },
        weights={"AAA": 0.5, "BBB": 0.5},
    )

    assert "la anualización con 252 o 365 periodos es aproximada" in portfolio.report()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_portfolio.py::test_return_gaps_reports_calendar_days tests/test_portfolio.py::test_alignment_summary_reports_multi_day_returns tests/test_portfolio.py::test_report_warns_about_multi_day_return_intervals -v`

Expected: FAIL because `return_gaps` and the summary keys do not exist.

- [ ] **Step 3: Implement `return_gaps` and extend `alignment_summary`**

In `src/quantfolio/portfolio.py`, add the shared helper next to the dataclass:

```python
def _calendar_gaps(dates: pd.DatetimeIndex) -> pd.Series[int]:
    """Return the calendar-day gaps between consecutive dates."""
    return dates.to_series().diff().dt.days.dropna().astype(int)
```

In `Portfolio`:

```python
    def return_gaps(self) -> pd.Series[int]:
        """Return the calendar-day gaps between consecutive return dates."""
        return _calendar_gaps(pd.DatetimeIndex(self.get_returns().index))
```

In `alignment_summary`, add:

```python
        # The first shared date is the base of the first return, so the return intervals start
        # on the second one; this mirrors ``return_gaps()`` without requiring two returns.
        gaps = _calendar_gaps(pd.DatetimeIndex(common.index[1:]))
        multi_day_returns = int((gaps > 1).sum())
        multi_day_share = float(multi_day_returns / len(gaps)) if len(gaps) else 0.0
        max_gap_days = int(gaps.max()) if len(gaps) else 0
```

and include the three keys in the returned dict. Disjoint calendars therefore report a zero
coverage and zero gap statistics instead of raising.

- [ ] **Step 4: Add the report line and warning**

In the quality section:

```python
            f"- Intervalos entre retornos que abarcan más de un día natural: "
            f"{quality['multi_day_share']:.1%} (máximo {quality['max_gap_days']} días)",
```

In `_collect_risk_warnings`, after the coverage warning:

```python
    if multi_day_share > MULTI_DAY_RETURNS_WARNING_THRESHOLD:
        risk_warnings.append(
            f"El {multi_day_share:.1%} de los intervalos entre retornos abarca "
            "más de un día natural; la anualización con 252 o 365 periodos es aproximada."
        )
```

- [ ] **Step 5: Document the approximation**

Add a bullet to the README "Limitaciones y advertencias" section:

```markdown
- Las carteras que mezclan calendarios (por ejemplo, cripto y acciones) calculan los retornos
  sobre la intersección de fechas; algunos intervalos entre retornos abarcan varios días naturales
  y la anualización con 252 o 365 periodos es aproximada. El informe muestra el porcentaje afectado.
  Una cartera de un solo calendario también puede superar el 5 % porque los fines de semana cuentan
  como días naturales, así que la advertencia describe ese porcentaje medido y no afirma que la
  cartera mezcle calendarios.
```

- [ ] **Step 6: Run the tests**

Run: `uv run pytest tests/test_portfolio.py -v`

Expected: PASS, including the existing coverage warning test.

- [ ] **Step 7: Run the five global gates and commit**

```bash
git add src/quantfolio/portfolio.py src/quantfolio/reporting.py README.md tests/test_portfolio.py
git commit -m "feat: expose mixed-calendar return gaps"
```

- [ ] **Step PR: Push and open the pull request**

```bash
git push -u origin feat/mixed-calendar-diagnostics
gh pr create --fill
```

Expected: the PR's `Quality gates` and `Strict analysis` checks run on the branch. Merge only when both are green.

---

### Task 8: Harden the cache path

**Files:**
- Modify: `src/quantfolio/sources/cache.py`
- Test: `tests/test_sources.py`

**Interfaces:**
- Consumes: `validate_ticker`.
- Produces: `_cache_stem(ticker: str) -> str`, preserving safe names and sanitizing separators.

**Branch:** `fix/cache-path-safety` (cut from `main`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_sources.py`:

```python
def test_cache_sanitizes_tickers_with_separators(tmp_path: Path) -> None:
    """A pair ticker becomes a single safe filename."""
    cached = CachedPriceSource(StubSource(TRADING_DATES), cache_dir=tmp_path)

    cached.get_prices("BTC/USD", "2025-01-02", "2025-02-27")

    path = tmp_path / "stub" / "BTC-USD.csv"
    assert path.exists()
    assert tmp_path in path.parents


def test_cache_rejects_unsafe_ticker_stems(tmp_path: Path) -> None:
    """A ticker that sanitizes to nothing is rejected."""
    cached = CachedPriceSource(StubSource(TRADING_DATES), cache_dir=tmp_path)

    with pytest.raises(ValueError, match="caché"):
        cached.get_prices("../", "2025-01-02", "2025-02-27")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_sources.py::test_cache_sanitizes_tickers_with_separators tests/test_sources.py::test_cache_rejects_unsafe_ticker_stems -v`

Expected: FAIL because the cache path still uses the raw ticker.

- [ ] **Step 3: Implement `_cache_stem`**

In `src/quantfolio/sources/cache.py`:

```python
def _cache_stem(ticker: str) -> str:
    """Return a safe cache filename stem for a ticker."""
    stem = ticker.replace("/", "-").replace("\\", "-").replace("..", "-").strip("-")
    if not stem:
        msg = "El ticker no produce un nombre de caché válido."
        raise ValueError(msg)
    return stem
```

Use it in `get_prices`:

```python
        path = self._cache_dir / _slug(self._source.name) / f"{_cache_stem(symbol)}.csv"
```

Safe tickers keep their name (`AAA.csv`), so the existing cache tests continue to pass.

The cache also writes the requested ticker in a `ticker` column, so a file whose column does not
match the requested ticker is a cache miss. Legacy files without the column are trusted only when
`_cache_stem(ticker) == ticker`, i.e. when the ticker needed no sanitization.

- [ ] **Step 4: Run the source tests**

Run: `uv run pytest tests/test_sources.py -v`

Expected: PASS, including `test_cache_writes_and_reuses_csv`.

- [ ] **Step 5: Run the five global gates and commit**

```bash
git add src/quantfolio/sources/cache.py tests/test_sources.py
git commit -m "fix: keep cache files inside the provider directory"
```

- [ ] **Step PR: Push and open the pull request**

```bash
git push -u origin fix/cache-path-safety
gh pr create --fill
```

Expected: the PR's `Quality gates` and `Strict analysis` checks run on the branch. Merge only when both are green.

---

### Task 9: Fix the single-asset simulation label

**Files:**
- Modify: `src/quantfolio/reporting.py`
- Modify: `src/quantfolio/models.py`
- Modify: `src/quantfolio/portfolio.py`
- Test: `tests/test_reporting.py`

**Interfaces:**
- Consumes: `plot_simulation_paths`.
- Produces: `plot_simulation_paths(..., value_label: str = "Valor de la cartera")`; `PriceSeries.plot_simulation` passes `"Precio"`.

**Branch:** `fix/simulation-price-label` (cut from `main` after Task 2 merges).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_reporting.py`:

```python
def test_series_simulation_uses_the_price_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A single-asset simulation is labelled as a price, not a portfolio."""
    monkeypatch.setattr(plt, "show", lambda: None)
    asset = make_series("AAA", [10.0, 11.0, 12.0, 13.0])
    simulations = asset.simulate_monte_carlo(
        MonteCarloParameters(n_paths=2, horizon=5, seed=1)
    )

    asset.plot_simulation(simulations, max_paths=1)

    assert plt.gcf().axes[0].get_ylabel() == "Precio"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_reporting.py::test_series_simulation_uses_the_price_label -v`

Expected: FAIL because the label is `Valor de la cartera`.

- [ ] **Step 3: Parameterize the label**

In `reporting.py`:

```python
def plot_simulation_paths(
    simulations: pd.DataFrame,
    *,
    max_paths: int = 100,
    value_label: str = "Valor de la cartera",
) -> None:
```

Use `trajectory_axis.set_ylabel(value_label)`.

In `models.py`, `PriceSeries.plot_simulation` calls:

```python
        plot_simulation_paths(simulations, max_paths=max_paths, value_label="Precio")
```

`Portfolio.plot_simulation` keeps the default.

- [ ] **Step 4: Run the reporting tests**

Run: `uv run pytest tests/test_reporting.py -v`

Expected: PASS, including the portfolio label test.

- [ ] **Step 5: Run the five global gates and commit**

```bash
git add src/quantfolio/reporting.py src/quantfolio/models.py src/quantfolio/portfolio.py tests/test_reporting.py
git commit -m "fix: label single-asset simulations as prices"
```

- [ ] **Step PR: Push and open the pull request**

```bash
git push -u origin fix/simulation-price-label
gh pr create --fill
```

Expected: the PR's `Quality gates` and `Strict analysis` checks run on the branch. Merge only when both are green.

---

### Task 10: Pin the notebook end date and re-run every notebook

**Files:**
- Modify: `notebooks/quantfolio_demo.ipynb`
- Modify: `notebooks/portfolio_stocks.ipynb`
- Modify: `notebooks/portfolio_indices.ipynb`
- Modify: `notebooks/portfolio_fixed_income.ipynb`
- Modify: `notebooks/portfolio_crypto.ipynb`
- Create: `tests/test_notebooks.py`

**Interfaces:**
- Consumes: the executed notebooks.
- Produces: `END = "2026-11-06"` in every notebook, `end=END` on every price/macro call, and an offline regression test.

**Branch:** `fix/notebook-end-dates` (cut from `main` after Tasks 2-7 and 9 merge).

- [ ] **Step 1: Write the failing notebook test**

Create `tests/test_notebooks.py`:

```python
"""Offline checks for the committed notebooks."""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

NOTEBOOKS = [
    "notebooks/quantfolio_demo.ipynb",
    "notebooks/portfolio_stocks.ipynb",
    "notebooks/portfolio_indices.ipynb",
    "notebooks/portfolio_fixed_income.ipynb",
    "notebooks/portfolio_crypto.ipynb",
]


@pytest.mark.parametrize("path", NOTEBOOKS)
def test_notebooks_pin_the_end_date_and_have_no_errors(path: str) -> None:
    """Every notebook is deterministic, executed and free of stored tracebacks."""
    notebook = json.loads((ROOT / path).read_text(encoding="utf-8"))
    code_cells = [cell for cell in notebook["cells"] if cell["cell_type"] == "code"]
    sources = "\n".join("".join(cell["source"]) for cell in code_cells)

    assert 'END = "2026-11-06"' in sources
    assert "pd.Timestamp.now()" not in sources
    assert "datetime.now(" not in sources
    assert "date.today(" not in sources
    assert not any(
        output.get("output_type") == "error"
        for cell in code_cells
        for output in cell.get("outputs", [])
    ), path

    call_lines = [
        line
        for line in sources.splitlines()
        if any(token in line for token in (".get_prices(", ".get_many(", ".get_series("))
    ]
    assert call_lines, path
    assert all("end=END" in line for line in call_lines), path
    assert any(cell.get("outputs") for cell in code_cells), path
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_notebooks.py -v`

Expected: FAIL because the demo still uses `pd.Timestamp.now()` and the other notebooks have no `END`.

- [ ] **Step 3: Add the constant and pass `end=END`**

In every notebook constants cell, add:

```python
END = "2026-11-06"
```

Pass `end=END` to every call that accepts it:

- `quantfolio_demo.ipynb`: `yahoo.get_many(STOCKS, ...)`, `yahoo.get_many(INDEXES, ...)`,
  `kraken.get_many(CRYPTO, ...)`, `cached.get_prices(CACHE_SAMPLE, ...)`,
  `cached.get_many(STOCKS + INDEX_ETFS + BONDS, ...)`, `fred.get_series("DGS10", ...)`,
  `fred.get_series("DGS10", ..., as_of="2025-03-14")`.
- `portfolio_stocks.ipynb`, `portfolio_indices.ipynb`, `portfolio_fixed_income.ipynb`:
  `source.get_many(TICKERS, start=START, end=END)` and `fred.get_series("DGS10", start=START, end=END)`.
- `portfolio_crypto.ipynb`: `source.get_many(TICKERS, start=START, end=END)`.

Add one markdown sentence per notebook: "Datos hasta la última sesión disponible anterior a
`END` (2026-11-06)."

- [ ] **Step 4: Execute every notebook from the cache**

```bash
uv run jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.timeout=600 notebooks/portfolio_stocks.ipynb
uv run jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.timeout=600 notebooks/portfolio_indices.ipynb
uv run jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.timeout=600 notebooks/portfolio_fixed_income.ipynb
uv run jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.timeout=600 notebooks/portfolio_crypto.ipynb
uv run jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.timeout=600 notebooks/quantfolio_demo.ipynb
```

Expected: each command exits 0; no traceback; plots embedded. The crypto notebook needs network
for Kraken.

- [ ] **Step 5: Run the notebook test and the five global gates**

Run: `uv run pytest tests/test_notebooks.py -v`

Expected: PASS.

Then run the five global gates. Expected: all exit 0.

- [ ] **Step 6: Commit**

```bash
git add notebooks/portfolio_stocks.ipynb notebooks/portfolio_indices.ipynb notebooks/portfolio_fixed_income.ipynb notebooks/portfolio_crypto.ipynb notebooks/quantfolio_demo.ipynb tests/test_notebooks.py
git commit -m "fix: pin notebook end dates and re-run all notebooks"
```

- [ ] **Step PR: Push and open the pull request**

```bash
git push -u origin fix/notebook-end-dates
gh pr create --fill
```

Expected: the PR's `Quality gates` and `Strict analysis` checks run on the branch. Merge only when both are green.

---

### Task 11: Prune unused runtime dependencies

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`

**Interfaces:**
- Consumes: the import audit (`plotly`, `scikit-learn`, `seaborn`, `openpyxl`, `scipy`, `pyrefly` are not imported).
- Produces: a leaner direct dependency list.

**Branch:** `build/prune-dependencies` (cut from `main`).

- [ ] **Step 1: Remove the unused direct dependencies**

```bash
uv remove plotly scikit-learn seaborn openpyxl scipy pyrefly
```

- [ ] **Step 2: Verify the direct dependency list**

Run: `uv tree --depth 1`

Expected: no `plotly`, `scikit-learn`, `seaborn`, `openpyxl` or `pyrefly` at the top level. `scipy`
may remain as a transitive dependency of another package; that is acceptable.

- [ ] **Step 3: Run the five global gates**

Run the five commands in **Global Constraints**.

Expected: all exit 0. If a gate fails because a package was actually used, re-add only that package
and record why in the commit message.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "build: prune unused runtime dependencies"
```

- [ ] **Step PR: Push and open the pull request**

```bash
git push -u origin build/prune-dependencies
gh pr create --fill
```

Expected: the PR's `Quality gates` and `Strict analysis` checks run on the branch. Merge only when both are green.

---

### Task 12: Update the README claims and document the new report

**Files:**
- Modify: `README.md`
- Modify: `notebooks/quantfolio_demo.ipynb` (markdown cell only)
- Modify: `docs/superpowers/specs/2026-11-06-quantfolio-hardening-design.md`
- Modify: `docs/superpowers/specs/2026-11-06-dedicated-portfolios-design.md`
- Modify: `docs/superpowers/plans/2026-11-06-quantfolio-hardening.md`

**Interfaces:**
- Consumes: Tasks 2–11.
- Produces: user-facing documentation that matches the code, plus a spec and plan that record what
  actually shipped.

**Branch:** `docs/report-and-notebooks` (cut from `main` after Tasks 2-11 merge).

- [ ] **Step 1: Fix the stale claims**

- `README.md:29`: update the branch-coverage figure in the quality bullet to 100 %.
- `README.md:41`: replace the clone placeholder with
  `git clone https://github.com/alejandroperezpujante/quantfolio.git` and the following `cd` with
  `cd quantfolio`, so the directory matches the cloned repository name.
- `README.md:175`: replace the unsanitized cache path with the sanitized layout
  (`data/<proveedor>/<ticker-saneado>.csv`, e.g. `BTC/USD` → `BTC-USD.csv`) and note that the
  original ticker lives in a `ticker` column so two tickers that sanitize to the same stem never
  share prices.
- `README.md:383`: change "correlaciones" to "correlaciones (calculadas en `plots_report`)" or remove
  the word if the sentence still reads correctly.

- [ ] **Step 2: Document the new report content**

In the "Informes" section, add:

```markdown
- El informe incluye, además de la composición y las métricas básicas, la máxima caída
  histórica, el ratio de Sharpe, el VaR y el CVaR históricos al 95 %, la rentabilidad geométrica
  (CAGR), la deriva del logaritmo usada por Monte Carlo y el error estándar de la rentabilidad
  anualizada. `risk_free_rate` y `confidence` son parámetros del método.
- La sección de calidad muestra el periodo de la muestra, los años de historia, la cobertura por
  activo y el porcentaje de intervalos entre retornos que abarcan más de un día natural.
```

- [ ] **Step 3: Document the notebook pinning**

In the "Uso" section, add:

```markdown
Los cuadernos fijan `END = "2026-11-06"` para que sus resultados sean reproducibles; como `END` es
exclusivo, la última sesión incluida es 2026-11-05 en todos los mercados.
```

Update the demo notebook's cache markdown cell to the sanitized layout and the `ticker` column,
without touching code cells, execution counts or stored outputs.

- [ ] **Step 4: Reconcile the design record with the shipped code**

- Hardening spec: "return intervals that span more than one calendar day", the `periods_per_year`
  note for `Portfolio.sharpe_ratio`, `IC 95%`, `largest weight > 50 %`, the disjoint-calendar
  behaviour of `alignment_summary()`, the `ticker` column in the cache section and the notebook test
  scope.
- Hardening plan: drop the unreachable CVaR guard, add `periods_per_year` to `Portfolio.sharpe_ratio`,
  update Task 7 to the shipped `_calendar_gaps` helper and warning text, note the `ticker` column in
  Task 8 and use the shipped Task 10 test.
- Dedicated-portfolios spec: replace the "nested cache path" clause with the sanitized layout while
  keeping the reason the crypto notebook uses the raw `KrakenSource`.

- [ ] **Step 5: Verify the claims**

Scan `README.md`, the two specs and the notebooks for the stale strings replaced in Step 1 and in the
earlier tasks (the superseded coverage figure, the clone placeholder, the mixed-calendar warning
wording, the unsanitized cache path, the spaced `IC 95` label, the `≥ 50 %` concentration threshold
and the old quality label). The scan must return no matches; only the corrected correlation sentence
in the README is allowed to contain "correlaciones".

- [ ] **Step 6: Run the five global gates and commit**

```bash
git add README.md notebooks/quantfolio_demo.ipynb docs/superpowers/specs/2026-11-06-quantfolio-hardening-design.md docs/superpowers/specs/2026-11-06-dedicated-portfolios-design.md docs/superpowers/plans/2026-11-06-quantfolio-hardening.md
git commit -m "docs: document the hardened report and reproducible notebooks"
```

- [ ] **Step PR: Push and open the pull request**

```bash
git push -u origin docs/report-and-notebooks
gh pr create --fill
```

Expected: the PR's `Quality gates` and `Strict analysis` checks run on the branch. Merge only when both are green.

---

### Task 13 (optional): Add `PriceSeries.summary()` with return statistics

**Files:**
- Modify: `src/quantfolio/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Consumes: `quantfolio.risk` from Task 1.
- Produces: `PriceSeries.summary(*, periods_per_year: int = 252) -> dict[str, float]` with
  `mean_daily_return`, `daily_volatility`, `annualized_return_approx`, `annualized_volatility`,
  `max_drawdown` and `sharpe_ratio`.

**Branch:** `feat/price-series-summary` (cut from `main` after Task 1 merges).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_models.py`:

```python
def test_price_series_summary_matches_manual() -> None:
    """A single asset exposes the same return statistics as a portfolio."""
    asset = make_series("TEST", [100.0, 101.0, 102.01, 103.0301])
    returns = asset.prices.pct_change().dropna()

    summary = asset.summary()

    assert summary["mean_daily_return"] == pytest.approx(float(returns.mean()))
    assert summary["annualized_return_approx"] == pytest.approx(float(returns.mean()) * 252)
    assert summary["max_drawdown"] == pytest.approx(max_drawdown(returns))
```

Add the `max_drawdown` import.

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_models.py::test_price_series_summary_matches_manual -v`

Expected: FAIL because `PriceSeries.summary` does not exist.

- [ ] **Step 3: Implement the method**

Compute `returns = self.prices.pct_change().dropna()`, require at least two returns, and return the
six keys. Delegate drawdown and Sharpe to `quantfolio.risk`.

- [ ] **Step 4: Run the model tests and the five global gates**

Run: `uv run pytest tests/test_models.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/quantfolio/models.py tests/test_models.py
git commit -m "feat: add return statistics to PriceSeries"
```

- [ ] **Step PR: Push and open the pull request**

```bash
git push -u origin feat/price-series-summary
gh pr create --fill
```

Expected: the PR's `Quality gates` and `Strict analysis` checks run on the branch. Merge only when both are green.

---

### Task 14: Full verification

**Files:**
- No new files; fix anything the gates reveal.

**Interfaces:**
- Consumes: every merged task.
- Produces: a green `main` and the merged task PRs.

**Branch:** `chore/final-verification` only if a gate requires a change; otherwise run on `main`
after every task PR has merged.

- [ ] **Step 1: Run the five local gates**

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
uv run pytest
uv run pre-commit run --all-files
```

Expected: all exit 0; coverage 100 %.

- [ ] **Step 2: Re-execute every notebook**

Run the five `nbconvert` commands from Task 10. Expected: each exits 0.

- [ ] **Step 3: Check the notebooks for errors**

```bash
uv run python - <<'PY'
import json
from pathlib import Path

for path in sorted(Path("notebooks").glob("*.ipynb")):
    notebook = json.loads(path.read_text(encoding="utf-8"))
    code = [cell for cell in notebook["cells"] if cell["cell_type"] == "code"]
    assert any(cell.get("outputs") for cell in code), f"no output in {path}"
    assert not any(
        output.get("output_type") == "error"
        for cell in code
        for output in cell.get("outputs", [])
    ), f"error output in {path}"
    print(f"{path}: ok")
PY
```

Expected: five `ok` lines.

- [ ] **Step 4: Check the working tree**

Run: `git status --short`

Expected: only intended changes; no `notebooks/data/`, `coverage.xml`, `junit.xml` or scratch files.

- [ ] **Step 5: Open a pull request only if the verification required changes**

If `git status --short` shows changes, create `chore/final-verification`, commit, push and open a
pull request. Otherwise, no branch or PR is needed; the task PRs already carry the changes.

```bash
git switch -c chore/final-verification
git add <changed files>
git commit -m "chore: verify the hardening release"
git push -u origin chore/final-verification
gh pr create --fill
```

Expected: the PR's `Quality gates` and `Strict analysis` checks run on the branch; merge only when
both are green.

---

## Self-review

- **Spec coverage:** 4.5 risk metrics (Tasks 1–2), diagnostics and uncertainty (Task 3), warnings
  (Task 4), return reconciliation (Task 5), tiny samples (Task 6), mixed calendars (Task 7), cache
  (Task 8), labels (Task 9), notebooks (Task 10), dependencies (Task 11), docs (Task 12), 4.3
  asset statistics (Task 13). Group composition and presentation are in the spec's non-code
  actions.
- **Step scan:** every step names the file, the test or the command; no "handle edge cases" or
  "add validation" placeholders.
- **Branch protocol:** every task has a named, descriptive branch, a base, a commit and a PR step;
  no branch is reused, and dependent tasks name their prerequisite in the base column.
- **Type consistency:** `Portfolio.report` and `render_portfolio_report` use the same keyword names
  (`risk_free_rate`, `confidence`); `plot_simulation_paths` uses `value_label` in both callers;
  `_cache_stem` is the only cache filename helper.
- **Review Focus:** the five failure modes have tests in Tasks 6, 7, 4, 4 and 8 respectively.
- **Proportion:** the plan is longer than the spec because the repository's strict gates require
  exact tests and interfaces; the code blocks are signatures, assertions and exact labels, not
  full implementations.
