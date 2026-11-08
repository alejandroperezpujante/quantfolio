"""Automatic composition of market sources, currency rates and portfolios."""

from __future__ import annotations

import math
import re
import warnings
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pandas as pd

from quantfolio.currency import ExchangeRates
from quantfolio.models import PriceSeries, _normalize_currency_code
from quantfolio.portfolio import Portfolio
from quantfolio.runtime import create_price_source_registry
from quantfolio.sources import (
    AlphaVantageSource,
    CachedPriceSource,
    ECBExchangeRateSource,
    PriceSource,
)
from quantfolio.sources.base import naive_timestamp, validate_ticker

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from quantfolio.sources.base import DateLike


@dataclass
class AutoPortfolioConfig:
    """Inputs and optional overrides for an automatically assembled portfolio.

    Provider priority keys are ``equity``, ``crypto``, ``index`` and ``prefixed``;
    ticker-specific priorities take precedence. Custom providers must be present in
    ``sources`` and understand their configured provider-specific symbols.
    """

    weights: Mapping[str, float]
    start: DateLike
    end: DateLike | None = None
    reporting_currency: str | None = None
    sources: Mapping[str, PriceSource] | None = None
    provider_priorities: Mapping[str, Sequence[str]] = field(default_factory=dict)
    ticker_priorities: Mapping[str, Sequence[str]] = field(default_factory=dict)
    provider_symbols: Mapping[str, Mapping[str, str]] = field(default_factory=dict)
    quote_currencies: Mapping[str, str] = field(default_factory=dict)
    cache_enabled: bool = True
    cache_dir: str | Path = "data"
    cache_ttl_days: int = 7
    cache_refresh: bool = False
    fx_source: PriceSource | None = None
    exchange_rates: ExchangeRates | None = None
    fx_lookback_days: int = 7
    fx_max_age_days: int = 4


_DEFAULT_PRIORITIES: dict[str, tuple[str, ...]] = {
    "equity": ("yahoo", "alpha-vantage"),
    "crypto": ("kraken", "alpha-vantage"),
    "index": ("yahoo",),
    "prefixed": ("alpha-vantage",),
}
_CRYPTO_PAIR = re.compile(r"[A-Za-z0-9]{1,20}/[A-Za-z]{3}")


def _family(ticker: str) -> str:
    """Select only routes whose symbol convention is known."""
    if ":" in ticker:
        return "prefixed"
    if ticker.startswith("^"):
        return "index"
    return "crypto" if _CRYPTO_PAIR.fullmatch(ticker) else "equity"


def _validate_config(config: AutoPortfolioConfig) -> None:
    """Reject invalid settings before creating sources or making requests."""
    if not config.weights:
        msg = "La cartera debe contener al menos un activo."
        raise ValueError(msg)
    for ticker in config.weights:
        if validate_ticker(ticker) != ticker:
            msg = "Los tickers no pueden contener espacios exteriores."
            raise ValueError(msg)
    if any(not math.isfinite(weight) or weight < 0 for weight in config.weights.values()):
        msg = "Las ponderaciones deben ser finitas y no negativas."
        raise ValueError(msg)
    if sum(config.weights.values()) <= 0:
        msg = "La suma de las ponderaciones debe ser positiva."
        raise ValueError(msg)


def _validate_dates_and_currencies(config: AutoPortfolioConfig) -> None:
    """Validate the date interval and currency settings."""
    start = naive_timestamp(config.start)
    if pd.isna(start) or (
        config.end is not None
        and (pd.isna(naive_timestamp(config.end)) or naive_timestamp(config.end) <= start)
    ):
        msg = "El intervalo de fechas no es válido."
        raise ValueError(msg)
    if config.reporting_currency is not None:
        _normalize_currency_code(config.reporting_currency, "La divisa de reporte")
    for ticker, currency in config.quote_currencies.items():
        if ticker not in config.weights:
            msg = f"La divisa indicada no corresponde al activo {ticker}."
            raise ValueError(msg)
        _normalize_currency_code(currency, "La divisa de cotización")


def _validate_options(config: AutoPortfolioConfig) -> None:
    """Validate cache, FX and provider overrides."""
    for value, name in (
        (config.cache_ttl_days, "cache_ttl_days"),
        (config.fx_lookback_days, "fx_lookback_days"),
        (config.fx_max_age_days, "fx_max_age_days"),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            msg = f"{name} debe ser un entero no negativo."
            raise ValueError(msg)
    if set(config.provider_priorities) - set(_DEFAULT_PRIORITIES):
        msg = "La prioridad incluye una familia de activos desconocida."
        raise ValueError(msg)
    if (set(config.ticker_priorities) | set(config.provider_symbols)) - set(config.weights):
        msg = "La configuración de proveedor incluye activos desconocidos."
        raise ValueError(msg)
    if any(
        not order or len(set(order)) != len(order)
        for order in (*config.provider_priorities.values(), *config.ticker_priorities.values())
    ):
        msg = "Cada prioridad de proveedores debe ser no vacía y sin duplicados."
        raise ValueError(msg)
    exchange_rates: object = config.exchange_rates
    if exchange_rates is not None and not isinstance(exchange_rates, ExchangeRates):
        msg = "exchange_rates debe ser una colección ExchangeRates."
        raise TypeError(msg)


def _adapt_series(asset: PriceSeries, ticker: str, currency: str | None) -> PriceSeries:
    """Retain quote-unit provenance without converting already normalized prices twice."""
    if asset.quote_currency is None and currency is None:
        msg = f"No se conoce la divisa de cotización de {ticker}; indica quote_currencies."
        raise ValueError(msg)
    if (
        currency is not None
        and asset.quote_currency is not None
        and _normalize_currency_code(currency, "La divisa de cotización") != asset.quote_currency
    ):
        msg = f"La divisa indicada para {ticker} no coincide con la del proveedor."
        raise ValueError(msg)
    return PriceSeries(
        ticker=ticker,
        prices=asset.prices / asset.quote_unit_factor,
        source=asset.source,
        quote_currency=currency if currency is not None else asset.quote_currency,
        quote_unit=asset.quote_unit,
    )


class _CheckedPriceSource(PriceSource):
    """Check provider identity before a response can be written to the cache."""

    def __init__(self, source: PriceSource) -> None:
        self._source = source

    @property
    def name(self) -> str:
        """Separate Alpha Vantage caches by the plan's pricing semantics."""
        if isinstance(self._source, AlphaVantageSource):
            return f"{self._source.name} ({self._source.plan.value})"
        return self._source.name

    def get_prices(self, ticker: str, start: DateLike, end: DateLike | None = None) -> PriceSeries:
        """Reject a response for an instrument other than the requested symbol."""
        asset = self._source.get_prices(ticker, start, end)
        if asset.ticker != ticker:
            msg = f"El ticker recibido {asset.ticker} no coincide con el solicitado {ticker}."
            raise ValueError(msg)
        return asset


class _Assembler:
    """Resolve sources and fetch the inputs needed by a portfolio."""

    def __init__(self, config: AutoPortfolioConfig) -> None:
        self.config = config
        self.sources = (
            config.sources
            if config.sources is not None
            else create_price_source_registry(cache_dir=config.cache_dir)
        )
        self.cached: dict[str, PriceSource] = {}

    def source(self, key: str) -> PriceSource:
        """Return a source with the configured cache wrapper, constructed on demand."""
        source = _CheckedPriceSource(self.sources[key])
        if not self.config.cache_enabled:
            return source
        cache_key = f"{key}:{source.name}"
        if cache_key not in self.cached:
            self.cached[cache_key] = CachedPriceSource(
                source,
                cache_dir=self.config.cache_dir,
                ttl_days=self.config.cache_ttl_days,
                refresh=self.config.cache_refresh,
            )
        return self.cached[cache_key]

    def asset(self, ticker: str) -> PriceSeries:
        """Fetch an asset using explicit priorities or safe built-in routes."""
        family = _family(ticker)
        priority = self.config.ticker_priorities.get(
            ticker, self.config.provider_priorities.get(family, _DEFAULT_PRIORITIES[family])
        )
        override = self.config.quote_currencies.get(ticker)
        errors: list[str] = []
        for key in priority:
            if key not in self.sources:
                errors.append(f"{key}: no disponible")
                continue
            symbol = self.config.provider_symbols.get(ticker, {}).get(key, ticker)
            if key == "alpha-vantage" and family == "crypto" and symbol == ticker:
                symbol = f"CRYPTO:{ticker}"
            source = self.source(key)
            try:
                asset = source.get_prices(symbol, self.config.start, self.config.end)
                if (
                    asset.quote_currency is None
                    and override is None
                    and self.config.cache_enabled
                    and asset.source.endswith(" (cache)")
                ):
                    refreshed = CachedPriceSource(
                        _CheckedPriceSource(self.sources[key]),
                        cache_dir=self.config.cache_dir,
                        ttl_days=self.config.cache_ttl_days,
                        refresh=True,
                    )
                    asset = refreshed.get_prices(symbol, self.config.start, self.config.end)
                result = _adapt_series(asset, ticker, override)
            except (ValueError, OSError) as exc:
                errors.append(f"{key}: {exc}")
                continue
            if errors:
                warnings.warn(
                    f"No se pudo usar {', '.join(errors)}; se utiliza {source.name}. "
                    "Los precios pueden diferir por ajustes o mercado de cotización.",
                    RuntimeWarning,
                    stacklevel=3,
                )
            return result
        msg = f"No se pudo obtener {ticker}: {'; '.join(errors)}"
        raise ValueError(msg)

    def rates(self, assets: Mapping[str, PriceSeries]) -> ExchangeRates:
        """Fetch only the EUR-based legs needed for the reporting currency."""
        if self.config.exchange_rates is not None:
            return self.config.exchange_rates
        target = self.config.reporting_currency
        if target is not None:
            target = _normalize_currency_code(target, "La divisa de reporte")
        currencies = {asset.quote_currency for asset in assets.values()}
        if target is None or currencies == {target}:
            return ExchangeRates()
        required = {
            currency
            for currency in currencies | {target}
            if currency is not None and currency != "EUR"
        }
        pairs = [f"FX:EUR/{currency}" for currency in sorted(required)]
        source = (
            self.config.fx_source if self.config.fx_source is not None else ECBExchangeRateSource()
        )
        source = _CheckedPriceSource(source)
        if self.config.cache_enabled:
            source = CachedPriceSource(
                source,
                cache_dir=self.config.cache_dir,
                ttl_days=min(self.config.cache_ttl_days, self.config.fx_max_age_days),
                refresh=self.config.cache_refresh,
            )
        start = (
            (naive_timestamp(self.config.start) - pd.Timedelta(days=self.config.fx_lookback_days))
            .date()
            .isoformat()
        )
        return ExchangeRates.from_source(
            source, pairs, start, self.config.end, max_age_days=self.config.fx_max_age_days
        )


class AutoPortfolio(Portfolio):
    """A portfolio assembled from a compact configuration and market-data sources."""

    def __init__(self, config: AutoPortfolioConfig) -> None:
        """Validate settings, retrieve asset and FX histories, and initialize analytics."""
        _validate_config(config)
        _validate_dates_and_currencies(config)
        _validate_options(config)
        assembler = _Assembler(config)
        assets = {ticker: assembler.asset(ticker) for ticker in config.weights}
        if (
            config.reporting_currency is None
            and len({asset.quote_currency for asset in assets.values()}) > 1
        ):
            msg = "La cartera mezcla divisas; indica una divisa de reporte."
            raise ValueError(msg)
        rates = assembler.rates(assets)
        super().__init__(
            assets=assets,
            weights=dict(config.weights),
            reporting_currency=config.reporting_currency,
            exchange_rates=rates,
        )
