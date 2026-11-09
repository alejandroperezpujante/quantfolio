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


class FixedPriceSource(MemorySource):
    """Return a constant raw-unit price for every requested observation."""

    def __init__(self, name: str, prices: dict[str, tuple[float, str | None]]) -> None:
        """Store each ticker's raw value and provider unit."""
        super().__init__(name, {ticker: unit for ticker, (_, unit) in prices.items()})
        self.values = {ticker: value for ticker, (value, _) in prices.items()}

    def get_prices(self, ticker: str, start: DateLike, end: DateLike | None = None) -> PriceSeries:
        """Return the configured value on the fake source's calendar."""
        reference = super().get_prices(ticker, start, end)
        prices = pd.Series(self.values[ticker], index=reference.prices.index, dtype=float)
        return PriceSeries(
            ticker,
            prices,
            source=self.name,
            quote_unit=self.currencies[ticker],
        )


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


def test_explicit_family_routes_ambiguous_symbols() -> None:
    """Explicit families route hyphen-free and compact crypto symbols safely."""
    kraken = MemorySource("Kraken", {"BTC/USDT": "USD", "ETHUSD": "USD"}, fail=True)
    alpha = MemorySource(
        "Alpha",
        {"CRYPTO:BTC/USDT": "USD", "CRYPTO:ETH/USD": "USD"},
    )
    yahoo = MemorySource("Yahoo", {"BRK/B": "USD"})

    ambiguous_config = AutoPortfolioConfig(
        weights={"BTC/USDT": 1},
        start="2025-01-02",
        sources={"kraken": kraken, "alpha-vantage": alpha},
        asset_families={"BTC/USDT": "crypto"},
        cache_enabled=False,
    )
    with pytest.warns(RuntimeWarning, match=r"kraken.*Alpha"):
        token = AutoPortfolio(ambiguous_config)
    assert kraken.calls[0][0] == "BTC/USDT"
    assert alpha.calls[0][0] == "CRYPTO:BTC/USDT"
    assert token.assets["BTC/USDT"].source == "Alpha"

    compact_config = AutoPortfolioConfig(
        weights={"ETHUSD": 1},
        start="2025-01-02",
        sources={"kraken": kraken, "alpha-vantage": alpha},
        asset_families={"ETHUSD": "crypto"},
        provider_symbols={"ETHUSD": {"alpha-vantage": "CRYPTO:ETH/USD"}},
        cache_enabled=False,
    )
    with pytest.warns(RuntimeWarning, match=r"kraken.*Alpha"):
        compact = AutoPortfolio(compact_config)
    assert kraken.calls[-1][0] == "ETHUSD"
    assert alpha.calls[-1][0] == "CRYPTO:ETH/USD"
    assert compact.assets["ETHUSD"].source == "Alpha"

    share_class = AutoPortfolio(
        AutoPortfolioConfig(
            weights={"BRK/B": 1},
            start="2025-01-02",
            sources={"yahoo": yahoo},
            asset_families={"BRK/B": "equity"},
            cache_enabled=False,
        )
    )
    assert yahoo.calls[0][0] == "BRK/B"
    assert share_class.assets["BRK/B"].source == "Yahoo"


def test_long_slash_quote_requires_explicit_family_before_fetch() -> None:
    """A slash pair with a long quote asset is not silently routed as an equity."""
    yahoo = MemorySource("Yahoo", {"BTC/USDT": "USD"})
    config = AutoPortfolioConfig(
        weights={"BTC/USDT": 1},
        start="2025-01-02",
        sources={"yahoo": yahoo},
        cache_enabled=False,
    )

    with pytest.raises(ValueError, match="asset_families"):
        AutoPortfolio(config)

    assert yahoo.calls == []


def test_compact_crypto_requires_explicit_alpha_symbol() -> None:
    """A compact crypto symbol is never split or sent to Alpha as an equity by guesswork."""
    kraken = MemorySource("Kraken", {"ETHUSD": "USD"}, fail=True)
    alpha = MemorySource("Alpha", {"ETHUSD": "USD"})
    config = AutoPortfolioConfig(
        weights={"ETHUSD": 1},
        start="2025-01-02",
        sources={"kraken": kraken, "alpha-vantage": alpha},
        asset_families={"ETHUSD": "crypto"},
        cache_enabled=False,
    )

    with pytest.raises(ValueError, match="provider_symbols"):
        AutoPortfolio(config)

    assert alpha.calls == []


def test_crypto_quote_is_fiat_only() -> None:
    """Crypto pricing accepts fiat quote labels only when they belong to the ECB table."""
    for ticker, currency in (("BTC/USD", "USD"), ("BTC/EUR", "EUR")):
        portfolio = AutoPortfolio(
            AutoPortfolioConfig(
                weights={ticker: 1},
                start="2025-01-02",
                sources={"kraken": MemorySource("Kraken", {ticker: currency})},
                asset_families={ticker: "crypto"},
                cache_enabled=False,
            )
        )
        assert portfolio.assets[ticker].quote_currency == currency

    non_fiat = MemorySource("Kraken", {"ETH/BTC": "BTC"})
    non_fiat_config = AutoPortfolioConfig(
        weights={"ETH/BTC": 1},
        start="2025-01-02",
        sources={"kraken": non_fiat},
        asset_families={"ETH/BTC": "crypto"},
        cache_enabled=False,
    )
    with pytest.raises(ValueError, match="fiat"):
        AutoPortfolio(non_fiat_config)


def test_unknown_crypto_quote_allows_only_legacy_analysis() -> None:
    """Unknown crypto markets remain legacy-only and reject any fiat interpretation."""
    source = MemorySource("Kraken", {"BTC/USDT": None})

    def config(**overrides: object) -> AutoPortfolioConfig:
        """Build an explicit crypto configuration with optional monetary settings."""
        settings: dict[str, object] = {
            "weights": {"BTC/USDT": 1},
            "start": "2025-01-02",
            "sources": {"kraken": source},
            "asset_families": {"BTC/USDT": "crypto"},
            "cache_enabled": False,
        }
        settings.update(overrides)
        return AutoPortfolioConfig(**settings)  # type: ignore[arg-type]

    legacy = AutoPortfolio(config())
    assert legacy.assets["BTC/USDT"].quote_currency is None

    for overrides in (
        {"quote_currencies": {"BTC/USDT": "USD"}},
        {"quote_units": {"BTC/USDT": "USD"}},
        {"reporting_currency": "USD"},
    ):
        invalid_config = config(**overrides)
        with pytest.raises(ValueError, match="fiat"):
            AutoPortfolio(invalid_config)


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


@pytest.mark.parametrize("alias", ["GBp", "GBX", "ILA", "ZAc"])
def test_quote_currency_rejects_unit_aliases(alias: str) -> None:
    """Automatic overrides cannot disguise a quote unit as a currency."""
    source = MemorySource("Yahoo", {"AAA": None})
    config = AutoPortfolioConfig(
        weights={"AAA": 1},
        start="2025-01-02",
        sources={"yahoo": source},
        quote_currencies={"AAA": alias},
        cache_enabled=False,
    )

    with pytest.raises(ValueError, match="quote_unit"):
        AutoPortfolio(config)

    assert source.calls == []


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
        quote_units={"AAA": "USD"},
        cache_enabled=False,
    )
    portfolio = AutoPortfolio(config)
    assert custom.calls[0][0] == "ALIAS"
    assert portfolio.assets["AAA"].quote_currency == "USD"
    assert portfolio.assets["AAA"].ticker == "AAA"


def test_missing_currency_allows_legacy_and_exhausted_sources_are_actionable() -> None:
    """Unknown-only portfolios are legacy-valid, while exhausted sources remain actionable."""
    missing = MemorySource("Missing", {"AAA": None})
    config = AutoPortfolioConfig(
        weights={"AAA": 1}, start="2025-01-02", sources={"yahoo": missing}, cache_enabled=False
    )
    assert AutoPortfolio(config).assets["AAA"].quote_currency is None
    config.sources = {"yahoo": MemorySource("Broken", {}, fail=True)}
    with pytest.raises(ValueError, match=r"AAA.*yahoo"):
        AutoPortfolio(config)


def test_currency_conflict_stops_provider_fallback() -> None:
    """A provider currency conflict is terminal rather than a fallback trigger."""
    yahoo = MemorySource("Yahoo", {"AAA": "USD"})
    alpha = MemorySource("Alpha", {"AAA": None})
    config = AutoPortfolioConfig(
        weights={"AAA": 1},
        start="2025-01-02",
        sources={"yahoo": yahoo, "alpha-vantage": alpha},
        quote_currencies={"AAA": "EUR"},
        cache_enabled=False,
    )

    with pytest.raises(ValueError, match="no coincide"):
        AutoPortfolio(config)
    assert alpha.calls == []

    unavailable = MemorySource("Yahoo", {"AAA": "USD"}, fail=True)
    alpha = MemorySource("Alpha", {"AAA": "USD"})
    config.sources = {"yahoo": unavailable, "alpha-vantage": alpha}
    config.quote_currencies = {}
    with pytest.warns(RuntimeWarning, match=r"yahoo.*Alpha"):
        portfolio = AutoPortfolio(config)
    assert alpha.calls[0][0] == "AAA"
    assert portfolio.assets["AAA"].quote_currency == "USD"


def test_legacy_cache_with_currency_override_refreshes_unit(tmp_path: Path) -> None:
    """A metadata-free cache is refreshed before a currency interpretation."""
    path = tmp_path / "yahoo" / "VOD.L.csv"
    path.parent.mkdir(parents=True)
    dates = pd.date_range("2024-12-26", "2025-01-09")
    pd.DataFrame({"Date": dates, "Close": [120.0] * len(dates)}).to_csv(path, index=False)
    source = FixedPriceSource("Yahoo", {"VOD.L": (120.0, "GBp")})
    config = AutoPortfolioConfig(
        weights={"VOD.L": 1},
        start="2025-01-02",
        end="2025-01-08",
        sources={"yahoo": source},
        quote_currencies={"VOD.L": "GBP"},
        cache_dir=tmp_path,
    )

    portfolio = AutoPortfolio(config)

    assert len(source.calls) == 1
    assert portfolio.assets["VOD.L"].quote_currency == "GBP"
    assert portfolio.assets["VOD.L"].quote_unit == "GBp"
    assert portfolio.assets["VOD.L"].prices.iloc[0] == pytest.approx(1.2)

    pd.DataFrame({"Date": dates, "Close": [120.0] * len(dates)}).to_csv(path, index=False)
    inaccessible = MemorySource("Yahoo", {"VOD.L": "GBp"}, fail=True)
    config.sources = {"yahoo": inaccessible}
    with pytest.raises(ValueError, match="No se pudo obtener"):
        AutoPortfolio(config)

    config.sources = {"yahoo": source}
    config.quote_currencies = {"VOD.L": "EUR"}
    with pytest.raises(ValueError, match="no coincide"):
        AutoPortfolio(config)


def test_unknown_unit_requires_explicit_confirmation_for_currency_analysis() -> None:
    """Unknown raw units require a manual unit before any currency interpretation."""
    source = FixedPriceSource("Yahoo", {"AAA": (120.0, None)})
    reporting = AutoPortfolioConfig(
        weights={"AAA": 1},
        start="2025-01-02",
        reporting_currency="EUR",
        sources={"yahoo": source},
        cache_enabled=False,
    )
    with pytest.raises(ValueError, match="quote_units"):
        AutoPortfolio(reporting)

    override = AutoPortfolioConfig(
        weights={"AAA": 1},
        start="2025-01-02",
        sources={"yahoo": source},
        quote_currencies={"AAA": "GBP"},
        cache_enabled=False,
    )
    with pytest.raises(ValueError, match="quote_units"):
        AutoPortfolio(override)

    override.quote_units = {"AAA": "GBp"}
    minor = AutoPortfolio(override)
    assert minor.assets["AAA"].prices.iloc[0] == pytest.approx(1.2)
    assert minor.assets["AAA"].quote_currency == "GBP"
    assert minor.assets["AAA"].quote_unit == "GBp"

    override.quote_units = {"AAA": "GBP"}
    canonical = AutoPortfolio(override)
    assert canonical.assets["AAA"].prices.iloc[0] == pytest.approx(120.0)

    invalid = AutoPortfolioConfig(
        weights={"AAA": 1},
        start="2025-01-02",
        sources={"yahoo": source},
        quote_units={"OTHER": "GBp"},
        cache_enabled=False,
    )
    with pytest.raises(ValueError, match="no corresponde"):
        AutoPortfolio(invalid)

    incoherent = AutoPortfolioConfig(
        weights={"AAA": 1},
        start="2025-01-02",
        sources={"yahoo": source},
        quote_currencies={"AAA": "EUR"},
        quote_units={"AAA": "GBp"},
        cache_enabled=False,
    )
    with pytest.raises(ValueError, match="no coincide"):
        AutoPortfolio(incoherent)

    known = FixedPriceSource("Yahoo", {"BBB": (120.0, "GBX")})
    conflicting = AutoPortfolioConfig(
        weights={"BBB": 1},
        start="2025-01-02",
        sources={"yahoo": known},
        quote_units={"BBB": "GBp"},
        cache_enabled=False,
    )
    with pytest.raises(ValueError, match="unidad"):
        AutoPortfolio(conflicting)

    class CurrencyOnlySource(MemorySource):
        """Return a provider currency without inventing its raw quote unit."""

        def get_prices(
            self, ticker: str, start: DateLike, end: DateLike | None = None
        ) -> PriceSeries:
            """Return prices whose currency is known and whose unit is not."""
            reference = super().get_prices(ticker, start, end)
            return PriceSeries(ticker, reference.prices, source=self.name, quote_currency="GBP")

    currency_only = CurrencyOnlySource("Yahoo", {"CCC": None})
    reinterpreted = AutoPortfolioConfig(
        weights={"CCC": 1},
        start="2025-01-02",
        sources={"yahoo": currency_only},
        quote_units={"CCC": "GBp"},
        cache_enabled=False,
    )
    with pytest.raises(ValueError, match="no se puede reinterpretar"):
        AutoPortfolio(reinterpreted)


def test_auto_portfolio_allows_unknown_currencies_without_conversion() -> None:
    """A fully unknown legacy portfolio remains valid without monetary analysis."""
    unknown = MemorySource("Yahoo", {"AAA": None, "BBB": None})
    portfolio = AutoPortfolio(
        AutoPortfolioConfig(
            weights={"AAA": 1, "BBB": 1},
            start="2025-01-02",
            sources={"yahoo": unknown},
            cache_enabled=False,
        )
    )
    assert all(asset.quote_currency is None for asset in portfolio.assets.values())

    partial = MemorySource("Yahoo", {"AAA": "USD", "BBB": None})
    partial_config = AutoPortfolioConfig(
        weights={"AAA": 1, "BBB": 1},
        start="2025-01-02",
        sources={"yahoo": partial},
        cache_enabled=False,
    )
    with pytest.raises(ValueError, match="divisas conocidas y desconocidas"):
        AutoPortfolio(partial_config)


def test_cached_metadata_is_refreshed_once(tmp_path: Path) -> None:
    """Cached metadata is refreshed once."""
    source = MemorySource("Yahoo", {"AAA": None})
    config = AutoPortfolioConfig(
        weights={"AAA": 1},
        start="2025-01-02",
        end="2025-01-08",
        reporting_currency="USD",
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


def test_supplied_rates_age_precedence() -> None:
    """Supplied rate ages win unless an explicit option contradicts them."""
    rate = PriceSeries(
        ticker="FX:USD/EUR",
        prices=pd.Series([0.9], index=pd.DatetimeIndex(["2025-01-02"])),
        source="Manual rates",
        quote_currency="EUR",
    )
    supplied = ExchangeRates([rate], max_age_days=500)
    yahoo = MemorySource("Yahoo", {"AAA": "USD"})

    def config(**overrides: object) -> AutoPortfolioConfig:
        settings: dict[str, object] = {
            "weights": {"AAA": 1},
            "start": "2025-01-02",
            "end": "2025-01-08",
            "reporting_currency": "EUR",
            "sources": {"yahoo": yahoo},
            "exchange_rates": supplied,
            "cache_enabled": False,
        }
        settings.update(overrides)
        return AutoPortfolioConfig(**settings)  # type: ignore[arg-type]

    inherited = AutoPortfolio(config())
    assert inherited.exchange_rates.max_age_days == 500
    yahoo.calls.clear()

    mismatched_config = config(fx_max_age_days=0)
    with pytest.raises(ValueError, match="fx_max_age_days"):
        AutoPortfolio(mismatched_config)
    assert yahoo.calls == []

    matched = AutoPortfolio(config(fx_max_age_days=500))
    assert matched.exchange_rates.max_age_days == 500

    default_source = MemorySource("Yahoo", {"BBB": "USD"})
    default_fx = MemorySource("FX", {"FX:EUR/USD": "USD"})
    defaulted = AutoPortfolio(
        AutoPortfolioConfig(
            weights={"BBB": 1},
            start="2025-01-02",
            reporting_currency="EUR",
            sources={"yahoo": default_source},
            fx_source=default_fx,
            cache_enabled=False,
        )
    )
    assert defaulted.exchange_rates.max_age_days == 4

    zero_source = MemorySource("Yahoo", {"CCC": "USD"})
    zero_fx = MemorySource("FX", {"FX:EUR/USD": "USD"})
    zero = AutoPortfolio(
        AutoPortfolioConfig(
            weights={"CCC": 1},
            start="2025-01-02",
            reporting_currency="EUR",
            sources={"yahoo": zero_source},
            fx_source=zero_fx,
            fx_max_age_days=0,
            cache_enabled=False,
        )
    )
    assert zero.exchange_rates.max_age_days == 0


def test_rates_without_reporting_currency_fail_before_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-empty supplied rates require a target before the source registry exists."""
    rate = PriceSeries(
        ticker="FX:USD/EUR",
        prices=pd.Series([0.9], index=pd.DatetimeIndex(["2025-01-02"])),
        source="Manual rates",
        quote_currency="EUR",
    )
    config = AutoPortfolioConfig(
        weights={"AAA": 1},
        start="2025-01-02",
        exchange_rates=ExchangeRates([rate]),
    )

    def forbidden_registry(**_kwargs: object) -> dict[str, PriceSource]:
        msg = "the registry must not be constructed"
        raise AssertionError(msg)

    monkeypatch.setattr(
        "quantfolio.auto_portfolio.create_price_source_registry", forbidden_registry
    )
    with pytest.raises(ValueError, match="divisa de reporte"):
        AutoPortfolio(config)

    source = MemorySource("Yahoo", {"AAA": "USD"})
    legacy = AutoPortfolio(
        AutoPortfolioConfig(
            weights={"AAA": 1},
            start="2025-01-02",
            sources={"yahoo": source},
            exchange_rates=ExchangeRates(),
            cache_enabled=False,
        )
    )
    assert legacy.exchange_rates.rates == ()


def test_download_window_covers_max_age() -> None:
    """The FX download looks back far enough to validate a Friday carry-forward."""

    class FridayRateSource(PriceSource):
        """Return one Friday observation for every request and record its window."""

        def __init__(self) -> None:
            self.calls: list[tuple[str, DateLike, DateLike | None]] = []

        @property
        def name(self) -> str:
            """Return the fake provider name."""
            return "Friday FX"

        def get_prices(
            self,
            ticker: str,
            start: DateLike,
            end: DateLike | None = None,
        ) -> PriceSeries:
            """Return the configured Friday rate."""
            self.calls.append((ticker, start, end))
            return PriceSeries(
                ticker,
                pd.Series([1.25], index=pd.DatetimeIndex(["2025-01-03"])),
                source=self.name,
                quote_currency="USD",
            )

    asset_source = MemorySource("Yahoo", {"AAA": "USD"})
    fx_source = FridayRateSource()
    portfolio = AutoPortfolio(
        AutoPortfolioConfig(
            weights={"AAA": 1},
            start="2025-01-06",
            end="2025-01-07",
            reporting_currency="EUR",
            sources={"yahoo": asset_source},
            fx_source=fx_source,
            fx_lookback_days=0,
            fx_max_age_days=4,
            cache_enabled=False,
        )
    )

    assert pd.Timestamp(fx_source.calls[0][1]) == pd.Timestamp("2025-01-02")
    assert portfolio.get_reporting_prices().iloc[0, 0] == pytest.approx(111.0 / 1.25)

    later_asset = MemorySource("Yahoo", {"BBB": "USD"})
    later = AutoPortfolio(
        AutoPortfolioConfig(
            weights={"BBB": 1},
            start="2025-01-08",
            end="2025-01-09",
            reporting_currency="EUR",
            sources={"yahoo": later_asset},
            fx_source=FridayRateSource(),
            fx_lookback_days=0,
            fx_max_age_days=4,
            cache_enabled=False,
        )
    )
    with pytest.raises(ValueError, match="obsoleto"):
        later.get_reporting_prices()


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


def test_alpha_cache_isolated_by_plan_direct_and_auto(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Direct and automatic caches keep free raw and premium adjusted data separate."""
    calls: list[AlphaVantagePlan] = []
    dates = pd.bdate_range("2025-01-02", periods=5)

    def get_prices(
        source: AlphaVantageSource, ticker: str, start: DateLike, end: DateLike | None = None
    ) -> PriceSeries:
        del start, end
        calls.append(source.plan)
        first_price = 100.0 if source.plan is AlphaVantagePlan.FREE else 80.0
        prices = pd.Series([first_price + position for position in range(len(dates))], index=dates)
        return PriceSeries(ticker, prices, source=source.name, quote_currency="USD")

    monkeypatch.setattr(AlphaVantageSource, "get_prices", get_prices)
    direct_dir = tmp_path / "direct"
    legacy = direct_dir / "alpha-vantage" / "AAA.csv"
    legacy.parent.mkdir(parents=True)
    pd.DataFrame({"Date": dates, "Close": [55.0] * len(dates), "ticker": "AAA"}).to_csv(
        legacy, index=False
    )
    legacy_contents = legacy.read_text(encoding="utf-8")

    direct_prices: dict[AlphaVantagePlan, list[float]] = {}
    for plan in (AlphaVantagePlan.FREE, AlphaVantagePlan.PREMIUM):
        alpha = AlphaVantageSource("example", plan=plan, indexes_enabled=False)
        cached = CachedPriceSource(alpha, cache_dir=direct_dir)
        first = cached.get_prices("AAA", "2025-01-02", "2025-01-10")
        second = cached.get_prices("AAA", "2025-01-02", "2025-01-10")
        direct_prices[plan] = list(second.prices)
        assert second.source.endswith("(cache)")
        assert list(first.prices) == list(second.prices)
    assert calls == [AlphaVantagePlan.FREE, AlphaVantagePlan.PREMIUM]
    assert direct_prices[AlphaVantagePlan.FREE][0] == pytest.approx(100.0)
    assert direct_prices[AlphaVantagePlan.PREMIUM][0] == pytest.approx(80.0)
    assert (direct_dir / "alpha-vantage-free-v2" / "AAA.csv").is_file()
    assert (direct_dir / "alpha-vantage-premium-v2" / "AAA.csv").is_file()
    assert legacy.read_text(encoding="utf-8") == legacy_contents

    calls.clear()
    auto_dir = tmp_path / "auto"
    auto_prices: dict[AlphaVantagePlan, float] = {}
    for plan in (AlphaVantagePlan.FREE, AlphaVantagePlan.PREMIUM):
        alpha = AlphaVantageSource("example", plan=plan, indexes_enabled=False)
        config = AutoPortfolioConfig(
            weights={"AAA": 1},
            start="2025-01-02",
            end="2025-01-10",
            sources={"alpha-vantage": alpha},
            ticker_priorities={"AAA": ("alpha-vantage",)},
            cache_dir=auto_dir,
        )
        auto_first = AutoPortfolio(config)
        auto_second = AutoPortfolio(config)
        auto_prices[plan] = float(auto_second.assets["AAA"].prices.iloc[0])
        assert auto_first.assets["AAA"].prices.equals(auto_second.assets["AAA"].prices)
    assert calls == [AlphaVantagePlan.FREE, AlphaVantagePlan.PREMIUM]
    assert auto_prices[AlphaVantagePlan.FREE] == pytest.approx(100.0)
    assert auto_prices[AlphaVantagePlan.PREMIUM] == pytest.approx(80.0)
    assert (auto_dir / "alpha-vantage-free-v2" / "AAA.csv").is_file()
    assert (auto_dir / "alpha-vantage-premium-v2" / "AAA.csv").is_file()


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
        ("asset_families", {"OTHER": "equity"}, "no corresponde"),
        ("asset_families", {"AAA": "commodity"}, "familia"),
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
