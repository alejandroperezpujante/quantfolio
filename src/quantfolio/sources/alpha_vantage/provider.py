"""Historical equity price source backed by the Alpha Vantage REST API."""

from typing import TYPE_CHECKING, cast

import pandas as pd

from quantfolio.models import PriceSeries
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
    from collections.abc import Mapping
    from pathlib import Path

    from quantfolio.sources.base import DateLike

#: Daily equity endpoint served to free keys.
FREE_EQUITY_FUNCTION = "TIME_SERIES_DAILY"

#: Adjusted daily equity endpoint served to premium keys.
PREMIUM_EQUITY_FUNCTION = "TIME_SERIES_DAILY_ADJUSTED"

#: Free keys only receive the latest observation count of a compact response.
FREE_COMPACT_OBSERVATIONS = 100

#: Provider provenance recorded for each equity mode.
FREE_EQUITY_PROVENANCE = "Alpha Vantage (free, raw)"
PREMIUM_EQUITY_PROVENANCE = "Alpha Vantage (premium, adjusted)"

#: Payload keys and price columns of the daily equity endpoints.
_SERIES_KEY = "Time Series (Daily)"
_RAW_CLOSE_FIELD = "4. close"
_ADJUSTED_CLOSE_FIELD = "5. adjusted close"
_COMPACT_OUTPUT_SIZE = "compact"
_FULL_OUTPUT_SIZE = "full"


def _parse_dates(entries: Mapping[str, object], symbol: str) -> pd.DatetimeIndex:
    """Return the observation index of a daily time-series table.

    Args:
        entries: Mapping from date strings to daily observation rows.
        symbol: Caller ticker used in the error message.

    Returns:
        The parsed, timezone-naive daily index.

    Raises:
        ValueError: If an observation date cannot be parsed.

    """
    try:
        return pd.DatetimeIndex([pd.Timestamp(day) for day in entries])
    except TypeError, ValueError:
        msg = f"Alpha Vantage devolvió fechas no válidas para {symbol}."
        raise ValueError(msg) from None


def _parse_daily(
    payload: Mapping[str, object],
    field: str,
    symbol: str,
) -> pd.Series[float]:
    """Extract one daily price column from an equity response.

    Args:
        payload: Decoded JSON body of a daily equity endpoint.
        field: Price column to extract, either raw or adjusted close.
        symbol: Caller ticker used as the series name and in error messages.

    Returns:
        The requested column indexed by observation date.

    Raises:
        TypeError: If an observation row is not a JSON object.
        ValueError: If the payload has no usable daily table.

    """
    table = payload.get(_SERIES_KEY)
    if not isinstance(table, dict) or not table:
        msg = f"Alpha Vantage no devolvió una serie diaria para {symbol}."
        raise ValueError(msg)
    entries = cast("Mapping[str, object]", table)
    rows: list[Mapping[str, object]] = []
    for row in entries.values():
        if not isinstance(row, dict):
            msg = f"Alpha Vantage devolvió una fila diaria no válida para {symbol}."
            raise TypeError(msg)
        rows.append(cast("Mapping[str, object]", row))
    index = _parse_dates(entries, symbol)
    numeric = pd.to_numeric(pd.Series([row.get(field) for row in rows]), errors="coerce")
    return pd.Series(numeric.to_numpy(), index=index, name=symbol)


class AlphaVantageSource(PriceSource):
    """Historical daily equity closes from Alpha Vantage.

    The plan decides the endpoint semantics: free keys receive raw compact data, while
    premium keys receive full-history adjusted closes. Both modes are normalized into the
    same :class:`quantfolio.models.PriceSeries` object used by every other provider.

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
        """Return the daily close-price history of one equity.

        Args:
            ticker: Equity symbol, for example ``"IBM"``.
            start: First observation date (inclusive).
            end: Last observation date (exclusive); defaults to the present.

        Returns:
            The normalized price series.

        Raises:
            TypeError: If the response contains a malformed observation row.
            ValueError: If the ticker is empty, the response is malformed, the free
                compact cap cannot cover ``start``, or the window has no observations.
            AlphaVantageError: If Alpha Vantage cannot serve the request. An entitlement
                denial of adjusted data downgrades the source to free before re-raising.

        """
        symbol = validate_ticker(ticker)
        start_stamp = naive_timestamp(start)
        history = self._history(symbol)
        self._ensure_compact_coverage(history.prices, start_stamp, symbol)
        window = history.prices[history.prices.index >= start_stamp]
        if end is not None:
            window = window[window.index < naive_timestamp(end)]
        if window.empty:
            msg = (
                f"No se han encontrado datos de {symbol} en Alpha Vantage "
                "para las fechas solicitadas."
            )
            raise ValueError(msg)
        return PriceSeries(ticker=symbol, prices=window, source=history.source)

    def _history(self, symbol: str) -> PriceSeries:
        """Return the complete normalized history available to the current plan."""
        if self._plan is AlphaVantagePlan.FREE:
            return self._free_history(symbol)
        return self._premium_history(symbol)

    def _free_history(self, symbol: str) -> PriceSeries:
        """Return raw close prices from the compact daily endpoint."""
        payload = self._client.get(
            function=FREE_EQUITY_FUNCTION,
            symbol=symbol.upper(),
            outputsize=_COMPACT_OUTPUT_SIZE,
        )
        prices = _parse_daily(payload, _RAW_CLOSE_FIELD, symbol)
        return PriceSeries(ticker=symbol, prices=prices, source=FREE_EQUITY_PROVENANCE)

    def _premium_history(self, symbol: str) -> PriceSeries:
        """Return adjusted close prices from the full daily endpoint.

        An entitlement denial means the key cannot use adjusted data, so the source
        downgrades its runtime capabilities before the error is re-raised. The market-data
        request is never retried.
        """
        try:
            payload = self._client.get(
                function=PREMIUM_EQUITY_FUNCTION,
                symbol=symbol.upper(),
                outputsize=_FULL_OUTPUT_SIZE,
            )
        except AlphaVantageError as error:
            if error.category is AlphaVantageErrorCategory.ENTITLEMENT:
                self._downgrade()
            raise
        prices = _parse_daily(payload, _ADJUSTED_CLOSE_FIELD, symbol)
        return PriceSeries(ticker=symbol, prices=prices, source=PREMIUM_EQUITY_PROVENANCE)

    def _ensure_compact_coverage(
        self,
        prices: pd.Series[float],
        start: pd.Timestamp,
        symbol: str,
    ) -> None:
        """Reject a capped compact response that cannot cover the requested start.

        Free compact responses stop after :data:`FREE_COMPACT_OBSERVATIONS` observations.
        A response that reaches that cap while beginning after ``start`` has silently
        dropped every earlier observation, so it is rejected instead of truncated. Full
        endpoints are never capped, which keeps late asset inception valid.

        Args:
            prices: Complete normalized history of the response.
            start: First observation date requested by the caller.
            symbol: Caller ticker used in the error message.

        Raises:
            ValueError: If a capped free response begins after ``start``.

        """
        if self._plan is not AlphaVantagePlan.FREE:
            return
        if len(prices) != FREE_COMPACT_OBSERVATIONS:
            return
        first_observation = prices.index.min()
        if first_observation <= start:
            return
        msg = (
            f"Alpha Vantage solo devuelve las últimas {FREE_COMPACT_OBSERVATIONS} "
            f"observaciones diarias en modo compacto: para {symbol} la primera disponible "
            f"es {first_observation.date()}, no {start.date()}. Usa una fecha de inicio más "
            "reciente o una clave premium."
        )
        raise ValueError(msg)

    def _downgrade(self) -> None:
        """Switch to free capabilities and persist the downgrade exactly once."""
        self._plan = AlphaVantagePlan.FREE
        self._indexes_enabled = False
        capabilities = AlphaVantageCapabilities(
            plan=self._plan,
            indexes_enabled=self._indexes_enabled,
        )
        self._store.save(self._api_key, capabilities)
