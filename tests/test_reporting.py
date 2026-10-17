"""Tests for the reporting and plotting helpers."""

from typing import TYPE_CHECKING

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from quantfolio.portfolio import Portfolio
from quantfolio.reporting import plot_portfolio_report, plot_simulation_paths
from quantfolio.simulation import MonteCarloParameters
from tests.helpers import make_series

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(autouse=True)
def _close_figures() -> Iterator[None]:
    """Close every figure after each test to keep the suite headless."""
    yield
    plt.close("all")


def _build_portfolio() -> Portfolio:
    """Return a two-asset portfolio suitable for plotting."""
    return Portfolio(
        assets={
            "AAA": make_series("AAA", [10.0 + position for position in range(10)]),
            "BBB": make_series("BBB", [20.0 + position for position in range(10)]),
        },
        weights={"AAA": 0.5, "BBB": 0.5},
    )


def test_plot_portfolio_report_runs_headless(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The analytical dashboard renders without a display."""
    monkeypatch.setattr(plt, "show", lambda: None)

    plot_portfolio_report(_build_portfolio())

    assert plt.get_fignums()


def test_plot_simulation_paths_runs_headless(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Simulation charts render without a display."""
    monkeypatch.setattr(plt, "show", lambda: None)
    simulations = pd.DataFrame(np.linspace(100.0, 120.0, 30).reshape(6, 5))

    plot_simulation_paths(simulations, max_paths=3)

    assert plt.get_fignums()


def test_plot_simulation_paths_rejects_empty_frames() -> None:
    """An empty simulation matrix cannot be plotted."""
    with pytest.raises(ValueError, match="simulaciones"):
        plot_simulation_paths(pd.DataFrame())


def test_plot_simulation_paths_rejects_non_positive_max_paths() -> None:
    """The number of drawn trajectories must be positive."""
    with pytest.raises(ValueError, match="max_paths"):
        plot_simulation_paths(pd.DataFrame(np.ones((3, 2))), max_paths=0)


def test_portfolio_and_series_plot_delegates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The public plot methods delegate to the reporting helpers."""
    monkeypatch.setattr(plt, "show", lambda: None)
    portfolio = _build_portfolio()
    simulations = portfolio.simulate_monte_carlo(
        MonteCarloParameters(n_paths=4, horizon=5, seed=42)
    )

    portfolio.plots_report()
    portfolio.plot_simulation(simulations, max_paths=2)
    portfolio.assets["AAA"].plot_simulation(simulations, max_paths=2)

    assert len(plt.get_fignums()) == 3
