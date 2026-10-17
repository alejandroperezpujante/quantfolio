# AGENTS.md

Read this before doing anything in this repository.

## Purpose

This repository hosts **Quantfolio**, the implementation of the B1-T1 assignment (toolkit for
multi-source market-data ingestion, price-series analysis and portfolio management with Monte
Carlo simulation). The assignment text lives in `docs/assignment/`.

The research-only constraint from the original scaffold has been retired by team decision: the
repository now contains the toolkit implementation, its tests and its documentation.

## Layout rules

- `src/quantfolio/` holds **library code only**: importable, typed, tested modules. No demo
  scripts, hardcoded tickers, sample weights or `print`-driven flows.
- `notebooks/` holds **all runnable entry points and reproducible demos** (notebooks are the
  deliverable entry point). Any new end-to-end example belongs there.
- `tests/` holds the test suite. Tests must not hit the network: mock every provider call.
- `docs/` holds background research and project documentation (including the architecture
  diagram); `docs/README.md` indexes it.
- Scripts, scratch files and datasets are not committed; the CSV cache is gitignored.

## Environment

- Python 3.14, managed exclusively with `uv`. Do not use pip, conda, or poetry.
- `.python-version` pins 3.14; `pyproject.toml` requires `>=3.14`. Do not raise the target
  to a pre-release Python without explicit instruction.
- Add dependencies with `uv add <pkg>` and `uv add --dev <pkg>`.
- Runtime libraries available: numpy, pandas, matplotlib, seaborn, scipy, scikit-learn, plotly,
  openpyxl, jupyter and yfinance.

## Quality gates (must pass before any commit)

- `uv run ruff check .`
- `uv run ruff format .`
- `uv run mypy src`
- `uv run pytest`
- `uv run pre-commit run --all-files`

Pre-commit hooks are installed; do not bypass them with `--no-verify`.

## Conventions

- Docstrings and code comments are written in **English** (Google style, as in the scaffold).
- User-facing text is written in **Spanish**: exception messages, Markdown reports, plot labels
  and `print` output in notebooks.
- Public API is re-exported from `src/quantfolio/__init__.py`; keep `__all__` sorted.
- New market-data providers must implement the `quantfolio.sources.PriceSource` contract and
  emit the same internal objects as the existing providers.
- Mathematical formulas in Markdown use LaTeX: `$...$` inline and `$$...$$` for display blocks.
