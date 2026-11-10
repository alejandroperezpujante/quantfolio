"""Committed notebooks execute offline and keep their reproducible presentation policy."""

from __future__ import annotations

import json
import socket
from typing import TYPE_CHECKING

import matplotlib.pyplot as plt
import pytest

from tests.support.notebooks import (
    NOTEBOOKS,
    code_cells,
    execute_notebook,
    install_notebook_transports,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def _offline_notebook_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove network access, Alpha Vantage credentials and interactive plotting."""
    monkeypatch.delenv("ALPHA_VANTAGE_API_KEY", raising=False)
    monkeypatch.setattr(plt, "show", lambda: None)

    def blocked(*_args: object, **_kwargs: object) -> None:
        msg = "Los cuadernos no pueden acceder a la red durante las pruebas."
        raise AssertionError(msg)

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)


@pytest.mark.parametrize("path", NOTEBOOKS, ids=lambda path: path.stem)
def test_notebook_executes_all_cells_offline(
    path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every notebook completes with deterministic provider fakes and a temp cache."""
    install_notebook_transports(monkeypatch)
    monkeypatch.chdir(tmp_path)

    namespace = execute_notebook(path)

    assert namespace["END"] == "2026-11-06"
    assert "portfolio" in namespace
    assert plt.get_fignums()
    plt.close("all")


@pytest.mark.parametrize("path", NOTEBOOKS, ids=lambda path: path.stem)
def test_notebook_format_is_pinned_and_free_of_stored_errors(path: Path) -> None:
    """Notebooks keep a fixed horizon, omit wall-clock dates and store successful outputs."""
    cells = code_cells(path)
    sources = "\n".join("".join(cell["source"]) for cell in cells)

    assert 'END = "2026-11-06"' in sources
    assert "pd.Timestamp.now()" not in sources
    assert "datetime.now(" not in sources
    assert "date.today(" not in sources
    assert not any(
        output.get("output_type") == "error" for cell in cells for output in cell.get("outputs", [])
    ), path
    assert any(cell.get("outputs") for cell in cells), path

    notebook = json.loads(path.read_text(encoding="utf-8"))
    assert notebook["nbformat"] >= 4
