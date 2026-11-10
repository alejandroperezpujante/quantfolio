"""Public guarantees shared by every historical price-source implementation."""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, cast

import pandas as pd
import pytest

from quantfolio.models import PriceSeries
from quantfolio.sources import PriceSource
from quantfolio.sources.base import naive_timestamp, validate_ticker
from tests.support.providers import ProviderCase, contract_cases, public_source_classes

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


@pytest.fixture(params=["yahoo", "kraken", "ecb", "alpha", "cached"])
def provider_case(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> ProviderCase:
    """Return the requested configured public provider."""
    cases = {case.key: case for case in contract_cases(monkeypatch, tmp_path)}
    return cases[request.param]


def test_every_public_price_source_participates(provider_case: ProviderCase) -> None:
    """The contract fixture covers every concrete production implementation."""
    assert provider_case.source.__class__ in public_source_classes()


def test_provider_identity_is_explicit(provider_case: ProviderCase) -> None:
    """Every provider has a name and a semantic cache namespace."""
    assert provider_case.source.name.strip()
    assert provider_case.source.cache_namespace.strip()


def test_single_download_has_normalized_requested_identity(provider_case: ProviderCase) -> None:
    """One download preserves ticker identity, normalizes dates and keeps positive prices."""
    asset = provider_case.source.get_prices(
        provider_case.ticker,
        provider_case.start,
        provider_case.end,
    )

    assert isinstance(asset, PriceSeries)
    assert asset.ticker == provider_case.ticker
    assert asset.prices.name == provider_case.ticker
    assert isinstance(asset.prices.index, pd.DatetimeIndex)
    assert asset.prices.index.tz is None
    assert asset.prices.index.is_monotonic_increasing
    assert asset.prices.index.is_unique
    assert (asset.prices > 0).all()
    assert asset.prices.index.equals(provider_case.expected_dates)
    if provider_case.expected_quote_currency is not None:
        assert asset.quote_currency == provider_case.expected_quote_currency


def test_window_is_start_inclusive_and_end_exclusive(provider_case: ProviderCase) -> None:
    """The requested dates select the expected half-open window."""
    asset = provider_case.source.get_prices(
        provider_case.ticker,
        provider_case.start,
        provider_case.end,
    )

    assert provider_case.start in asset.prices.index
    assert provider_case.end not in asset.prices.index
    assert asset.prices.index[0] >= provider_case.start
    assert asset.prices.index[-1] < provider_case.end


def test_blank_ticker_is_rejected_before_transport(provider_case: ProviderCase) -> None:
    """Every implementation rejects a blank requested ticker."""
    with pytest.raises(ValueError, match="ticker"):
        provider_case.source.get_prices("   ", provider_case.start, provider_case.end)


def test_batch_download_preserves_requested_tickers(provider_case: ProviderCase) -> None:
    """A batch returns one independently labelled series per requested ticker."""
    batch = provider_case.source.get_many(
        provider_case.batch,
        provider_case.start,
        provider_case.end,
    )

    assert tuple(batch) == provider_case.batch
    for ticker in provider_case.batch:
        assert batch[ticker].ticker == ticker
        assert batch[ticker].prices.index.equals(provider_case.expected_dates)


def test_batch_matches_individual_downloads(provider_case: ProviderCase) -> None:
    """Batch composition does not change provider semantics."""
    batch = provider_case.source.get_many(
        provider_case.batch,
        provider_case.start,
        provider_case.end,
    )
    individual = {
        ticker: provider_case.source.get_prices(ticker, provider_case.start, provider_case.end)
        for ticker in provider_case.batch
    }

    for ticker in provider_case.batch:
        pd.testing.assert_series_equal(
            batch[ticker].prices,
            individual[ticker].prices,
            check_freq=False,
        )


@pytest.mark.parametrize("tickers", [(), ("AAPL", "AAPL")])
def test_batch_validation_is_shared(
    provider_case: ProviderCase,
    tickers: tuple[str, ...],
) -> None:
    """Empty and duplicate batches fail consistently before provider work."""
    with pytest.raises(ValueError, match=r"ticker|duplicados|al menos"):
        provider_case.source.get_many(tickers, provider_case.start, provider_case.end)


def test_contract_factory_matches_all_public_classes() -> None:
    """A guard forces every new public source into the contract matrix."""
    expected = {source_class.__name__ for source_class in public_source_classes()}
    assert expected == {
        "AlphaVantageSource",
        "CachedPriceSource",
        "ECBExchangeRateSource",
        "KrakenSource",
        "YahooFinanceSource",
    }


def test_shared_input_helpers_normalize_text_and_timezone_aware_dates() -> None:
    """The public provider helpers trim tickers and remove timezone metadata."""
    stamp = naive_timestamp(pd.Timestamp("2025-01-02 12:30", tz="Europe/Madrid"))

    assert validate_ticker("  AAPL  ") == "AAPL"
    assert stamp == pd.Timestamp("2025-01-02 12:30")
    assert stamp.tz is None
    invalid_ticker = cast("str", object())
    with pytest.raises(TypeError, match="texto"):
        validate_ticker(invalid_ticker)


def test_abstract_source_defaults_cannot_be_used_as_an_implementation() -> None:
    """A concrete subclass that delegates to the abstract defaults fails explicitly."""
    source = cast("PriceSource", object())
    name_property = inspect.getattr_static(PriceSource, "name")
    assert isinstance(name_property, property)
    assert name_property.fget is not None
    name_getter = cast("Callable[[PriceSource], str]", name_property.fget)

    with pytest.raises(NotImplementedError):
        name_getter(source)
    with pytest.raises(NotImplementedError):
        PriceSource.get_prices(source, "AAPL", "2025-01-02")
