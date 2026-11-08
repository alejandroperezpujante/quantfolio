"""Test configuration: force a headless matplotlib backend."""

import os

os.environ.setdefault("MPLBACKEND", "Agg")


import pytest


@pytest.fixture(autouse=True)
def mock_yahoo_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep Yahoo metadata calls offline unless a test supplies its own response."""
    monkeypatch.setattr("yfinance.Ticker.get_history_metadata", lambda *_args, **_kwargs: {})
