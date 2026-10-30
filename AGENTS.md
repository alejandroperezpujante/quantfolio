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

## SonarQube analysis

The project is analysed by the team's SonarQube instance under its strictest configuration: the `Python Strict`
and `IPython Strict` quality profiles (every analyzer rule active; the only exemptions are `python:S1722`
new-style-classes and, for notebooks only, `ipython:S113`, both documented in the README) and the
`Quantfolio Strict` quality gate (zero issues, 100 % coverage, 0 % duplication, A/A/A ratings, on both overall
and new code).

```console
uv run pytest          # writes coverage.xml and junit.xml, consumed by the analyzer
source ~/.config/sonar/quantfolio.env  # SONAR_HOST_URL + SONAR_TOKEN (never committed)
sonar-scanner          # analyzes src/ + notebooks/ + tests/; fails when the gate is not green
```

`sonar-project.properties` holds the project settings; server URL and token come from the environment.

CI: `.github/workflows/ci.yml` runs on every pull request and on every push to `main`. Its `Quality gates` job
runs the five local gates and uploads the `test-report` artifact (`coverage.xml`, `junit.xml`,
`test-report/test-summary.json`); the reusable `.github/workflows/sonarqube.yml` is then called with those
reports, joins the tailnet as an ephemeral `tag:ci` node and fails the run when the strict quality gate is not
green. Required repository secrets/variables: `TS_OAUTH_CLIENT_ID` and `TS_OAUTH_SECRET` (Tailscale OAuth
client), `SONAR_TOKEN` (secret) and `SONAR_HOST_URL` (variable); the three secrets must also exist as Dependabot
secrets so its pull requests can run the analysis. Keep those names in sync if the workflows change.

## The `main` branch is protected

Direct pushes to `main` are rejected for everyone, administrators included: every change reaches the branch
through a pull request whose required status checks — `Quality gates` and `Strict analysis` — must pass on the
exact revision being merged (branch protection also requires the branch to be up to date with `main`). No
approving review is required, so either contributor can merge their own pull request once both checks are
green. Every run leaves evidence: a step summary, downloadable artifacts (`test-report`, `sonar-report`) and a
summary comment on the pull request. Never use `git push origin main`; open a branch and a pull request
instead.

## Dependabot auto-merge

Patch and minor Dependabot updates arm auto-merge themselves (`.github/workflows/dependabot-automerge.yml`):
once `Quality gates` and `Strict analysis` are green on the revision, they merge without a human. Any pull request
whose highest change is a major version is never armed and stays open for review. After every merge into `main` the
workflow updates the branches of the armed pull requests that fell behind, because branch protection requires
`main` to be up to date; it also repeats that sweep hourly, because a merge that the workflow armed does not
trigger a `push` run.

## Conventions

- Docstrings and code comments are written in **English** (Google style, as in the scaffold).
- User-facing text is written in **Spanish**: exception messages, Markdown reports, plot labels
  and `print` output in notebooks.
- Public API is re-exported from `src/quantfolio/__init__.py`; keep `__all__` sorted.
- New market-data providers must implement the `quantfolio.sources.PriceSource` contract and
  emit the same internal objects as the existing providers.
- Mathematical formulas in Markdown use LaTeX: `$...$` inline and `$$...$$` for display blocks.
