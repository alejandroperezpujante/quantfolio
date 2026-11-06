"""Offline checks for the committed notebooks."""

import json
from pathlib import Path

import pytest

NOTEBOOKS = [
    "notebooks/quantfolio_demo.ipynb",
    "notebooks/portfolio_stocks.ipynb",
    "notebooks/portfolio_indices.ipynb",
    "notebooks/portfolio_fixed_income.ipynb",
    "notebooks/portfolio_crypto.ipynb",
]


@pytest.mark.parametrize("path", NOTEBOOKS)
def test_notebooks_pin_the_end_date_and_have_no_errors(path: str) -> None:
    """Every notebook is deterministic and free of stored tracebacks."""
    notebook = json.loads(Path(path).read_text(encoding="utf-8"))
    code_cells = [cell for cell in notebook["cells"] if cell["cell_type"] == "code"]
    sources = "\n".join("".join(cell["source"]) for cell in code_cells)

    assert 'END = "2026-11-06"' in sources
    assert "pd.Timestamp.now()" not in sources
    assert not any(
        output.get("output_type") == "error"
        for cell in code_cells
        for output in cell.get("outputs", [])
    ), path
