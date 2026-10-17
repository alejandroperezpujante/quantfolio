"""Tests for the price-series model."""

from typing import cast

import numpy as np
import pandas as pd
import pytest

from quantfolio.models import PriceSeries, clean_numeric_series
from quantfolio.simulation import MonteCarloParameters
from tests.helpers import TRADING_DATES, make_prices, make_series


def test_price_series_cleans_invalid_prices() -> None:
    """Missing, non-numeric and non-positive prices are dropped."""
    prices = pd.Series(
        [10.0, np.nan, -5.0, 0.0, 20.0, "bad"],
        index=TRADING_DATES[:6],
    )
    asset = PriceSeries(ticker="TEST", prices=cast("pd.Series[float]", prices))

    assert len(asset.prices) == 2
    assert (asset.prices > 0).all()


def test_price_series_sorts_and_deduplicates_dates() -> None:
    """The index is sorted and duplicated dates keep the last observation."""
    index = TRADING_DATES[[2, 0, 1, 2]]
    prices = pd.Series([13.0, 11.0, 12.0, 14.0], index=index)

    asset = PriceSeries(ticker="TEST", prices=prices)

    assert asset.prices.index.is_monotonic_increasing
    assert len(asset.prices) == 3
    assert asset.prices.iloc[2] == pytest.approx(14.0)


def test_price_series_drops_timezone_information() -> None:
    """Timezone-aware indexes are converted to timezone-naive timestamps."""
    index = pd.date_range("2025-01-01", periods=3, tz="UTC")
    asset = PriceSeries(ticker="TEST", prices=pd.Series([1.0, 2.0, 3.0], index=index))

    assert isinstance(asset.prices.index, pd.DatetimeIndex)
    assert asset.prices.index.tz is None


def test_price_series_computes_automatic_statistics() -> None:
    """Mean and sample standard deviation are computed on instantiation."""
    asset = PriceSeries(ticker="TEST", prices=make_prices([10.0, 12.0, 14.0]))

    assert asset.mean_price == pytest.approx(12.0)
    assert asset.std_price == pytest.approx(2.0)


def test_price_series_single_observation_has_zero_std() -> None:
    """A single observation reports zero dispersion."""
    asset = make_series("TEST", [10.0])

    assert asset.std_price == 0.0


def test_price_series_rejects_empty_ticker() -> None:
    """Whitespace-only tickers are rejected."""
    prices = make_prices([10.0])

    with pytest.raises(ValueError, match="ticker"):
        PriceSeries(ticker="   ", prices=prices)


def test_price_series_rejects_empty_series() -> None:
    """Empty price series are rejected."""
    prices = cast("pd.Series[float]", pd.Series([], dtype=float))

    with pytest.raises(ValueError, match="vacía"):
        PriceSeries(ticker="TEST", prices=prices)


def test_price_series_rejects_non_datetime_index() -> None:
    """Price series must be indexed by date."""
    prices = pd.Series([10.0, 11.0], dtype=float)

    with pytest.raises(TypeError, match="DatetimeIndex"):
        PriceSeries(ticker="TEST", prices=prices)


def test_price_series_rejects_non_series_prices() -> None:
    """The prices argument must be a pandas Series."""
    prices = cast("pd.Series[float]", [10.0, 11.0])

    with pytest.raises(TypeError, match=r"pandas\.Series"):
        PriceSeries(ticker="TEST", prices=prices)


def test_price_series_rejects_series_without_valid_prices() -> None:
    """A series with only non-positive values is rejected."""
    prices = pd.Series([-1.0, 0.0], index=TRADING_DATES[:2])

    with pytest.raises(ValueError, match="positivos"):
        PriceSeries(ticker="TEST", prices=prices)


def test_price_series_simulation_requires_two_prices() -> None:
    """Monte Carlo simulation needs at least two observations."""
    asset = make_series("TEST", [10.0])

    with pytest.raises(ValueError, match="dos precios"):
        asset.simulate_monte_carlo()


def test_price_series_simulation_starts_at_the_last_price() -> None:
    """Asset simulations default to the last observed price."""
    asset = make_series("TEST", [10.0, 11.0, 12.0, 13.0])

    simulations = asset.simulate_monte_carlo(MonteCarloParameters(n_paths=3, horizon=5, seed=42))

    assert simulations.shape == (6, 3)
    assert (simulations.iloc[0] == 13.0).all()


def test_price_series_simulation_honours_explicit_assumptions() -> None:
    """Explicit assumptions override the historical estimates."""
    asset = make_series("TEST", [10.0, 11.0, 12.0, 13.0])

    simulations = asset.simulate_monte_carlo(
        MonteCarloParameters(
            n_paths=2,
            horizon=252,
            initial_value=100.0,
            return_assumption=0.1,
            volatility_assumption=0.0,
            seed=1,
        )
    )

    expected = 100.0 * np.exp(0.1)
    assert simulations.iloc[-1, 0] == pytest.approx(expected)


def test_clean_numeric_series_keeps_negative_values_by_default() -> None:
    """Macro-style series may legitimately contain negative values."""
    values = pd.Series([-0.5, 0.25, np.nan], index=TRADING_DATES[:3])

    cleaned = clean_numeric_series(values)

    assert list(cleaned) == [-0.5, 0.25]
