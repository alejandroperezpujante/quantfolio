"""Quantfolio: multi-source market data, price analysis and portfolio management."""

from quantfolio.auto_portfolio import AutoPortfolio, AutoPortfolioConfig
from quantfolio.constants import TRADING_DAYS_PER_YEAR
from quantfolio.currency import ExchangeRateObservation, ExchangeRates
from quantfolio.macro import FredMacroSource, MacroSeries
from quantfolio.models import PriceSeries
from quantfolio.portfolio import Portfolio
from quantfolio.risk import (
    compound_annual_growth,
    drawdown_series,
    drift_standard_error,
    historical_cvar,
    historical_var,
    max_drawdown,
    sharpe_ratio,
)
from quantfolio.runtime import create_price_source_registry
from quantfolio.simulation import MonteCarloParameters
from quantfolio.sources import (
    AlphaVantagePlan,
    AlphaVantageSource,
    CachedPriceSource,
    ECBExchangeRateSource,
    KrakenSource,
    PriceSource,
    YahooFinanceSource,
)

__all__ = [
    "TRADING_DAYS_PER_YEAR",
    "AlphaVantagePlan",
    "AlphaVantageSource",
    "AutoPortfolio",
    "AutoPortfolioConfig",
    "CachedPriceSource",
    "ECBExchangeRateSource",
    "ExchangeRateObservation",
    "ExchangeRates",
    "FredMacroSource",
    "KrakenSource",
    "MacroSeries",
    "MonteCarloParameters",
    "Portfolio",
    "PriceSeries",
    "PriceSource",
    "YahooFinanceSource",
    "compound_annual_growth",
    "create_price_source_registry",
    "drawdown_series",
    "drift_standard_error",
    "historical_cvar",
    "historical_var",
    "max_drawdown",
    "sharpe_ratio",
]
