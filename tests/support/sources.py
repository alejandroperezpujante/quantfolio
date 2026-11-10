"""Scripted price sources used to isolate callers from provider mechanics."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

import pandas as pd

from quantfolio.models import PriceSeries
from quantfolio.sources.base import DateLike, PriceSource, validate_ticker

ResponseFactory = Callable[[str, DateLike, DateLike | None], PriceSeries]
ScriptedResponse = PriceSeries | Exception | ResponseFactory


@dataclass
class ScriptedPriceSource(PriceSource):
    """Price source whose responses are supplied by each test."""

    responses: Mapping[str, ScriptedResponse]
    source_name: str = "Stub"
    namespace: str | None = None
    calls: list[tuple[str, DateLike, DateLike | None]] = field(default_factory=list)

    @property
    def name(self) -> str:
        """Return the configured provider name."""
        return self.source_name

    @property
    def cache_namespace(self) -> str:
        """Return an optional semantic namespace for cache isolation tests."""
        return self.namespace if self.namespace is not None else super().cache_namespace

    def get_prices(
        self,
        ticker: str,
        start: DateLike,
        end: DateLike | None = None,
    ) -> PriceSeries:
        """Return the configured response for ``ticker``."""
        symbol = validate_ticker(ticker)
        self.calls.append((symbol, start, end))
        response = self.responses[symbol]
        if isinstance(response, Exception):
            raise response
        if callable(response):
            return response(symbol, start, end)
        return response


def filtered_series(
    asset: PriceSeries,
    start: DateLike,
    end: DateLike | None = None,
) -> PriceSeries:
    """Return a copy of ``asset`` restricted to the inclusive-start, exclusive-end window."""
    mask = asset.prices.index >= pd.Timestamp(start)
    if end is not None:
        mask &= asset.prices.index < pd.Timestamp(end)
    window = asset.prices[mask]
    if window.empty:
        msg = f"No se han encontrado datos para {asset.ticker}."
        raise ValueError(msg)
    return PriceSeries(
        ticker=asset.ticker,
        prices=window / asset.quote_unit_factor,
        source=asset.source,
        quote_currency=asset.quote_currency,
        quote_unit=asset.quote_unit,
    )


def table_source(
    name: str,
    responses: Mapping[str, PriceSeries | Exception],
    *,
    namespace: str | None = None,
) -> ScriptedPriceSource:
    """Return a source that serves and windows a table of public price series."""
    configured: dict[str, ScriptedResponse] = {}
    for ticker, response in responses.items():
        if isinstance(response, Exception):
            configured[ticker] = response
        else:

            def response_for(
                _symbol: str,
                start: DateLike,
                end: DateLike | None,
                *,
                asset: PriceSeries = response,
            ) -> PriceSeries:
                return filtered_series(asset, start, end)

            configured[ticker] = response_for
    return ScriptedPriceSource(configured, source_name=name, namespace=namespace)
