"""Tests for the Alpha Vantage price source."""

import warnings
from typing import TYPE_CHECKING, cast

import pandas as pd
import pytest

from quantfolio.sources import alpha_vantage
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
from quantfolio.sources.alpha_vantage.provider import AlphaVantageSource
from quantfolio.sources.cache import CachedPriceSource

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

API_KEY = "test-key"
FREE_FUNCTION = "TIME_SERIES_DAILY"
PREMIUM_FUNCTION = "TIME_SERIES_DAILY_ADJUSTED"
FREE_PROVENANCE = "Alpha Vantage (free, raw)"
PREMIUM_PROVENANCE = "Alpha Vantage (premium, adjusted)"


def _daily_row(close: float, *, adjusted: bool) -> dict[str, str]:
    """Return one official-shaped daily observation."""
    row = {
        "1. open": f"{close - 0.5:.4f}",
        "2. high": f"{close + 1.0:.4f}",
        "3. low": f"{close - 1.0:.4f}",
        "4. close": f"{close - 0.25 if adjusted else close:.4f}",
        "5. volume": "1000000",
    }
    if adjusted:
        row = {
            "1. open": row["1. open"],
            "2. high": row["2. high"],
            "3. low": row["3. low"],
            "4. close": row["4. close"],
            "5. adjusted close": f"{close:.4f}",
            "6. volume": row["5. volume"],
            "7. dividend amount": "0.0000",
            "8. split coefficient": "1.000000",
        }
    return row


def _daily_payload(
    first: pd.Timestamp,
    periods: int,
    *,
    adjusted: bool,
) -> dict[str, object]:
    """Return an official-shaped daily time-series payload."""
    dates = pd.bdate_range(start=first, periods=periods)
    output_size = "Full size" if adjusted else "Compact"
    information = (
        "Daily Adjusted Prices and Volumes"
        if adjusted
        else "Daily Prices (open, high, low, close) and Volumes"
    )
    return {
        "Meta Data": {
            "1. Information": information,
            "2. Symbol": "IBM",
            "3. Last Refreshed": dates[-1].strftime("%Y-%m-%d"),
            "4. Output Size": output_size,
            "5. Time Zone": "US/Eastern",
        },
        "Time Series (Daily)": {
            date.strftime("%Y-%m-%d"): _daily_row(100.0 + position, adjusted=adjusted)
            for position, date in enumerate(dates)
        },
    }


def free_payload(first: pd.Timestamp, periods: int) -> dict[str, object]:
    """Return a compact raw daily payload."""
    return _daily_payload(first, periods, adjusted=False)


def premium_payload(first: pd.Timestamp, periods: int) -> dict[str, object]:
    """Return a full adjusted daily payload."""
    return _daily_payload(first, periods, adjusted=True)


def _observation_dates(first: pd.Timestamp, periods: int) -> pd.DatetimeIndex:
    """Return the business-day observation dates of a fixture."""
    return pd.bdate_range(start=first, periods=periods)


def index_payload(first: pd.Timestamp, periods: int) -> dict[str, object]:
    """Return an official-shaped daily index payload."""
    dates = _observation_dates(first, periods)
    return {
        "Meta Data": {
            "1. Information": "Daily Prices and Volumes for Index",
            "2. Symbol": "SPX",
            "3. Last Refreshed": dates[-1].strftime("%Y-%m-%d"),
            "4. Time Zone": "US/Eastern",
        },
        "data": [
            {
                "date": date.strftime("%Y-%m-%d"),
                "open": "5000.0000",
                "high": "5010.0000",
                "low": "4990.0000",
                "close": f"{5000.0 + position:.4f}",
            }
            for position, date in enumerate(dates)
        ],
    }


def fx_payload(first: pd.Timestamp, periods: int) -> dict[str, object]:
    """Return an official-shaped daily FX payload using ``4. close``."""
    dates = _observation_dates(first, periods)
    return {
        "Meta Data": {
            "1. Information": "Forex Daily Prices (open, high, low, close)",
            "2. From Symbol": "EUR",
            "3. To Symbol": "USD",
            "4. Last Refreshed": dates[-1].strftime("%Y-%m-%d"),
            "5. Time Zone": "UTC",
        },
        "Time Series FX (Daily)": {
            date.strftime("%Y-%m-%d"): {
                "1. open": "1.1000",
                "2. high": "1.1100",
                "3. low": "1.0900",
                "4. close": f"{1.1000 + position / 1000:.4f}",
            }
            for position, date in enumerate(dates)
        },
    }


def crypto_payload(first: pd.Timestamp, periods: int) -> dict[str, object]:
    """Return an official-shaped daily crypto payload using plain ``4. close``."""
    dates = _observation_dates(first, periods)
    return {
        "Meta Data": {
            "1. Information": "Daily Prices and Volumes for Digital Currency",
            "2. Digital Currency Code": "BTC",
            "3. Digital Currency Name": "Bitcoin",
            "4. Market Code": "EUR",
            "5. Market Name": "Euro",
            "6. Last Refreshed": dates[-1].strftime("%Y-%m-%d"),
            "7. Time Zone": "UTC",
        },
        "Time Series (Digital Currency Daily)": {
            date.strftime("%Y-%m-%d"): {
                "1. open": "40000.00000000",
                "2. high": "41000.00000000",
                "3. low": "39000.00000000",
                "4. close": f"{40000.0 + position:.8f}",
                "5. volume": "12.34567890",
            }
            for position, date in enumerate(dates)
        },
    }


def commodity_payload(
    first: pd.Timestamp,
    periods: int,
    *,
    field: str,
    base: float,
) -> dict[str, object]:
    """Return an official-shaped commodity payload with the given price field."""
    dates = _observation_dates(first, periods)
    return {
        "name": "Commodity fixture",
        "interval": "daily",
        "unit": "fixture unit",
        "data": [
            {"date": date.strftime("%Y-%m-%d"), field: f"{base + position:.4f}"}
            for position, date in enumerate(dates)
        ],
    }


class _ClientStub:
    """Record requests and serve queued responses or errors."""

    def __init__(self, responses: Sequence[object]) -> None:
        self.calls: list[dict[str, str]] = []
        self._responses = list(responses)

    def get(self, **parameters: str) -> dict[str, object]:
        """Return the next queued response, repeating the last one."""
        self.calls.append(parameters)
        response = self._responses[min(len(self.calls) - 1, len(self._responses) - 1)]
        if isinstance(response, AlphaVantageError):
            raise response
        return cast("dict[str, object]", response)


def install_client(
    monkeypatch: pytest.MonkeyPatch,
    responses: Sequence[object],
) -> _ClientStub:
    """Replace the HTTP client with a recording stub."""
    stub = _ClientStub(responses)
    monkeypatch.setattr(AlphaVantageClient, "get", stub.get)
    return stub


def make_source(
    plan: AlphaVantagePlan,
    *,
    indexes_enabled: bool = False,
    cache_dir: str | Path = "data",
) -> AlphaVantageSource:
    """Return a source with the requested runtime capabilities."""
    return AlphaVantageSource(
        API_KEY,
        plan=plan,
        indexes_enabled=indexes_enabled,
        cache_dir=cache_dir,
    )


def free_source_with_compact_rows(
    monkeypatch: pytest.MonkeyPatch,
    periods: int,
    *,
    first: pd.Timestamp,
    cache_dir: str | Path = "data",
) -> AlphaVantageSource:
    """Return a free source serving a compact response with ``periods`` rows."""
    install_client(monkeypatch, [free_payload(first, periods)])
    return make_source(AlphaVantagePlan.FREE, cache_dir=cache_dir)


def premium_source_with_rows(
    monkeypatch: pytest.MonkeyPatch,
    *,
    first: pd.Timestamp,
    periods: int,
    cache_dir: str | Path = "data",
) -> AlphaVantageSource:
    """Return a premium source serving an adjusted response with ``periods`` rows."""
    install_client(monkeypatch, [premium_payload(first, periods)])
    return make_source(AlphaVantagePlan.PREMIUM, indexes_enabled=True, cache_dir=cache_dir)


def premium_source_with_entitlement_error_then_any(
    monkeypatch: pytest.MonkeyPatch,
    *,
    cache_dir: str | Path = "data",
) -> tuple[AlphaVantageSource, list[dict[str, str]]]:
    """Return a premium source that denies adjusted data without ever retrying."""
    error = AlphaVantageError(
        "La clave no tiene acceso al endpoint premium.",
        AlphaVantageErrorCategory.ENTITLEMENT,
    )
    stub = install_client(monkeypatch, [error, premium_payload(pd.Timestamp("2025-01-02"), 2)])
    source = make_source(AlphaVantagePlan.PREMIUM, indexes_enabled=True, cache_dir=cache_dir)
    return source, stub.calls


def warn_but_do_not_write(*_args: object, **_kwargs: object) -> None:
    """Warn in Spanish without persisting capabilities."""
    warnings.warn(
        "No se pudo guardar la caché de capacidades de Alpha Vantage (test).",
        RuntimeWarning,
        stacklevel=2,
    )


def premium_source(
    *,
    indexes_enabled: bool = True,
    cache_dir: str | Path = "data",
) -> AlphaVantageSource:
    """Return a premium source with the requested index entitlement."""
    return make_source(
        AlphaVantagePlan.PREMIUM, indexes_enabled=indexes_enabled, cache_dir=cache_dir
    )


def premium_source_with_index_entitlement_error(
    monkeypatch: pytest.MonkeyPatch,
    *,
    cache_dir: str | Path = "data",
) -> tuple[AlphaVantageSource, list[dict[str, str]]]:
    """Return a premium source whose index endpoint denies entitlement."""
    error = AlphaVantageError(
        "La clave no tiene acceso al endpoint de índices.",
        AlphaVantageErrorCategory.ENTITLEMENT,
    )
    stub = install_client(monkeypatch, [error, index_payload(pd.Timestamp("2025-01-02"), 2)])
    source = premium_source(cache_dir=cache_dir)
    return source, stub.calls


def test_package_exports_the_public_api() -> None:
    """The package exposes the plan type and the equity source."""
    assert alpha_vantage.__all__ == ["AlphaVantagePlan", "AlphaVantageSource"]
    assert alpha_vantage.AlphaVantagePlan is AlphaVantagePlan
    assert alpha_vantage.AlphaVantageSource is AlphaVantageSource


def test_name_and_runtime_properties() -> None:
    """The provider exposes its name and read-only runtime capabilities."""
    source = make_source(AlphaVantagePlan.PREMIUM, indexes_enabled=True)

    assert source.name == "Alpha Vantage"
    assert source.plan is AlphaVantagePlan.PREMIUM
    assert source.indexes_enabled is True
    with pytest.raises(AttributeError):
        source.plan = AlphaVantagePlan.FREE  # type: ignore[misc]


def test_free_source_requests_compact_raw_series(monkeypatch: pytest.MonkeyPatch) -> None:
    """Free keys use raw compact daily data."""
    stub = install_client(monkeypatch, [free_payload(pd.Timestamp("2025-01-02"), 3)])

    asset = make_source(AlphaVantagePlan.FREE).get_prices("IBM", "2025-01-02")

    assert stub.calls == [
        {"function": FREE_FUNCTION, "symbol": "IBM", "outputsize": "compact"},
    ]
    assert asset.source == FREE_PROVENANCE
    assert list(asset.prices) == [100.0, 101.0, 102.0]


def test_premium_source_requests_full_adjusted_series(monkeypatch: pytest.MonkeyPatch) -> None:
    """Premium keys use the adjusted full-history endpoint."""
    stub = install_client(monkeypatch, [premium_payload(pd.Timestamp("2025-01-02"), 3)])

    asset = make_source(AlphaVantagePlan.PREMIUM, indexes_enabled=True).get_prices(
        "IBM", "2025-01-02"
    )

    assert stub.calls == [
        {"function": PREMIUM_FUNCTION, "symbol": "IBM", "outputsize": "full"},
    ]
    assert asset.source == PREMIUM_PROVENANCE
    assert list(asset.prices) == [100.0, 101.0, 102.0]


def test_start_is_inclusive(monkeypatch: pytest.MonkeyPatch) -> None:
    """The requested start date is part of the window."""
    source = free_source_with_compact_rows(monkeypatch, 3, first=pd.Timestamp("2025-01-02"))

    asset = source.get_prices("IBM", "2025-01-03")

    assert list(asset.prices.index) == [pd.Timestamp("2025-01-03"), pd.Timestamp("2025-01-06")]


def test_end_is_exclusive(monkeypatch: pytest.MonkeyPatch) -> None:
    """The requested end date is excluded from the window."""
    source = free_source_with_compact_rows(monkeypatch, 3, first=pd.Timestamp("2025-01-02"))

    asset = source.get_prices("IBM", "2025-01-02", "2025-01-03")

    assert list(asset.prices.index) == [pd.Timestamp("2025-01-02")]


def test_original_stripped_ticker_is_preserved(monkeypatch: pytest.MonkeyPatch) -> None:
    """The caller ticker is stripped for the result but normalized for the request."""
    stub = install_client(monkeypatch, [free_payload(pd.Timestamp("2025-01-02"), 2)])

    asset = make_source(AlphaVantagePlan.FREE).get_prices("  ibm  ", "2025-01-02")

    assert asset.ticker == "ibm"
    assert asset.prices.name == "ibm"
    assert stub.calls[0]["symbol"] == "IBM"


def test_empty_window_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """A window without observations raises a clear Spanish error."""
    source = free_source_with_compact_rows(monkeypatch, 3, first=pd.Timestamp("2025-01-02"))

    with pytest.raises(ValueError, match="No se han encontrado"):
        source.get_prices("IBM", "2025-02-01")


def test_empty_ticker_fails_before_http(monkeypatch: pytest.MonkeyPatch) -> None:
    """Invalid tickers never reach the HTTP client."""
    stub = install_client(monkeypatch, [free_payload(pd.Timestamp("2025-01-02"), 2)])
    source = make_source(AlphaVantagePlan.FREE)

    with pytest.raises(ValueError, match="vacío"):
        source.get_prices("   ", "2025-01-02")

    assert stub.calls == []


def test_get_many_keys_match_the_requested_tickers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Batch extraction keeps one keyed series per requested ticker."""
    stub = install_client(
        monkeypatch,
        [
            free_payload(pd.Timestamp("2025-01-02"), 2),
            free_payload(pd.Timestamp("2025-01-02"), 2),
        ],
    )
    source = make_source(AlphaVantagePlan.FREE)

    result = source.get_many(["AAA", "BBB"], "2025-01-02")

    assert set(result) == {"AAA", "BBB"}
    assert result["AAA"].ticker == "AAA"
    assert result["BBB"].ticker == "BBB"
    assert [call["symbol"] for call in stub.calls] == ["AAA", "BBB"]


def test_non_positive_and_missing_closes_are_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    """Normalization keeps only finite, strictly positive closes."""
    payload = {
        "Time Series (Daily)": {
            "2025-01-02": {"4. close": "100.0"},
            "2025-01-03": {"4. close": "not-a-number"},
            "2025-01-06": {"4. close": "0"},
            "2025-01-07": {"4. close": "-5.0"},
        },
    }
    install_client(monkeypatch, [payload])

    asset = make_source(AlphaVantagePlan.FREE).get_prices("IBM", "2025-01-02")

    assert list(asset.prices) == [100.0]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"Time Series (Daily)": []},
        {"Time Series (Daily)": {}},
    ],
)
def test_missing_daily_table_raises(
    monkeypatch: pytest.MonkeyPatch,
    payload: object,
) -> None:
    """Responses without a usable daily table are rejected."""
    install_client(monkeypatch, [payload])
    source = make_source(AlphaVantagePlan.FREE)

    with pytest.raises(ValueError, match="serie diaria"):
        source.get_prices("IBM", "2025-01-02")


def test_non_object_daily_row_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unexpected row shapes are rejected instead of silently ignored."""
    install_client(monkeypatch, [{"Time Series (Daily)": {"2025-01-02": ["not", "a", "row"]}}])
    source = make_source(AlphaVantagePlan.FREE)

    with pytest.raises(TypeError, match="fila diaria"):
        source.get_prices("IBM", "2025-01-02")


@pytest.mark.parametrize("day", ["not-a-date", ""])
def test_invalid_dates_raise(monkeypatch: pytest.MonkeyPatch, day: str) -> None:
    """Malformed observation dates are rejected."""
    install_client(monkeypatch, [{"Time Series (Daily)": {day: {"4. close": "100.0"}}}])
    source = make_source(AlphaVantagePlan.FREE)

    with pytest.raises(ValueError, match="fechas no válidas"):
        source.get_prices("IBM", "2025-01-02")


def test_free_compact_rejects_clipped_start(monkeypatch: pytest.MonkeyPatch) -> None:
    """A capped compact response that cannot cover the start is rejected."""
    source = free_source_with_compact_rows(monkeypatch, 100, first=pd.Timestamp("2025-01-02"))

    with pytest.raises(ValueError, match="100"):
        source.get_prices("IBM", "2020-01-01")


def test_free_compact_accepts_a_covered_start(monkeypatch: pytest.MonkeyPatch) -> None:
    """A capped response that starts on the requested date is complete."""
    source = free_source_with_compact_rows(monkeypatch, 100, first=pd.Timestamp("2025-01-02"))

    asset = source.get_prices("IBM", "2025-01-02")

    assert asset.prices.index.min() == pd.Timestamp("2025-01-02")
    assert len(asset.prices) == 100


def test_free_short_response_is_not_treated_as_clipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only a full compact response can prove that history was capped."""
    source = free_source_with_compact_rows(monkeypatch, 2, first=pd.Timestamp("2025-01-02"))

    with pytest.raises(ValueError, match="No se han encontrado"):
        source.get_prices("IBM", "2026-01-01")


def test_full_history_allows_late_inception(monkeypatch: pytest.MonkeyPatch) -> None:
    """A full adjusted response may start after the requested date."""
    source = premium_source_with_rows(monkeypatch, first=pd.Timestamp("2020-06-01"), periods=2)

    asset = source.get_prices("NEW", "2020-01-01")

    assert asset.prices.index.min() == pd.Timestamp("2020-06-01")


def test_full_history_never_applies_the_compact_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """Even a 100-row full response is accepted when the asset is that young."""
    source = premium_source_with_rows(monkeypatch, first=pd.Timestamp("2020-06-01"), periods=100)

    asset = source.get_prices("NEW", "2020-01-01")

    assert asset.prices.index.min() == pd.Timestamp("2020-06-01")
    assert len(asset.prices) == 100


def test_downgrade_survives_cache_write_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unwritable cache still downgrades the runtime and never retries."""
    source, calls = premium_source_with_entitlement_error_then_any(monkeypatch)
    monkeypatch.setattr(AlphaVantageCapabilityStore, "save", warn_but_do_not_write)

    with pytest.warns(RuntimeWarning, match="caché"), pytest.raises(AlphaVantageError):
        source.get_prices("IBM", "2025-01-01")

    assert source.plan is AlphaVantagePlan.FREE
    assert source.indexes_enabled is False
    assert len(calls) == 1


def test_downgrade_persists_free_capabilities_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """An entitlement denial persists exactly one free/index-disabled snapshot."""
    source, calls = premium_source_with_entitlement_error_then_any(monkeypatch, cache_dir=tmp_path)
    saved: list[tuple[str, AlphaVantageCapabilities]] = []

    def record(
        _store: AlphaVantageCapabilityStore,
        api_key: str,
        capabilities: AlphaVantageCapabilities,
    ) -> None:
        saved.append((api_key, capabilities))

    monkeypatch.setattr(AlphaVantageCapabilityStore, "save", record)

    with pytest.raises(AlphaVantageError):
        source.get_prices("IBM", "2025-01-01")

    assert saved == [
        (API_KEY, AlphaVantageCapabilities(AlphaVantagePlan.FREE, indexes_enabled=False)),
    ]
    assert len(calls) == 1


def test_downgrade_writes_the_cache(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The downgraded capabilities are readable through the capability store."""
    source, _ = premium_source_with_entitlement_error_then_any(monkeypatch, cache_dir=tmp_path)

    with pytest.raises(AlphaVantageError):
        source.get_prices("IBM", "2025-01-01")

    assert AlphaVantageCapabilityStore(tmp_path).load(API_KEY) == AlphaVantageCapabilities(
        AlphaVantagePlan.FREE,
        indexes_enabled=False,
    )


@pytest.mark.parametrize(
    "category",
    [AlphaVantageErrorCategory.GENERIC, AlphaVantageErrorCategory.QUOTA],
)
def test_non_entitlement_errors_do_not_downgrade(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    category: AlphaVantageErrorCategory,
) -> None:
    """Other API errors propagate without changing capabilities or the cache."""
    install_client(monkeypatch, [AlphaVantageError("Error temporal.", category)])
    source = make_source(AlphaVantagePlan.PREMIUM, indexes_enabled=True, cache_dir=tmp_path)

    with pytest.raises(AlphaVantageError):
        source.get_prices("IBM", "2025-01-01")

    assert source.plan is AlphaVantagePlan.PREMIUM
    assert source.indexes_enabled is True
    assert AlphaVantageCapabilityStore(tmp_path).load(API_KEY) is None


def test_index_route_requests_daily_index_data(monkeypatch: pytest.MonkeyPatch) -> None:
    """The SP500 alias becomes SPX on the daily index endpoint."""
    stub = install_client(monkeypatch, [index_payload(pd.Timestamp("2025-01-02"), 3)])

    asset = premium_source().get_prices("INDEX:SP500", "2025-01-02")

    assert stub.calls == [{"function": "INDEX_DATA", "symbol": "SPX", "interval": "daily"}]
    assert asset.ticker == "INDEX:SP500"
    assert asset.source == "Alpha Vantage (premium, daily)"
    assert list(asset.prices) == [5000.0, 5001.0, 5002.0]


def test_index_symbols_are_uppercased_without_an_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    """Other valid index symbols are only uppercased."""
    stub = install_client(monkeypatch, [index_payload(pd.Timestamp("2025-01-02"), 2)])

    asset = premium_source().get_prices("INDEX:ndx", "2025-01-02")

    assert stub.calls == [{"function": "INDEX_DATA", "symbol": "NDX", "interval": "daily"}]
    assert asset.ticker == "INDEX:ndx"


@pytest.mark.parametrize(
    ("plan", "indexes_enabled"),
    [
        (AlphaVantagePlan.FREE, False),
        (AlphaVantagePlan.PREMIUM, False),
    ],
)
def test_unavailable_indexes_fail_before_http(
    monkeypatch: pytest.MonkeyPatch,
    plan: AlphaVantagePlan,
    *,
    indexes_enabled: bool,
) -> None:
    """Indexes require both a premium plan and the index entitlement."""
    stub = install_client(monkeypatch, [index_payload(pd.Timestamp("2025-01-02"), 2)])
    source = make_source(plan, indexes_enabled=indexes_enabled)

    with pytest.raises(ValueError, match="índice"):
        source.get_prices("INDEX:SP500", "2025-01-01")

    assert stub.calls == []


def test_index_entitlement_denial_disables_only_indexes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """An index entitlement denial keeps the premium plan and disables indexes only."""
    source, calls = premium_source_with_index_entitlement_error(monkeypatch, cache_dir=tmp_path)

    with pytest.raises(AlphaVantageError):
        source.get_prices("INDEX:SP500", "2025-01-01")

    assert source.plan is AlphaVantagePlan.PREMIUM
    assert source.indexes_enabled is False
    assert len(calls) == 1


def test_index_entitlement_denial_persists_premium_capabilities(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The persisted snapshot records premium without index access."""
    source, _ = premium_source_with_index_entitlement_error(monkeypatch, cache_dir=tmp_path)

    with pytest.raises(AlphaVantageError):
        source.get_prices("INDEX:SP500", "2025-01-01")

    assert AlphaVantageCapabilityStore(tmp_path).load(API_KEY) == AlphaVantageCapabilities(
        AlphaVantagePlan.PREMIUM,
        indexes_enabled=False,
    )


def test_index_entitlement_denial_keeps_other_families(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Other families keep working with premium provenance after an index denial."""
    error = AlphaVantageError(
        "La clave no tiene acceso al endpoint de índices.",
        AlphaVantageErrorCategory.ENTITLEMENT,
    )
    stub = install_client(monkeypatch, [error, fx_payload(pd.Timestamp("2025-01-02"), 2)])
    source = premium_source(cache_dir=tmp_path)

    with pytest.raises(AlphaVantageError):
        source.get_prices("INDEX:SP500", "2025-01-01")
    asset = source.get_prices("FX:EUR/USD", "2025-01-02")

    assert asset.source == "Alpha Vantage (premium, daily)"
    assert len(stub.calls) == 2


def test_non_index_entitlement_errors_keep_capabilities(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """An entitlement denial outside indexes does not change runtime capabilities."""
    install_client(
        monkeypatch,
        [AlphaVantageError("Sin acceso.", AlphaVantageErrorCategory.ENTITLEMENT)],
    )
    source = premium_source(cache_dir=tmp_path)

    with pytest.raises(AlphaVantageError):
        source.get_prices("FX:EUR/USD", "2025-01-01")

    assert source.plan is AlphaVantagePlan.PREMIUM
    assert source.indexes_enabled is True
    assert AlphaVantageCapabilityStore(tmp_path).load(API_KEY) is None


def test_fx_route_requests_full_history(monkeypatch: pytest.MonkeyPatch) -> None:
    """FX pairs use the daily endpoint with the complete history."""
    stub = install_client(monkeypatch, [fx_payload(pd.Timestamp("2025-01-02"), 3)])

    asset = premium_source().get_prices("FX:eur/usd", "2025-01-02")

    assert stub.calls == [
        {
            "function": "FX_DAILY",
            "from_symbol": "EUR",
            "to_symbol": "USD",
            "outputsize": "full",
        }
    ]
    assert asset.ticker == "FX:eur/usd"
    assert asset.source == "Alpha Vantage (premium, daily)"
    assert list(asset.prices) == [1.1, 1.101, 1.102]


def test_fx_full_history_is_not_subject_to_the_compact_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A free key still receives uncapped FX history with free provenance."""
    stub = install_client(monkeypatch, [fx_payload(pd.Timestamp("2025-01-02"), 100)])

    asset = make_source(AlphaVantagePlan.FREE).get_prices("FX:EUR/USD", "2020-01-01")

    assert stub.calls[0]["outputsize"] == "full"
    assert asset.prices.index.min() == pd.Timestamp("2025-01-02")
    assert asset.source == "Alpha Vantage (free, daily)"


def test_crypto_route_uses_the_current_plain_close(monkeypatch: pytest.MonkeyPatch) -> None:
    """Crypto requests the digital-currency endpoint and extracts plain ``4. close``."""
    stub = install_client(monkeypatch, [crypto_payload(pd.Timestamp("2025-01-02"), 2)])

    asset = premium_source().get_prices("CRYPTO:1inch/usd", "2025-01-02")

    assert stub.calls == [
        {"function": "DIGITAL_CURRENCY_DAILY", "symbol": "1INCH", "market": "USD"}
    ]
    assert asset.ticker == "CRYPTO:1inch/usd"
    assert asset.source == "Alpha Vantage (premium, daily)"
    assert list(asset.prices) == [40000.0, 40001.0]


@pytest.mark.parametrize(
    ("ticker", "expected", "field"),
    [
        ("COMMODITY:WTI", {"function": "WTI", "interval": "daily"}, "value"),
        ("COMMODITY:BRENT", {"function": "BRENT", "interval": "daily"}, "value"),
        ("COMMODITY:NATURAL_GAS", {"function": "NATURAL_GAS", "interval": "daily"}, "value"),
        (
            "COMMODITY:GOLD",
            {"function": "GOLD_SILVER_HISTORY", "symbol": "GOLD", "interval": "daily"},
            "price",
        ),
        (
            "COMMODITY:XAU",
            {"function": "GOLD_SILVER_HISTORY", "symbol": "GOLD", "interval": "daily"},
            "price",
        ),
        (
            "COMMODITY:SILVER",
            {"function": "GOLD_SILVER_HISTORY", "symbol": "SILVER", "interval": "daily"},
            "price",
        ),
        (
            "COMMODITY:XAG",
            {"function": "GOLD_SILVER_HISTORY", "symbol": "SILVER", "interval": "daily"},
            "price",
        ),
    ],
)
def test_commodity_routes_force_daily_interval(
    monkeypatch: pytest.MonkeyPatch,
    ticker: str,
    expected: dict[str, str],
    field: str,
) -> None:
    """Approved commodity aliases always request the daily interval."""
    stub = install_client(
        monkeypatch,
        [commodity_payload(pd.Timestamp("2025-01-02"), 2, field=field, base=70.0)],
    )

    asset = premium_source().get_prices(ticker, "2025-01-02")

    assert stub.calls == [expected]
    assert asset.ticker == ticker
    assert asset.source == "Alpha Vantage (premium, daily)"
    assert list(asset.prices) == [70.0, 71.0]


@pytest.mark.parametrize(
    "ticker",
    [
        "FX:../USD",
        "FX:EUR/USD/extra",
        "CRYPTO:BTC/..",
        "UNKNOWN:IBM",
    ],
)
def test_invalid_prefixed_tickers_fail_before_http(
    monkeypatch: pytest.MonkeyPatch,
    ticker: str,
) -> None:
    """Malformed pairs and unknown prefixes never reach the client."""
    stub = install_client(monkeypatch, [index_payload(pd.Timestamp("2025-01-02"), 2)])
    source = premium_source()

    with pytest.raises(ValueError, match="Alpha Vantage"):
        source.get_prices(ticker, "2025-01-01")

    assert stub.calls == []


@pytest.mark.parametrize(
    "ticker",
    [
        "INDEX:../SPX",
        "INDEX:SP 500",
        "INDEX:",
        "FX:EURUSD",
        "FX:EUR/US",
        "FX:EUR//USD",
        "CRYPTO:BTC",
        "CRYPTO:/USD",
        "COMMODITY:",
        "COMMODITY:COPPER",
        "COMMODITY:ALL_COMMODITIES",
        "COMMODITY:WTI:EXTRA",
        ":IBM",
    ],
)
def test_more_invalid_tickers_fail_before_http(
    monkeypatch: pytest.MonkeyPatch,
    ticker: str,
) -> None:
    """Separators, traversal, malformed codes and unapproved commodities are rejected."""
    stub = install_client(monkeypatch, [index_payload(pd.Timestamp("2025-01-02"), 2)])
    source = premium_source()

    with pytest.raises(ValueError, match="Alpha Vantage"):
        source.get_prices(ticker, "2025-01-01")

    assert stub.calls == []


@pytest.mark.parametrize("payload", [{}, {"data": []}])
def test_missing_array_table_raises(
    monkeypatch: pytest.MonkeyPatch,
    payload: object,
) -> None:
    """Responses without a usable array table are rejected."""
    install_client(monkeypatch, [payload])
    source = premium_source()

    with pytest.raises(ValueError, match="serie diaria"):
        source.get_prices("INDEX:SPX", "2025-01-02")


def test_non_object_array_row_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unexpected array row shapes are rejected instead of silently ignored."""
    install_client(monkeypatch, [{"data": [["not", "a", "row"]]}])
    source = premium_source()

    with pytest.raises(TypeError, match="fila diaria"):
        source.get_prices("INDEX:SPX", "2025-01-02")


def test_invalid_array_dates_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing or non-text array dates are rejected."""
    install_client(monkeypatch, [{"data": [{"date": None, "close": "100.0"}]}])
    source = premium_source()

    with pytest.raises(ValueError, match="fechas no válidas"):
        source.get_prices("INDEX:SPX", "2025-01-02")


def test_free_compact_cap_uses_raw_row_count(monkeypatch: pytest.MonkeyPatch) -> None:
    """Normalization cannot hide a capped 100-row compact response."""
    dates = _observation_dates(pd.Timestamp("2025-01-02"), 100)
    table: dict[str, object] = {
        date.strftime("%Y-%m-%d"): _daily_row(100.0 + position, adjusted=False)
        for position, date in enumerate(dates)
    }
    table[dates[50].strftime("%Y-%m-%d")] = {"4. close": "not-a-number"}
    install_client(monkeypatch, [{"Time Series (Daily)": table}])
    source = make_source(AlphaVantagePlan.FREE)

    with pytest.raises(ValueError, match="100"):
        source.get_prices("IBM", "2020-01-01")


def test_fx_series_round_trips_through_the_csv_cache(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A routed pair can be written to and read from the generic CSV cache."""
    stub = install_client(monkeypatch, [fx_payload(pd.Timestamp("2025-01-02"), 5)])
    cached = CachedPriceSource(premium_source(), cache_dir=tmp_path)

    first = cached.get_prices("FX:EUR/USD", "2025-01-02", "2025-01-09")
    second = cached.get_prices("FX:EUR/USD", "2025-01-02", "2025-01-09")

    assert len(stub.calls) == 1
    assert second.ticker == "FX:EUR/USD"
    assert second.source.endswith("(cache)")
    assert list(second.prices) == list(first.prices)
    assert (tmp_path / "alpha-vantage" / "FX:EUR" / "USD.csv").is_file()


def test_non_equity_window_is_inclusive_start_and_exclusive_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Routed families reuse the inclusive/exclusive window semantics."""
    install_client(monkeypatch, [index_payload(pd.Timestamp("2025-01-02"), 4)])

    asset = premium_source().get_prices("INDEX:SPX", "2025-01-03", "2025-01-07")

    assert list(asset.prices.index) == [pd.Timestamp("2025-01-03"), pd.Timestamp("2025-01-06")]


def test_get_many_routes_each_ticker_family(monkeypatch: pytest.MonkeyPatch) -> None:
    """Batch extraction keeps one keyed series and one request per family."""
    stub = install_client(
        monkeypatch,
        [index_payload(pd.Timestamp("2025-01-02"), 2), fx_payload(pd.Timestamp("2025-01-02"), 2)],
    )

    result = premium_source().get_many(["INDEX:SPX", "FX:EUR/USD"], "2025-01-02")

    assert set(result) == {"INDEX:SPX", "FX:EUR/USD"}
    assert result["INDEX:SPX"].ticker == "INDEX:SPX"
    assert result["FX:EUR/USD"].ticker == "FX:EUR/USD"
    assert [call["function"] for call in stub.calls] == ["INDEX_DATA", "FX_DAILY"]
