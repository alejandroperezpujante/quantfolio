"""Provider-specific parsing and error mapping for Yahoo, Kraken and the ECB."""

from __future__ import annotations

import json
from collections import UserDict
from typing import TYPE_CHECKING, Self, cast
from urllib.parse import parse_qs, urlparse

import pandas as pd
import pytest

from tests.support.builders import TRADING_DATES
from tests.support.transports import (
    FakeHTTPResponse,
    ecb_csv,
    install_kraken,
    kraken_pair,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from quantfolio.sources.base import DateLike

from quantfolio.sources import ECBExchangeRateSource, KrakenSource, YahooFinanceSource


def _yahoo_frame(values: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {"Open": [value - 1.0 for value in values], "Close": values},
        index=TRADING_DATES[: len(values)],
    )


def test_yahoo_reduces_multiindex_and_normalizes_quote_units(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Multi-level Yahoo columns reduce to one close series and canonical quote metadata."""
    columns = pd.MultiIndex.from_product([["Close", "Open"], ["AAPL"]])
    frame = pd.DataFrame(
        [[1.20, 1.10], [1.25, 1.15]],
        index=TRADING_DATES[:2],
        columns=columns,
    )

    def download(*_args: object, **_kwargs: object) -> pd.DataFrame:
        return frame

    class Ticker:
        def __init__(self, _symbol: str) -> None:
            pass

        def get_history_metadata(self) -> dict[str, str]:
            return {"currency": "GBp"}

    monkeypatch.setattr("quantfolio.sources.yahoo.yf.download", download)
    monkeypatch.setattr("quantfolio.sources.yahoo.yf.Ticker", Ticker)

    asset = YahooFinanceSource().get_prices("VOD.L", TRADING_DATES[0])

    assert list(asset.prices) == pytest.approx([0.012, 0.0125])
    assert asset.quote_currency == "GBP"
    assert asset.quote_unit == "GBp"


def test_yahoo_rejects_empty_or_close_less_downloads(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing rows and missing close columns are reported as provider errors."""
    for frame, message in (
        (pd.DataFrame(), "No se han encontrado"),
        (pd.DataFrame({"Open": [1.0]}, index=TRADING_DATES[:1]), "Close"),
    ):

        def download(
            *_args: object,
            response: pd.DataFrame = frame,
            **_kwargs: object,
        ) -> pd.DataFrame:
            return response

        monkeypatch.setattr("quantfolio.sources.yahoo.yf.download", download)
        source = YahooFinanceSource()
        with pytest.raises(ValueError, match=message):
            source.get_prices("AAPL", TRADING_DATES[0])


def test_yahoo_metadata_failures_do_not_discard_prices(monkeypatch: pytest.MonkeyPatch) -> None:
    """Invalid, absent and mapping metadata leave prices intact and currency explicit."""

    def download(*_args: object, **_kwargs: object) -> pd.DataFrame:
        return _yahoo_frame([10.0, 11.0, 12.0])

    class Ticker:
        def __init__(self, symbol: str) -> None:
            self.symbol = symbol

        def get_history_metadata(self) -> Mapping[str, str]:
            if self.symbol == "INVALID":
                return {"currency": "not-a-currency"}
            if self.symbol == "MISSING":
                return {}
            if self.symbol == "OFFLINE":
                msg = "metadata unavailable"
                raise OSError(msg)
            return UserDict({"currency": "EUR"})

    monkeypatch.setattr("quantfolio.sources.yahoo.yf.download", download)
    monkeypatch.setattr("quantfolio.sources.yahoo.yf.Ticker", Ticker)
    source = YahooFinanceSource()

    for symbol in ("INVALID", "MISSING", "OFFLINE"):
        asset = source.get_prices(symbol, TRADING_DATES[0])
        assert list(asset.prices) == [10.0, 11.0, 12.0]
        assert asset.quote_currency is None
    assert source.get_prices("SAN.MC", TRADING_DATES[0]).quote_currency == "EUR"


def test_yahoo_accepts_a_single_close_selection_returned_as_a_series(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A close selection already reduced to one series passes through unchanged."""
    selected = pd.Series([10.0, 11.0], index=TRADING_DATES[:2], name="AAPL")

    class Frame:
        empty = False
        columns = pd.MultiIndex.from_tuples([("Close", "AAPL")])

        @staticmethod
        def xs(*_args: object, **_kwargs: object) -> pd.Series[float]:
            return selected

    monkeypatch.setattr(
        "quantfolio.sources.yahoo.yf.download",
        lambda *_args, **_kwargs: cast("pd.DataFrame", Frame()),
    )

    asset = YahooFinanceSource().get_prices("AAPL", TRADING_DATES[0])

    pd.testing.assert_series_equal(asset.prices, selected, check_freq=False)


class _FakeResponse:
    """Context-managed raw Kraken response."""

    def __init__(self, payload: object) -> None:
        self.payload = payload

    def read(self) -> bytes:
        return json.dumps(self.payload).encode()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


def _kraken_candles(count: int, *, first: pd.Timestamp) -> dict[str, object]:
    rows = [
        [
            (first + pd.Timedelta(days=position)).timestamp(),
            "100.0",
            "102.0",
            "99.0",
            "101.0",
            "101.0",
            "5.0",
            count,
        ]
        for position in range(count)
    ]
    return {"error": [], "result": {"PAIR": rows, "last": 0}}


def test_kraken_maps_wire_errors_and_empty_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    """Endpoint, payload, transport and window failures all retain their public meaning."""
    cases = (
        ({"error": ["EQuery:Unknown asset pair"], "result": {}}, None, "Kraken devolvió"),
        ({"error": [], "result": {"PAIR": [], "last": 0}}, None, "No se han encontrado"),
        ({"error": [], "result": "unexpected"}, None, "No se han encontrado"),
        (None, OSError("offline"), "No se pudo descargar"),
    )

    for payload, transport_error, message in cases:

        def urlopen(
            _url: str,
            timeout: int = 30,
            *,
            response: object = payload,
            error: Exception | None = transport_error,
        ) -> _FakeResponse:
            del timeout
            if error is not None:
                raise error
            return _FakeResponse(response)

        monkeypatch.setattr("quantfolio.sources.kraken.urlopen", urlopen)
        source = KrakenSource()
        with pytest.raises(ValueError, match=message):
            source.get_prices("XBTUSD", "2025-01-02")

    window_payload = _kraken_candles(2, first=pd.Timestamp("2025-01-02"))
    monkeypatch.setattr(
        "quantfolio.sources.kraken.urlopen",
        lambda *_args, **_kwargs: _FakeResponse(window_payload),
    )
    source = KrakenSource()
    with pytest.raises(ValueError, match="No se han encontrado"):
        source.get_prices("XBTUSD", "2025-06-01")


def test_kraken_rejects_clipped_retention_but_accepts_full_coverage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 720-candle response is rejected only when it silently clips the requested start."""
    first = pd.Timestamp("2024-10-27")
    payload = _kraken_candles(720, first=first)
    monkeypatch.setattr(
        "quantfolio.sources.kraken.urlopen",
        lambda *_args, **_kwargs: _FakeResponse(payload),
    )
    source = KrakenSource()

    with pytest.raises(ValueError, match="720 velas"):
        source.get_prices("XBTUSD", "2020-01-01")
    asset = source.get_prices("XBTUSD", first)
    assert len(asset.prices) == 720
    assert asset.prices.index.min() == first


def test_kraken_quote_metadata_requires_an_explicit_or_valid_market_pair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only ECB fiat quote legs label crypto prices."""
    values = pd.Series([100.0, 101.0, 102.0], index=TRADING_DATES[:3])
    prices = {}
    names = {}
    for ticker, market_name in (
        ("BTC/USD", "XXBTZUSD"),
        ("ETH/BTC", "XETHXXBT"),
        ("BTC/USDT", "XBTUSDT"),
        ("XBTUSD", "XBT/USD"),
        ("XETHXXBT", "ETH/XBT"),
        ("XBTUSDT", "XBT/USDT"),
    ):
        pair = kraken_pair(ticker)
        prices[pair] = values
        names[pair] = market_name
    install_kraken(monkeypatch, prices, market_names=names)
    source = KrakenSource()
    expected = {
        "BTC/USD": "USD",
        "ETH/BTC": None,
        "BTC/USDT": None,
        "XBTUSD": "USD",
        "XETHXXBT": None,
        "XBTUSDT": None,
    }

    for ticker, currency in expected.items():
        assert source.get_prices(ticker, TRADING_DATES[0]).quote_currency == currency


def test_kraken_metadata_failures_keep_prices(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unavailable or malformed market metadata only leaves the quote currency unknown."""
    values = pd.Series([100.0, 101.0], index=TRADING_DATES[:2])
    for metadata_error, market_name in (
        (OSError("offline"), None),
        (None, ""),
        (None, None),
    ):
        install_kraken(
            monkeypatch,
            {"XBTUSD": values},
            market_names={"XBTUSD": market_name},
            metadata_error=metadata_error,
        )
        asset = KrakenSource().get_prices("XBTUSD", TRADING_DATES[0])
        assert list(asset.prices) == [100.0, 101.0]
        assert asset.quote_currency is None


def test_ecb_builds_the_reference_rate_request_and_half_open_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ECB series key, query dates and pair normalization follow the public contract."""
    values = pd.Series(
        [1.02, 1.03, 1.04], index=pd.to_datetime(["2025-01-02", "2025-01-03", "2025-01-06"])
    )
    urls: list[str] = []

    def urlopen(url: str, timeout: int = 30) -> FakeHTTPResponse:
        assert timeout == 30
        urls.append(url)
        return FakeHTTPResponse(ecb_csv(values))

    monkeypatch.setattr("quantfolio.sources.ecb.urlopen", urlopen)
    asset = ECBExchangeRateSource().get_prices("fx:eur/usd", "2025-01-02", "2025-01-07")

    request = urlparse(urls[0])
    assert request.path.endswith("/EXR/D.USD.EUR.SP00.A")
    assert parse_qs(request.query) == {
        "startPeriod": ["2025-01-02"],
        "endPeriod": ["2025-01-06"],
        "format": ["csvdata"],
    }
    assert asset.ticker == "FX:EUR/USD"
    assert asset.quote_currency == "USD"
    assert list(asset.prices) == [1.02, 1.03, 1.04]


def test_ecb_open_ended_window_keeps_every_observation_after_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Omitting ``end`` leaves the public ECB window open after its inclusive start."""
    values = pd.Series(
        [1.02, 1.03, 1.04],
        index=pd.DatetimeIndex(["2025-01-02", "2025-01-03", "2025-01-06"]),
    )

    def urlopen(_url: str, timeout: int = 30) -> FakeHTTPResponse:
        del timeout
        return FakeHTTPResponse(ecb_csv(values))

    monkeypatch.setattr("quantfolio.sources.ecb.urlopen", urlopen)
    asset = ECBExchangeRateSource().get_prices("FX:EUR/USD", values.index[0])

    assert list(asset.prices) == pytest.approx([1.02, 1.03, 1.04])


def test_ecb_rejects_invalid_pairs_and_windows_before_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unsupported pairs and invalid windows fail in Spanish without an HTTP request."""
    calls = 0

    def urlopen(_url: str, timeout: int = 30) -> FakeHTTPResponse:
        nonlocal calls
        del timeout
        calls += 1
        return FakeHTTPResponse(ecb_csv(pd.Series([1.0], index=TRADING_DATES[:1])))

    monkeypatch.setattr("quantfolio.sources.ecb.urlopen", urlopen)
    source = ECBExchangeRateSource()
    invalid_requests = (
        ("FX:USD/EUR", "2025-01-02", None, "EUR como primera"),
        ("FX:EURUSD", "2025-01-02", None, "formato"),
        ("FX:EUR/EUR", "2025-01-02", None, "EUR/EUR"),
        ("FX:EUR/USD", cast("DateLike", None), None, "fecha inicial"),
        ("FX:EUR/USD", cast("DateLike", pd.NaT), None, "fecha inicial"),
        ("FX:EUR/USD", "2025-01-02", cast("DateLike", pd.NaT), "fecha final"),
        ("FX:EUR/USD", "2025-01-02", "2025-01-02", "posterior"),
    )

    for ticker, start, end, message in invalid_requests:
        with pytest.raises(ValueError, match=message):
            source.get_prices(ticker, start, end)
    assert calls == 0


def test_ecb_maps_malformed_empty_invalid_and_network_responses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid CSV shapes and wire failures never leak parser or transport exceptions."""
    cases = (
        ("", "CSV"),
        ("TIME_PERIOD,VALUE\n2025-01-02,1.02\n", "columnas"),
        ("TIME_PERIOD,OBS_VALUE\n", "No se han encontrado"),
        ("TIME_PERIOD,OBS_VALUE\n2025-01-01,1.02\n", "No se han encontrado"),
        ("TIME_PERIOD,OBS_VALUE\n2025-01-02,0\n2025-01-03,invalid\n", "no válidos"),
        ("TIME_PERIOD,OBS_VALUE\n2025-01-02,1.02\n2025-01-03,inf\n", "no válidos"),
    )

    for payload, message in cases:

        def urlopen(
            _url: str,
            timeout: int = 30,
            *,
            response: str = payload,
        ) -> FakeHTTPResponse:
            del timeout
            return FakeHTTPResponse(response)

        monkeypatch.setattr("quantfolio.sources.ecb.urlopen", urlopen)
        source = ECBExchangeRateSource()
        with pytest.raises(ValueError, match=message):
            source.get_prices("FX:EUR/USD", "2025-01-02", "2025-01-04")

    def offline(_url: str, timeout: int = 30) -> FakeHTTPResponse:
        del timeout
        msg = "offline"
        raise OSError(msg)

    monkeypatch.setattr("quantfolio.sources.ecb.urlopen", offline)
    source = ECBExchangeRateSource()
    with pytest.raises(ValueError, match="No se pudo descargar"):
        source.get_prices("FX:EUR/USD", "2025-01-02")
