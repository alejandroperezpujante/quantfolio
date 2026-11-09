"""Automatic composition of market sources, currency rates and portfolios."""

from __future__ import annotations

import math
import re
import warnings
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pandas as pd

from quantfolio.currency import ExchangeRates
from quantfolio.models import PriceSeries
from quantfolio.portfolio import Portfolio
from quantfolio.quote_metadata import (
    ECB_FIAT_CURRENCIES,
    _normalize_currency_code,
    _normalize_quote_unit,
)
from quantfolio.runtime import create_price_source_registry
from quantfolio.sources import (
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
    quote_units: Mapping[str, str] = field(default_factory=dict)
    asset_families: Mapping[str, str] = field(default_factory=dict)
    cache_enabled: bool = True
    cache_dir: str | Path = "data"
    cache_ttl_days: int = 7
    cache_refresh: bool = False
    fx_source: PriceSource | None = None
    exchange_rates: ExchangeRates | None = None
    fx_lookback_days: int = 7
    fx_max_age_days: int | None = None


_DEFAULT_PRIORITIES: dict[str, tuple[str, ...]] = {
    "equity": ("yahoo", "alpha-vantage"),
    "crypto": ("kraken", "alpha-vantage"),
    "index": ("yahoo",),
    "prefixed": ("alpha-vantage",),
}
_ALLOWED_ASSET_FAMILIES = frozenset({"equity", "crypto", "index", "prefixed"})
_DEFAULT_FX_MAX_AGE_DAYS = 4
_MIN_ALPHANUMERIC_QUOTE_LENGTH = 4
_QUOTE_CURRENCY_LABEL = "La divisa de cotización"
_SLASH_PAIR = re.compile(r"[A-Za-z0-9]{1,20}/([A-Za-z0-9]{1,20})")
_CRYPTO_PAIR = re.compile(r"[A-Za-z0-9]{1,20}/[A-Za-z]{3}")


class _QuoteCurrencyConflictError(ValueError):
    """A provider currency disagrees with an explicit user override."""


@dataclass(frozen=True)
class _RequestedQuote:
    """Normalized explicit quote metadata requested for one asset."""

    currency: str | None
    unit: str | None
    unit_currency: str | None
    factor: float


def _family(ticker: str, override: str | None = None) -> str:
    """Select only routes whose symbol convention is known."""
    if override is not None:
        family = override
    elif ":" in ticker:
        family = "prefixed"
    elif ticker.startswith("^"):
        family = "index"
    else:
        pair = _SLASH_PAIR.fullmatch(ticker)
        if pair is not None and len(pair.group(1)) >= _MIN_ALPHANUMERIC_QUOTE_LENGTH:
            msg = f"El par {ticker} requiere una familia explícita en asset_families."
            raise ValueError(msg)
        family = "crypto" if _CRYPTO_PAIR.fullmatch(ticker) else "equity"
    return family


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
        _normalize_currency_code(currency, _QUOTE_CURRENCY_LABEL)
    for ticker, unit in config.quote_units.items():
        if ticker not in config.weights:
            msg = f"La unidad indicada no corresponde al activo {ticker}."
            raise ValueError(msg)
        _, unit_currency, _ = _normalize_quote_unit(unit)
        override_currency = config.quote_currencies.get(ticker)
        if (
            override_currency is not None
            and _normalize_currency_code(
                override_currency,
                _QUOTE_CURRENCY_LABEL,
            )
            != unit_currency
        ):
            msg = f"La unidad indicada para {ticker} no coincide con su divisa."
            raise ValueError(msg)


def _validate_numeric_options(config: AutoPortfolioConfig) -> None:
    """Validate cache and FX integer settings."""
    for value, name in (
        (config.cache_ttl_days, "cache_ttl_days"),
        (config.fx_lookback_days, "fx_lookback_days"),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            msg = f"{name} debe ser un entero no negativo."
            raise ValueError(msg)
    if config.fx_max_age_days is not None and (
        isinstance(config.fx_max_age_days, bool)
        or not isinstance(config.fx_max_age_days, int)
        or config.fx_max_age_days < 0
    ):
        msg = "fx_max_age_days debe ser un entero no negativo."
        raise ValueError(msg)


def _validate_provider_options(config: AutoPortfolioConfig) -> None:
    """Validate provider priorities, asset families and provider overrides."""
    if set(config.provider_priorities) - set(_DEFAULT_PRIORITIES):
        msg = "La prioridad incluye una familia de activos desconocida."
        raise ValueError(msg)
    if (set(config.ticker_priorities) | set(config.provider_symbols)) - set(config.weights):
        msg = "La configuración de proveedor incluye activos desconocidos."
        raise ValueError(msg)
    if set(config.asset_families) - set(config.weights):
        msg = "La familia indicada no corresponde a ningún activo."
        raise ValueError(msg)
    if any(
        not isinstance(family, str) or family not in _ALLOWED_ASSET_FAMILIES
        for family in config.asset_families.values()
    ):
        msg = "La familia de activo debe ser equity, crypto, index o prefixed."
        raise ValueError(msg)
    for ticker in config.weights:
        _family(ticker, config.asset_families.get(ticker))
    if any(
        not order or len(set(order)) != len(order)
        for order in (*config.provider_priorities.values(), *config.ticker_priorities.values())
    ):
        msg = "Cada prioridad de proveedores debe ser no vacía y sin duplicados."
        raise ValueError(msg)


def _validate_exchange_rate_options(config: AutoPortfolioConfig) -> None:
    """Validate supplied rates and their age contract."""
    exchange_rates: object = config.exchange_rates
    if exchange_rates is not None and not isinstance(exchange_rates, ExchangeRates):
        msg = "exchange_rates debe ser una colección ExchangeRates."
        raise TypeError(msg)
    if exchange_rates is not None and exchange_rates.rates and config.reporting_currency is None:
        msg = "Debes indicar una divisa de reporte para usar tipos de cambio."
        raise ValueError(msg)
    if (
        exchange_rates is not None
        and config.fx_max_age_days is not None
        and config.fx_max_age_days != exchange_rates.max_age_days
    ):
        msg = "fx_max_age_days debe coincidir con el máximo de exchange_rates cuando se especifica."
        raise ValueError(msg)


def _validate_options(config: AutoPortfolioConfig) -> None:
    """Validate cache, FX and provider overrides before any source is created."""
    _validate_numeric_options(config)
    _validate_provider_options(config)
    _validate_exchange_rate_options(config)


def _effective_fx_max_age_days(config: AutoPortfolioConfig) -> int:
    """Return the supplied or downloaded FX carry-forward limit."""
    if config.fx_max_age_days is None:
        return _DEFAULT_FX_MAX_AGE_DAYS
    return config.fx_max_age_days


def _unit_identity(unit: str) -> str:
    """Return a case-insensitive unit identity that still distinguishes pence from pounds."""
    return "GBp" if unit == "GBp" else unit.upper()


def _validate_crypto_quote(asset: PriceSeries, ticker: str, *, monetary_view: bool) -> None:
    """Reject non-fiat crypto labels and fiat interpretations of an unknown market."""
    if asset.quote_currency is None:
        if monetary_view:
            msg = (
                f"No se puede confirmar la divisa fiat de cotización de {ticker}; "
                "proporciona una serie cuyo mercado ya esté expresado en fiat."
            )
            raise ValueError(msg)
        return
    if asset.quote_currency not in ECB_FIAT_CURRENCIES:
        msg = (
            f"El proveedor etiquetó {ticker} con {asset.quote_currency}, "
            "que no es una divisa fiat del BCE."
        )
        raise ValueError(msg)


def _requested_quote(currency: str | None, quote_unit: str | None) -> _RequestedQuote:
    """Normalize the explicitly requested currency and quote unit."""
    requested_currency = (
        _normalize_currency_code(currency, _QUOTE_CURRENCY_LABEL) if currency is not None else None
    )
    if quote_unit is None:
        return _RequestedQuote(requested_currency, None, None, 1.0)
    unit, unit_currency, factor = _normalize_quote_unit(quote_unit)
    return _RequestedQuote(requested_currency, unit, unit_currency, factor)


def _validate_quote_conflicts(
    asset: PriceSeries,
    ticker: str,
    requested: _RequestedQuote,
) -> None:
    """Reject explicit metadata that contradicts known provider metadata."""
    if (
        requested.currency is not None
        and asset.quote_currency is not None
        and requested.currency != asset.quote_currency
    ):
        msg = f"La divisa indicada para {ticker} no coincide con la del proveedor."
        raise _QuoteCurrencyConflictError(msg)
    if (
        requested.unit is not None
        and asset.quote_unit is not None
        and _unit_identity(requested.unit) != _unit_identity(asset.quote_unit)
    ):
        msg = f"La unidad indicada para {ticker} no coincide con la del proveedor."
        raise _QuoteCurrencyConflictError(msg)


def _validate_supplied_unit(
    asset: PriceSeries,
    ticker: str,
    requested: _RequestedQuote,
) -> None:
    """Reject reapplying a minor unit to an already normalized provider series."""
    if (
        requested.unit is not None
        and asset.quote_unit is None
        and asset.quote_currency is not None
        and (requested.factor < 1.0 or requested.unit_currency != asset.quote_currency)
    ):
        msg = (
            f"El proveedor ya expresa {ticker} en {asset.quote_currency}; "
            "no se puede reinterpretar como una unidad menor."
        )
        raise _QuoteCurrencyConflictError(msg)


def _validate_known_quote(
    asset: PriceSeries,
    ticker: str,
    requested: _RequestedQuote,
    *,
    reporting_currency: str | None,
) -> None:
    """Require explicit unit metadata before a monetary interpretation when it is unknown."""
    if (
        requested.unit is None
        and asset.quote_currency is None
        and asset.quote_unit is None
        and (reporting_currency is not None or requested.currency is not None)
    ):
        msg = f"No se conoce la unidad de cotización de {ticker}; indica su unidad en quote_units."
        raise ValueError(msg)


def _adapt_series(
    asset: PriceSeries,
    ticker: str,
    currency: str | None,
    quote_unit: str | None,
    *,
    reporting_currency: str | None,
) -> PriceSeries:
    """Apply explicit metadata without relabeling or converting a normalized series twice."""
    requested = _requested_quote(currency, quote_unit)
    _validate_quote_conflicts(asset, ticker, requested)
    _validate_supplied_unit(asset, ticker, requested)
    _validate_known_quote(
        asset,
        ticker,
        requested,
        reporting_currency=reporting_currency,
    )
    final_currency = requested.currency or asset.quote_currency or requested.unit_currency
    final_unit = requested.unit or asset.quote_unit
    if final_currency is None:
        return PriceSeries(
            ticker=ticker,
            prices=asset.prices,
            source=asset.source,
        )
    raw_prices = asset.prices / asset.quote_unit_factor
    return PriceSeries(
        ticker=ticker,
        prices=raw_prices,
        source=asset.source,
        quote_currency=final_currency,
        quote_unit=final_unit,
    )


class _CheckedPriceSource(PriceSource):
    """Check provider identity before a response can be written to the cache."""

    def __init__(self, source: PriceSource) -> None:
        self._source = source

    @property
    def name(self) -> str:
        """Return the wrapped provider's visible name."""
        return self._source.name

    @property
    def cache_namespace(self) -> str:
        """Delegate cache identity to the wrapped provider's current semantics."""
        return self._source.cache_namespace

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
        family = _family(ticker, self.config.asset_families.get(ticker))
        priority = self.config.ticker_priorities.get(
            ticker, self.config.provider_priorities.get(family, _DEFAULT_PRIORITIES[family])
        )
        override = self.config.quote_currencies.get(ticker)
        unit = self.config.quote_units.get(ticker)
        monetary_view = (
            self.config.reporting_currency is not None or override is not None or unit is not None
        )
        errors: list[str] = []
        for key in priority:
            if key not in self.sources:
                errors.append(f"{key}: no disponible")
                continue
            try:
                asset, source_name = self._fetch_candidate(
                    key,
                    ticker,
                    family,
                    monetary_view=monetary_view,
                )
            except (ValueError, OSError) as exc:
                errors.append(f"{key}: {exc}")
                continue
            if family == "crypto":
                _validate_crypto_quote(asset, ticker, monetary_view=monetary_view)
            result = _adapt_series(
                asset,
                ticker,
                override,
                unit,
                reporting_currency=self.config.reporting_currency,
            )
            if errors:
                warnings.warn(
                    f"No se pudo usar {', '.join(errors)}; se utiliza {source_name}. "
                    "Los precios pueden diferir por ajustes o mercado de cotización.",
                    RuntimeWarning,
                    stacklevel=3,
                )
            return result
        msg = f"No se pudo obtener {ticker}: {'; '.join(errors)}"
        raise ValueError(msg)

    def _fetch_candidate(
        self,
        key: str,
        ticker: str,
        family: str,
        *,
        monetary_view: bool,
    ) -> tuple[PriceSeries, str]:
        """Fetch one provider candidate, refreshing stale unit metadata when needed."""
        symbol = self._requested_symbol(key, ticker, family)
        source = self.source(key)
        asset = source.get_prices(symbol, self.config.start, self.config.end)
        asset = self._refresh_cached_metadata(
            key,
            asset,
            symbol,
            monetary_view=monetary_view,
        )
        return asset, source.name

    def _requested_symbol(self, key: str, ticker: str, family: str) -> str:
        """Return the provider-specific symbol without guessing compact crypto pairs."""
        configured_symbol = self.config.provider_symbols.get(ticker, {}).get(key)
        if key == "alpha-vantage" and family == "crypto" and configured_symbol is None:
            if "/" not in ticker:
                msg = "un símbolo compacto requiere provider_symbols con su par"
                raise ValueError(msg)
            return f"CRYPTO:{ticker}"
        return configured_symbol if configured_symbol is not None else ticker

    def _refresh_cached_metadata(
        self,
        key: str,
        asset: PriceSeries,
        symbol: str,
        *,
        monetary_view: bool,
    ) -> PriceSeries:
        """Refetch a cached series once when monetary analysis needs missing quote metadata."""
        if not (
            asset.quote_currency is None
            and monetary_view
            and self.config.cache_enabled
            and asset.source.endswith(" (cache)")
        ):
            return asset
        refreshed = CachedPriceSource(
            _CheckedPriceSource(self.sources[key]),
            cache_dir=self.config.cache_dir,
            ttl_days=self.config.cache_ttl_days,
            refresh=True,
        )
        return refreshed.get_prices(symbol, self.config.start, self.config.end)

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
        effective_max_age_days = _effective_fx_max_age_days(self.config)
        if self.config.cache_enabled:
            source = CachedPriceSource(
                source,
                cache_dir=self.config.cache_dir,
                ttl_days=min(self.config.cache_ttl_days, effective_max_age_days),
                refresh=self.config.cache_refresh,
            )
        lookback_days = max(self.config.fx_lookback_days, effective_max_age_days)
        start = (
            (naive_timestamp(self.config.start) - pd.Timedelta(days=lookback_days))
            .date()
            .isoformat()
        )
        return ExchangeRates.from_source(
            source,
            pairs,
            start,
            self.config.end,
            max_age_days=effective_max_age_days,
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
        currencies = {
            asset.quote_currency for asset in assets.values() if asset.quote_currency is not None
        }
        if config.reporting_currency is None and len(currencies) > 1:
            msg = "La cartera mezcla divisas; indica una divisa de reporte."
            raise ValueError(msg)
        rates = assembler.rates(assets)
        super().__init__(
            assets=assets,
            weights=dict(config.weights),
            reporting_currency=config.reporting_currency,
            exchange_rates=rates,
        )
