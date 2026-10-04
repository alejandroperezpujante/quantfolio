"""Smoke tests for the scaffold module, exercising the src-layout import path."""

from typing import TYPE_CHECKING, cast

import yfinance as yf  # type: ignore[import-untyped]

from quantfolio import add
from quantfolio.example import add as add_direct

if TYPE_CHECKING:
    import pandas as pd  # type: ignore[import-untyped]


def get_latest_nvidia_stock(period: str = "1mo") -> pd.DataFrame:
    """Return recent NVIDIA (``NVDA``) daily price history.

    The most recent trading day is the final row, so ``result.iloc[-1]`` is the
    latest available quote. This is an environment smoke-test helper: it exercises
    live market-data access (``yfinance``) and plotting, and is deliberately kept
    out of the ``quantfolio`` package itself.

    Args:
        period: Look-back window understood by ``yfinance``, for example ``"1mo"``,
            ``"3mo"`` or ``"1y"``.

    Returns:
        Daily open/high/low/close/volume rows indexed by date, oldest first.

    """
    ticker = yf.Ticker("NVDA")
    return cast("pd.DataFrame", ticker.history(period=period, auto_adjust=True))


def test_add_is_reexported() -> None:
    """``quantfolio.add`` re-exports the example implementation."""
    assert add(2, 3) == 5


def test_add_direct_import() -> None:
    """The example module is importable directly and computes a sum."""
    assert add_direct(-4, 10) == 6
