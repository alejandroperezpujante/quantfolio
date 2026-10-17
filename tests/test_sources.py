"""Tests for the market-data sources."""

import json
from typing import TYPE_CHECKING, Self, cast

import pandas as pd
import pytest

from quantfolio.sources.base import validate_ticker
from quantfolio.sources.cache import CachedPriceSource
from quantfolio.sources.kraken import KrakenSource
from quantfolio.sources.yahoo import YahooFinanceSource
from tests.helpers import TRADING_DATES, StubSource

if TYPE_CHECKING:
    from pathlib import Path


def test_validate_ticker_strips_whitespace() -> None:
    """Surrounding whitespace is removed from tickers."""
    assert validate_ticker("  AAPL ") == "AAPL"


def test_validate_ticker_rejects_empty_tickers() -> None:
    """Whitespace-only tickers are rejected."""
    with pytest.raises(ValueError, match="vacío"):
        validate_ticker("   ")


def test_validate_ticker_rejects_non_string_values() -> None:
    """Non-string tickers are rejected with a type error."""
    with pytest.raises(TypeError, match="texto"):
        validate_ticker(cast("str", 42))


def test_get_many_returns_one_series_per_ticker() -> None:
    """Batch extraction returns a normalized series for every ticker."""
    source = StubSource(TRADING_DATES)

    result = source.get_many(["AAA", "BBB"], "2025-01-02", "2025-03-01")

    assert set(result) == {"AAA", "BBB"}
    assert source.calls == 2
    assert result["AAA"].source == "Stub"


@pytest.mark.parametrize(
    ("tickers", "message"),
    [([], "al menos un ticker"), (["AAA", "AAA"], "duplicados")],
)
def test_get_many_rejects_invalid_batches(tickers: list[str], message: str) -> None:
    """Empty batches and duplicated tickers are rejected."""
    with pytest.raises(ValueError, match=message):
        StubSource(TRADING_DATES).get_many(tickers, "2025-01-02")


def _price_frame() -> pd.DataFrame:
    """Return a minimal yfinance-style frame."""
    return pd.DataFrame(
        {"Open": [5.0, 6.0, 7.0], "Close": [10.0, 11.0, 12.0]},
        index=TRADING_DATES[:3],
    )


def test_yahoo_source_returns_normalized_series(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Yahoo downloads are normalized into a PriceSeries."""

    def fake_download(*_args: object, **_kwargs: object) -> pd.DataFrame:
        return _price_frame()

    monkeypatch.setattr("quantfolio.sources.yahoo.yf.download", fake_download)

    asset = YahooFinanceSource().get_prices("AAPL", "2025-01-02", "2025-01-08")

    assert asset.ticker == "AAPL"
    assert asset.source == "Yahoo Finance"
    assert list(asset.prices) == [10.0, 11.0, 12.0]


def test_yahoo_source_handles_multiindex_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Multi-level yfinance columns are reduced to the close prices."""
    columns = pd.MultiIndex.from_product([["Close", "Open"], ["AAPL"]])
    frame = pd.DataFrame(
        [[10.0, 5.0], [11.0, 6.0]],
        index=TRADING_DATES[:2],
        columns=columns,
    )

    def fake_download(*_args: object, **_kwargs: object) -> pd.DataFrame:
        return frame

    monkeypatch.setattr("quantfolio.sources.yahoo.yf.download", fake_download)

    asset = YahooFinanceSource().get_prices("AAPL", "2025-01-02")

    assert list(asset.prices) == [10.0, 11.0]


def test_yahoo_source_rejects_empty_downloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty responses raise a clear error."""

    def fake_download(*_args: object, **_kwargs: object) -> pd.DataFrame:
        return pd.DataFrame()

    monkeypatch.setattr("quantfolio.sources.yahoo.yf.download", fake_download)

    with pytest.raises(ValueError, match="No se han encontrado"):
        YahooFinanceSource().get_prices("AAPL", "2025-01-02")


def test_yahoo_source_rejects_missing_close_column(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Responses without close prices are rejected."""
    frame = pd.DataFrame({"Open": [1.0]}, index=TRADING_DATES[:1])

    def fake_download(*_args: object, **_kwargs: object) -> pd.DataFrame:
        return frame

    monkeypatch.setattr("quantfolio.sources.yahoo.yf.download", fake_download)

    with pytest.raises(ValueError, match="Close"):
        YahooFinanceSource().get_prices("AAPL", "2025-01-02")


def test_yahoo_source_rejects_empty_tickers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ticker validation happens before any download."""

    def fake_download(*_args: object, **_kwargs: object) -> pd.DataFrame:
        return _price_frame()

    monkeypatch.setattr("quantfolio.sources.yahoo.yf.download", fake_download)

    with pytest.raises(ValueError, match="vacío"):
        YahooFinanceSource().get_prices("  ", "2025-01-02")


class _FakeResponse:
    """Minimal context-manager replacement for a urlopen response."""

    def __init__(self, payload: object) -> None:
        self._payload = payload

    def read(self) -> bytes:
        """Return the JSON-encoded payload."""
        return json.dumps(self._payload).encode()

    def __enter__(self) -> Self:
        """Enter the context manager."""
        return self

    def __exit__(self, *args: object) -> None:
        """Exit the context manager."""


def _kraken_payload() -> dict[str, object]:
    """Return a minimal Kraken OHLC payload with two daily candles."""
    return {
        "error": [],
        "result": {
            "XXBTZUSD": [
                [
                    1735776000.0,
                    "93000.0",
                    "95000.0",
                    "92000.0",
                    "94000.0",
                    "93500.0",
                    "10.5",
                    100.0,
                ],
                [
                    1735862400.0,
                    "94000.0",
                    "96000.0",
                    "93000.0",
                    "95000.0",
                    "94500.0",
                    "12.5",
                    120.0,
                ],
            ],
            "last": 1735862400.0,
        },
    }


def test_kraken_source_parses_ohlc(monkeypatch: pytest.MonkeyPatch) -> None:
    """Kraken responses are normalized into a PriceSeries."""

    def fake_urlopen(url: str, timeout: int = 30) -> _FakeResponse:
        assert "pair=XBTUSD" in url
        assert "interval=1440" in url
        assert timeout == 30
        return _FakeResponse(_kraken_payload())

    monkeypatch.setattr("quantfolio.sources.kraken.urlopen", fake_urlopen)

    asset = KrakenSource().get_prices("BTC/USD", "2025-01-02", "2025-01-10")

    assert asset.ticker == "BTC/USD"
    assert asset.source == "Kraken"
    assert list(asset.prices) == [94000.0, 95000.0]


def test_kraken_source_filters_by_end_date(monkeypatch: pytest.MonkeyPatch) -> None:
    """The end date is exclusive, matching the other providers."""

    def fake_urlopen(_url: str, timeout: int = 30) -> _FakeResponse:
        del timeout
        return _FakeResponse(_kraken_payload())

    monkeypatch.setattr("quantfolio.sources.kraken.urlopen", fake_urlopen)

    asset = KrakenSource().get_prices("XBTUSD", "2025-01-02", "2025-01-03")

    assert list(asset.prices) == [94000.0]


def test_kraken_source_rejects_endpoint_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Errors reported by the endpoint raise a clear exception."""
    payload = {"error": ["EQuery:Unknown asset pair"], "result": {}}

    def fake_urlopen(_url: str, timeout: int = 30) -> _FakeResponse:
        del timeout
        return _FakeResponse(payload)

    monkeypatch.setattr("quantfolio.sources.kraken.urlopen", fake_urlopen)

    with pytest.raises(ValueError, match="Kraken devolvió un error"):
        KrakenSource().get_prices("XBTUSD", "2025-01-02")


def test_kraken_source_rejects_empty_candles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty candle lists raise a clear error."""
    payload = {"error": [], "result": {"XXBTZUSD": [], "last": 0.0}}

    def fake_urlopen(_url: str, timeout: int = 30) -> _FakeResponse:
        del timeout
        return _FakeResponse(payload)

    monkeypatch.setattr("quantfolio.sources.kraken.urlopen", fake_urlopen)

    with pytest.raises(ValueError, match="No se han encontrado"):
        KrakenSource().get_prices("XBTUSD", "2025-01-02")


def test_kraken_source_rejects_malformed_payloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unexpected payload shapes raise a clear error."""
    payload = {"error": [], "result": "unexpected"}

    def fake_urlopen(_url: str, timeout: int = 30) -> _FakeResponse:
        del timeout
        return _FakeResponse(payload)

    monkeypatch.setattr("quantfolio.sources.kraken.urlopen", fake_urlopen)

    with pytest.raises(ValueError, match="No se han encontrado"):
        KrakenSource().get_prices("XBTUSD", "2025-01-02")


def test_kraken_source_rejects_windows_without_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A window that excludes every candle raises a clear error."""

    def fake_urlopen(_url: str, timeout: int = 30) -> _FakeResponse:
        del timeout
        return _FakeResponse(_kraken_payload())

    monkeypatch.setattr("quantfolio.sources.kraken.urlopen", fake_urlopen)

    with pytest.raises(ValueError, match="No se han encontrado"):
        KrakenSource().get_prices("XBTUSD", "2025-06-01")


def test_kraken_source_wraps_download_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Network errors are reported as download errors."""

    def fake_urlopen(_url: str, timeout: int = 30) -> _FakeResponse:
        del timeout
        msg = "offline"
        raise OSError(msg)

    monkeypatch.setattr("quantfolio.sources.kraken.urlopen", fake_urlopen)

    with pytest.raises(ValueError, match="No se pudo descargar"):
        KrakenSource().get_prices("XBTUSD", "2025-01-02")


def test_cache_writes_and_reuses_csv(tmp_path: Path) -> None:
    """A valid cache file avoids a second download."""
    upstream = StubSource(TRADING_DATES)
    cached = CachedPriceSource(upstream, cache_dir=tmp_path)

    first = cached.get_prices("AAA", "2025-01-02", "2025-02-27")
    path = tmp_path / "stub" / "AAA.csv"
    second = cached.get_prices("AAA", "2025-01-02", "2025-02-27")

    assert upstream.calls == 1
    assert first.source == "Stub"
    assert path.exists()
    assert second.source == "Stub (cache)"
    pd.testing.assert_series_equal(first.prices, second.prices, check_freq=False)


def test_cache_uses_a_provider_slug_directory(tmp_path: Path) -> None:
    """Cache files live in a provider-specific directory."""
    cached = CachedPriceSource(
        StubSource(TRADING_DATES, name="Fake Provider"),
        cache_dir=tmp_path,
    )

    cached.get_prices("AAA", "2025-01-02", "2025-02-27")

    assert (tmp_path / "fake-provider" / "AAA.csv").exists()
    assert cached.name == "Fake Provider (cache)"


def test_cache_refresh_forces_downloads(tmp_path: Path) -> None:
    """The refresh flag bypasses valid cache files."""
    upstream = StubSource(TRADING_DATES)
    cached = CachedPriceSource(upstream, cache_dir=tmp_path, refresh=True)

    cached.get_prices("AAA", "2025-01-02", "2025-02-27")
    cached.get_prices("AAA", "2025-01-02", "2025-02-27")

    assert upstream.calls == 2


def test_cache_downloads_when_the_window_is_not_covered(tmp_path: Path) -> None:
    """A cache file that starts too late is replaced."""
    upstream = StubSource(TRADING_DATES)
    cached = CachedPriceSource(upstream, cache_dir=tmp_path)

    cached.get_prices("AAA", "2025-01-02", "2025-02-27")
    cached.get_prices("AAA", "2024-12-01", "2025-02-27")

    assert upstream.calls == 2


def test_cache_downloads_when_the_cached_data_is_stale(tmp_path: Path) -> None:
    """A cache file that ends too early is replaced."""
    upstream = StubSource(TRADING_DATES)
    cached = CachedPriceSource(upstream, cache_dir=tmp_path)

    cached.get_prices("AAA", "2025-01-02", "2025-02-27")
    cached.get_prices("AAA", "2025-01-02", "2025-03-20")

    assert upstream.calls == 2


def test_cache_ignores_corrupt_files(tmp_path: Path) -> None:
    """Unreadable cache files are replaced by a fresh download."""
    path = tmp_path / "stub" / "AAA.csv"
    path.parent.mkdir(parents=True)
    path.write_text("not,a,price,file\n", encoding="utf-8")
    upstream = StubSource(TRADING_DATES)
    cached = CachedPriceSource(upstream, cache_dir=tmp_path)

    asset = cached.get_prices("AAA", "2025-01-02", "2025-02-27")

    assert upstream.calls == 1
    assert asset.source == "Stub"


def test_cache_reuses_recent_files_when_no_end_is_given(tmp_path: Path) -> None:
    """Without an end date, recent cache files are reused."""
    today = pd.Timestamp.now().normalize()
    dates = pd.bdate_range(end=today, periods=10)
    path = tmp_path / "stub" / "AAA.csv"
    path.parent.mkdir(parents=True)
    pd.DataFrame({"Date": dates, "Close": [10.0 + position for position in range(10)]}).to_csv(
        path, index=False
    )
    upstream = StubSource(TRADING_DATES)
    cached = CachedPriceSource(upstream, cache_dir=tmp_path)

    asset = cached.get_prices("AAA", (today - pd.Timedelta(days=5)).date())

    assert upstream.calls == 0
    assert asset.source == "Stub (cache)"
    assert len(asset.prices) >= 2


def test_cache_downloads_when_the_window_has_one_observation(
    tmp_path: Path,
) -> None:
    """A single observation in the requested window is not enough."""
    dates = pd.bdate_range("2025-01-02", periods=5)
    path = tmp_path / "stub" / "AAA.csv"
    path.parent.mkdir(parents=True)
    pd.DataFrame({"Date": dates, "Close": [10.0, 11.0, 12.0, 13.0, 14.0]}).to_csv(path, index=False)
    upstream = StubSource(TRADING_DATES)
    cached = CachedPriceSource(upstream, cache_dir=tmp_path)

    cached.get_prices("AAA", "2025-01-08", "2025-01-10")

    assert upstream.calls == 1


def test_cache_rejects_negative_ttl(tmp_path: Path) -> None:
    """The cache lifetime cannot be negative."""
    with pytest.raises(ValueError, match="ttl_days"):
        CachedPriceSource(StubSource(TRADING_DATES), cache_dir=tmp_path, ttl_days=-1)
