"""Observable freshness, identity and metadata behavior of the CSV cache."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pandas as pd
import pytest

from quantfolio.sources import CachedPriceSource, PriceSource
from tests.support.builders import TRADING_DATES, make_series
from tests.support.sources import ScriptedPriceSource, filtered_series

if TYPE_CHECKING:
    from pathlib import Path

    from quantfolio.models import PriceSeries
    from quantfolio.sources.base import DateLike


def _generation_source(
    *,
    base: float = 10.0,
    source_name: str = "Stub",
    namespace: str | None = None,
    quote_currency: str | None = None,
    quote_unit: str | None = None,
) -> tuple[ScriptedPriceSource, dict[str, int]]:
    state = {"generation": 0}

    def respond(symbol: str, start: DateLike, end: DateLike | None) -> PriceSeries:
        state["generation"] += 1
        asset = make_series(
            symbol,
            [base + state["generation"] + position for position in range(len(TRADING_DATES))],
            source=source_name,
            quote_currency=quote_currency,
            quote_unit=quote_unit,
        )
        return filtered_series(asset, start, end)

    source = ScriptedPriceSource(
        {
            "AAA": respond,
            "BTC/USD": respond,
            "BTC-USD": respond,
            "BTC\\USD": respond,
            "123": respond,
            "NA": respond,
            "nan": respond,
            "null": respond,
        },
        source_name=source_name,
        namespace=namespace,
    )
    return source, state


def _cached(
    source: PriceSource,
    directory: Path,
    *,
    ttl_days: int = 7,
    refresh: bool = False,
) -> CachedPriceSource:
    return CachedPriceSource(source, cache_dir=directory, ttl_days=ttl_days, refresh=refresh)


def test_cache_reuses_valid_rows_and_refresh_replaces_them(tmp_path: Path) -> None:
    """A valid file suppresses provider work while refresh obtains a newer observation set."""
    source, _state = _generation_source()
    cache = _cached(source, tmp_path)
    start, end = TRADING_DATES[0], TRADING_DATES[20]

    first = cache.get_prices("AAA", start, end)
    reused = cache.get_prices("AAA", start, end)
    refreshed = _cached(source, tmp_path, refresh=True).get_prices("AAA", start, end)

    assert first.source == "Stub"
    assert reused.source == "Stub (cache)"
    pd.testing.assert_series_equal(first.prices, reused.prices, check_freq=False)
    assert refreshed.source == "Stub"
    assert not refreshed.prices.equals(first.prices)


def test_cache_uses_the_write_time_namespace_and_stamps_the_requested_ticker(
    tmp_path: Path,
) -> None:
    """Provider normalization cannot break later cache hits and the write namespace wins."""

    @dataclass
    class SwitchingSource(PriceSource):
        calls: int = field(default=0)
        namespace: str = "before"

        @property
        def name(self) -> str:
            return "Fake Provider"

        @property
        def cache_namespace(self) -> str:
            return self.namespace

        def get_prices(
            self,
            _ticker: str,
            start: DateLike,
            end: DateLike | None = None,
        ) -> PriceSeries:
            del start, end
            self.calls += 1
            asset = make_series("NORMALIZED", [10.0, 11.0, 12.0])
            self.namespace = "after"
            return asset

    source = SwitchingSource()
    cache = _cached(source, tmp_path)

    first = cache.get_prices("RAW", TRADING_DATES[0], TRADING_DATES[5])
    second = cache.get_prices("RAW", TRADING_DATES[0], TRADING_DATES[5])

    assert first.ticker == "NORMALIZED"
    assert second.ticker == "RAW"
    assert second.source == "Stub (cache)"
    assert not (tmp_path / "before" / "RAW.csv").exists()
    assert (tmp_path / "after" / "RAW.csv").is_file()
    assert cache.name == "Fake Provider (cache)"


def test_cache_misses_when_start_end_or_observation_count_is_not_covered(
    tmp_path: Path,
) -> None:
    """Files that start late, end stale, or expose fewer than two rows are re-downloaded."""
    source, _state = _generation_source(base=10.0)
    original = _cached(source, tmp_path).get_prices(
        "AAA",
        TRADING_DATES[0],
        TRADING_DATES[20],
    )

    later_source, _later_state = _generation_source(
        base=100.0,
        source_name="Later",
        namespace="stub",
    )
    earlier = _cached(later_source, tmp_path).get_prices(
        "AAA",
        pd.Timestamp("2024-12-01"),
        TRADING_DATES[20],
    )
    stale_source, _stale_state = _generation_source(
        base=200.0,
        source_name="Stale",
        namespace="stub",
    )
    stale = _cached(stale_source, tmp_path).get_prices(
        "AAA",
        TRADING_DATES[0],
        pd.Timestamp("2026-01-01"),
    )

    path = tmp_path / "stub" / "AAA.csv"
    pd.DataFrame(
        {
            "Date": TRADING_DATES[:2],
            "Close": [5.0, 6.0],
            "ticker": ["AAA", "AAA"],
            "source": ["Tiny", "Tiny"],
        }
    ).to_csv(path, index=False)
    tiny_source, _tiny_state = _generation_source(
        base=300.0,
        source_name="Tiny replacement",
        namespace="stub",
    )
    tiny = _cached(tiny_source, tmp_path).get_prices(
        "AAA",
        TRADING_DATES[1],
        TRADING_DATES[2],
    )

    assert original.source == "Stub"
    assert earlier.source == "Later"
    assert stale.source == "Stale"
    assert tiny.source == "Tiny replacement"


def test_cache_reuses_recent_files_for_open_ended_requests(tmp_path: Path) -> None:
    """An open end uses the current date to evaluate freshness and can reuse a recent file."""
    today = pd.Timestamp.now().normalize()
    dates = pd.bdate_range(end=today, periods=10)
    path = tmp_path / "stub" / "AAA.csv"
    path.parent.mkdir(parents=True)
    pd.DataFrame({"Date": dates, "Close": [10.0 + position for position in range(10)]}).to_csv(
        path,
        index=False,
    )
    source, _state = _generation_source(
        base=100.0,
        source_name="Fresh download",
        namespace="stub",
    )

    asset = _cached(source, tmp_path).get_prices("AAA", today - pd.Timedelta(days=5))

    assert asset.source == "Fresh download (cache)"
    assert len(asset.prices) >= 2


def test_cache_discards_corrupt_empty_and_untrusted_legacy_files(tmp_path: Path) -> None:
    """Malformed files and sanitized legacy names fall back to a trusted fresh download."""
    stub_dir = tmp_path / "stub"
    stub_dir.mkdir()
    (stub_dir / "AAA.csv").write_text("not,a,price,file\n", encoding="utf-8")
    source, _state = _generation_source(base=10.0)
    corrupt = _cached(source, tmp_path).get_prices("AAA", TRADING_DATES[0], TRADING_DATES[10])
    assert corrupt.source == "Stub"

    (stub_dir / "AAA.csv").write_text("Date,Close,ticker\n", encoding="utf-8")
    empty = _cached(source, tmp_path).get_prices("AAA", TRADING_DATES[0], TRADING_DATES[10])
    assert empty.source == "Stub"

    pd.DataFrame({"Date": TRADING_DATES[:5], "Close": [1.0, 2.0, 3.0, 4.0, 5.0]}).to_csv(
        stub_dir / "BTC-USD.csv", index=False
    )
    source, _state = _generation_source(base=20.0)
    legacy = _cached(source, tmp_path).get_prices(
        "BTC/USD",
        TRADING_DATES[0],
        TRADING_DATES[5],
    )
    assert legacy.source == "Stub"
    assert pd.read_csv(stub_dir / "BTC-USD.csv")["ticker"].iloc[0] == "BTC/USD"


def test_cache_sanitizes_separators_but_preserves_ticker_identity(tmp_path: Path) -> None:
    """Slash, backslash, numeric and NA-like tickers never collide or lose their text identity."""
    source, _state = _generation_source(base=10.0)
    cache = _cached(source, tmp_path)
    cache.get_prices("BTC/USD", TRADING_DATES[0], TRADING_DATES[10])
    collision = cache.get_prices("BTC-USD", TRADING_DATES[0], TRADING_DATES[10])
    backslash = cache.get_prices("BTC\\USD", TRADING_DATES[0], TRADING_DATES[10])

    assert collision.ticker == "BTC-USD"
    assert backslash.ticker == "BTC\\USD"
    assert (tmp_path / "stub" / "BTC-USD.csv").is_file()
    assert pd.read_csv(tmp_path / "stub" / "BTC-USD.csv")["ticker"].iloc[0] == "BTC\\USD"

    numeric = cache.get_prices("123", TRADING_DATES[0], TRADING_DATES[10])
    assert numeric.ticker == "123"
    for ticker in ("NA", "nan", "null"):
        cached = cache.get_prices(ticker, TRADING_DATES[0], TRADING_DATES[10])
        again = cache.get_prices(ticker, TRADING_DATES[0], TRADING_DATES[10])
        assert cached.ticker == again.ticker == ticker
        assert again.source == "Stub (cache)"

    with pytest.raises(ValueError, match="caché"):
        cache.get_prices("../", TRADING_DATES[0], TRADING_DATES[10])


def test_cache_round_trips_quote_metadata_and_defaults_legacy_metadata_to_unknown(
    tmp_path: Path,
) -> None:
    """Minor-unit prices normalize once before storage and once after retrieval."""
    source, _state = _generation_source(quote_unit="GBX")
    cache = _cached(source, tmp_path)
    first = cache.get_prices("AAA", TRADING_DATES[0], TRADING_DATES[10])
    second = cache.get_prices("AAA", TRADING_DATES[0], TRADING_DATES[10])

    assert first.quote_currency == second.quote_currency == "GBP"
    assert first.quote_unit == second.quote_unit == "GBX"
    pd.testing.assert_series_equal(first.prices, second.prices, check_freq=False)

    legacy_path = tmp_path / "stub" / "LEGACY.csv"
    pd.DataFrame({"Date": TRADING_DATES[:5], "Close": [10.0, 11.0, 12.0, 13.0, 14.0]}).to_csv(
        legacy_path,
        index=False,
    )
    legacy = cache.get_prices("LEGACY", TRADING_DATES[0], TRADING_DATES[5])
    assert legacy.source == "Stub (cache)"
    assert legacy.quote_currency is None
    assert legacy.quote_unit is None


def test_cache_rejects_negative_ttl(tmp_path: Path) -> None:
    """A negative freshness policy is invalid at construction time."""
    source, _state = _generation_source()
    with pytest.raises(ValueError, match="ttl_days"):
        _cached(source, tmp_path, ttl_days=-1)
