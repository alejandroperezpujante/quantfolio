"""Observable behaviour of price and macro series models."""

import math
from typing import cast

import numpy as np
import pandas as pd
import pytest

from quantfolio.macro import MacroSeries
from quantfolio.models import PriceSeries, clean_numeric_series
from quantfolio.risk import max_drawdown, sharpe_ratio
from quantfolio.simulation import MonteCarloParameters
from tests.support.builders import TRADING_DATES, make_prices, make_series


def test_price_cleaning_drops_invalid_values_sorts_and_keeps_the_last_duplicate() -> None:
    """Price construction returns a numeric, chronological and positive series."""
    duplicate_index = TRADING_DATES[[2, 0, 1, 2, 3, 4]]
    raw = pd.Series([13.0, np.nan, 12.0, 14.0, -1.0, "bad"], index=duplicate_index)
    asset = PriceSeries(ticker="TEST", prices=cast("pd.Series[float]", raw))

    assert list(asset.prices) == [12.0, 14.0]
    assert asset.prices.index.is_monotonic_increasing
    assert asset.prices.name == "TEST"


def test_price_statistics_sort_and_remove_timezone_information() -> None:
    """Mean and sample dispersion are computed on a timezone-naive calendar."""
    index = pd.date_range("2025-01-01", periods=3, tz="UTC")
    asset = PriceSeries(ticker="TEST", prices=pd.Series([10.0, 12.0, 14.0], index=index))

    assert pd.DatetimeIndex(asset.prices.index).tz is None
    assert asset.mean_price == pytest.approx(12.0)
    assert asset.std_price == pytest.approx(2.0)
    assert make_series("ONE", [10.0]).std_price == 0.0


def test_clean_numeric_series_keeps_signed_values_by_default() -> None:
    """The general cleaner is not restricted to positive market prices."""
    values = clean_numeric_series(pd.Series([1.0, -2.0, math.nan], index=TRADING_DATES[:3]))

    assert list(values) == [1.0, -2.0]


def test_price_series_rejects_invalid_container_shapes() -> None:
    """Ticker, Series, calendar and usable-price requirements fail explicitly."""
    valid_prices = make_prices([10.0])
    empty_prices = cast("pd.Series[float]", pd.Series([], dtype=float))
    undated_prices = pd.Series([10.0, 11.0])
    wrong_container = cast("pd.Series[float]", [10.0])
    non_positive = pd.Series([-1.0, 0.0], index=TRADING_DATES[:2])
    with pytest.raises(ValueError, match="ticker"):
        PriceSeries(ticker="  ", prices=valid_prices)
    with pytest.raises(ValueError, match="vacía"):
        PriceSeries(ticker="TEST", prices=empty_prices)
    with pytest.raises(TypeError, match="DatetimeIndex"):
        PriceSeries(ticker="TEST", prices=undated_prices)
    with pytest.raises(TypeError, match=r"pandas\.Series"):
        PriceSeries(ticker="TEST", prices=wrong_container)
    with pytest.raises(ValueError, match="positivos"):
        PriceSeries(ticker="TEST", prices=non_positive)


def test_fx_series_requires_every_rate_to_be_positive_and_finite() -> None:
    """FX provenance activates the stricter no-gap validation before cleaning."""
    for invalid_rate in (math.nan, math.inf, 0.0, -1.0):
        prices = pd.Series([1.1, invalid_rate], index=TRADING_DATES[:2])
        with pytest.raises(ValueError, match="tipos de cambio"):
            PriceSeries(ticker="FX:EUR/USD", prices=prices)


def test_quote_units_are_normalized_to_canonical_currency_values() -> None:
    """Documented minor units are scaled while canonical currencies pass through."""
    for unit, currency in (("GBX", "GBP"), ("GBp", "GBP"), ("ILA", "ILS"), ("ZAc", "ZAR")):
        asset = make_series("TEST", [120.0, 125.0], quote_unit=unit)
        assert asset.quote_currency == currency
        assert asset.quote_unit == unit
        assert asset.quote_unit_factor == pytest.approx(0.01)
        assert list(asset.prices) == pytest.approx([1.2, 1.25])
    canonical = make_series("TEST", [120.0], quote_unit="GBP")
    assert canonical.quote_currency == "GBP"
    assert canonical.prices.iloc[0] == pytest.approx(120.0)


def test_currency_metadata_is_explicit_canonical_and_consistent() -> None:
    """Currency codes are uppercased but never inferred from the ticker."""
    explicit = make_series("AAPL", [10.0, 11.0], quote_currency=" usd ")
    inferred = make_series("USD", [10.0, 11.0])

    assert explicit.quote_currency == "USD"
    assert explicit.quote_unit is None
    assert inferred.quote_currency is None
    with pytest.raises(ValueError, match="no coincide"):
        make_series("TEST", [10.0], quote_currency="USD", quote_unit="GBX")


def test_invalid_currency_metadata_has_specific_errors() -> None:
    """Unit aliases, malformed codes and non-text metadata never pass silently."""
    for alias in ("GBp", "GBX", "ILA", "ZAc"):
        with pytest.raises(ValueError, match="quote_unit"):
            make_series("TEST", [120.0], quote_currency=alias)
    with pytest.raises(ValueError, match=r"GBp.*GBP|GBP.*GBp"):
        make_series("TEST", [120.0], quote_unit="Gbp")
    for currency in ("US", ""):
        with pytest.raises(ValueError, match="divisa"):
            make_series("TEST", [10.0], quote_currency=currency)
    invalid_currency = cast("str", 5)
    with pytest.raises(TypeError, match="divisa"):
        make_series("TEST", [10.0], quote_currency=invalid_currency)
    for unit in ("", "US"):
        with pytest.raises(ValueError, match="unidad"):
            make_series("TEST", [10.0], quote_unit=unit)
    invalid_unit = cast("str", 5)
    with pytest.raises(ValueError, match="unidad"):
        make_series("TEST", [10.0], quote_unit=invalid_unit)


def test_price_summary_matches_manual_risk_statistics() -> None:
    """The summary exposes direct returns, annualization and shared risk measures."""
    asset = make_series("TEST", [100.0, 101.0, 103.0, 102.0, 104.0])
    returns = asset.prices.pct_change().dropna()
    summary = asset.summary()

    assert set(summary) == {
        "mean_daily_return",
        "daily_volatility",
        "annualized_return_approx",
        "annualized_volatility",
        "max_drawdown",
        "sharpe_ratio",
    }
    assert summary["mean_daily_return"] == pytest.approx(float(returns.mean()))
    assert summary["daily_volatility"] == pytest.approx(float(returns.std(ddof=1)))
    assert summary["annualized_return_approx"] == pytest.approx(float(returns.mean()) * 252)
    assert summary["annualized_volatility"] == pytest.approx(
        float(returns.std(ddof=1)) * math.sqrt(252)
    )
    assert summary["max_drawdown"] == pytest.approx(max_drawdown(returns))
    assert summary["sharpe_ratio"] == pytest.approx(sharpe_ratio(returns))
    assert asset.summary(periods_per_year=365)["annualized_return_approx"] == pytest.approx(
        float(returns.mean()) * 365
    )


def test_price_summary_rejects_short_or_invalid_samples() -> None:
    """Summary validation matches the shared risk and calendar contracts."""
    short_asset = make_series("TEST", [10.0])
    valid_asset = make_series("TEST", [10.0, 11.0, 12.0])
    with pytest.raises(ValueError, match="dos observaciones"):
        short_asset.summary()
    with pytest.raises(ValueError, match="periods_per_year"):
        valid_asset.summary(periods_per_year=0)


def test_asset_simulation_uses_last_price_and_honours_overrides() -> None:
    """Price simulations default to the last close while explicit settings take precedence."""
    asset = make_series("TEST", [10.0, 11.0, 12.0, 13.0])
    simulations = asset.simulate_monte_carlo(MonteCarloParameters(n_paths=3, horizon=5, seed=42))
    overridden = asset.simulate_monte_carlo(
        MonteCarloParameters(
            n_paths=2,
            horizon=5,
            initial_value=100.0,
            return_assumption=0.0,
            volatility_assumption=0.0,
            seed=1,
        )
    )

    assert simulations.shape == (6, 3)
    assert (simulations.iloc[0] == 13.0).all()
    assert (overridden == 100.0).all().all()
    short_asset = make_series("SHORT", [10.0])
    with pytest.raises(ValueError, match="dos precios"):
        short_asset.simulate_monte_carlo()


def test_asset_simulation_uses_the_requested_calendar() -> None:
    """Historical log drift follows the simulation's periods-per-year setting."""
    asset = make_series("TEST", [100.0, 101.0, 102.01, 103.0301])
    simulations = asset.simulate_monte_carlo(
        MonteCarloParameters(n_paths=1, horizon=365, periods_per_year=365, seed=1)
    )

    expected = 103.0301 * math.exp(float(np.log1p(0.01)) * 365)
    assert simulations.iloc[-1, 0] == pytest.approx(expected)


def test_macro_series_cleans_values_tracks_vintage_and_flags_duplicates() -> None:
    """Macro observations keep signed levels while recording duplicate exact dates."""
    index = TRADING_DATES[[2, 0, 1, 2]]
    series = MacroSeries(
        series_id="DGS10",
        values=pd.Series([-0.5, 1.0, 2.0, 3.0], index=index),
        vintage_date=pd.Timestamp("2025-03-15"),
    )
    default_vintage = MacroSeries(
        series_id="DGS10",
        values=pd.Series([1.0], index=TRADING_DATES[:1]),
    )

    assert series.duplicate_observation_dates is True
    assert list(series.values) == [1.0, 2.0, 3.0]
    assert series.index_levels is series.values  # noqa: PD011
    assert series.vintage_date == pd.Timestamp("2025-03-15")
    assert default_vintage.vintage_date is None


def test_macro_series_rejects_invalid_identifiers_and_values() -> None:
    """Macro models require a non-empty identifier, Series and useful values."""
    values = pd.Series([1.0], index=TRADING_DATES[:1])
    wrong_container = cast("pd.Series[float]", [1.0])
    empty_values = cast("pd.Series[float]", pd.Series([], dtype=float))
    unusable_values = cast("pd.Series[float]", pd.Series([".", "n/a"], index=TRADING_DATES[:2]))
    with pytest.raises(ValueError, match="identificador"):
        MacroSeries(series_id="  ", values=values)
    with pytest.raises(TypeError, match=r"pandas\.Series"):
        MacroSeries(series_id="DGS10", values=wrong_container)
    with pytest.raises(ValueError, match="vacía"):
        MacroSeries(series_id="DGS10", values=empty_values)
    with pytest.raises(ValueError, match="válidos"):
        MacroSeries(series_id="DGS10", values=unusable_values)
