"""Configured provider cases shared by the public source contract suite."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

import pandas as pd

from quantfolio.sources import (
    AlphaVantagePlan,
    AlphaVantageSource,
    CachedPriceSource,
    ECBExchangeRateSource,
    KrakenSource,
    PriceSource,
    YahooFinanceSource,
)
from tests.support.builders import TRADING_DATES, make_series
from tests.support.sources import ScriptedPriceSource, filtered_series
from tests.support.transports import (
    alpha_daily_payload,
    install_alpha,
    install_ecb,
    install_kraken,
    install_yahoo,
    kraken_pair,
)

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from quantfolio.models import PriceSeries
    from quantfolio.sources.base import DateLike


@dataclass(frozen=True)
class ProviderCase:
    """One public source implementation configured against a deterministic transport."""

    key: str
    source: PriceSource
    ticker: str
    batch: tuple[str, str]
    start: pd.Timestamp
    end: pd.Timestamp
    expected_dates: pd.DatetimeIndex
    expected_quote_currency: str | None = None


def market_values() -> pd.Series[float]:
    """Return a positive five-observation series shared by every provider."""
    return pd.Series([100.0, 101.0, 102.0, 103.0, 104.0], index=TRADING_DATES[:5])


def _yahoo_case(monkeypatch: pytest.MonkeyPatch) -> ProviderCase:
    values = market_values()
    prices = {"AAPL": values, "MSFT": values + 10.0}
    install_yahoo(monkeypatch, prices, currencies={"AAPL": "USD", "MSFT": "USD"})
    return ProviderCase(
        key="yahoo",
        source=YahooFinanceSource(),
        ticker="AAPL",
        batch=("AAPL", "MSFT"),
        start=values.index[1],
        end=values.index[4],
        expected_dates=pd.DatetimeIndex(values.index[1:4]),
        expected_quote_currency="USD",
    )


def _kraken_case(monkeypatch: pytest.MonkeyPatch) -> ProviderCase:
    values = market_values()
    usd_pair = kraken_pair("BTC/USD")
    eur_pair = kraken_pair("ETH/EUR")
    install_kraken(monkeypatch, {usd_pair: values, eur_pair: values + 10.0})
    return ProviderCase(
        key="kraken",
        source=KrakenSource(),
        ticker="BTC/USD",
        batch=("BTC/USD", "ETH/EUR"),
        start=values.index[1],
        end=values.index[4],
        expected_dates=pd.DatetimeIndex(values.index[1:4]),
        expected_quote_currency="USD",
    )


def _ecb_case(monkeypatch: pytest.MonkeyPatch) -> ProviderCase:
    values = market_values()
    install_ecb(
        monkeypatch,
        {
            "FX:EUR/USD": values,
            "FX:EUR/GBP": values / 1.2,
        },
    )
    return ProviderCase(
        key="ecb",
        source=ECBExchangeRateSource(),
        ticker="FX:EUR/USD",
        batch=("FX:EUR/USD", "FX:EUR/GBP"),
        start=values.index[1],
        end=values.index[4],
        expected_dates=pd.DatetimeIndex(values.index[1:4]),
        expected_quote_currency="USD",
    )


def _alpha_case(
    monkeypatch: pytest.MonkeyPatch,
    cache_dir: Path,
) -> ProviderCase:
    values = market_values()
    install_alpha(
        monkeypatch,
        {"TIME_SERIES_DAILY": alpha_daily_payload(values.tolist())},
    )
    return ProviderCase(
        key="alpha",
        source=AlphaVantageSource(
            "contract-key",
            plan=AlphaVantagePlan.FREE,
            indexes_enabled=False,
            cache_dir=cache_dir,
        ),
        ticker="IBM",
        batch=("IBM", "MSFT"),
        start=values.index[1],
        end=values.index[4],
        expected_dates=pd.DatetimeIndex(values.index[1:4]),
    )


def _cached_case(cache_dir: Path) -> ProviderCase:
    values = market_values()
    responses = {
        "AAPL": make_series("AAPL", values.tolist(), source="Scripted"),
        "MSFT": make_series("MSFT", (values + 10.0).tolist(), source="Scripted"),
    }

    def response_for(symbol: str, start: DateLike, end: DateLike | None) -> PriceSeries:
        return filtered_series(
            responses[symbol],
            start,
            end,
        )

    upstream = ScriptedPriceSource(
        dict.fromkeys(responses, response_for),
        source_name="Scripted",
        namespace="scripted-v1",
    )
    source = CachedPriceSource(upstream, cache_dir=cache_dir / "prices", ttl_days=30)
    return ProviderCase(
        key="cached",
        source=source,
        ticker="AAPL",
        batch=("AAPL", "MSFT"),
        start=values.index[1],
        end=values.index[4],
        expected_dates=pd.DatetimeIndex(values.index[1:4]),
    )


def contract_cases(
    monkeypatch: pytest.MonkeyPatch,
    cache_dir: Path,
) -> list[ProviderCase]:
    """Return every public provider case represented by the contract fixture."""
    return [
        _yahoo_case(monkeypatch),
        _kraken_case(monkeypatch),
        _ecb_case(monkeypatch),
        _alpha_case(monkeypatch, cache_dir),
        _cached_case(cache_dir),
    ]


def public_source_classes() -> set[type[PriceSource]]:
    """Return every concrete production ``PriceSource`` implementation."""

    def descendants(parent: type[object]) -> set[type[PriceSource]]:
        found: set[type[PriceSource]] = set()
        for child in parent.__subclasses__():
            implementation = cast("type[PriceSource]", child)
            found.add(implementation)
            found.update(descendants(implementation))
        return found

    return {
        implementation
        for implementation in descendants(PriceSource)
        if implementation.__module__.startswith("quantfolio.")
        and not implementation.__module__.startswith("quantfolio.sources.base")
        and not implementation.__name__.startswith("_")
    }
