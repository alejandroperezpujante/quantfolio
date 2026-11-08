"""Offline tests for automatic portfolio composition."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd
import pytest

from quantfolio import (
    AlphaVantagePlan,
    AlphaVantageSource,
    AutoPortfolio,
    AutoPortfolioConfig,
    CachedPriceSource,
    ExchangeRates,
    Portfolio,
    PriceSeries,
)
from quantfolio.sources import DateLike, PriceSource

if TYPE_CHECKING:
    from pathlib import Path


class MemorySource(PriceSource):
    """Record requests and return fixed market data without network access."""

    def __init__(self, name: str, currencies: dict[str, str | None], *, fail: bool = False) -> None:
        """Store the fake source and its response settings."""
        self._name = name
        self.currencies = currencies
        self.fail = fail
        self.calls: list[tuple[str, DateLike, DateLike | None]] = []

    @property
    def name(self) -> str:
        """Return the fake provider name."""
        return self._name

    def get_prices(self, ticker: str, start: DateLike, end: DateLike | None = None) -> PriceSeries:
        """Return deterministic prices and record each request."""
        self.calls.append((ticker, start, end))
        if self.fail:
            msg = "Proveedor no disponible"
            raise ValueError(msg)
        unit = self.currencies[ticker]
        dates = pd.date_range("2024-12-26", "2025-01-09")
        prices = pd.Series([100.0 + i for i in range(len(dates))], index=dates)
        prices = prices[prices.index >= pd.Timestamp(start)]
        if end is not None:
            prices = prices[prices.index < pd.Timestamp(end)]
        return PriceSeries(ticker, prices, source=self.name, quote_unit=unit)


def test_default_routing_and_portfolio_analytics() -> None:
    """Default routing and portfolio analytics."""
    yahoo = MemorySource("Yahoo", {"AAPL": "USD"})
    kraken = MemorySource("Kraken", {"BTC/USD": "USD"})
    config = AutoPortfolioConfig(
        weights={"AAPL": 3, "BTC/USD": 1},
        start="2025-01-02",
        end="2025-01-08",
        sources={"yahoo": yahoo, "kraken": kraken},
        cache_enabled=False,
    )
    portfolio = AutoPortfolio(config)
    assert isinstance(portfolio, Portfolio)
    assert portfolio.weights == {"AAPL": 0.75, "BTC/USD": 0.25}
    assert len(portfolio.portfolio_returns()) == 5
    assert yahoo.calls[0][0] == "AAPL"
    assert kraken.calls[0][0] == "BTC/USD"


def test_fallback_translates_ticker_and_preserves_quote_units() -> None:
    """Fallback translates ticker and preserves quote units."""
    kraken = MemorySource("Kraken", {}, fail=True)
    alpha = MemorySource("Alpha", {"CRYPTO:BTC/USD": "USD"})
    config = AutoPortfolioConfig(
        weights={"BTC/USD": 1},
        start="2025-01-02",
        end="2025-01-08",
        sources={"kraken": kraken, "alpha-vantage": alpha},
        cache_enabled=False,
    )
    with pytest.warns(RuntimeWarning, match=r"kraken.*Alpha"):
        portfolio = AutoPortfolio(config)
    assert alpha.calls[0][0] == "CRYPTO:BTC/USD"
    assert portfolio.assets["BTC/USD"].ticker == "BTC/USD"
    assert portfolio.assets["BTC/USD"].source == "Alpha"


def test_mixed_currency_requires_explicit_reporting_currency() -> None:
    """Mixed currency requires explicit reporting currency."""
    yahoo = MemorySource("Yahoo", {"US": "USD", "EU": "EUR"})
    config = AutoPortfolioConfig(
        weights={"US": 1, "EU": 1},
        start="2025-01-02",
        sources={"yahoo": yahoo},
        cache_enabled=False,
    )
    with pytest.raises(ValueError, match="divisa de reporte"):
        AutoPortfolio(config)


def test_fx_requests_eur_legs_and_converts() -> None:
    """Fx requests eur legs and converts."""
    yahoo = MemorySource("Yahoo", {"US": "USD", "UK": "GBP"})

    class FixedRates(MemorySource):
        """Provide distinct EUR reference rates."""

        def get_prices(
            self, ticker: str, start: DateLike, end: DateLike | None = None
        ) -> PriceSeries:
            """Return 1.25 USD or 0.8 GBP per EUR."""
            asset = super().get_prices(ticker, start, end)
            value = 1.25 if ticker == "FX:EUR/USD" else 0.8
            return PriceSeries(ticker, asset.prices * 0 + value, source=self.name)

    fx = FixedRates("FX", {"FX:EUR/USD": "USD", "FX:EUR/GBP": "GBP"})
    config = AutoPortfolioConfig(
        weights={"US": 1, "UK": 1},
        start="2025-01-02",
        end="2025-01-08",
        reporting_currency="GBP",
        sources={"yahoo": yahoo},
        fx_source=fx,
        cache_enabled=False,
    )
    portfolio = AutoPortfolio(config)
    assert {call[0] for call in fx.calls} == {"FX:EUR/USD", "FX:EUR/GBP"}
    assert all(pd.Timestamp(call[1]) == pd.Timestamp("2024-12-26") for call in fx.calls)
    converted = portfolio.get_reporting_prices()
    assert converted["US"].iloc[0] == pytest.approx(107.0 / 1.25 * 0.8)
    assert converted["UK"].iloc[0] == pytest.approx(107.0)


def test_configured_source_symbols_and_currency_override() -> None:
    """Configured source symbols and currency override."""
    custom = MemorySource("Custom", {"ALIAS": None})
    config = AutoPortfolioConfig(
        weights={"AAA": 1},
        start="2025-01-02",
        sources={"custom": custom},
        ticker_priorities={"AAA": ("custom",)},
        provider_symbols={"AAA": {"custom": "ALIAS"}},
        quote_currencies={"AAA": "USD"},
        cache_enabled=False,
    )
    portfolio = AutoPortfolio(config)
    assert custom.calls[0][0] == "ALIAS"
    assert portfolio.assets["AAA"].quote_currency == "USD"
    assert portfolio.assets["AAA"].ticker == "AAA"


def test_missing_currency_and_exhausted_sources_are_actionable() -> None:
    """Missing currency and exhausted sources are actionable."""
    missing = MemorySource("Missing", {"AAA": None})
    config = AutoPortfolioConfig(
        weights={"AAA": 1}, start="2025-01-02", sources={"yahoo": missing}, cache_enabled=False
    )
    with pytest.raises(ValueError, match=r"divisa.*AAA"):
        AutoPortfolio(config)
    config.sources = {"yahoo": MemorySource("Broken", {}, fail=True)}
    with pytest.raises(ValueError, match=r"AAA.*yahoo"):
        AutoPortfolio(config)


def test_cached_metadata_is_refreshed_once(tmp_path: Path) -> None:
    """Cached metadata is refreshed once."""
    source = MemorySource("Yahoo", {"AAA": None})
    config = AutoPortfolioConfig(
        weights={"AAA": 1},
        start="2025-01-02",
        end="2025-01-08",
        sources={"yahoo": source},
        cache_dir=tmp_path,
    )
    CachedPriceSource(source, cache_dir=tmp_path).get_prices("AAA", "2025-01-02", "2025-01-08")
    source.currencies["AAA"] = "USD"
    portfolio = AutoPortfolio(config)
    assert portfolio.assets["AAA"].quote_currency == "USD"
    assert len(source.calls) == 2


def test_supplied_rates_avoid_fx_fetch() -> None:
    """Supplied rates avoid fx fetch."""
    yahoo = MemorySource("Yahoo", {"AAA": "USD"})
    fx = MemorySource("FX", {"FX:EUR/USD": "USD"})
    rate = fx.get_prices("FX:EUR/USD", "2024-12-26", "2025-01-08")
    fx.calls.clear()
    config = AutoPortfolioConfig(
        weights={"AAA": 1},
        start="2025-01-02",
        end="2025-01-08",
        reporting_currency="EUR",
        sources={"yahoo": yahoo},
        fx_source=fx,
        exchange_rates=ExchangeRates([rate]),
        cache_enabled=False,
    )
    portfolio = AutoPortfolio(config)
    assert fx.calls == []
    assert not portfolio.get_reporting_prices().empty


def test_invalid_weights_rejected_before_fetch() -> None:
    """Invalid weights rejected before fetch."""
    yahoo = MemorySource("Yahoo", {"AAA": "USD"})
    config = AutoPortfolioConfig(
        weights={"AAA": -1}, start="2025-01-02", sources={"yahoo": yahoo}, cache_enabled=False
    )
    with pytest.raises(ValueError, match="ponderaciones"):
        AutoPortfolio(config)
    assert yahoo.calls == []


def test_renamed_subunit_preserves_normalized_values() -> None:
    """Provider-specific symbols retain pence prices and original quote units."""
    source = MemorySource("Yahoo", {"ALIAS": "GBp"})
    config = AutoPortfolioConfig(
        weights={"AAA": 1},
        start="2025-01-02",
        sources={"yahoo": source},
        provider_symbols={"AAA": {"yahoo": "ALIAS"}},
        cache_enabled=False,
    )
    portfolio = AutoPortfolio(config)
    asset = portfolio.assets["AAA"]
    assert asset.quote_currency == "GBP"
    assert asset.quote_unit == "GBp"
    assert asset.prices.iloc[0] == pytest.approx(1.07)


@pytest.mark.parametrize("weights", [{}, {"AAA": 0}, {"AAA": float("nan")}])
def test_invalid_weights_do_not_fetch(weights: dict[str, float]) -> None:
    """Invalid compositions are rejected before contacting providers."""
    source = MemorySource("Yahoo", {"AAA": "USD"})
    config = AutoPortfolioConfig(weights=weights, start="2025-01-02", sources={"yahoo": source})
    with pytest.raises(ValueError, match=r"activo|ponderaciones"):
        AutoPortfolio(config)
    assert source.calls == []


def test_invalid_end_is_rejected_before_fetch() -> None:
    """Reject an invalid exclusive end without contacting providers."""
    source = MemorySource("Yahoo", {"AAA": "USD"})
    config = AutoPortfolioConfig(
        weights={"AAA": 1}, start="2025-01-02", end="2025-01-02", sources={"yahoo": source}
    )
    with pytest.raises(ValueError, match="fechas"):
        AutoPortfolio(config)
    assert source.calls == []


def test_quote_override_cannot_relabel_known_currency() -> None:
    """A currency override cannot turn USD prices into EUR prices by relabeling."""

    class ExplicitCurrencySource(MemorySource):
        """Provide a known currency without original unit metadata."""

        def get_prices(
            self, ticker: str, start: DateLike, end: DateLike | None = None
        ) -> PriceSeries:
            """Return a USD series with no quote-unit field."""
            asset = super().get_prices(ticker, start, end)
            return PriceSeries(ticker, asset.prices, source=self.name, quote_currency="USD")

    source = ExplicitCurrencySource("Kraken", {"BTC/USD": None})
    config = AutoPortfolioConfig(
        weights={"BTC/USD": 1},
        start="2025-01-02",
        sources={"kraken": source},
        quote_currencies={"BTC/USD": "EUR"},
        cache_enabled=False,
    )
    with pytest.raises(ValueError, match="divisa"):
        AutoPortfolio(config)


def test_provider_cannot_return_another_ticker() -> None:
    """A provider response must identify the requested provider-specific symbol."""

    class WrongTickerSource(MemorySource):
        """Return an unrelated instrument."""

        def get_prices(
            self, ticker: str, start: DateLike, end: DateLike | None = None
        ) -> PriceSeries:
            """Replace the returned ticker with a different instrument."""
            asset = super().get_prices(ticker, start, end)
            return PriceSeries("OTHER", asset.prices, source=self.name, quote_currency="USD")

    source = WrongTickerSource("Yahoo", {"AAA": "USD"})
    config = AutoPortfolioConfig(
        weights={"AAA": 1},
        start="2025-01-02",
        sources={"yahoo": source},
        cache_enabled=False,
    )
    with pytest.raises(ValueError, match="ticker"):
        AutoPortfolio(config)


def test_alpha_cache_isolated_by_plan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A plan change cannot reuse prices cached under different adjustment semantics."""
    calls: list[AlphaVantagePlan] = []

    def get_prices(
        source: AlphaVantageSource, ticker: str, start: DateLike, end: DateLike | None = None
    ) -> PriceSeries:
        calls.append(source.plan)
        fake = MemorySource(source.plan.value, {ticker: "USD"})
        return fake.get_prices(ticker, start, end)

    monkeypatch.setattr(AlphaVantageSource, "get_prices", get_prices)
    for plan in (AlphaVantagePlan.FREE, AlphaVantagePlan.PREMIUM):
        alpha = AlphaVantageSource("example", plan=plan, indexes_enabled=False)
        config = AutoPortfolioConfig(
            weights={"AAA": 1},
            start="2025-01-02",
            end="2025-01-08",
            sources={"alpha-vantage": alpha},
            ticker_priorities={"AAA": ("alpha-vantage",)},
            cache_dir=tmp_path,
        )
        AutoPortfolio(config)
    assert calls == [AlphaVantagePlan.FREE, AlphaVantagePlan.PREMIUM]


def test_wrong_symbol_is_not_written_to_cache(tmp_path: Path) -> None:
    """A provider mismatch cannot become a valid-looking cached ticker."""

    class WrongTickerSource(MemorySource):
        """Return a different ticker until corrected."""

        def get_prices(
            self, ticker: str, start: DateLike, end: DateLike | None = None
        ) -> PriceSeries:
            """Return a wrongly labeled asset."""
            asset = super().get_prices(ticker, start, end)
            return PriceSeries("OTHER", asset.prices, source=self.name, quote_currency="USD")

    source = WrongTickerSource("Yahoo", {"AAA": "USD"})
    config = AutoPortfolioConfig(
        weights={"AAA": 1},
        start="2025-01-02",
        end="2025-01-08",
        sources={"yahoo": source},
        cache_dir=tmp_path,
    )
    with pytest.raises(ValueError, match="ticker"):
        AutoPortfolio(config)
    assert not list(tmp_path.rglob("*.csv"))


def test_fx_source_cannot_return_another_pair() -> None:
    """A wrong FX pair is rejected before it can be cached or used."""

    class WrongPair(MemorySource):
        """Return the wrong FX pair."""

        def get_prices(
            self, ticker: str, start: DateLike, end: DateLike | None = None
        ) -> PriceSeries:
            """Return the wrong currency pair."""
            asset = super().get_prices(ticker, start, end)
            return PriceSeries("FX:EUR/GBP", asset.prices, source=self.name, quote_currency="GBP")

    source = MemorySource("Yahoo", {"AAA": "USD"})
    fx = WrongPair("FX", {"FX:EUR/USD": "USD"})
    config = AutoPortfolioConfig(
        weights={"AAA": 1},
        start="2025-01-02",
        reporting_currency="EUR",
        sources={"yahoo": source},
        fx_source=fx,
        cache_enabled=False,
    )
    with pytest.raises(ValueError, match="ticker"):
        AutoPortfolio(config)


@pytest.mark.parametrize(
    ("attribute", "value", "message"),
    [
        ("weights", {" AAA": 1.0}, "espacios"),
        ("quote_currencies", {"OTHER": "USD"}, "no corresponde"),
        ("cache_ttl_days", -1, "cache_ttl_days"),
        ("fx_lookback_days", True, "fx_lookback_days"),
        ("fx_max_age_days", 1.5, "fx_max_age_days"),
        ("provider_priorities", {"unknown": ("yahoo",)}, "familia"),
        ("ticker_priorities", {"OTHER": ("yahoo",)}, "desconocidos"),
        ("ticker_priorities", {"AAA": ()}, "prioridad"),
        ("ticker_priorities", {"AAA": ("yahoo", "yahoo")}, "duplicados"),
        ("exchange_rates", "invalid", "ExchangeRates"),
        ("start", "NaT", "fechas"),
        ("end", "NaT", "fechas"),
    ],
)
def test_invalid_options_are_rejected_before_fetch(
    attribute: str, value: object, message: str
) -> None:
    """Invalid configuration is rejected without contacting a provider."""
    source = MemorySource("Yahoo", {"AAA": "USD"})
    config = AutoPortfolioConfig(weights={"AAA": 1}, start="2025-01-02", sources={"yahoo": source})
    setattr(config, attribute, value)
    with pytest.raises((ValueError, TypeError), match=message):
        AutoPortfolio(config)
    assert source.calls == []


def test_index_and_prefixed_routes() -> None:
    """Index and explicit Alpha Vantage families use their respective sources."""
    yahoo = MemorySource("Yahoo", {"^GSPC": "USD"})
    alpha = MemorySource("Alpha", {"COMMODITY:GOLD": "USD"})
    config = AutoPortfolioConfig(
        weights={"^GSPC": 1, "COMMODITY:GOLD": 1},
        start="2025-01-02",
        sources={"yahoo": yahoo, "alpha-vantage": alpha},
        cache_enabled=False,
    )
    portfolio = AutoPortfolio(config)
    assert set(portfolio.assets) == {"^GSPC", "COMMODITY:GOLD"}
    assert yahoo.calls[0][0] == "^GSPC"
    assert alpha.calls[0][0] == "COMMODITY:GOLD"


def test_registry_and_cached_fx_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The default registry and FX provider are created and cached automatically."""
    yahoo = MemorySource("Yahoo", {"AAA": "USD", "BBB": "USD"})
    fx = MemorySource("FX", {"FX:EUR/USD": "USD"})
    monkeypatch.setattr(
        "quantfolio.auto_portfolio.create_price_source_registry", lambda **_: {"yahoo": yahoo}
    )
    monkeypatch.setattr("quantfolio.auto_portfolio.ECBExchangeRateSource", lambda: fx)
    config = AutoPortfolioConfig(
        weights={"AAA": 1, "BBB": 1},
        start="2025-01-02",
        end="2025-01-08",
        reporting_currency="EUR",
        cache_dir=tmp_path,
    )
    first = AutoPortfolio(config)
    second = AutoPortfolio(config)
    assert first.get_reporting_prices().equals(second.get_reporting_prices())
    assert len(yahoo.calls) == 2
    assert len(fx.calls) == 1


def test_stale_fx_cache_is_refreshed_for_new_asset(tmp_path: Path) -> None:
    """An old FX cache must not prevent conversion of newer asset prices."""
    yahoo = MemorySource("Yahoo", {"AAA": "USD"})
    fx = MemorySource("FX", {"FX:EUR/USD": "USD"})
    CachedPriceSource(fx, cache_dir=tmp_path).get_prices("FX:EUR/USD", "2024-12-26", "2025-01-04")
    portfolio = AutoPortfolio(
        AutoPortfolioConfig(
            weights={"AAA": 1},
            start="2025-01-02",
            end="2025-01-10",
            reporting_currency="EUR",
            sources={"yahoo": yahoo},
            fx_source=fx,
            cache_dir=tmp_path,
        )
    )
    assert portfolio.get_reporting_prices().index.max() == pd.Timestamp("2025-01-09")


def test_same_currency_does_not_fetch_rates() -> None:
    """A reporting currency equal to every asset needs no FX provider."""
    source = MemorySource("Yahoo", {"AAA": "USD"})
    fx = MemorySource("FX", {}, fail=True)
    config = AutoPortfolioConfig(
        weights={"AAA": 1},
        start="2025-01-02",
        reporting_currency="USD",
        sources={"yahoo": source},
        fx_source=fx,
        cache_enabled=False,
    )
    portfolio = AutoPortfolio(config)
    assert portfolio.get_prices().equals(portfolio.get_reporting_prices())
    assert fx.calls == []
