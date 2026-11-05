"""Tests for the Alpha Vantage equity price source."""

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

    with pytest.raises(ValueError, match="vacío"):
        make_source(AlphaVantagePlan.FREE).get_prices("   ", "2025-01-02")

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

    with pytest.raises(ValueError, match="serie diaria"):
        make_source(AlphaVantagePlan.FREE).get_prices("IBM", "2025-01-02")


def test_non_object_daily_row_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unexpected row shapes are rejected instead of silently ignored."""
    install_client(monkeypatch, [{"Time Series (Daily)": {"2025-01-02": ["not", "a", "row"]}}])

    with pytest.raises(TypeError, match="fila diaria"):
        make_source(AlphaVantagePlan.FREE).get_prices("IBM", "2025-01-02")


def test_invalid_dates_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    """Malformed observation dates are rejected."""
    install_client(monkeypatch, [{"Time Series (Daily)": {"not-a-date": {"4. close": "100.0"}}}])

    with pytest.raises(ValueError, match="fechas no válidas"):
        make_source(AlphaVantagePlan.FREE).get_prices("IBM", "2025-01-02")


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
