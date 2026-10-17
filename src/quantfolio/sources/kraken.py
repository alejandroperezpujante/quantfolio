"""Kraken public market-data source."""

import json
from typing import TYPE_CHECKING, cast
from urllib.parse import urlencode
from urllib.request import urlopen

import pandas as pd

from quantfolio.models import PriceSeries
from quantfolio.sources.base import PriceSource, naive_timestamp, validate_ticker

if TYPE_CHECKING:
    from quantfolio.sources.base import DateLike

KRAKEN_OHLC_URL = "https://api.kraken.com/0/public/OHLC"

#: Kraken daily candles are requested with a 1,440-minute interval.
KRAKEN_DAILY_INTERVAL = 1_440

#: Maximum number of candles Kraken serves per response (~2 years of daily data).
KRAKEN_CANDLE_LIMIT = 720

#: Timeout, in seconds, applied to Kraken requests.
HTTP_TIMEOUT = 30

_OHLC_COLUMNS = ("time", "open", "high", "low", "close", "vwap", "volume", "count")


def _to_pair(ticker: str) -> str:
    """Return the Kraken pair symbol for a user-facing ticker."""
    pair = ticker.replace("/", "").upper()
    if pair.startswith("BTC"):
        pair = f"XBT{pair[3:]}"
    return pair


def _fetch_candles(url: str, symbol: str) -> list[list[object]]:
    """Download and validate the candle list of a Kraken OHLC response."""
    try:
        with urlopen(url, timeout=HTTP_TIMEOUT) as response:
            payload = cast("dict[str, object]", json.load(response))
    except (OSError, ValueError) as exc:
        msg = f"No se pudo descargar la serie {symbol} de Kraken: {exc}"
        raise ValueError(msg) from exc
    errors = payload.get("error")
    if isinstance(errors, list) and errors:
        msg = f"Kraken devolvió un error para {symbol}: {errors}"
        raise ValueError(msg)
    result = payload.get("result")
    candles = (
        [value for key, value in result.items() if key != "last"]
        if isinstance(result, dict)
        else []
    )
    if len(candles) != 1 or not isinstance(candles[0], list) or not candles[0]:
        msg = f"No se han encontrado datos para {symbol} en Kraken."
        raise ValueError(msg)
    return cast("list[list[object]]", candles[0])


def _ensure_retention_covers_start(
    symbol: str,
    prices: pd.Series[float],
    start_stamp: pd.Timestamp,
) -> None:
    """Reject responses where Kraken's retention window clipped the requested start.

    Kraken returns at most :data:`KRAKEN_CANDLE_LIMIT` of the most recent candles of an
    interval, so a response that hits that limit while starting well after ``start_stamp``
    has silently dropped every earlier observation.

    Args:
        symbol: Pair ticker, used in the error message.
        prices: Full close-price series returned by the endpoint.
        start_stamp: First observation date requested by the caller.

    Raises:
        ValueError: If the response starts more than one day after ``start_stamp``.

    """
    first_observation = prices.index.min()
    clipped = first_observation > start_stamp + pd.Timedelta(days=1)
    if len(prices) >= KRAKEN_CANDLE_LIMIT and clipped:
        msg = (
            f"Kraken solo conserva las últimas {KRAKEN_CANDLE_LIMIT} velas de cada intervalo "
            f"(≈2 años de datos diarios): para {symbol} la primera vela disponible es "
            f"{first_observation.date()}, no {start_stamp.date()}. "
            "Ajusta la fecha de inicio o usa otro proveedor."
        )
        raise ValueError(msg)


class KrakenSource(PriceSource):
    """Historical daily close prices from Kraken's keyless OHLC API.

    This provider complements Yahoo Finance and demonstrates that different market-data
    APIs produce identical internal objects. Kraken only keeps the most recent candles of
    each interval (about two years of daily data), so a ``start`` beyond that retention
    window raises a clear error instead of returning a silently truncated series.
    """

    @property
    def name(self) -> str:
        """Return the provider name."""
        return "Kraken"

    def get_prices(
        self,
        ticker: str,
        start: DateLike,
        end: DateLike | None = None,
    ) -> PriceSeries:
        """Download the daily close-price history of one pair.

        Args:
            ticker: Pair ticker, for example ``"BTC/USD"`` or ``"XBTUSD"``.
            start: First observation date (inclusive).
            end: Last observation date (exclusive); defaults to the present.

        Returns:
            The normalized price series.

        Raises:
            ValueError: If the ticker is empty or the endpoint returns no usable data.

        """
        symbol = validate_ticker(ticker)
        pair = _to_pair(symbol)
        start_stamp = naive_timestamp(start)
        params = {
            "pair": pair,
            "interval": str(KRAKEN_DAILY_INTERVAL),
            "since": str(int(start_stamp.tz_localize("UTC").timestamp())),
        }
        candles = _fetch_candles(f"{KRAKEN_OHLC_URL}?{urlencode(params)}", symbol)
        frame = pd.DataFrame(candles, columns=list(_OHLC_COLUMNS))
        prices = pd.Series(
            pd.to_numeric(frame["close"], errors="coerce").to_numpy(),
            index=pd.DatetimeIndex(pd.to_datetime(frame["time"], unit="s", utc=True)),
            name=symbol,
        )
        asset = PriceSeries(ticker=symbol, prices=prices, source=self.name)
        window = asset.prices[asset.prices.index >= start_stamp]
        if end is not None:
            window = window[window.index < naive_timestamp(end)]
        if window.empty:
            msg = f"No se han encontrado datos para {symbol} en Kraken."
            raise ValueError(msg)
        _ensure_retention_covers_start(symbol, asset.prices, start_stamp)
        return PriceSeries(ticker=symbol, prices=window, source=self.name)
