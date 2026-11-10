"""Fake provider transports that keep every test and notebook execution offline."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any, Self, cast
from urllib.parse import parse_qs, urlparse

import pandas as pd

from quantfolio.sources.alpha_vantage.client import AlphaVantageClient
from quantfolio.sources.alpha_vantage.provider import (
    FREE_EQUITY_FUNCTION,
    PREMIUM_EQUITY_FUNCTION,
)

if TYPE_CHECKING:
    from datetime import date

    import pytest

    from quantfolio.sources.base import DateLike

API_KEY = "test-key"
KRAKEN_PAIR_URL = "https://api.kraken.com/0/public/AssetPairs"


class FakeHTTPResponse:
    """Minimal context-manager response exposing bytes to ``json.load`` and parsers."""

    def __init__(self, payload: bytes | str | object) -> None:
        """Encode the configured body once."""
        if isinstance(payload, bytes):
            self._payload = payload
        elif isinstance(payload, str):
            self._payload = payload.encode()
        else:
            self._payload = json.dumps(payload).encode()

    def read(self) -> bytes:
        """Return the configured response bytes."""
        return self._payload

    def __enter__(self) -> Self:
        """Enter the response context."""
        return self

    def __exit__(self, *_args: object) -> None:
        """Exit the response context."""


def install_yahoo(
    monkeypatch: pytest.MonkeyPatch,
    prices: Mapping[str, pd.Series[float]],
    *,
    currencies: Mapping[str, str] | None = None,
    metadata_error: Exception | None = None,
) -> None:
    """Install deterministic Yahoo downloads and metadata."""
    currency_map = currencies or {}

    def download(
        symbol: str,
        *,
        start: DateLike,
        end: DateLike | None = None,
        **_kwargs: object,
    ) -> pd.DataFrame:
        series = prices[symbol.strip()]
        mask = series.index >= pd.Timestamp(start)
        if end is not None:
            mask &= series.index < pd.Timestamp(end)
        window = series[mask]
        return pd.DataFrame({"Open": window - 0.5, "Close": window})

    class Ticker:
        def __init__(self, symbol: str) -> None:
            self.symbol = symbol

        def get_history_metadata(self) -> Mapping[str, str]:
            if metadata_error is not None:
                raise metadata_error
            currency = currency_map.get(self.symbol)
            return {} if currency is None else {"currency": currency}

    monkeypatch.setattr("quantfolio.sources.yahoo.yf.download", download)
    monkeypatch.setattr("quantfolio.sources.yahoo.yf.Ticker", Ticker)


def kraken_pair(symbol: str) -> str:
    """Translate a display pair to the compact wire pair used by the fake."""
    pair = symbol.replace("/", "").upper()
    if pair.startswith("BTC"):
        return f"XBT{pair[3:]}"
    return pair


def kraken_payload(series: pd.Series[float]) -> dict[str, object]:
    """Build a Kraken OHLC payload from a close-price series."""
    candles = [
        [
            int(pd.Timestamp(cast("str", timestamp)).tz_localize("UTC").timestamp()),
            str(value),
            str(value + 1.0),
            str(value - 1.0),
            str(value),
            str(value),
            "1.0",
            1,
        ]
        for timestamp, value in series.items()
    ]
    return {"error": [], "result": {"PAIR": candles, "last": 0}}


def install_kraken(
    monkeypatch: pytest.MonkeyPatch,
    prices: Mapping[str, pd.Series[float]],
    *,
    market_names: Mapping[str, object] | None = None,
    metadata_error: Exception | None = None,
) -> None:
    """Install deterministic Kraken OHLC and market-metadata responses."""
    names = market_names or {}

    def urlopen(url: str, timeout: int = 30) -> FakeHTTPResponse:
        del timeout
        query = parse_qs(urlparse(url).query)
        if url.startswith(KRAKEN_PAIR_URL):
            if metadata_error is not None:
                raise metadata_error
            pair = query["pair"][0]
            return FakeHTTPResponse(
                {"error": [], "result": {pair: {"wsname": names.get(pair, "")}}}
            )
        pair = query["pair"][0]
        series = prices[pair]
        since = pd.to_datetime(int(query["since"][0]), unit="s", utc=True).tz_localize(None)
        return FakeHTTPResponse(kraken_payload(series[series.index >= since]))

    monkeypatch.setattr("quantfolio.sources.kraken.urlopen", urlopen)


def ecb_csv(series: pd.Series[float]) -> str:
    """Encode a close-price series as the ECB CSV response."""
    rows = "\n".join(
        f"{pd.Timestamp(cast('str', day)):%Y-%m-%d},{value}" for day, value in series.items()
    )
    return f"TIME_PERIOD,OBS_VALUE\n{rows}\n"


def install_ecb(
    monkeypatch: pytest.MonkeyPatch,
    series: pd.Series[float] | Mapping[str, pd.Series[float]],
) -> None:
    """Install deterministic ECB CSV responses for one or more currency pairs."""
    payloads = {"FX:EUR/USD": series} if isinstance(series, pd.Series) else dict(series)

    def urlopen(url: str, timeout: int = 30) -> FakeHTTPResponse:
        del timeout
        series_key = urlparse(url).path.rsplit("/", maxsplit=1)[-1]
        quote = series_key.split(".")[1]
        return FakeHTTPResponse(ecb_csv(payloads[f"FX:EUR/{quote}"]).encode())

    monkeypatch.setattr("quantfolio.sources.ecb.urlopen", urlopen)


def install_fred(
    monkeypatch: pytest.MonkeyPatch,
    prices: Mapping[str, pd.Series[float]],
    *,
    vintages: Mapping[str, date] | None = None,
) -> None:
    """Install a deterministic ALFRED CSV reader."""
    vintage_map = vintages or {}
    original_read_csv = pd.read_csv

    def read_csv(url: object, dtype: object) -> pd.DataFrame:
        if not isinstance(url, str) or not url.startswith("https://alfred.stlouisfed.org/"):
            return original_read_csv(cast("Any", url), dtype=cast("Any", dtype))
        assert dtype is str
        query = parse_qs(urlparse(url).query)
        series_id = query["id"][0]
        source = prices[series_id]
        mask = pd.Series(1, index=source.index, dtype=bool)
        if "cosd" in query:
            mask &= source.index >= pd.Timestamp(query["cosd"][0])
        if "coed" in query:
            mask &= source.index < pd.Timestamp(query["coed"][0])
        window = source[mask]
        vintage = vintage_map.get(series_id)
        suffix = f"_{vintage:%Y%m%d}" if vintage is not None else ""
        return pd.DataFrame(
            {
                "observation_date": [f"{day:%Y-%m-%d}" for day in window.index],
                f"{series_id}{suffix}": [str(value) for value in window],
            }
        )

    monkeypatch.setattr("quantfolio.macro.pd.read_csv", read_csv)


def alpha_daily_payload(
    values: Sequence[float],
    *,
    first: str = "2025-01-02",
    adjusted: bool = False,
    array_based: bool = False,
    field: str | None = None,
) -> dict[str, object]:
    """Build an official-shaped Alpha Vantage daily payload."""
    dates = pd.bdate_range(first, periods=len(values))
    price_field = field or ("5. adjusted close" if adjusted else "4. close")
    if array_based:
        return {
            "data": [
                {"date": f"{day:%Y-%m-%d}", price_field: str(value)}
                for day, value in zip(dates, values, strict=True)
            ]
        }
    digital_currency = adjusted and field == "4. close"
    table = "Time Series (Digital Currency Daily)" if digital_currency else "Time Series (Daily)"
    return {
        table: {
            f"{day:%Y-%m-%d}": {price_field: str(value)}
            for day, value in zip(dates, values, strict=True)
        }
    }


def install_alpha(
    monkeypatch: pytest.MonkeyPatch,
    responses: Mapping[str, object] | Sequence[object],
) -> list[dict[str, str]]:
    """Install a recording Alpha Vantage client and return its request log."""
    calls: list[dict[str, str]] = []
    if isinstance(responses, Mapping):
        by_function = responses
        queued = list(responses.values())
    else:
        by_function = {}
        queued = list(responses)

    def get(_client: AlphaVantageClient, **parameters: str) -> dict[str, object]:
        calls.append(parameters)
        response = by_function.get(parameters["function"])
        if response is None:
            response = queued[min(len(calls) - 1, len(queued) - 1)]
        if isinstance(response, Exception):
            raise response
        return cast("dict[str, object]", response)

    monkeypatch.setattr(AlphaVantageClient, "get", get)
    return calls


def default_alpha_responses() -> dict[str, dict[str, object]]:
    """Return valid equity responses for both Alpha Vantage plan endpoints."""
    return {
        FREE_EQUITY_FUNCTION: alpha_daily_payload([100.0, 101.0]),
        PREMIUM_EQUITY_FUNCTION: alpha_daily_payload([100.0, 101.0], adjusted=True),
    }


def notebook_yahoo_series(
    start: str = "2024-12-20",
    end: str = "2026-11-06",
) -> pd.Series[float]:
    """Return a deterministic business-day series long enough for every notebook."""
    index = pd.bdate_range(start, end, inclusive="left")
    positions = pd.Series(range(len(index)), index=index, dtype=float)
    return 100.0 + positions * 0.05


def notebook_macro_series() -> pd.Series[float]:
    """Return a deterministic macro level covering all notebook windows."""
    index = pd.date_range("2024-11-01", "2026-11-05", freq="B")
    positions = pd.Series(range(len(index)), index=index, dtype=float)
    return 300.0 + positions * 0.01
