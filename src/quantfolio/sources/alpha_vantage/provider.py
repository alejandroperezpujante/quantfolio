"""Historical daily price source backed by the Alpha Vantage REST API."""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, cast

import pandas as pd

from quantfolio.models import PriceSeries
from quantfolio.quote_metadata import ECB_FIAT_CURRENCIES
from quantfolio.sources.alpha_vantage.capabilities import (
    AlphaVantageCapabilities,
    AlphaVantageCapabilityStore,
    AlphaVantagePlan,
)
from quantfolio.sources.alpha_vantage.client import (
    AlphaVantageClient,
    AlphaVantageError,
    AlphaVantageErrorCategory,
)
from quantfolio.sources.base import PriceSource, naive_timestamp, validate_ticker

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    from quantfolio.sources.base import DateLike

#: Daily equity endpoint served to free keys.
FREE_EQUITY_FUNCTION = "TIME_SERIES_DAILY"

#: Adjusted daily equity endpoint served to premium keys.
PREMIUM_EQUITY_FUNCTION = "TIME_SERIES_DAILY_ADJUSTED"

#: Daily index endpoint, gated by both the premium plan and the index entitlement.
INDEX_FUNCTION = "INDEX_DATA"

#: Daily foreign-exchange endpoint, always requesting the complete history.
FX_FUNCTION = "FX_DAILY"

#: Daily digital-currency endpoint.
CRYPTO_FUNCTION = "DIGITAL_CURRENCY_DAILY"

#: Daily gold and silver endpoint.
GOLD_SILVER_FUNCTION = "GOLD_SILVER_HISTORY"

#: Free keys only receive the latest observation count of a compact response.
FREE_COMPACT_OBSERVATIONS = 100

#: Provider provenance recorded for each equity mode.
FREE_EQUITY_PROVENANCE = "Alpha Vantage (free, raw)"
PREMIUM_EQUITY_PROVENANCE = "Alpha Vantage (premium, adjusted)"

_DAILY_INTERVAL = "daily"
_COMPACT_OUTPUT_SIZE = "compact"
_FULL_OUTPUT_SIZE = "full"

#: Decoded JSON object handled by the response parsers.
_JsonObject = Mapping[str, object]


def _as_json_object(value: object) -> _JsonObject:
    """Return the JSON-object view of a value already validated as a mapping."""
    return cast("Mapping[str, object]", value)


#: Payload keys that hold the daily observations of each endpoint family.
_EQUITY_TABLE = "Time Series (Daily)"
_FX_TABLE = "Time Series FX (Daily)"
_CRYPTO_TABLE = "Time Series (Digital Currency Daily)"
_ARRAY_TABLE = "data"

#: Price columns of the daily endpoint families.
_RAW_CLOSE_FIELD = "4. close"
_ADJUSTED_CLOSE_FIELD = "5. adjusted close"
_INDEX_CLOSE_FIELD = "close"
_COMMODITY_VALUE_FIELD = "value"
_COMMODITY_PRICE_FIELD = "price"

#: Convenience index aliases mapped to their Alpha Vantage catalog symbol.
_INDEX_ALIASES = {"SP500": "SPX"}

#: Accepted index symbols: catalog identifiers without separators or traversal.
_INDEX_SYMBOL_PATTERN = re.compile(r"[A-Za-z0-9]{1,10}")

#: Accepted FX pairs: two three-letter currency codes joined by one slash.
_FX_PAIR_PATTERN = re.compile(r"([A-Za-z]{3})/([A-Za-z]{3})")

#: Accepted crypto pairs: alphanumeric symbol and market joined by one slash.
_CRYPTO_PAIR_PATTERN = re.compile(r"([A-Za-z0-9]{1,20})/([A-Za-z0-9]{1,20})")

#: Approved commodity aliases mapped to function, extra parameters and price field.
_COMMODITY_SPECS: dict[str, tuple[str, dict[str, str], str]] = {
    "WTI": ("WTI", {"interval": _DAILY_INTERVAL}, _COMMODITY_VALUE_FIELD),
    "BRENT": ("BRENT", {"interval": _DAILY_INTERVAL}, _COMMODITY_VALUE_FIELD),
    "NATURAL_GAS": ("NATURAL_GAS", {"interval": _DAILY_INTERVAL}, _COMMODITY_VALUE_FIELD),
    "GOLD": (
        GOLD_SILVER_FUNCTION,
        {"symbol": "GOLD", "interval": _DAILY_INTERVAL},
        _COMMODITY_PRICE_FIELD,
    ),
    "XAU": (
        GOLD_SILVER_FUNCTION,
        {"symbol": "GOLD", "interval": _DAILY_INTERVAL},
        _COMMODITY_PRICE_FIELD,
    ),
    "SILVER": (
        GOLD_SILVER_FUNCTION,
        {"symbol": "SILVER", "interval": _DAILY_INTERVAL},
        _COMMODITY_PRICE_FIELD,
    ),
    "XAG": (
        GOLD_SILVER_FUNCTION,
        {"symbol": "SILVER", "interval": _DAILY_INTERVAL},
        _COMMODITY_PRICE_FIELD,
    ),
}


class _Family(StrEnum):
    """Asset family that selects request parameters and entitlement handling."""

    EQUITY = "equity"
    INDEX = "index"
    FX = "fx"
    CRYPTO = "crypto"
    COMMODITY = "commodity"


@dataclass(frozen=True)
class _Route:
    """Request and parsing specification of one daily Alpha Vantage endpoint.

    Attributes:
        family: Asset family used to select entitlement handling.
        function: Alpha Vantage ``function`` parameter.
        parameters: Endpoint parameters other than ``function``.
        table: Payload key that holds the daily observations.
        price_field: Observation field that carries the close price.
        provenance: Source recorded in the resulting price series.
        array_based: Whether observations are a list of objects instead of a mapping.
        compact: Whether the response is capped by the free compact output size.

    """

    family: _Family
    function: str
    parameters: dict[str, str]
    table: str
    price_field: str
    provenance: str
    array_based: bool = False
    compact: bool = False


@dataclass(frozen=True)
class _History:
    """Daily history returned by one endpoint.

    Attributes:
        prices: Parsed prices, before :class:`quantfolio.models.PriceSeries` normalization.
        raw_rows: Observation count delivered by the endpoint.

    """

    prices: pd.Series[float]
    raw_rows: int


def _parse_dates(days: Iterable[object], symbol: str) -> pd.DatetimeIndex:
    """Return the parsed observation index of a daily response.

    Args:
        days: Observation dates as delivered by the endpoint.
        symbol: Caller ticker used in the error message.

    Returns:
        The parsed, timezone-naive daily index.

    Raises:
        ValueError: If an observation date is missing, not a string, or unparsable.

    """
    msg = f"Alpha Vantage devolvió fechas no válidas para {symbol}."
    values = list(days)
    if not all(isinstance(day, str) for day in values):
        raise ValueError(msg)
    try:
        index = pd.DatetimeIndex([pd.Timestamp(day) for day in cast("list[str]", values)])
    except TypeError, ValueError:
        raise ValueError(msg) from None
    if index.hasnans:
        raise ValueError(msg)
    return index


def _series(
    days: Iterable[object],
    values: Iterable[object],
    symbol: str,
) -> pd.Series[float]:
    """Build the numeric daily series of one endpoint response.

    Args:
        days: Observation dates as delivered by the endpoint.
        values: Raw price values, converted to numbers with invalid entries as ``NaN``.
        symbol: Caller ticker used as the series name.

    Returns:
        The parsed series indexed by observation date.

    """
    index = _parse_dates(days, symbol)
    numeric = pd.to_numeric(pd.Series(list(values)), errors="coerce")
    return pd.Series(numeric.to_numpy(), index=index, name=symbol)


def _parse_table(
    payload: _JsonObject,
    table: str,
    field: str,
    symbol: str,
) -> _History:
    """Extract one daily price column from a date-keyed response table.

    Args:
        payload: Decoded JSON body of a daily endpoint.
        table: Payload key that holds the date-keyed observations.
        field: Price column to extract.
        symbol: Caller ticker used in error messages.

    Returns:
        The parsed history and its raw observation count.

    Raises:
        TypeError: If an observation row is not a JSON object.
        ValueError: If the payload has no usable daily table.

    """
    entries = payload.get(table)
    if not isinstance(entries, dict) or not entries:
        msg = f"Alpha Vantage no devolvió una serie diaria para {symbol}."
        raise ValueError(msg)
    rows = _as_json_object(entries)
    values: list[object] = []
    for row in rows.values():
        if not isinstance(row, dict):
            msg = f"Alpha Vantage devolvió una fila diaria no válida para {symbol}."
            raise TypeError(msg)
        values.append(_as_json_object(row).get(field))
    return _History(prices=_series(rows, values, symbol), raw_rows=len(rows))


def _parse_array(
    payload: _JsonObject,
    table: str,
    field: str,
    symbol: str,
) -> _History:
    """Extract one daily price column from a list-shaped response table.

    Args:
        payload: Decoded JSON body of a daily endpoint.
        table: Payload key that holds the list of observations.
        field: Price column to extract.
        symbol: Caller ticker used in error messages.

    Returns:
        The parsed history and its raw observation count.

    Raises:
        TypeError: If an observation row is not a JSON object.
        ValueError: If the payload has no usable daily table.

    """
    entries = payload.get(table)
    if not isinstance(entries, list) or not entries:
        msg = f"Alpha Vantage no devolvió una serie diaria para {symbol}."
        raise ValueError(msg)
    days: list[object] = []
    values: list[object] = []
    for row in entries:
        if not isinstance(row, dict):
            msg = f"Alpha Vantage devolvió una fila diaria no válida para {symbol}."
            raise TypeError(msg)
        entry = _as_json_object(row)
        days.append(entry.get("date"))
        values.append(entry.get(field))
    return _History(prices=_series(days, values, symbol), raw_rows=len(days))


class AlphaVantageSource(PriceSource):
    """Historical daily prices from Alpha Vantage.

    The plan decides the equity endpoint semantics: free keys receive raw compact data,
    while premium keys receive full-history adjusted closes. Prefixed tickers route to the
    index, FX, crypto, and commodity families. Every family is normalized into the same
    :class:`quantfolio.models.PriceSeries` object used by the other providers.

    Args:
        api_key: Alpha Vantage credential, never exposed in output or errors.
        plan: Subscription plan detected for the key.
        indexes_enabled: Whether the key may query the index endpoints.
        cache_dir: Root directory of the capability cache used by runtime downgrades.

    """

    def __init__(
        self,
        api_key: str,
        *,
        plan: AlphaVantagePlan,
        indexes_enabled: bool,
        cache_dir: str | Path = "data",
    ) -> None:
        """Store the credential, runtime capabilities and capability cache."""
        self._api_key = api_key
        self._client = AlphaVantageClient(api_key)
        self._store = AlphaVantageCapabilityStore(cache_dir)
        self._plan = plan
        self._indexes_enabled = indexes_enabled

    @property
    def name(self) -> str:
        """Return the provider name."""
        return "Alpha Vantage"

    @property
    def cache_namespace(self) -> str:
        """Separate raw free data from adjusted premium data across cache versions."""
        return f"{self.name} {self._plan.value} v2"

    @property
    def plan(self) -> AlphaVantagePlan:
        """Return the plan currently in force for this source."""
        return self._plan

    @property
    def indexes_enabled(self) -> bool:
        """Return whether the source may query the index endpoints."""
        return self._indexes_enabled

    def get_prices(
        self,
        ticker: str,
        start: DateLike,
        end: DateLike | None = None,
    ) -> PriceSeries:
        """Return the daily close-price history of one supported instrument.

        Args:
            ticker: Equity symbol (``"IBM"``) or a prefixed ticker such as
                ``"INDEX:SP500"``, ``"FX:EUR/USD"``, ``"CRYPTO:BTC/EUR"`` or
                ``"COMMODITY:GOLD"``.
            start: First observation date (inclusive).
            end: Last observation date (exclusive); defaults to the present.

        Returns:
            The normalized price series.

        Raises:
            TypeError: If the response contains a malformed observation row.
            ValueError: If the ticker is malformed, the requested family is unavailable,
                the response is malformed, the free compact cap cannot cover ``start``,
                or the window has no observations.
            AlphaVantageError: If Alpha Vantage cannot serve the request. An entitlement
                denial downgrades the affected capabilities before it is re-raised.

        """
        symbol = validate_ticker(ticker)
        start_stamp = naive_timestamp(start)
        route = self._route(symbol)
        history = self._fetch(route, symbol)
        self._ensure_compact_coverage(route, history, start_stamp, symbol)
        window = history.prices[history.prices.index >= start_stamp]
        if end is not None:
            window = window[window.index < naive_timestamp(end)]
        if window.empty:
            msg = (
                f"No se han encontrado datos de {symbol} en Alpha Vantage "
                "para las fechas solicitadas."
            )
            raise ValueError(msg)
        quote_currency = None
        if route.family is _Family.FX:
            quote_currency = route.parameters["to_symbol"]
        elif route.family is _Family.CRYPTO:
            market = route.parameters["market"]
            if market in ECB_FIAT_CURRENCIES:
                quote_currency = market
        return PriceSeries(
            ticker=symbol,
            prices=window,
            source=route.provenance,
            quote_currency=quote_currency,
        )

    def _route(self, symbol: str) -> _Route:
        """Return the request and parsing specification of one ticker.

        Args:
            symbol: Stripped caller ticker.

        Returns:
            The endpoint specification of the ticker family.

        Raises:
            ValueError: If the prefix is unknown or the family-specific code is invalid.

        """
        prefix, separator, remainder = symbol.partition(":")
        if not separator:
            return self._equity_route(symbol)
        family = prefix.strip().upper()
        code = remainder.strip()
        handlers = {
            "INDEX": self._index_route,
            "FX": self._fx_route,
            "CRYPTO": self._crypto_route,
            "COMMODITY": self._commodity_route,
        }
        handler = handlers.get(family)
        if handler is None:
            msg = f"Alpha Vantage no admite el ticker {symbol}: prefijo desconocido."
            raise ValueError(msg)
        return handler(code, symbol)

    def _equity_route(self, symbol: str) -> _Route:
        """Return the plan-specific daily equity endpoint."""
        parameters = {"symbol": symbol.upper()}
        if self._plan is AlphaVantagePlan.FREE:
            return _Route(
                family=_Family.EQUITY,
                function=FREE_EQUITY_FUNCTION,
                parameters={**parameters, "outputsize": _COMPACT_OUTPUT_SIZE},
                table=_EQUITY_TABLE,
                price_field=_RAW_CLOSE_FIELD,
                provenance=FREE_EQUITY_PROVENANCE,
                compact=True,
            )
        return _Route(
            family=_Family.EQUITY,
            function=PREMIUM_EQUITY_FUNCTION,
            parameters={**parameters, "outputsize": _FULL_OUTPUT_SIZE},
            table=_EQUITY_TABLE,
            price_field=_ADJUSTED_CLOSE_FIELD,
            provenance=PREMIUM_EQUITY_PROVENANCE,
        )

    def _index_route(self, code: str, symbol: str) -> _Route:
        """Return the daily index endpoint after validating symbol and entitlement."""
        if _INDEX_SYMBOL_PATTERN.fullmatch(code) is None:
            msg = f"Alpha Vantage no admite el símbolo de índice {symbol}."
            raise ValueError(msg)
        if self._plan is not AlphaVantagePlan.PREMIUM:
            msg = "Los índices de Alpha Vantage requieren una clave premium."
            raise ValueError(msg)
        if not self._indexes_enabled:
            msg = "La clave de Alpha Vantage no tiene habilitado el acceso a los índices."
            raise ValueError(msg)
        index_symbol = code.upper()
        return _Route(
            family=_Family.INDEX,
            function=INDEX_FUNCTION,
            parameters={
                "symbol": _INDEX_ALIASES.get(index_symbol, index_symbol),
                "interval": _DAILY_INTERVAL,
            },
            table=_ARRAY_TABLE,
            price_field=_INDEX_CLOSE_FIELD,
            provenance=self._daily_provenance(),
            array_based=True,
        )

    def _fx_route(self, code: str, symbol: str) -> _Route:
        """Return the full-history daily FX endpoint of a validated pair."""
        match = _FX_PAIR_PATTERN.fullmatch(code)
        if match is None:
            msg = (
                "Alpha Vantage espera un par de divisas con el formato FX:BASE/COTIZADA, "
                f"con dos códigos de tres letras, y recibió {symbol}."
            )
            raise ValueError(msg)
        base, quote = match.groups()
        return _Route(
            family=_Family.FX,
            function=FX_FUNCTION,
            parameters={
                "from_symbol": base.upper(),
                "to_symbol": quote.upper(),
                "outputsize": _FULL_OUTPUT_SIZE,
            },
            table=_FX_TABLE,
            price_field=_RAW_CLOSE_FIELD,
            provenance=self._daily_provenance(),
        )

    def _crypto_route(self, code: str, symbol: str) -> _Route:
        """Return the daily digital-currency endpoint of a validated pair."""
        match = _CRYPTO_PAIR_PATTERN.fullmatch(code)
        if match is None:
            msg = (
                "Alpha Vantage espera un par de criptomonedas con el formato "
                f"CRYPTO:SÍMBOLO/MERCADO y recibió {symbol}."
            )
            raise ValueError(msg)
        crypto, market = match.groups()
        return _Route(
            family=_Family.CRYPTO,
            function=CRYPTO_FUNCTION,
            parameters={"symbol": crypto.upper(), "market": market.upper()},
            table=_CRYPTO_TABLE,
            price_field=_RAW_CLOSE_FIELD,
            provenance=self._daily_provenance(),
        )

    def _commodity_route(self, code: str, symbol: str) -> _Route:
        """Return the daily endpoint of an approved commodity alias."""
        spec = _COMMODITY_SPECS.get(code.upper())
        if spec is None:
            msg = f"Alpha Vantage no sirve datos diarios para el producto {symbol}."
            raise ValueError(msg)
        function, parameters, price_field = spec
        return _Route(
            family=_Family.COMMODITY,
            function=function,
            parameters=dict(parameters),
            table=_ARRAY_TABLE,
            price_field=price_field,
            provenance=self._daily_provenance(),
            array_based=True,
        )

    def _daily_provenance(self) -> str:
        """Return the provenance of a non-equity daily series."""
        return f"Alpha Vantage ({self._plan.value}, daily)"

    def _fetch(self, route: _Route, symbol: str) -> _History:
        """Request one route and return its parsed daily history.

        An entitlement denial updates runtime capabilities before the error is re-raised,
        and the market-data request is never retried.

        Args:
            route: Endpoint specification to request.
            symbol: Caller ticker used as the series name and in error messages.

        Returns:
            The parsed history of the response.

        Raises:
            AlphaVantageError: If the API rejects or cannot serve the request.
            TypeError: If the response contains a malformed observation row.
            ValueError: If the response has no usable daily table.

        """
        try:
            payload = self._client.get(function=route.function, **route.parameters)
        except AlphaVantageError as error:
            if error.category is AlphaVantageErrorCategory.ENTITLEMENT:
                self._handle_entitlement_denial(route)
            raise
        if route.array_based:
            return _parse_array(payload, route.table, route.price_field, symbol)
        return _parse_table(payload, route.table, route.price_field, symbol)

    def _handle_entitlement_denial(self, route: _Route) -> None:
        """Update runtime capabilities after an entitlement denial."""
        if route.family is _Family.INDEX:
            self._disable_indexes()
        elif route.family is _Family.EQUITY and self._plan is AlphaVantagePlan.PREMIUM:
            self._downgrade()

    def _ensure_compact_coverage(
        self,
        route: _Route,
        history: _History,
        start: pd.Timestamp,
        symbol: str,
    ) -> None:
        """Reject a capped compact response that cannot cover the requested start.

        Free compact responses stop after :data:`FREE_COMPACT_OBSERVATIONS` observations.
        A response that reaches that cap while beginning after ``start`` has silently
        dropped every earlier observation, so it is rejected instead of truncated. The
        cap is detected on the raw row count, so normalization cannot hide a response
        that was truncated to exactly :data:`FREE_COMPACT_OBSERVATIONS` rows. Full
        endpoints are never capped, which keeps late asset inception valid.

        Args:
            route: Endpoint specification that produced the history.
            history: Parsed history and its raw observation count.
            start: First observation date requested by the caller.
            symbol: Caller ticker used in the error message.

        Raises:
            ValueError: If a capped compact response begins after ``start``.

        """
        if not route.compact or history.raw_rows != FREE_COMPACT_OBSERVATIONS:
            return
        first_observation = history.prices.index.min()
        if first_observation <= start:
            return
        msg = (
            f"Alpha Vantage solo devuelve las últimas {FREE_COMPACT_OBSERVATIONS} "
            f"observaciones diarias en modo compacto: para {symbol} la primera disponible "
            f"es {first_observation.date()}, no {start.date()}. Usa una fecha de inicio más "
            "reciente o una clave premium."
        )
        raise ValueError(msg)

    def _disable_indexes(self) -> None:
        """Disable index access and persist it without touching the plan."""
        self._indexes_enabled = False
        self._persist_capabilities()

    def _downgrade(self) -> None:
        """Switch to free capabilities and persist them."""
        self._plan = AlphaVantagePlan.FREE
        self._indexes_enabled = False
        self._persist_capabilities()

    def _persist_capabilities(self) -> None:
        """Persist the current runtime capabilities through the capability store."""
        capabilities = AlphaVantageCapabilities(
            plan=self._plan,
            indexes_enabled=self._indexes_enabled,
        )
        self._store.save(self._api_key, capabilities)
