"""Runtime composition for the available market-data sources."""

import os
import warnings
from types import MappingProxyType
from typing import TYPE_CHECKING

from quantfolio.sources import KrakenSource, PriceSource, YahooFinanceSource
from quantfolio.sources.alpha_vantage.capabilities import create_alpha_vantage_source
from quantfolio.sources.alpha_vantage.client import AlphaVantageError

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path


def create_price_source_registry(
    *,
    cache_dir: str | Path = "data",
    environ: Mapping[str, str] | None = None,
) -> Mapping[str, PriceSource]:
    """Return the immutable registry of configured price sources.

    Yahoo Finance and Kraken are always available. Alpha Vantage is included only when
    ``ALPHA_VANTAGE_API_KEY`` is present and its live validation succeeds.

    Args:
        cache_dir: Root directory for the optional Alpha Vantage capability cache.
        environ: Environment mapping to read at invocation; defaults to ``os.environ``.

    Returns:
        An immutable mapping keyed by ``yahoo``, ``kraken``, and optionally
        ``alpha-vantage``.

    """
    environment = os.environ if environ is None else environ
    sources: dict[str, PriceSource] = {
        "yahoo": YahooFinanceSource(),
        "kraken": KrakenSource(),
    }
    api_key = environment.get("ALPHA_VANTAGE_API_KEY", "").strip()
    if not api_key:
        warnings.warn(
            "ALPHA_VANTAGE_API_KEY no está configurada; se continúa sin Alpha Vantage.",
            RuntimeWarning,
            stacklevel=2,
        )
        return MappingProxyType(sources)
    try:
        sources["alpha-vantage"] = create_alpha_vantage_source(api_key, cache_dir=cache_dir)
    except AlphaVantageError as error:
        warnings.warn(
            f"No se pudo inicializar Alpha Vantage: {error}",
            RuntimeWarning,
            stacklevel=2,
        )
    return MappingProxyType(sources)
