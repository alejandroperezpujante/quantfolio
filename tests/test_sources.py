"""Tests for the market-data sources."""

from typing import TYPE_CHECKING, cast

import pandas as pd
import pytest

from quantfolio.sources.base import validate_ticker
from quantfolio.sources.cache import CachedPriceSource
from quantfolio.sources.stooq import StooqSource
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


def _stooq_frame() -> pd.DataFrame:
    """Return a minimal Stooq-style CSV frame."""
    return pd.DataFrame({"Date": ["2025-01-02", "2025-01-03"], "Close": [10.0, 11.0]})


def test_stooq_source_parses_csv(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stooq CSV responses are normalized into a PriceSeries."""

    def fake_read_csv(url: str) -> pd.DataFrame:
        assert "s=aapl.us" in url
        assert "d1=20250102" in url
        assert "d2=20250110" in url
        return _stooq_frame()

    monkeypatch.setattr("quantfolio.sources.stooq.pd.read_csv", fake_read_csv)

    asset = StooqSource().get_prices("aapl.us", "2025-01-02", "2025-01-10")

    assert asset.source == "Stooq"
    assert list(asset.prices) == [10.0, 11.0]


def test_stooq_source_rejects_empty_payloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty CSV responses raise a clear error."""

    def fake_read_csv(_url: str) -> pd.DataFrame:
        return pd.DataFrame()

    monkeypatch.setattr("quantfolio.sources.stooq.pd.read_csv", fake_read_csv)

    with pytest.raises(ValueError, match="No se han encontrado"):
        StooqSource().get_prices("aapl.us", "2025-01-02")


def test_stooq_source_rejects_missing_close_column(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CSV responses without close prices are rejected."""

    def fake_read_csv(_url: str) -> pd.DataFrame:
        return pd.DataFrame({"Date": ["2025-01-02"]})

    monkeypatch.setattr("quantfolio.sources.stooq.pd.read_csv", fake_read_csv)

    with pytest.raises(ValueError, match="No se han encontrado"):
        StooqSource().get_prices("aapl.us", "2025-01-02")


def test_stooq_source_wraps_download_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Network errors are reported as download errors."""

    def fake_read_csv(_url: str) -> pd.DataFrame:
        msg = "offline"
        raise OSError(msg)

    monkeypatch.setattr("quantfolio.sources.stooq.pd.read_csv", fake_read_csv)

    with pytest.raises(ValueError, match="No se pudo descargar"):
        StooqSource().get_prices("aapl.us", "2025-01-02")


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
