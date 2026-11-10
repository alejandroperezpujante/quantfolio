"""End-to-end mixed-currency AutoPortfolio workflow through public APIs."""

from __future__ import annotations

from typing import TYPE_CHECKING

import matplotlib.pyplot as plt
import pandas as pd
import pytest

from quantfolio import AutoPortfolio, AutoPortfolioConfig, MonteCarloParameters
from quantfolio.sources import KrakenSource, YahooFinanceSource
from tests.support.builders import make_series
from tests.support.sources import table_source
from tests.support.transports import install_ecb, install_yahoo

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


@pytest.fixture(autouse=True)
def _close_figures(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Keep the workflow headless and release matplotlib state between runs."""
    monkeypatch.setattr(plt, "show", lambda: None)
    yield
    plt.close("all")


def _workflow_dates() -> pd.DatetimeIndex:
    """Return a short but complete business-day calendar around the requested window."""
    return pd.bdate_range("2024-12-20", "2025-01-17")


def test_mixed_currency_autoportfolio_routes_falls_back_caches_and_analyses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The public workflow composes providers, EUR conversion, diagnostics and simulation."""
    dates = _workflow_dates()
    install_yahoo(
        monkeypatch,
        {
            "AAPL": pd.Series(
                [100.0 + position for position in range(len(dates))],
                index=dates,
                dtype=float,
            ),
            "SAN.MC": pd.Series(
                [50.0 + position / 2.0 for position in range(len(dates))],
                index=dates,
                dtype=float,
            ),
        },
        currencies={"AAPL": "USD", "SAN.MC": "EUR"},
    )
    install_ecb(monkeypatch, pd.Series(1.1, index=dates))

    alpha = table_source(
        "Alpha",
        {
            "CRYPTO:BTC/USD": make_series(
                "CRYPTO:BTC/USD",
                [1000.0 + position for position in range(len(dates))],
                dates=dates,
                source="Alpha",
                quote_currency="USD",
            )
        },
    )

    def unavailable_kraken(url: str, timeout: int = 30) -> None:
        del url, timeout
        msg = "sin conexión"
        raise ValueError(msg)

    monkeypatch.setattr("quantfolio.sources.kraken.urlopen", unavailable_kraken)
    config = AutoPortfolioConfig(
        weights={"AAPL": 0.4, "SAN.MC": 0.3, "BTC/USD": 0.3},
        start="2025-01-02",
        end="2025-01-16",
        reporting_currency="EUR",
        sources={
            "yahoo": YahooFinanceSource(),
            "kraken": KrakenSource(),
            "alpha-vantage": alpha,
        },
        cache_dir=tmp_path / "cache",
    )

    with pytest.warns(RuntimeWarning, match="Alpha"):
        portfolio = AutoPortfolio(config)

    assert portfolio.weights == {"AAPL": 0.4, "SAN.MC": 0.3, "BTC/USD": 0.3}
    assert portfolio.assets["BTC/USD"].source == "Alpha"
    reporting = portfolio.get_reporting_prices()
    assert reporting["AAPL"].iloc[0] == pytest.approx(portfolio.assets["AAPL"].prices.iloc[0] / 1.1)
    assert reporting["BTC/USD"].iloc[0] == pytest.approx(
        portfolio.assets["BTC/USD"].prices.iloc[0] / 1.1
    )
    assert reporting["SAN.MC"].iloc[0] == pytest.approx(portfolio.assets["SAN.MC"].prices.iloc[0])

    diagnostics = portfolio.analysis_currency_conversion_diagnostics()
    converted = diagnostics[diagnostics["asset"] == "AAPL"]
    identity = diagnostics[diagnostics["asset"] == "SAN.MC"]
    assert set(converted["pair"]) == {"FX:EUR/USD"}
    assert set(converted["source"]) == {"ECB reference rates"}
    assert set(identity["pair"]) == {"-"}
    assert set(identity["source"]) == {"No requerida"}

    report = portfolio.report(risk_free_rate=0.02)
    assert "## 1. Composición" in report
    assert "## 2. Métricas históricas" in report
    assert "Conversión de divisas" in report
    assert "FX:EUR/USD" in report

    portfolio.plots_report()
    assert plt.get_fignums()

    parameters = MonteCarloParameters(n_paths=4, horizon=5, seed=42)
    first = portfolio.simulate_monte_carlo(parameters)
    second = portfolio.simulate_monte_carlo(parameters)
    assert first.shape == (6, 4)
    pd.testing.assert_frame_equal(first, second)

    with pytest.warns(RuntimeWarning, match="Alpha"):
        cached = AutoPortfolio(config)
    assert cached.assets["AAPL"].source == "Yahoo Finance (cache)"
    assert cached.assets["BTC/USD"].source == "Alpha (cache)"
    assert cached.get_reporting_prices()["AAPL"].iloc[0] == pytest.approx(
        cached.assets["AAPL"].prices.iloc[0] / 1.1
    )
