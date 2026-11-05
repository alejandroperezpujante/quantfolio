"""Tests for Alpha Vantage runtime plans and the capability cache."""

import hashlib
import json
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest

from quantfolio.sources.alpha_vantage.capabilities import (
    CAPABILITY_TTL,
    SCHEMA_VERSION,
    AlphaVantageCapabilities,
    AlphaVantageCapabilityStore,
    AlphaVantagePlan,
)

API_KEY = "test-key"


def store(root: Path) -> AlphaVantageCapabilityStore:
    """Return a capability store rooted at ``root``."""
    return AlphaVantageCapabilityStore(root)


def utc_now_iso() -> str:
    """Return the current timezone-aware UTC timestamp in ISO 8601 format."""
    return datetime.now(UTC).isoformat()


def cache_path(root: Path, api_key: str = API_KEY) -> Path:
    """Return the cache path expected for a key."""
    digest = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
    return root / "alpha-vantage" / "capabilities" / f"{digest}.json"


def write_payload(root: Path, payload: object, *, api_key: str = API_KEY) -> Path:
    """Write an arbitrary JSON payload at the cache path of a key."""
    path = cache_path(root, api_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def write_cache(
    root: Path,
    *,
    detected_at: str | None = None,
    schema_version: int = SCHEMA_VERSION,
    plan: object = AlphaVantagePlan.PREMIUM.value,
    indexes_enabled: object = True,
) -> Path:
    """Write one cache entry with the requested metadata."""
    payload = {
        "schema_version": schema_version,
        "detected_at": utc_now_iso() if detected_at is None else detected_at,
        "plan": plan,
        "indexes_enabled": indexes_enabled,
    }
    return write_payload(root, payload)


def raise_oserror(*_args: object, **_kwargs: object) -> None:
    """Raise an ``OSError`` to simulate an unavailable filesystem."""
    msg = "filesystem unavailable"
    raise OSError(msg)


def test_plan_values_are_the_documented_strings() -> None:
    """Plans serialize as the documented lowercase strings."""
    assert [plan.value for plan in AlphaVantagePlan] == ["free", "premium"]


def test_cache_constants_match_the_specification() -> None:
    """The schema version and TTL are the pinned values."""
    assert SCHEMA_VERSION == 1
    assert CAPABILITY_TTL.total_seconds() == 86400


def test_capabilities_are_frozen() -> None:
    """Detected capabilities cannot be mutated after construction."""
    capabilities = AlphaVantageCapabilities(AlphaVantagePlan.FREE, indexes_enabled=False)

    with pytest.raises(FrozenInstanceError):
        capabilities.plan = AlphaVantagePlan.PREMIUM  # type: ignore[misc]


@pytest.mark.parametrize("plan", list(AlphaVantagePlan))
@pytest.mark.parametrize("indexes_enabled", [False, True])
def test_round_trip_preserves_capabilities(
    tmp_path: Path,
    *,
    plan: AlphaVantagePlan,
    indexes_enabled: bool,
) -> None:
    """Every plan and index combination survives a save/load round trip."""
    capabilities = AlphaVantageCapabilities(plan, indexes_enabled)

    store(tmp_path).save(API_KEY, capabilities)

    assert store(tmp_path).load(API_KEY) == capabilities


def test_cache_file_is_the_full_sha256_of_the_key(tmp_path: Path) -> None:
    """Cache files are named after the complete SHA-256 fingerprint of the key."""
    store(tmp_path).save(
        API_KEY, AlphaVantageCapabilities(AlphaVantagePlan.FREE, indexes_enabled=False)
    )

    path = cache_path(tmp_path)

    assert path.is_file()
    assert path.parent == tmp_path / "alpha-vantage" / "capabilities"
    assert path.name == f"{hashlib.sha256(API_KEY.encode('utf-8')).hexdigest()}.json"
    assert len(path.stem) == 64


def test_cache_stores_only_capability_metadata(tmp_path: Path) -> None:
    """The cache holds the schema version, UTC timestamp, plan, and index flag."""
    store(tmp_path).save(
        API_KEY, AlphaVantageCapabilities(AlphaVantagePlan.PREMIUM, indexes_enabled=True)
    )

    payload = cast(
        "dict[str, object]",
        json.loads(cache_path(tmp_path).read_text(encoding="utf-8")),
    )

    assert set(payload) == {"schema_version", "detected_at", "plan", "indexes_enabled"}
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["plan"] == AlphaVantagePlan.PREMIUM.value
    assert payload["indexes_enabled"] is True
    detected_at = payload["detected_at"]
    assert isinstance(detected_at, str)
    assert datetime.fromisoformat(detected_at).tzinfo is not None


def test_cache_never_contains_the_raw_key(tmp_path: Path) -> None:
    """Neither cache paths nor cache contents expose the raw API key."""
    store(tmp_path).save(
        API_KEY, AlphaVantageCapabilities(AlphaVantagePlan.PREMIUM, indexes_enabled=True)
    )

    items = list(tmp_path.rglob("*"))

    assert items
    for item in items:
        assert API_KEY not in str(item.relative_to(tmp_path))
        if item.is_file():
            assert API_KEY not in item.read_text(encoding="utf-8")


def test_fresh_cache_loads(tmp_path: Path) -> None:
    """A fresh manually written entry is loaded without a provider call."""
    write_cache(tmp_path, detected_at=utc_now_iso(), plan="free", indexes_enabled=False)

    assert store(tmp_path).load(API_KEY) == AlphaVantageCapabilities(
        AlphaVantagePlan.FREE,
        indexes_enabled=False,
    )


def test_entry_just_below_the_ttl_is_fresh(tmp_path: Path) -> None:
    """An entry younger than 24 hours is still a hit."""
    detected_at = datetime.now(UTC) - CAPABILITY_TTL + timedelta(minutes=5)
    write_cache(tmp_path, detected_at=detected_at.isoformat())

    assert store(tmp_path).load(API_KEY) is not None


def test_entry_expires_at_the_ttl(tmp_path: Path) -> None:
    """An entry aged 24 hours or more is a miss."""
    detected_at = datetime.now(UTC) - CAPABILITY_TTL
    write_cache(tmp_path, detected_at=detected_at.isoformat())

    assert store(tmp_path).load(API_KEY) is None


def test_invalid_cache_metadata_is_a_miss(tmp_path: Path) -> None:
    """Malformed, naive, future, and wrong-version timestamps are misses."""
    for detected_at in ("not-a-date", "2026-11-04T10:00:00", "2999-01-01T00:00:00+00:00"):
        write_cache(tmp_path, detected_at=detected_at, schema_version=1)
        assert store(tmp_path).load("test-key") is None
    write_cache(tmp_path, detected_at=utc_now_iso(), schema_version=999)
    assert store(tmp_path).load("test-key") is None


def test_invalid_json_is_a_miss(tmp_path: Path) -> None:
    """A cache file that is not valid JSON is a miss."""
    path = cache_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("not json", encoding="utf-8")

    assert store(tmp_path).load(API_KEY) is None


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {},
        {"schema_version": 1, "detected_at": utc_now_iso(), "plan": "free"},
        {
            "schema_version": 1,
            "detected_at": utc_now_iso(),
            "plan": "gold",
            "indexes_enabled": False,
        },
        {"schema_version": 1, "detected_at": utc_now_iso(), "plan": 2, "indexes_enabled": False},
        {"schema_version": 1, "detected_at": 42, "plan": "free", "indexes_enabled": False},
        {
            "schema_version": 1,
            "detected_at": utc_now_iso(),
            "plan": "free",
            "indexes_enabled": "yes",
        },
        {
            "schema_version": "1",
            "detected_at": utc_now_iso(),
            "plan": "free",
            "indexes_enabled": False,
        },
    ],
)
def test_malformed_payload_is_a_miss(tmp_path: Path, payload: object) -> None:
    """Malformed payload shapes and values never count as cached capabilities."""
    write_payload(tmp_path, payload)

    assert store(tmp_path).load(API_KEY) is None


def test_cache_is_scoped_to_the_key(tmp_path: Path) -> None:
    """Capabilities cached for one key are invisible to another key."""
    store(tmp_path).save(
        "first-key",
        AlphaVantageCapabilities(AlphaVantagePlan.FREE, indexes_enabled=False),
    )

    assert store(tmp_path).load("second-key") is None
    assert store(tmp_path).load("first-key") is not None


def test_unreadable_cache_is_a_miss(tmp_path: Path) -> None:
    """A cache file that is not valid UTF-8 is a miss."""
    path = cache_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\xff\xfe")

    assert store(tmp_path).load(API_KEY) is None


def test_cache_path_that_is_a_directory_is_a_miss(tmp_path: Path) -> None:
    """An unreadable cache path is a miss instead of an exception."""
    cache_path(tmp_path).mkdir(parents=True)

    assert store(tmp_path).load(API_KEY) is None


def test_invalidate_removes_the_cached_entry(tmp_path: Path) -> None:
    """Invalidation deletes the file so the next load rediscovers capabilities."""
    store(tmp_path).save(
        API_KEY, AlphaVantageCapabilities(AlphaVantagePlan.PREMIUM, indexes_enabled=True)
    )

    store(tmp_path).invalidate(API_KEY)

    assert not cache_path(tmp_path).exists()
    assert store(tmp_path).load(API_KEY) is None


def test_invalidation_of_a_missing_entry_is_a_no_op(tmp_path: Path) -> None:
    """Invalidating an absent cache file does not raise."""
    store(tmp_path).invalidate(API_KEY)

    assert not cache_path(tmp_path).exists()


def test_cache_write_failure_warns_without_raising(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed atomic replacement warns in Spanish and leaves no partial cache."""
    monkeypatch.setattr(Path, "replace", raise_oserror)

    with pytest.warns(RuntimeWarning, match="caché"):
        store(tmp_path).save(
            "test-key", AlphaVantageCapabilities(AlphaVantagePlan.FREE, indexes_enabled=False)
        )

    assert not cache_path(tmp_path).exists()
    assert list(cache_path(tmp_path).parent.iterdir()) == []


def test_cache_invalidation_failure_warns_without_raising(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An invalidation failure warns in Spanish instead of raising."""
    write_cache(tmp_path)
    monkeypatch.setattr(Path, "unlink", raise_oserror)

    with pytest.warns(RuntimeWarning, match="caché"):
        store(tmp_path).invalidate(API_KEY)

    assert cache_path(tmp_path).exists()
