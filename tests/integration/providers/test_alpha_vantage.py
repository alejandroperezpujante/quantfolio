"""Alpha Vantage client, capability discovery, routing and runtime downgrade behavior."""

from __future__ import annotations

import hashlib
import json
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Self, cast
from urllib.parse import parse_qs, urlparse

import pandas as pd
import pytest

from quantfolio.sources import (
    AlphaVantagePlan,
    AlphaVantageSource,
    CachedPriceSource,
    alpha_vantage,
)
from quantfolio.sources.alpha_vantage.capabilities import (
    CAPABILITY_TTL,
    SCHEMA_VERSION,
    AlphaVantageCapabilities,
    AlphaVantageCapabilityStore,
    create_alpha_vantage_source,
)
from quantfolio.sources.alpha_vantage.client import (
    ALPHA_VANTAGE_QUERY_URL,
    HTTP_TIMEOUT,
    AlphaVantageClient,
    AlphaVantageError,
    AlphaVantageErrorCategory,
)
from tests.support.transports import alpha_daily_payload, install_alpha

if TYPE_CHECKING:
    from collections.abc import Sequence

API_KEY = "test-key"
FREE_FUNCTION = "TIME_SERIES_DAILY"
PREMIUM_FUNCTION = "TIME_SERIES_DAILY_ADJUSTED"
INDEX_FUNCTION = "INDEX_DATA"
FX_FUNCTION = "FX_DAILY"
CRYPTO_FUNCTION = "DIGITAL_CURRENCY_DAILY"
GOLD_FUNCTION = "GOLD_SILVER_HISTORY"


def _date_strings(periods: int = 3, first: str = "2025-01-02") -> list[str]:
    return [f"{day:%Y-%m-%d}" for day in pd.bdate_range(first, periods=periods)]


def _daily_table(
    periods: int = 3,
    *,
    field: str = "4. close",
    first: str = "2025-01-02",
) -> dict[str, object]:
    return {
        day: {field: str(100.0 + position)}
        for position, day in enumerate(_date_strings(periods, first))
    }


def _fx_payload(periods: int = 3, first: str = "2025-01-02") -> dict[str, object]:
    return {
        "Time Series FX (Daily)": {
            day: {"4. close": str(1.10 + position / 1_000)}
            for position, day in enumerate(_date_strings(periods, first))
        }
    }


def _crypto_payload(periods: int = 3, first: str = "2025-01-02") -> dict[str, object]:
    return {
        "Time Series (Digital Currency Daily)": {
            day: {"4. close": str(40_000.0 + position)}
            for position, day in enumerate(_date_strings(periods, first))
        }
    }


def _array_payload(
    field: str,
    values: Sequence[float],
    *,
    first: str = "2025-01-02",
) -> dict[str, object]:
    return {
        "data": [
            {"date": day, field: str(value)}
            for day, value in zip(_date_strings(len(values), first), values, strict=True)
        ]
    }


def _source(
    plan: AlphaVantagePlan = AlphaVantagePlan.FREE,
    *,
    indexes_enabled: bool = False,
    cache_dir: Path | str = "data",
) -> AlphaVantageSource:
    return AlphaVantageSource(
        API_KEY,
        plan=plan,
        indexes_enabled=indexes_enabled,
        cache_dir=cache_dir,
    )


def _capability_path(root: Path, api_key: str = API_KEY) -> Path:
    digest = hashlib.sha256(api_key.encode()).hexdigest()
    return root / "alpha-vantage" / "capabilities" / f"{digest}.json"


def _write_capability_payload(root: Path, payload: object) -> Path:
    path = _capability_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _entitlement_error() -> AlphaVantageError:
    return AlphaVantageError("Sin acceso.", AlphaVantageErrorCategory.ENTITLEMENT)


class _RawResponse:
    """Raw bytes or a JSON object returned by the Alpha Vantage HTTP client."""

    def __init__(self, body: bytes | object, *, raw: bool = False) -> None:
        self.body = cast("bytes", body) if raw else json.dumps(body).encode()

    def read(self) -> bytes:
        return self.body

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


def test_alpha_client_targets_the_query_endpoint_and_forces_transport_parameters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The client owns JSON and the credential while preserving caller parameters."""
    urls: list[tuple[str, int]] = []

    def urlopen(url: str, timeout: int = HTTP_TIMEOUT) -> _RawResponse:
        urls.append((url, timeout))
        return _RawResponse({"Meta Data": {"2. Symbol": "IBM"}})

    monkeypatch.setattr("quantfolio.sources.alpha_vantage.client.urlopen", urlopen)
    payload = AlphaVantageClient(API_KEY).get(
        function=FREE_FUNCTION,
        symbol="IBM",
        datatype="csv",
        apikey="caller-key",
    )

    url, timeout = urls[0]
    assert payload == {"Meta Data": {"2. Symbol": "IBM"}}
    assert timeout == 30
    assert urlparse(url).path == "/query"
    assert parse_qs(urlparse(url).query) == {
        "function": [FREE_FUNCTION],
        "symbol": ["IBM"],
        "datatype": ["json"],
        "apikey": [API_KEY],
    }


def test_alpha_client_maps_transport_json_and_shape_failures_without_leaking_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Network and decoding failures become generic Spanish errors without the URL or key."""
    scenarios: tuple[tuple[object, str], ...] = (
        (b"<html>offline</html>", "JSON"),
        (b"", "JSON"),
        ([1, 2], "objeto"),
        ("text", "objeto"),
        (None, "objeto"),
    )
    for body, message in scenarios:

        def urlopen(
            _url: str,
            timeout: int = HTTP_TIMEOUT,
            *,
            response: object = body,
        ) -> _RawResponse:
            del timeout
            if isinstance(response, bytes):
                return _RawResponse(response, raw=True)
            return _RawResponse(response)

        monkeypatch.setattr("quantfolio.sources.alpha_vantage.client.urlopen", urlopen)
        client = AlphaVantageClient(API_KEY)
        with pytest.raises(AlphaVantageError, match=message) as captured:
            client.get(symbol="IBM")
        assert API_KEY not in str(captured.value)
        assert ALPHA_VANTAGE_QUERY_URL not in str(captured.value)

    def offline(_url: str, timeout: int = HTTP_TIMEOUT) -> _RawResponse:
        del timeout
        msg = f"offline {ALPHA_VANTAGE_QUERY_URL}?apikey={API_KEY}"
        raise OSError(msg)

    monkeypatch.setattr("quantfolio.sources.alpha_vantage.client.urlopen", offline)
    client = AlphaVantageClient(API_KEY)
    with pytest.raises(AlphaVantageError, match="No se pudo contactar") as captured:
        client.get(symbol="IBM")
    assert captured.value.__cause__ is None
    assert API_KEY not in str(captured.value)


def test_alpha_control_responses_are_classified_independently_of_wording_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Quota wins over premium wording; every control field needs text."""
    quota_phrases = (
        "rate limit",
        "call frequency",
        "requests per day",
        "requests per minute",
        "requests per second",
    )
    entitlement_phrases = (
        "premium endpoint",
        "premium api",
        "premium member",
        "entitlement",
    )
    fields = ("Error Message", "Information", "Note")
    cases: list[tuple[dict[str, object], AlphaVantageErrorCategory]] = []
    cases.extend(
        ({field: phrase.upper()}, AlphaVantageErrorCategory.QUOTA)
        for field in fields
        for phrase in quota_phrases
    )
    cases.extend(
        ({field: phrase.upper()}, AlphaVantageErrorCategory.ENTITLEMENT)
        for field in fields
        for phrase in entitlement_phrases
    )
    cases.extend(
        [
            ({"Error Message": "invalid"}, AlphaVantageErrorCategory.GENERIC),
            (
                {"Information": "25 requests per day; premium endpoint plans"},
                AlphaVantageErrorCategory.QUOTA,
            ),
            (
                {"Note": "premium endpoint plans", "Information": "rate limit"},
                AlphaVantageErrorCategory.QUOTA,
            ),
            ({"Note": None}, AlphaVantageErrorCategory.GENERIC),
            ({"Note": 42}, AlphaVantageErrorCategory.GENERIC),
        ]
    )

    for payload, expected in cases:

        def urlopen(
            _url: str,
            timeout: int = HTTP_TIMEOUT,
            *,
            response: object = payload,
        ) -> _RawResponse:
            del timeout
            return _RawResponse(response)

        monkeypatch.setattr("quantfolio.sources.alpha_vantage.client.urlopen", urlopen)
        client = AlphaVantageClient(API_KEY)
        with pytest.raises(AlphaVantageError) as captured:
            client.get(symbol="IBM")
        assert captured.value.category is expected


def test_alpha_error_categories_are_read_only_and_serialize_as_strings() -> None:
    """Error metadata is stable and categories preserve their documented values."""
    error = AlphaVantageError("mensaje", AlphaVantageErrorCategory.QUOTA)

    assert [str(category) for category in AlphaVantageErrorCategory] == [
        "generic",
        "quota",
        "entitlement",
    ]
    with pytest.raises(AttributeError):
        error.category = AlphaVantageErrorCategory.GENERIC  # type: ignore[misc]


def test_capability_store_round_trips_hashed_metadata_and_freshness_boundaries(
    tmp_path: Path,
) -> None:
    """Capabilities survive every plan/index combination without storing the raw key."""
    store = AlphaVantageCapabilityStore(tmp_path)
    capabilities = [
        AlphaVantageCapabilities(plan, indexes_enabled=indexes)
        for plan in AlphaVantagePlan
        for indexes in (False, True)
    ]
    for position, snapshot in enumerate(capabilities):
        store.save(f"{API_KEY}-{position}", snapshot)
        assert store.load(f"{API_KEY}-{position}") == snapshot

    store.save(API_KEY, capabilities[0])
    path = _capability_path(tmp_path)
    payload = cast("dict[str, object]", json.loads(path.read_text(encoding="utf-8")))
    assert set(payload) == {"schema_version", "detected_at", "plan", "indexes_enabled"}
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["plan"] == "free"
    assert payload["indexes_enabled"] is False
    assert datetime.fromisoformat(cast("str", payload["detected_at"])).tzinfo is not None
    assert API_KEY not in path.read_text(encoding="utf-8")
    assert len(path.stem) == 64

    fresh = datetime.now(UTC) - CAPABILITY_TTL + timedelta(minutes=5)
    _write_capability_payload(
        tmp_path,
        {
            "schema_version": SCHEMA_VERSION,
            "detected_at": fresh.isoformat(),
            "plan": "premium",
            "indexes_enabled": True,
        },
    )
    assert store.load(API_KEY) == AlphaVantageCapabilities(
        AlphaVantagePlan.PREMIUM,
        indexes_enabled=True,
    )
    expired = datetime.now(UTC) - CAPABILITY_TTL
    _write_capability_payload(
        tmp_path,
        {
            "schema_version": SCHEMA_VERSION,
            "detected_at": expired.isoformat(),
            "plan": "premium",
            "indexes_enabled": True,
        },
    )
    assert store.load(API_KEY) is None


def test_capability_store_treats_unreadable_and_malformed_entries_as_misses(
    tmp_path: Path,
) -> None:
    """Invalid encoding, JSON, metadata or payload shapes cannot assert entitlements."""
    store = AlphaVantageCapabilityStore(tmp_path)
    path = _capability_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\xff\xfe")
    assert store.load(API_KEY) is None
    path.write_text("not json", encoding="utf-8")
    assert store.load(API_KEY) is None

    invalid_payloads: tuple[object, ...] = (
        [],
        {},
        {"schema_version": 1, "detected_at": datetime.now(UTC).isoformat(), "plan": "free"},
        {
            "schema_version": 1,
            "detected_at": datetime.now(UTC).isoformat(),
            "plan": "gold",
            "indexes_enabled": False,
        },
        {
            "schema_version": 1,
            "detected_at": datetime.now(UTC).isoformat(),
            "plan": 2,
            "indexes_enabled": False,
        },
        {
            "schema_version": 1,
            "detected_at": 42,
            "plan": "free",
            "indexes_enabled": False,
        },
        {
            "schema_version": 1,
            "detected_at": datetime.now(UTC).isoformat(),
            "plan": "free",
            "indexes_enabled": "yes",
        },
        {
            "schema_version": 1,
            "detected_at": "2026-11-04T10:00:00",
            "plan": "free",
            "indexes_enabled": False,
        },
        {
            "schema_version": 1,
            "detected_at": "not-a-timestamp",
            "plan": "free",
            "indexes_enabled": False,
        },
        {
            "schema_version": 1,
            "detected_at": "2999-01-01T00:00:00+00:00",
            "plan": "free",
            "indexes_enabled": False,
        },
        {
            "schema_version": 999,
            "detected_at": datetime.now(UTC).isoformat(),
            "plan": "free",
            "indexes_enabled": False,
        },
    )
    for payload in invalid_payloads:
        _write_capability_payload(tmp_path, payload)
        assert store.load(API_KEY) is None

    path.unlink()
    path.mkdir()
    assert store.load(API_KEY) is None


def test_capability_store_invalidates_and_survives_filesystem_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalidation is best effort and write failures never leave partial entries."""
    store = AlphaVantageCapabilityStore(tmp_path)
    store.save(API_KEY, AlphaVantageCapabilities(AlphaVantagePlan.FREE, indexes_enabled=False))
    store.invalidate(API_KEY)
    store.invalidate(API_KEY)
    assert not _capability_path(tmp_path).exists()

    def fail_replace(_self: Path, _target: Path) -> Path:
        msg = "filesystem unavailable"
        raise OSError(msg)

    monkeypatch.setattr(Path, "replace", fail_replace)
    capabilities = AlphaVantageCapabilities(AlphaVantagePlan.PREMIUM, indexes_enabled=True)
    with pytest.warns(RuntimeWarning, match="caché"):
        store.save(API_KEY, capabilities)
    assert not _capability_path(tmp_path).exists()
    assert list(_capability_path(tmp_path).parent.iterdir()) == []

    monkeypatch.undo()
    store.save(API_KEY, AlphaVantageCapabilities(AlphaVantagePlan.FREE, indexes_enabled=False))

    def fail_unlink(_self: Path, *, missing_ok: bool = False) -> None:
        del missing_ok
        msg = "filesystem unavailable"
        raise OSError(msg)

    monkeypatch.setattr(Path, "unlink", fail_unlink)
    with pytest.warns(RuntimeWarning, match="caché"):
        store.invalidate(API_KEY)
    assert _capability_path(tmp_path).exists()


def test_capability_values_are_pinned_and_frozen() -> None:
    """Plan names, cache constants and capability snapshots are stable."""
    assert [plan.value for plan in AlphaVantagePlan] == ["free", "premium"]
    assert SCHEMA_VERSION == 1
    assert timedelta(hours=24) == CAPABILITY_TTL
    snapshot = AlphaVantageCapabilities(AlphaVantagePlan.FREE, indexes_enabled=False)
    with pytest.raises(FrozenInstanceError):
        snapshot.plan = AlphaVantagePlan.PREMIUM  # type: ignore[misc]


def test_discovery_detects_free_premium_and_cached_capabilities(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The mandatory key probe is followed by only the entitlement probes that are needed."""
    free_calls = install_alpha(
        monkeypatch,
        {
            FREE_FUNCTION: {"Time Series (Daily)": _daily_table()},
            PREMIUM_FUNCTION: _entitlement_error(),
        },
    )
    free = create_alpha_vantage_source(API_KEY, cache_dir=tmp_path)
    assert free.plan is AlphaVantagePlan.FREE
    assert free.indexes_enabled is False
    assert json.dumps(free_calls, sort_keys=True).count(PREMIUM_FUNCTION) == 1

    premium_calls = install_alpha(
        monkeypatch,
        {
            FREE_FUNCTION: {"Time Series (Daily)": _daily_table()},
            PREMIUM_FUNCTION: alpha_daily_payload([100.0], adjusted=True),
            INDEX_FUNCTION: _array_payload("close", [5_000.0]),
        },
    )
    premium = create_alpha_vantage_source("premium-key", cache_dir=tmp_path)
    assert premium.plan is AlphaVantagePlan.PREMIUM
    assert premium.indexes_enabled is True
    assert [call["function"] for call in premium_calls] == [
        FREE_FUNCTION,
        PREMIUM_FUNCTION,
        INDEX_FUNCTION,
    ]

    AlphaVantageCapabilityStore(tmp_path).save(
        "cached-key",
        AlphaVantageCapabilities(AlphaVantagePlan.PREMIUM, indexes_enabled=True),
    )
    cached_calls = install_alpha(
        monkeypatch,
        {FREE_FUNCTION: {"Time Series (Daily)": _daily_table()}},
    )
    cached = create_alpha_vantage_source("cached-key", cache_dir=tmp_path)
    assert cached.plan is AlphaVantagePlan.PREMIUM
    assert cached.indexes_enabled is True
    assert [call["function"] for call in cached_calls] == [FREE_FUNCTION]


def test_discovery_handles_index_denial_transient_and_malformed_probes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only an explicit index denial is persisted; ambiguous probes warn and stay uncached."""
    install_alpha(
        monkeypatch,
        {
            FREE_FUNCTION: {"Time Series (Daily)": _daily_table()},
            PREMIUM_FUNCTION: alpha_daily_payload([100.0], adjusted=True),
            INDEX_FUNCTION: _entitlement_error(),
        },
    )
    denied = create_alpha_vantage_source("denied-key", cache_dir=tmp_path)
    assert denied.plan is AlphaVantagePlan.PREMIUM
    assert denied.indexes_enabled is False
    assert AlphaVantageCapabilityStore(tmp_path).load("denied-key") == AlphaVantageCapabilities(
        AlphaVantagePlan.PREMIUM,
        indexes_enabled=False,
    )

    ambiguous_responses: tuple[object, ...] = (
        AlphaVantageError("temporal", AlphaVantageErrorCategory.GENERIC),
        {},
        {"data": []},
        {"data": [{"date": "2025-01-02"}]},
    )
    for position, index_response in enumerate(ambiguous_responses):
        key = f"ambiguous-{position}"
        install_alpha(
            monkeypatch,
            {
                FREE_FUNCTION: {"Time Series (Daily)": _daily_table()},
                PREMIUM_FUNCTION: alpha_daily_payload([100.0], adjusted=True),
                INDEX_FUNCTION: index_response,
            },
        )
        with pytest.warns(RuntimeWarning, match="índices"):
            source = create_alpha_vantage_source(key, cache_dir=tmp_path)
        assert source.plan is AlphaVantagePlan.PREMIUM
        assert source.indexes_enabled is False
        assert AlphaVantageCapabilityStore(tmp_path).load(key) is None


def test_discovery_rejects_ambiguous_plan_or_invalid_basic_probes_and_invalidates_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unexpected plan data raises, while invalid startup data removes stale capabilities."""
    store = AlphaVantageCapabilityStore(tmp_path)
    install_alpha(
        monkeypatch,
        {
            FREE_FUNCTION: {"Time Series (Daily)": _daily_table()},
            PREMIUM_FUNCTION: {"unexpected": "shape"},
        },
    )
    with pytest.raises(AlphaVantageError):
        create_alpha_vantage_source("ambiguous-plan", cache_dir=tmp_path)
    assert store.load("ambiguous-plan") is None

    bad_basics: tuple[dict[str, object], ...] = (
        {"Time Series (Daily)": {}},
        {"Time Series (Daily)": {"2025-01-02": {"unexpected": "100"}}},
    )
    for bad_basic in bad_basics:
        store.save(API_KEY, AlphaVantageCapabilities(AlphaVantagePlan.FREE, indexes_enabled=False))
        install_alpha(monkeypatch, {FREE_FUNCTION: bad_basic})
        with pytest.raises(AlphaVantageError):
            create_alpha_vantage_source(API_KEY, cache_dir=tmp_path)
        assert store.load(API_KEY) is None


def test_discovery_still_returns_a_source_when_capability_persistence_warns(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A valid key remains usable when the capability cache cannot be written."""
    install_alpha(
        monkeypatch,
        {
            FREE_FUNCTION: {"Time Series (Daily)": _daily_table()},
            PREMIUM_FUNCTION: _entitlement_error(),
        },
    )

    def fail_replace(_self: Path, _target: Path) -> Path:
        msg = "filesystem unavailable"
        raise OSError(msg)

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.warns(RuntimeWarning, match="caché"):
        source = create_alpha_vantage_source(API_KEY, cache_dir=tmp_path)
    assert source.plan is AlphaVantagePlan.FREE
    assert source.indexes_enabled is False


def test_alpha_equities_choose_raw_compact_or_adjusted_full_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The plan decides endpoint, output size, field and provenance."""
    free_calls = install_alpha(
        monkeypatch,
        {FREE_FUNCTION: alpha_daily_payload([100.0, 101.0, 102.0])},
    )
    free_asset = _source().get_prices("IBM", "2025-01-02")
    assert free_calls[-1] == {"function": FREE_FUNCTION, "symbol": "IBM", "outputsize": "compact"}
    assert free_asset.source == "Alpha Vantage (free, raw)"
    assert list(free_asset.prices) == [100.0, 101.0, 102.0]

    premium_calls = install_alpha(
        monkeypatch,
        {PREMIUM_FUNCTION: alpha_daily_payload([100.0, 101.0, 102.0], adjusted=True)},
    )
    premium_asset = _source(AlphaVantagePlan.PREMIUM, indexes_enabled=True).get_prices(
        "IBM",
        "2025-01-02",
    )
    assert premium_calls[-1] == {
        "function": PREMIUM_FUNCTION,
        "symbol": "IBM",
        "outputsize": "full",
    }
    assert premium_asset.source == "Alpha Vantage (premium, adjusted)"
    assert list(premium_asset.prices) == [100.0, 101.0, 102.0]


def test_alpha_equity_window_and_normalization_use_public_price_rules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Half-open windows, ticker identity and positive finite closes are preserved."""
    table = _daily_table(5)
    table["2025-01-06"] = {"4. close": "invalid"}
    table["2025-01-07"] = {"4. close": "0"}
    install_alpha(monkeypatch, {FREE_FUNCTION: {"Time Series (Daily)": table}})

    source = _source()
    asset = source.get_prices(" ibm ", "2025-01-03", "2025-01-08")

    assert asset.ticker == "ibm"
    assert list(asset.prices.index) == [pd.Timestamp("2025-01-03")]
    assert list(asset.prices) == [101.0]
    with pytest.raises(ValueError, match="No se han encontrado"):
        source.get_prices("IBM", "2026-01-01")
    with pytest.raises(ValueError, match="ticker"):
        source.get_prices("   ", "2025-01-01")


def test_alpha_daily_payload_validation_covers_tables_rows_and_dates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Malformed table and array payloads fail with their public Spanish messages."""
    table_failures: tuple[dict[str, object], ...] = (
        {},
        {"Time Series (Daily)": []},
        {"Time Series (Daily)": {}},
    )
    for payload in table_failures:
        install_alpha(monkeypatch, {FREE_FUNCTION: payload})
        source = _source()
        with pytest.raises(ValueError, match="serie diaria"):
            source.get_prices("IBM", "2025-01-02")

    install_alpha(
        monkeypatch,
        {FREE_FUNCTION: {"Time Series (Daily)": {"2025-01-02": ["not", "a", "row"]}}},
    )
    source = _source()
    with pytest.raises(TypeError, match="fila diaria"):
        source.get_prices("IBM", "2025-01-02")
    for day in ("not-a-date", ""):
        install_alpha(
            monkeypatch,
            {FREE_FUNCTION: {"Time Series (Daily)": {day: {"4. close": "100"}}}},
        )
        source = _source()
        with pytest.raises(ValueError, match="fechas no válidas"):
            source.get_prices("IBM", "2025-01-02")


def test_alpha_compact_and_full_histories_apply_the_correct_retention_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only a full 100-row compact response can prove that the requested start was clipped."""
    capped = alpha_daily_payload([100.0 + position for position in range(100)])
    install_alpha(monkeypatch, {FREE_FUNCTION: capped})
    free = _source()
    with pytest.raises(ValueError, match="100"):
        free.get_prices("IBM", "2020-01-01")
    assert len(free.get_prices("IBM", "2025-01-02").prices) == 100

    dates = _date_strings(100)
    raw_table = _daily_table(100)
    raw_table[dates[50]] = {"4. close": "not-a-number"}
    install_alpha(monkeypatch, {FREE_FUNCTION: {"Time Series (Daily)": raw_table}})
    source = _source()
    with pytest.raises(ValueError, match="100"):
        source.get_prices("IBM", "2020-01-01")

    install_alpha(
        monkeypatch,
        {
            PREMIUM_FUNCTION: alpha_daily_payload(
                [100.0 + p for p in range(100)], adjusted=True, first="2020-06-01"
            )
        },
    )
    premium = _source(AlphaVantagePlan.PREMIUM, indexes_enabled=True)
    assert len(premium.get_prices("NEW", "2020-01-01").prices) == 100


def test_alpha_equity_entitlement_denial_downgrades_and_persists_without_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A premium equity denial switches to free semantics, persists once and does not retry."""
    installed = install_alpha(monkeypatch, [_entitlement_error(), alpha_daily_payload([1.0])])
    source = _source(AlphaVantagePlan.PREMIUM, indexes_enabled=True, cache_dir=tmp_path)

    with pytest.raises(AlphaVantageError):
        source.get_prices("IBM", "2025-01-01")

    assert len(installed) == 1
    assert source.plan is AlphaVantagePlan.FREE
    assert source.indexes_enabled is False
    assert source.cache_namespace == "Alpha Vantage free v2"
    assert AlphaVantageCapabilityStore(tmp_path).load(API_KEY) == AlphaVantageCapabilities(
        AlphaVantagePlan.FREE,
        indexes_enabled=False,
    )


def test_alpha_equity_denial_still_downgrades_when_capability_write_warns(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Capability persistence is best effort and never blocks a runtime downgrade."""
    install_alpha(monkeypatch, [_entitlement_error()])
    source = _source(AlphaVantagePlan.PREMIUM, indexes_enabled=True, cache_dir=tmp_path)

    def fail_replace(_self: Path, _target: Path) -> Path:
        msg = "unavailable"
        raise OSError(msg)

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.warns(RuntimeWarning, match="caché"), pytest.raises(AlphaVantageError):
        source.get_prices("IBM", "2025-01-01")
    assert source.plan is AlphaVantagePlan.FREE
    assert source.indexes_enabled is False


def test_alpha_non_entitlement_failures_preserve_capabilities(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Quota and generic failures propagate without changing the plan or cache."""
    for category in (AlphaVantageErrorCategory.GENERIC, AlphaVantageErrorCategory.QUOTA):
        install_alpha(monkeypatch, [AlphaVantageError("temporal", category)])
        source = _source(AlphaVantagePlan.PREMIUM, indexes_enabled=True, cache_dir=tmp_path)
        with pytest.raises(AlphaVantageError):
            source.get_prices("IBM", "2025-01-01")
        assert source.plan is AlphaVantagePlan.PREMIUM
        assert source.indexes_enabled is True
        assert AlphaVantageCapabilityStore(tmp_path).load(API_KEY) is None


def test_alpha_index_routes_validate_alias_plan_entitlement_and_denial(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Index routing is gated before HTTP and a denial preserves the premium plan."""
    calls = install_alpha(monkeypatch, {INDEX_FUNCTION: _array_payload("close", [5_000.0])})
    source = _source(AlphaVantagePlan.PREMIUM, indexes_enabled=True)
    alias = source.get_prices("INDEX:SP500", "2025-01-02")
    upper = source.get_prices("INDEX:ndx", "2025-01-02")
    assert calls[-2]["symbol"] == "SPX"
    assert calls[-1]["symbol"] == "NDX"
    assert alias.prices.iloc[0] == 5_000.0
    assert upper.ticker == "INDEX:ndx"

    for plan, indexes in (
        (AlphaVantagePlan.FREE, False),
        (AlphaVantagePlan.PREMIUM, False),
    ):
        limited_source = _source(plan, indexes_enabled=indexes)
        with pytest.raises(ValueError, match="índice"):
            limited_source.get_prices("INDEX:SP500", "2025-01-01")

    install_alpha(
        monkeypatch,
        {INDEX_FUNCTION: _entitlement_error(), FX_FUNCTION: _fx_payload()},
    )
    denied = _source(AlphaVantagePlan.PREMIUM, indexes_enabled=True, cache_dir=tmp_path)
    with pytest.raises(AlphaVantageError):
        denied.get_prices("INDEX:SP500", "2025-01-01")
    assert denied.plan is AlphaVantagePlan.PREMIUM
    assert denied.indexes_enabled is False
    assert denied.get_prices("FX:EUR/USD", "2025-01-02").quote_currency == "USD"
    assert AlphaVantageCapabilityStore(tmp_path).load(API_KEY) == AlphaVantageCapabilities(
        AlphaVantagePlan.PREMIUM,
        indexes_enabled=False,
    )


def test_alpha_non_index_entitlement_errors_do_not_change_capabilities(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An entitlement denial outside the index family is not a plan downgrade signal."""
    install_alpha(monkeypatch, {FX_FUNCTION: _entitlement_error()})
    source = _source(AlphaVantagePlan.PREMIUM, indexes_enabled=True, cache_dir=tmp_path)
    with pytest.raises(AlphaVantageError):
        source.get_prices("FX:EUR/USD", "2025-01-01")
    assert source.plan is AlphaVantagePlan.PREMIUM
    assert source.indexes_enabled is True
    assert AlphaVantageCapabilityStore(tmp_path).load(API_KEY) is None


def test_alpha_fx_crypto_and_commodity_routes_normalize_their_public_series(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-equity families use their wire endpoint, parsing shape and quote metadata."""
    fx_calls = install_alpha(monkeypatch, {FX_FUNCTION: _fx_payload(3)})
    fx = _source(AlphaVantagePlan.PREMIUM, indexes_enabled=True).get_prices(
        "FX:eur/usd",
        "2025-01-02",
    )
    assert fx_calls[-1] == {
        "function": FX_FUNCTION,
        "from_symbol": "EUR",
        "to_symbol": "USD",
        "outputsize": "full",
    }
    assert fx.ticker == "FX:eur/usd"
    assert fx.quote_currency == "USD"
    assert list(fx.prices) == pytest.approx([1.1, 1.101, 1.102])

    crypto_calls = install_alpha(monkeypatch, {CRYPTO_FUNCTION: _crypto_payload(2)})
    crypto = _source(AlphaVantagePlan.PREMIUM, indexes_enabled=True).get_prices(
        "CRYPTO:1inch/usd",
        "2025-01-02",
    )
    assert crypto_calls[-1] == {
        "function": CRYPTO_FUNCTION,
        "symbol": "1INCH",
        "market": "USD",
    }
    assert crypto.quote_currency == "USD"
    assert crypto.ticker == "CRYPTO:1inch/usd"

    for market in ("BTC", "USDT"):
        install_alpha(monkeypatch, {CRYPTO_FUNCTION: _crypto_payload(2)})
        assert _source().get_prices(f"CRYPTO:ETH/{market}", "2025-01-02").quote_currency is None

    commodity_routes = {
        "WTI": ("WTI", {"interval": "daily"}, "value"),
        "BRENT": ("BRENT", {"interval": "daily"}, "value"),
        "NATURAL_GAS": ("NATURAL_GAS", {"interval": "daily"}, "value"),
        "GOLD": (GOLD_FUNCTION, {"symbol": "GOLD", "interval": "daily"}, "price"),
        "XAU": (GOLD_FUNCTION, {"symbol": "GOLD", "interval": "daily"}, "price"),
        "SILVER": (GOLD_FUNCTION, {"symbol": "SILVER", "interval": "daily"}, "price"),
        "XAG": (GOLD_FUNCTION, {"symbol": "SILVER", "interval": "daily"}, "price"),
    }
    for alias, (function, parameters, field) in commodity_routes.items():
        calls = install_alpha(
            monkeypatch,
            {function: _array_payload(field, [70.0, 71.0])},
        )
        asset = _source().get_prices(f"COMMODITY:{alias}", "2025-01-02")
        assert calls[-1] == {"function": function, **parameters}
        assert list(asset.prices) == [70.0, 71.0]


def test_alpha_invalid_prefixed_tickers_never_reach_the_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unknown prefixes, traversal and malformed family codes fail before HTTP."""
    install_alpha(monkeypatch, [RuntimeError("transport must not run")])
    invalid = (
        "UNKNOWN:IBM",
        "INDEX:../SPX",
        "INDEX:SP 500",
        "INDEX:",
        "FX:EURUSD",
        "FX:../USD",
        "FX:EUR/US",
        "FX:EUR//USD",
        "FX:EUR/USD/extra",
        "CRYPTO:BTC",
        "CRYPTO:/USD",
        "CRYPTO:BTC/..",
        "COMMODITY:",
        "COMMODITY:COPPER",
        "COMMODITY:ALL_COMMODITIES",
        "COMMODITY:WTI:EXTRA",
        ":IBM",
    )
    source = _source(AlphaVantagePlan.PREMIUM, indexes_enabled=True)
    for ticker in invalid:
        with pytest.raises(ValueError, match="Alpha Vantage"):
            source.get_prices(ticker, "2025-01-01")


def test_alpha_array_payload_validation_covers_tables_rows_and_dates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Index, FX-history and commodity arrays reject malformed response shapes."""
    source = _source(AlphaVantagePlan.PREMIUM, indexes_enabled=True)
    array_failures: tuple[dict[str, object], ...] = ({}, {"data": []})
    for payload in array_failures:
        install_alpha(monkeypatch, {INDEX_FUNCTION: payload})
        with pytest.raises(ValueError, match="serie diaria"):
            source.get_prices("INDEX:SPX", "2025-01-02")

    install_alpha(monkeypatch, {INDEX_FUNCTION: {"data": [["not", "a", "row"]]}})
    with pytest.raises(TypeError, match="fila diaria"):
        source.get_prices("INDEX:SPX", "2025-01-02")
    install_alpha(monkeypatch, {INDEX_FUNCTION: {"data": [{"date": None, "close": "100"}]}})
    with pytest.raises(ValueError, match="fechas no válidas"):
        source.get_prices("INDEX:SPX", "2025-01-02")


def test_alpha_get_many_routes_each_public_family(monkeypatch: pytest.MonkeyPatch) -> None:
    """Batch requests keep caller ticker identity while dispatching each family separately."""
    install_alpha(
        monkeypatch,
        {
            INDEX_FUNCTION: _array_payload("close", [5_000.0]),
            FX_FUNCTION: _fx_payload(1),
        },
    )
    result = _source(AlphaVantagePlan.PREMIUM, indexes_enabled=True).get_many(
        ["INDEX:SPX", "FX:EUR/USD"],
        "2025-01-02",
    )

    assert tuple(result) == ("INDEX:SPX", "FX:EUR/USD")
    assert result["INDEX:SPX"].ticker == "INDEX:SPX"
    assert result["FX:EUR/USD"].ticker == "FX:EUR/USD"


def test_alpha_cache_namespace_changes_after_runtime_downgrade(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Premium cache rows remain isolated when a denial downgrades subsequent free requests."""
    install_alpha(
        monkeypatch,
        [
            alpha_daily_payload([100.0, 101.0], adjusted=True),
            _entitlement_error(),
            alpha_daily_payload([200.0, 201.0]),
        ],
    )
    source = _source(AlphaVantagePlan.PREMIUM, indexes_enabled=True, cache_dir=tmp_path)
    premium_cache = CachedPriceSource(source, cache_dir=tmp_path)
    premium = premium_cache.get_prices("IBM", "2025-01-02", "2025-01-04")
    premium_path = tmp_path / "alpha-vantage-premium-v2" / "IBM.csv"
    free_path = tmp_path / "alpha-vantage-free-v2" / "IBM.csv"
    assert premium.source == "Alpha Vantage (premium, adjusted)"
    assert premium_path.is_file()

    refresh_cache = CachedPriceSource(source, cache_dir=tmp_path, refresh=True)
    with pytest.raises(AlphaVantageError):
        refresh_cache.get_prices(
            "IBM",
            "2025-01-02",
            "2025-01-04",
        )
    assert source.plan is AlphaVantagePlan.FREE
    free = CachedPriceSource(source, cache_dir=tmp_path).get_prices(
        "IBM",
        "2025-01-02",
        "2025-01-04",
    )
    cached_free = CachedPriceSource(source, cache_dir=tmp_path).get_prices(
        "IBM",
        "2025-01-02",
        "2025-01-04",
    )
    assert free.source == "Alpha Vantage (free, raw)"
    assert free_path.is_file()
    assert cached_free.source.endswith("(cache)")
    assert list(cached_free.prices) == list(free.prices)


def test_alpha_package_exports_and_runtime_properties_are_stable(tmp_path: Path) -> None:
    """The public package names the plan/source and capabilities stay read-only."""
    assert alpha_vantage.__all__ == ["AlphaVantagePlan", "AlphaVantageSource"]
    source = _source(AlphaVantagePlan.PREMIUM, indexes_enabled=True, cache_dir=tmp_path)
    assert source.name == "Alpha Vantage"
    assert source.cache_namespace == "Alpha Vantage premium v2"
    assert source.plan is AlphaVantagePlan.PREMIUM
    assert source.indexes_enabled is True
    with pytest.raises(AttributeError):
        source.plan = AlphaVantagePlan.FREE  # type: ignore[misc]
