"""Offline checks for the committed notebooks."""

import json
from pathlib import Path

import pytest

import quantfolio

ROOT = Path(__file__).resolve().parents[1]

NOTEBOOKS = [
    "notebooks/quantfolio_demo.ipynb",
    "notebooks/portfolio_stocks.ipynb",
    "notebooks/portfolio_indices.ipynb",
    "notebooks/portfolio_fixed_income.ipynb",
    "notebooks/portfolio_crypto.ipynb",
    "notebooks/portfolio_multi_currency.ipynb",
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
        if "portfolio.get_prices(" not in line
        and any(token in line for token in (".get_prices(", ".get_many(", ".get_series("))
    ]
    assert call_lines, path
    assert all("end=END" in line for line in call_lines), path
    assert any(cell.get("outputs") for cell in code_cells), path


def test_currency_models_are_exported_from_the_public_api() -> None:
    """Currency conversion types and the ECB source are importable from quantfolio."""
    for name in ("ECBExchangeRateSource", "ExchangeRateObservation", "ExchangeRates"):
        assert name in quantfolio.__all__
        assert getattr(quantfolio, name)


def test_multi_currency_notebook_demonstrates_ecb_and_manual_rates() -> None:
    """The notebook compares mixed local currencies, ECB rates and manual rates."""
    path = ROOT / "notebooks/portfolio_multi_currency.ipynb"
    assert path.is_file()
    notebook = json.loads(path.read_text(encoding="utf-8"))
    code_cells = [cell for cell in notebook["cells"] if cell["cell_type"] == "code"]
    sources = "\n".join("".join(cell["source"]) for cell in code_cells)

    assert "ECBExchangeRateSource()" in sources
    assert 'ecb_source.get_prices("FX:EUR/USD"' in sources
    assert 'ticker="FX:USD/EUR"' in sources
    assert 'quote_currency="USD"' in sources
    assert 'reporting_currency="EUR"' in sources
    assert ".get_reporting_prices()" in sources
    assert ".pct_change()" in sources
    assert 'END = "2026-11-06"' in sources
    assert any(cell.get("outputs") for cell in code_cells)


def test_unified_demo_uses_auto_portfolio() -> None:
    """The unified demo delegates portfolio setup to AutoPortfolio."""
    path = ROOT / "notebooks/quantfolio_demo.ipynb"
    notebook = json.loads(path.read_text(encoding="utf-8"))
    sources = "\n".join(
        "".join(cell["source"]) for cell in notebook["cells"] if cell["cell_type"] == "code"
    )
    assert "AutoPortfolio(" in sources
    assert "AutoPortfolioConfig(" in sources
    assert 'reporting_currency="EUR"' in sources
    assert "ExchangeRates.from_source(" not in sources
