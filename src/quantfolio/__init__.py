"""Quantfolio: multi-source market data, price analysis and portfolio management."""

from quantfolio.constants import TRADING_DAYS_PER_YEAR
from quantfolio.macro import FredMacroSource, MacroSeries
from quantfolio.models import PriceSeries
from quantfolio.portfolio import Portfolio
from quantfolio.runtime import create_price_source_registry
from quantfolio.simulation import MonteCarloParameters
from quantfolio.sources import (
    AlphaVantagePlan,
    AlphaVantageSource,
    CachedPriceSource,
    KrakenSource,
    PriceSource,
    YahooFinanceSource,
)

__all__ = [
    "TRADING_DAYS_PER_YEAR",
    "AlphaVantagePlan",
    "AlphaVantageSource",
    "CachedPriceSource",
    "FredMacroSource",
    "KrakenSource",
    "MacroSeries",
    "MonteCarloParameters",
    "Portfolio",
    "PriceSeries",
    "PriceSource",
    "YahooFinanceSource",
    "create_price_source_registry",
]
