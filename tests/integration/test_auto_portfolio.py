"""Public AutoPortfolio routing, currency, cache and provider composition behavior."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd
import pytest

from quantfolio import AutoPortfolio, AutoPortfolioConfig, ExchangeRates, Portfolio, PriceSeries
from quantfolio.sources import CachedPriceSource
from tests.support.builders import make_series
from tests.support.sources import ScriptedPriceSource, filtered_series, table_source

if TYPE_CHECKING:
    from pathlib import Path

    from quantfolio.sources import PriceSource

MARKET_DATES = pd.bdate_range("2024-12-26", "2025-01-10")


def _series(
    ticker: str,
    *,
    source: str = "Stub",
    currency: str | None = None,
    unit: str | None = None,
    values: list[float] | None = None,
) -> PriceSeries:
    configured = values or [100.0 + position for position in range(len(MARKET_DATES))]
    return make_series(
        ticker,
        configured,
        dates=MARKET_DATES,
        source=source,
        quote_currency=currency,
        quote_unit=unit,
    )


def _source(
    name: str,
    *,
    currency: str | None = "USD",
    unit: str | None = None,
    tickers: tuple[str, ...] = ("AAA",),
) -> ScriptedPriceSource:
    return table_source(
        name,
        {ticker: _series(ticker, source=name, currency=currency, unit=unit) for ticker in tickers},
    )


def _fx_source(rate: float = 1.25, pair: str = "FX:EUR/USD") -> ScriptedPriceSource:
    values = [rate] * len(MARKET_DATES)
    return table_source(
        "FX",
        {pair: make_series(pair, values, dates=MARKET_DATES, quote_currency=pair[-3:])},
    )


def _rates() -> ExchangeRates:
    pair = make_series(
        "FX:USD/EUR",
        [0.8],
        dates=["2025-01-02"],
        quote_currency="EUR",
    )
    return ExchangeRates([pair], max_age_days=500)


def test_default_routing_composes_a_portfolio_with_analytics() -> None:
    """Built-in families route equities to Yahoo and fiat crypto pairs to Kraken."""
    yahoo = _source("Yahoo", tickers=("AAPL",))
    kraken = _source("Kraken", tickers=("BTC/USD",))
    portfolio = AutoPortfolio(
        AutoPortfolioConfig(
            weights={"AAPL": 3, "BTC/USD": 1},
            start="2025-01-02",
            end="2025-01-09",
            sources={"yahoo": yahoo, "kraken": kraken},
            cache_enabled=False,
        )
    )

    assert isinstance(portfolio, Portfolio)
    assert portfolio.weights == {"AAPL": 0.75, "BTC/USD": 0.25}
    assert not portfolio.portfolio_returns().empty
    assert [call[0] for call in yahoo.calls] == ["AAPL"]
    assert [call[0] for call in kraken.calls] == ["BTC/USD"]


def test_crypto_fallback_uses_alpha_prefix_and_warns_about_market_differences() -> None:
    """A failed primary provider may fall back without changing caller ticker identity."""
    kraken = table_source("Kraken", {"BTC/USD": ValueError("Proveedor no disponible")})
    alpha = _source("Alpha", tickers=("CRYPTO:BTC/USD",))
    config = AutoPortfolioConfig(
        weights={"BTC/USD": 1},
        start="2025-01-02",
        sources={"kraken": kraken, "alpha-vantage": alpha},
        cache_enabled=False,
    )
    with pytest.warns(RuntimeWarning, match=r"kraken.*Alpha"):
        portfolio = AutoPortfolio(config)

    assert alpha.calls[0][0] == "CRYPTO:BTC/USD"
    assert portfolio.assets["BTC/USD"].ticker == "BTC/USD"
    assert portfolio.assets["BTC/USD"].source == "Alpha"


def test_explicit_crypto_family_supports_long_quotes_compact_symbols_and_overrides() -> None:
    """Explicit families and provider symbols resolve slash-containing and compact markets."""
    alpha = table_source(
        "Alpha",
        {
            "CRYPTO:BTC/USDT": _series("CRYPTO:BTC/USDT", source="Alpha", currency="USD"),
            "CRYPTO:ETH/USD": _series("CRYPTO:ETH/USD", source="Alpha", currency="USD"),
        },
    )
    failed_kraken = table_source(
        "Kraken",
        {
            "BTC/USDT": ValueError("unavailable"),
            "ETHUSD": ValueError("unavailable"),
        },
    )
    long_config = AutoPortfolioConfig(
        weights={"BTC/USDT": 1},
        start="2025-01-02",
        sources={"kraken": failed_kraken, "alpha-vantage": alpha},
        asset_families={"BTC/USDT": "crypto"},
        cache_enabled=False,
    )
    with pytest.warns(RuntimeWarning, match="Alpha"):
        long_pair = AutoPortfolio(long_config)
    compact_config = AutoPortfolioConfig(
        weights={"ETHUSD": 1},
        start="2025-01-02",
        sources={"kraken": failed_kraken, "alpha-vantage": alpha},
        asset_families={"ETHUSD": "crypto"},
        provider_symbols={"ETHUSD": {"alpha-vantage": "CRYPTO:ETH/USD"}},
        cache_enabled=False,
    )
    with pytest.warns(RuntimeWarning, match="Alpha"):
        compact = AutoPortfolio(compact_config)

    assert long_pair.assets["BTC/USDT"].source == "Alpha"
    assert compact.assets["ETHUSD"].source == "Alpha"
    assert alpha.calls[-1][0] == "CRYPTO:ETH/USD"


def test_index_share_class_and_prefixed_routes_keep_their_families() -> None:
    """Index and prefixed symbols use defaults; slash equities require a family."""
    yahoo = table_source(
        "Yahoo",
        {
            "^GSPC": _series("^GSPC", source="Yahoo", currency="USD"),
            "BRK/B": _series("BRK/B", source="Yahoo", currency="USD"),
        },
    )
    alpha = _source("Alpha", tickers=("COMMODITY:GOLD",))
    portfolio = AutoPortfolio(
        AutoPortfolioConfig(
            weights={"^GSPC": 1, "BRK/B": 1, "COMMODITY:GOLD": 1},
            start="2025-01-02",
            sources={"yahoo": yahoo, "alpha-vantage": alpha},
            asset_families={"BRK/B": "equity"},
            cache_enabled=False,
        )
    )

    assert set(portfolio.assets) == {"^GSPC", "BRK/B", "COMMODITY:GOLD"}
    assert {call[0] for call in yahoo.calls} == {"^GSPC", "BRK/B"}
    assert alpha.calls[0][0] == "COMMODITY:GOLD"


def test_ambiguous_long_slash_pair_is_rejected_before_any_fetch() -> None:
    """A long quote asset is never silently routed through the equity provider."""
    yahoo = _source("Yahoo", tickers=("BTC/USDT",))
    config = AutoPortfolioConfig(
        weights={"BTC/USDT": 1},
        start="2025-01-02",
        sources={"yahoo": yahoo},
        cache_enabled=False,
    )
    with pytest.raises(ValueError, match="asset_families"):
        AutoPortfolio(config)
    assert yahoo.calls == []


def test_compact_crypto_requires_an_explicit_alpha_market_symbol() -> None:
    """Alpha routing never guesses how to split a compact crypto symbol."""
    kraken = table_source("Kraken", {"ETHUSD": ValueError("unavailable")})
    alpha = _source("Alpha", tickers=("ETHUSD",))
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


@pytest.mark.parametrize(("ticker", "currency"), [("BTC/USD", "USD"), ("BTC/EUR", "EUR")])
def test_crypto_accepts_only_ecb_fiat_quote_currencies(ticker: str, currency: str) -> None:
    """Crypto quote labels must be fiat currencies published by the ECB."""
    portfolio = AutoPortfolio(
        AutoPortfolioConfig(
            weights={ticker: 1},
            start="2025-01-02",
            sources={"kraken": _source("Kraken", currency=currency, tickers=(ticker,))},
            asset_families={ticker: "crypto"},
            cache_enabled=False,
        )
    )
    assert portfolio.assets[ticker].quote_currency == currency
    source = _source("Kraken", currency="BTC", tickers=("ETH/BTC",))
    config = AutoPortfolioConfig(
        weights={"ETH/BTC": 1},
        start="2025-01-02",
        sources={"kraken": source},
        asset_families={"ETH/BTC": "crypto"},
        cache_enabled=False,
    )
    with pytest.raises(ValueError, match="fiat"):
        AutoPortfolio(config)


@pytest.mark.parametrize(
    "overrides",
    [
        {"quote_currencies": {"BTC/USDT": "USD"}},
        {"quote_units": {"BTC/USDT": "USD"}},
        {"reporting_currency": "USD"},
    ],
)
def test_unknown_crypto_market_allows_legacy_analysis_but_no_monetary_interpretation(
    overrides: dict[str, object],
) -> None:
    """An unknown crypto quote remains valid only when no conversion is requested."""
    source = _source("Kraken", currency=None, tickers=("BTC/USDT",))
    settings: dict[str, object] = {
        "weights": {"BTC/USDT": 1},
        "start": "2025-01-02",
        "sources": {"kraken": source},
        "asset_families": {"BTC/USDT": "crypto"},
        "cache_enabled": False,
    }
    legacy = AutoPortfolio(AutoPortfolioConfig(**settings))  # type: ignore[arg-type]
    assert legacy.assets["BTC/USDT"].quote_currency is None

    settings.update(overrides)
    config = AutoPortfolioConfig(**settings)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="fiat"):
        AutoPortfolio(config)


def test_mixed_or_partially_unknown_currencies_require_explicit_reporting_semantics() -> None:
    """Mixed known currencies need a target, and known/unknown mixes cannot be compared."""
    mixed = table_source(
        "Yahoo",
        {
            "US": _series("US", currency="USD"),
            "EU": _series("EU", currency="EUR"),
        },
    )
    mixed_config = AutoPortfolioConfig(
        weights={"US": 1, "EU": 1},
        start="2025-01-02",
        sources={"yahoo": mixed},
        cache_enabled=False,
    )
    with pytest.raises(ValueError, match="divisa de reporte"):
        AutoPortfolio(mixed_config)

    partial = table_source(
        "Yahoo",
        {
            "AAA": _series("AAA", currency="USD"),
            "BBB": _series("BBB", currency=None),
        },
    )
    partial_config = AutoPortfolioConfig(
        weights={"AAA": 1, "BBB": 1},
        start="2025-01-02",
        sources={"yahoo": partial},
        cache_enabled=False,
    )
    with pytest.raises(ValueError, match="conocidas y desconocidas"):
        AutoPortfolio(partial_config)


@pytest.mark.parametrize("alias", ["GBp", "GBX", "ILA", "ZAc"])
def test_currency_overrides_reject_minor_unit_aliases_before_fetch(alias: str) -> None:
    """An override cannot disguise a quote unit as a currency code."""
    source = _source("Yahoo", currency=None)
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


def test_fx_requests_only_required_eur_legs_and_converts_reporting_prices() -> None:
    """Direct EUR legs cover the target and every foreign asset without inverse quotes."""
    yahoo = table_source(
        "Yahoo",
        {
            "US": _series("US", currency="USD"),
            "UK": _series("UK", currency="GBP"),
        },
    )
    fx = table_source(
        "FX",
        {
            "FX:EUR/USD": make_series(
                "FX:EUR/USD",
                [1.25] * len(MARKET_DATES),
                dates=MARKET_DATES,
                quote_currency="USD",
            ),
            "FX:EUR/GBP": make_series(
                "FX:EUR/GBP",
                [0.8] * len(MARKET_DATES),
                dates=MARKET_DATES,
                quote_currency="GBP",
            ),
        },
    )
    portfolio = AutoPortfolio(
        AutoPortfolioConfig(
            weights={"US": 1, "UK": 1},
            start="2025-01-02",
            end="2025-01-09",
            reporting_currency="GBP",
            sources={"yahoo": yahoo},
            fx_source=fx,
            cache_enabled=False,
        )
    )

    assert [call[0] for call in fx.calls] == ["FX:EUR/GBP", "FX:EUR/USD"]
    converted = portfolio.get_reporting_prices()
    assert converted["US"].iloc[0] == pytest.approx(
        portfolio.assets["US"].prices.iloc[0] / 1.25 * 0.8
    )
    assert converted["UK"].iloc[0] == pytest.approx(portfolio.assets["UK"].prices.iloc[0])


def test_configured_symbols_currency_override_and_subunits_preserve_caller_identity() -> None:
    """Provider aliases and explicit units are normalized once under the requested ticker."""
    custom = _source("Custom", currency=None, unit="GBp", tickers=("ALIAS",))
    portfolio = AutoPortfolio(
        AutoPortfolioConfig(
            weights={"AAA": 1},
            start="2025-01-02",
            sources={"custom": custom},
            ticker_priorities={"AAA": ("custom",)},
            provider_symbols={"AAA": {"custom": "ALIAS"}},
            cache_enabled=False,
        )
    )
    asset = portfolio.assets["AAA"]
    assert custom.calls[0][0] == "ALIAS"
    assert asset.ticker == "AAA"
    assert asset.quote_currency == "GBP"
    assert asset.quote_unit == "GBp"
    assert asset.prices.iloc[0] == pytest.approx(1.05)


def test_unknown_currency_is_legacy_valid_and_exhausted_sources_are_actionable() -> None:
    """A no-metadata portfolio remains usable, while failures explain provider attempts."""
    unknown = _source("Yahoo", currency=None)
    config = AutoPortfolioConfig(
        weights={"AAA": 1},
        start="2025-01-02",
        sources={"yahoo": unknown},
        cache_enabled=False,
    )
    assert AutoPortfolio(config).assets["AAA"].quote_currency is None

    config.sources = {"yahoo": table_source("Broken", {"AAA": ValueError("offline")})}
    with pytest.raises(ValueError, match=r"AAA.*yahoo.*offline"):
        AutoPortfolio(config)


def test_currency_conflict_is_terminal_but_provider_failure_may_fall_back() -> None:
    """Explicit metadata contradictions stop immediately; transport failures do not."""
    conflicting_alpha = _source("Alpha", currency=None)
    config = AutoPortfolioConfig(
        weights={"AAA": 1},
        start="2025-01-02",
        sources={"yahoo": _source("Yahoo"), "alpha-vantage": conflicting_alpha},
        quote_currencies={"AAA": "EUR"},
        cache_enabled=False,
    )
    with pytest.raises(ValueError, match="no coincide"):
        AutoPortfolio(config)
    assert conflicting_alpha.calls == []

    config.sources = {
        "yahoo": table_source("Yahoo", {"AAA": ValueError("offline")}),
        "alpha-vantage": _source("Alpha"),
    }
    config.quote_currencies = {}
    with pytest.warns(RuntimeWarning, match=r"yahoo.*Alpha"):
        portfolio = AutoPortfolio(config)
    assert portfolio.assets["AAA"].quote_currency == "USD"


def test_legacy_metadata_free_cache_is_refreshed_before_currency_interpretation(
    tmp_path: Path,
) -> None:
    """A metadata-free cached row cannot satisfy a requested monetary view."""
    path = tmp_path / "yahoo" / "VOD.L.csv"
    path.parent.mkdir(parents=True)
    dates = pd.bdate_range("2025-01-02", "2025-01-08")
    pd.DataFrame({"Date": dates, "Close": [120.0] * len(dates)}).to_csv(path, index=False)
    raw = table_source(
        "Yahoo",
        {"VOD.L": _series("VOD.L", source="Yahoo", unit="GBp")},
    )

    portfolio = AutoPortfolio(
        AutoPortfolioConfig(
            weights={"VOD.L": 1},
            start="2025-01-02",
            end="2025-01-08",
            sources={"yahoo": raw},
            quote_currencies={"VOD.L": "GBP"},
            cache_dir=tmp_path,
        )
    )

    assert len(raw.calls) == 1
    assert portfolio.assets["VOD.L"].quote_currency == "GBP"
    assert portfolio.assets["VOD.L"].prices.iloc[0] == pytest.approx(1.05)


def test_unknown_raw_unit_requires_explicit_quote_unit_for_monetary_views() -> None:
    """Unknown units block reporting conversions until a caller declares the unit."""
    source = table_source("Yahoo", {"AAA": _series("AAA", values=[120.0] * len(MARKET_DATES))})
    config = AutoPortfolioConfig(
        weights={"AAA": 1},
        start="2025-01-02",
        reporting_currency="EUR",
        sources={"yahoo": source},
        cache_enabled=False,
    )
    with pytest.raises(ValueError, match="quote_units"):
        AutoPortfolio(config)

    for unit, expected in (("GBp", 1.2), ("GBP", 120.0)):
        portfolio = AutoPortfolio(
            AutoPortfolioConfig(
                weights={"AAA": 1},
                start="2025-01-02",
                sources={"yahoo": source},
                quote_units={"AAA": unit},
                cache_enabled=False,
            )
        )
        assert portfolio.assets["AAA"].prices.iloc[0] == pytest.approx(expected)


def test_currency_and_unit_overrides_must_correspond_and_match_provider_metadata() -> None:
    """Unrelated overrides and conflicting provider units are rejected before analysis."""
    unknown = table_source("Yahoo", {"AAA": _series("AAA", values=[120.0] * len(MARKET_DATES))})
    unrelated_config = AutoPortfolioConfig(
        weights={"AAA": 1},
        start="2025-01-02",
        sources={"yahoo": unknown},
        quote_units={"OTHER": "GBp"},
        cache_enabled=False,
    )
    with pytest.raises(ValueError, match="no corresponde"):
        AutoPortfolio(unrelated_config)
    conflicting_config = AutoPortfolioConfig(
        weights={"AAA": 1},
        start="2025-01-02",
        sources={"yahoo": unknown},
        quote_currencies={"AAA": "EUR"},
        quote_units={"AAA": "GBp"},
        cache_enabled=False,
    )
    with pytest.raises(ValueError, match="no coincide"):
        AutoPortfolio(conflicting_config)

    known = table_source("Yahoo", {"BBB": _series("BBB", unit="GBX")})
    unit_config = AutoPortfolioConfig(
        weights={"BBB": 1},
        start="2025-01-02",
        sources={"yahoo": known},
        quote_units={"BBB": "GBp"},
        cache_enabled=False,
    )
    with pytest.raises(ValueError, match="unidad"):
        AutoPortfolio(unit_config)

    canonical = table_source("Yahoo", {"CCC": _series("CCC", currency="GBP")})
    canonical_config = AutoPortfolioConfig(
        weights={"CCC": 1},
        start="2025-01-02",
        sources={"yahoo": canonical},
        quote_units={"CCC": "GBp"},
        cache_enabled=False,
    )
    with pytest.raises(ValueError, match="ya expresa"):
        AutoPortfolio(canonical_config)


def test_cache_refreshes_missing_provider_metadata_once_and_then_reuses_it(
    tmp_path: Path,
) -> None:
    """The AutoPortfolio cache refresh repairs legacy metadata without repeated fetches."""
    ticker = "AAA"
    dates = pd.bdate_range("2024-12-26", periods=12)
    no_metadata = PriceSeries(
        ticker,
        pd.Series([100.0] * len(dates), index=dates),
        source="Yahoo",
    )
    with_metadata = make_series(
        ticker,
        [100.0] * len(dates),
        dates=dates,
        source="Yahoo",
        quote_currency="USD",
    )
    responses: dict[str, PriceSeries] = {ticker: no_metadata}
    upstream = ScriptedPriceSource(
        {
            ticker: lambda _symbol, start, end: filtered_series(
                responses[ticker],
                start,
                end,
            )
        },
        source_name="Yahoo",
    )
    CachedPriceSource(upstream, cache_dir=tmp_path).get_prices(ticker, "2025-01-02", "2025-01-08")
    responses[ticker] = with_metadata

    first = AutoPortfolio(
        AutoPortfolioConfig(
            weights={ticker: 1},
            start="2025-01-02",
            end="2025-01-08",
            reporting_currency="USD",
            sources={"yahoo": upstream},
            cache_dir=tmp_path,
        )
    )
    second = AutoPortfolio(
        AutoPortfolioConfig(
            weights={ticker: 1},
            start="2025-01-02",
            end="2025-01-08",
            reporting_currency="USD",
            sources={"yahoo": upstream},
            cache_dir=tmp_path,
        )
    )

    assert first.assets[ticker].quote_currency == "USD"
    assert second.assets[ticker].quote_currency == "USD"
    assert len(upstream.calls) == 2


def test_supplied_rates_avoid_fx_fetch_and_keep_their_age_contract() -> None:
    """Explicit ExchangeRates are reused, including their max-age metadata."""
    fx = _fx_source()
    portfolio = AutoPortfolio(
        AutoPortfolioConfig(
            weights={"AAA": 1},
            start="2025-01-02",
            end="2025-01-09",
            reporting_currency="EUR",
            sources={"yahoo": _source("Yahoo")},
            fx_source=fx,
            exchange_rates=_rates(),
            cache_enabled=False,
        )
    )

    assert fx.calls == []
    assert portfolio.exchange_rates.max_age_days == 500
    assert not portfolio.get_reporting_prices().empty


def test_supplied_rate_age_must_match_an_explicit_option() -> None:
    """A caller cannot contradict the age already embedded in supplied rates."""
    source = _source("Yahoo")
    rates = _rates()
    config = AutoPortfolioConfig(
        weights={"AAA": 1},
        start="2025-01-02",
        reporting_currency="EUR",
        sources={"yahoo": source},
        exchange_rates=rates,
        fx_max_age_days=4,
        cache_enabled=False,
    )
    with pytest.raises(ValueError, match="fx_max_age_days"):
        AutoPortfolio(config)
    assert source.calls == []


def test_fx_lookback_covers_max_age_and_rejects_a_stale_rate_for_later_prices() -> None:
    """The FX window includes enough history to validate a Friday carry-forward."""
    friday = make_series(
        "FX:EUR/USD",
        [1.25],
        dates=["2025-01-03"],
        quote_currency="USD",
    )
    fx = table_source("FX", {"FX:EUR/USD": friday})
    portfolio = AutoPortfolio(
        AutoPortfolioConfig(
            weights={"AAA": 1},
            start="2025-01-06",
            end="2025-01-07",
            reporting_currency="EUR",
            sources={"yahoo": _source("Yahoo")},
            fx_source=fx,
            fx_lookback_days=3,
            fx_max_age_days=4,
            cache_enabled=False,
        )
    )
    assert pd.Timestamp(fx.calls[0][1]) == pd.Timestamp("2025-01-02")
    assert not portfolio.get_reporting_prices().empty

    later_rate = make_series(
        "FX:EUR/USD",
        [1.25],
        dates=["2025-01-08"],
        quote_currency="USD",
    )
    later = AutoPortfolio(
        AutoPortfolioConfig(
            weights={"AAA": 1},
            start="2025-01-09",
            end="2025-01-11",
            reporting_currency="EUR",
            sources={"yahoo": _source("Yahoo")},
            fx_source=table_source("FX", {"FX:EUR/USD": later_rate}),
            fx_lookback_days=1,
            fx_max_age_days=1,
            cache_enabled=False,
        )
    )
    with pytest.raises(ValueError, match="obsoleto"):
        later.get_reporting_prices()


def test_same_reporting_currency_needs_no_fx_provider() -> None:
    """An all-USD portfolio converts to USD without requesting any exchange rate."""
    fx = table_source("FX", {"FX:EUR/USD": ValueError("must not be called")})
    portfolio = AutoPortfolio(
        AutoPortfolioConfig(
            weights={"AAA": 1},
            start="2025-01-02",
            reporting_currency="USD",
            sources={"yahoo": _source("Yahoo")},
            fx_source=fx,
            cache_enabled=False,
        )
    )
    assert portfolio.get_prices().equals(portfolio.get_reporting_prices())
    assert fx.calls == []


@pytest.mark.parametrize("weights", [{}, {"AAA": 0}, {"AAA": float("nan")}, {"AAA": -1}])
def test_invalid_weights_are_rejected_before_fetch(weights: dict[str, float]) -> None:
    """Empty, non-positive and non-finite compositions never contact a provider."""
    source = _source("Yahoo")
    config = AutoPortfolioConfig(
        weights=weights,
        start="2025-01-02",
        sources={"yahoo": source},
        cache_enabled=False,
    )
    with pytest.raises(ValueError, match=r"activo|ponderaciones"):
        AutoPortfolio(config)
    assert source.calls == []


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
    attribute: str,
    value: object,
    message: str,
) -> None:
    """Invalid settings fail before source creation, regardless of their category."""
    source = _source("Yahoo")
    config = AutoPortfolioConfig(
        weights={"AAA": 1},
        start="2025-01-02",
        sources={"yahoo": source},
        cache_enabled=False,
    )
    setattr(config, attribute, value)
    with pytest.raises((ValueError, TypeError), match=message):
        AutoPortfolio(config)
    assert source.calls == []


def test_rates_without_a_reporting_currency_fail_before_registry_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-empty supplied rates require a target before any default provider exists."""

    def forbidden_registry(**_kwargs: object) -> dict[str, PriceSource]:
        msg = "registry must not be created"
        raise AssertionError(msg)

    monkeypatch.setattr(
        "quantfolio.auto_portfolio.create_price_source_registry",
        forbidden_registry,
    )
    config = AutoPortfolioConfig(
        weights={"AAA": 1},
        start="2025-01-02",
        exchange_rates=_rates(),
    )
    with pytest.raises(ValueError, match="divisa de reporte"):
        AutoPortfolio(config)


def test_provider_identity_errors_are_public_and_never_poison_the_cache(tmp_path: Path) -> None:
    """A provider returning another ticker or FX pair is rejected before caching."""
    wrong_ticker = table_source("Yahoo", {"AAA": _series("OTHER", currency="USD")})
    ticker_config = AutoPortfolioConfig(
        weights={"AAA": 1},
        start="2025-01-02",
        end="2025-01-08",
        sources={"yahoo": wrong_ticker},
        cache_dir=tmp_path,
    )
    with pytest.raises(ValueError, match="ticker"):
        AutoPortfolio(ticker_config)
    assert not list(tmp_path.rglob("*.csv"))

    wrong_pair = table_source(
        "FX",
        {"FX:EUR/USD": _series("FX:EUR/GBP", currency="GBP")},
    )
    pair_config = AutoPortfolioConfig(
        weights={"AAA": 1},
        start="2025-01-02",
        reporting_currency="EUR",
        sources={"yahoo": _source("Yahoo")},
        fx_source=wrong_pair,
        cache_enabled=False,
    )
    with pytest.raises(ValueError, match="ticker"):
        AutoPortfolio(pair_config)
