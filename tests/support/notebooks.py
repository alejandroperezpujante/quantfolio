"""Offline execution and shared transport fixtures for committed notebooks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd

from tests.support.transports import (
    install_ecb,
    install_fred,
    install_kraken,
    install_yahoo,
    kraken_pair,
    notebook_macro_series,
    notebook_yahoo_series,
)

if TYPE_CHECKING:
    import pytest

ROOT = Path(__file__).resolve().parents[2]

NOTEBOOKS = (
    ROOT / "notebooks/quantfolio_demo.ipynb",
    ROOT / "notebooks/portfolio_stocks.ipynb",
    ROOT / "notebooks/portfolio_indices.ipynb",
    ROOT / "notebooks/portfolio_fixed_income.ipynb",
    ROOT / "notebooks/portfolio_crypto.ipynb",
    ROOT / "notebooks/portfolio_multi_currency.ipynb",
)

YAHOO_CURRENCIES = {
    "AAPL": "USD",
    "JPM": "USD",
    "JNJ": "USD",
    "XOM": "USD",
    "WMT": "USD",
    "SPY": "USD",
    "QQQ": "USD",
    "IWM": "USD",
    "EFA": "USD",
    "EEM": "USD",
    "SHY": "USD",
    "IEF": "USD",
    "TLT": "USD",
    "LQD": "USD",
    "HYG": "USD",
    "SAN.MC": "EUR",
    "IEGA.AS": "EUR",
    "^GSPC": "USD",
    "^IBEX": "EUR",
}

KRAKEN_TICKERS = ("BTC/USD", "ETH/USD", "SOL/USD", "ADA/USD")


def code_cells(path: Path) -> list[dict[str, Any]]:
    """Return the code cells of a notebook in document order."""
    notebook = json.loads(path.read_text(encoding="utf-8"))
    return [cell for cell in notebook["cells"] if cell["cell_type"] == "code"]


def execute_notebook(path: Path) -> dict[str, object]:
    """Compile and execute every code cell in one fresh notebook namespace."""
    namespace: dict[str, object] = {"__name__": "__main__"}
    for position, cell in enumerate(code_cells(path)):
        source = "".join(cell["source"])
        filename = f"{path.name}:cell-{position}"
        exec(compile(source, filename, "exec"), namespace)  # noqa: S102
    return namespace


def install_notebook_transports(monkeypatch: pytest.MonkeyPatch) -> None:
    """Install deterministic Yahoo, Kraken, FRED and ECB responses for notebooks."""
    base = notebook_yahoo_series()
    yahoo_prices = {
        ticker: base + offset * 5.0 for offset, ticker in enumerate(sorted(YAHOO_CURRENCIES))
    }
    install_yahoo(monkeypatch, yahoo_prices, currencies=YAHOO_CURRENCIES)

    crypto_prices = {
        kraken_pair(ticker): base * (1.0 + offset / 10.0)
        for offset, ticker in enumerate(KRAKEN_TICKERS)
    }
    install_kraken(
        monkeypatch,
        crypto_prices,
        market_names={kraken_pair(ticker): ticker for ticker in KRAKEN_TICKERS},
    )

    fred_prices = {
        "DGS10": notebook_macro_series() / 75.0 + 0.5,
        "CPIAUCNS": pd.Series(
            [300.0 * (1.002**position) for position in range(23)],
            index=pd.date_range("2024-12-01", periods=23, freq="MS"),
            dtype=float,
        ),
    }
    install_fred(monkeypatch, fred_prices, vintages={"DGS10": pd.Timestamp("2025-03-14").date()})
    install_ecb(monkeypatch, base / 100.0 + 0.5)
