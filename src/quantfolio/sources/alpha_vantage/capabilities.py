"""Runtime plan metadata and the persistent capability cache for Alpha Vantage."""

from __future__ import annotations

import hashlib
import json
import warnings
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, cast
from uuid import uuid4

from quantfolio.sources.alpha_vantage.client import (
    AlphaVantageClient,
    AlphaVantageError,
    AlphaVantageErrorCategory,
)

if TYPE_CHECKING:
    from quantfolio.sources.alpha_vantage.provider import AlphaVantageSource

#: Version of the on-disk capability schema.
SCHEMA_VERSION = 1

#: Maximum accepted age of a cached capability entry.
CAPABILITY_TTL = timedelta(hours=24)

#: Cache subdirectory, below the configured root, that holds capability files.
_CAPABILITY_DIRECTORY = Path("alpha-vantage") / "capabilities"


class AlphaVantagePlan(StrEnum):
    """Subscription plan detected for an Alpha Vantage API key."""

    FREE = "free"
    PREMIUM = "premium"


@dataclass(frozen=True)
class AlphaVantageCapabilities:
    """Runtime entitlements detected for one Alpha Vantage API key.

    Attributes:
        plan: Subscription plan detected during capability discovery.
        indexes_enabled: Whether the key may query the index endpoints.

    """

    plan: AlphaVantagePlan
    indexes_enabled: bool


class AlphaVantageCapabilityStore:
    """Persist plan and index entitlements keyed by an API-key fingerprint.

    Only the SHA-256 fingerprint of the key is stored, so the cache never contains the
    credential. Entries are complete capability snapshots with a UTC detection timestamp.

    Args:
        cache_dir: Root cache directory; capability files live below its
            ``alpha-vantage/capabilities`` subdirectory.

    """

    def __init__(self, cache_dir: str | Path = "data") -> None:
        """Store the root directory of the capability cache."""
        self._cache_dir = Path(cache_dir)

    def load(self, api_key: str) -> AlphaVantageCapabilities | None:
        """Return the fresh cached capabilities for a key, or ``None`` on a miss.

        Missing, unreadable, malformed, expired, wrong-version, and future or naive
        timestamps are all treated as a miss so discovery runs again.

        Args:
            api_key: Credential whose SHA-256 fingerprint selects the cache file.

        Returns:
            The cached capabilities when the entry is valid and younger than
            :data:`CAPABILITY_TTL`, otherwise ``None``.

        """
        try:
            text = self._path(api_key).read_text(encoding="utf-8")
        except OSError, UnicodeDecodeError:
            return None
        try:
            payload: object = json.loads(text)
        except json.JSONDecodeError:
            return None
        return _parse_payload(payload)

    def save(self, api_key: str, capabilities: AlphaVantageCapabilities) -> None:
        """Atomically write the capabilities detected for a key.

        The entry is written to a temporary sibling file and moved into place, so a
        concurrent reader never observes a partial cache file. Filesystem failures emit
        a Spanish :class:`RuntimeWarning` and never disable the provider.

        Args:
            api_key: Credential whose SHA-256 fingerprint names the cache file.
            capabilities: Plan and index entitlement detected for the key.

        """
        path = self._path(api_key)
        payload = {
            "schema_version": SCHEMA_VERSION,
            "detected_at": datetime.now(UTC).isoformat(),
            "plan": capabilities.plan.value,
            "indexes_enabled": capabilities.indexes_enabled,
        }
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            temporary.replace(path)
        except OSError as exc:
            warnings.warn(
                f"No se pudo guardar la caché de capacidades de Alpha Vantage "
                f"({type(exc).__name__}).",
                RuntimeWarning,
                stacklevel=2,
            )
        finally:
            # A successful replacement leaves no temporary file behind, so the cleanup
            # only removes the leftovers of a failed write.
            with suppress(OSError):
                temporary.unlink(missing_ok=True)

    def invalidate(self, api_key: str) -> None:
        """Delete the cached capabilities for a key, if any.

        Filesystem failures emit a Spanish :class:`RuntimeWarning` instead of raising,
        because persisting capabilities is never a hard provider dependency.

        Args:
            api_key: Credential whose cache file is removed.

        """
        try:
            self._path(api_key).unlink(missing_ok=True)
        except OSError as exc:
            warnings.warn(
                f"No se pudo invalidar la caché de capacidades de Alpha Vantage "
                f"({type(exc).__name__}).",
                RuntimeWarning,
                stacklevel=2,
            )

    def _path(self, api_key: str) -> Path:
        """Return the cache path of a key without ever storing the key itself."""
        digest = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
        return self._cache_dir / _CAPABILITY_DIRECTORY / f"{digest}.json"


def _parse_payload(payload: object) -> AlphaVantageCapabilities | None:
    """Return the capabilities encoded in a cache payload, or ``None`` when invalid."""
    if not isinstance(payload, dict):
        return None
    body = cast("dict[str, object]", payload)
    plan = _parse_plan(body.get("plan"))
    indexes_enabled = body.get("indexes_enabled")
    if (
        body.get("schema_version") != SCHEMA_VERSION
        or plan is None
        or not isinstance(indexes_enabled, bool)
        or not _is_fresh(body.get("detected_at"))
    ):
        return None
    return AlphaVantageCapabilities(plan=plan, indexes_enabled=indexes_enabled)


def _parse_plan(value: object) -> AlphaVantagePlan | None:
    """Return a supported plan, or ``None`` when the value is unknown."""
    if not isinstance(value, str):
        return None
    try:
        return AlphaVantagePlan(value)
    except ValueError:
        return None


def _is_fresh(value: object) -> bool:
    """Return whether a timestamp is timezone-aware and younger than the TTL."""
    if not isinstance(value, str):
        return False
    try:
        detected_at = datetime.fromisoformat(value)
    except ValueError:
        return False
    return (
        detected_at.tzinfo is not None
        and timedelta(0) <= datetime.now(UTC) - detected_at < CAPABILITY_TTL
    )


def create_alpha_vantage_source(
    api_key: str,
    *,
    cache_dir: str | Path = "data",
) -> AlphaVantageSource:
    """Validate a key and discover its Alpha Vantage runtime capabilities.

    A compact raw IBM request always validates the key, even when a fresh capability
    snapshot is available. A cache hit then avoids only the entitlement probes.

    Args:
        api_key: Alpha Vantage credential used for the validation probes.
        cache_dir: Root directory of the optional capability cache.

    Returns:
        A configured source whose plan and index entitlement were validated or loaded.

    Raises:
        AlphaVantageError: If basic validation or plan discovery cannot complete.

    """
    store = AlphaVantageCapabilityStore(cache_dir)
    client = AlphaVantageClient(api_key)
    try:
        basic = client.get(function="TIME_SERIES_DAILY", symbol="IBM", outputsize="compact")
        _require_table_field(basic, "Time Series (Daily)", "4. close", "validación básica")
    except AlphaVantageError:
        store.invalidate(api_key)
        raise

    capabilities = store.load(api_key)
    if capabilities is None:
        capabilities = _discover_capabilities(client, store, api_key)
    return _source(api_key, capabilities, cache_dir)


def _discover_capabilities(
    client: AlphaVantageClient,
    store: AlphaVantageCapabilityStore,
    api_key: str,
) -> AlphaVantageCapabilities:
    """Discover and persist the plan and index entitlement of a validated key."""
    try:
        adjusted = client.get(
            function="TIME_SERIES_DAILY_ADJUSTED",
            symbol="IBM",
            outputsize="compact",
        )
        _require_table_field(adjusted, "Time Series (Daily)", "5. adjusted close", "plan")
    except AlphaVantageError as error:
        if error.category is not AlphaVantageErrorCategory.ENTITLEMENT:
            raise
        capabilities = AlphaVantageCapabilities(AlphaVantagePlan.FREE, indexes_enabled=False)
        store.save(api_key, capabilities)
        return capabilities

    premium = AlphaVantageCapabilities(AlphaVantagePlan.PREMIUM, indexes_enabled=True)
    try:
        index = client.get(function="INDEX_DATA", symbol="SPX", interval="daily")
        _require_array_field(index, "data", "close", "índices")
    except AlphaVantageError as error:
        capabilities = AlphaVantageCapabilities(AlphaVantagePlan.PREMIUM, indexes_enabled=False)
        if error.category is AlphaVantageErrorCategory.ENTITLEMENT:
            store.save(api_key, capabilities)
        else:
            warnings.warn(
                "No se pudo validar el acceso a índices de Alpha Vantage; "
                "los índices quedan deshabilitados.",
                RuntimeWarning,
                stacklevel=2,
            )
        return capabilities

    store.save(api_key, premium)
    return premium


def _source(
    api_key: str,
    capabilities: AlphaVantageCapabilities,
    cache_dir: str | Path,
) -> AlphaVantageSource:
    """Create a source lazily to keep the provider/capability import graph acyclic."""
    from quantfolio.sources.alpha_vantage.provider import AlphaVantageSource

    return AlphaVantageSource(
        api_key,
        plan=capabilities.plan,
        indexes_enabled=capabilities.indexes_enabled,
        cache_dir=cache_dir,
    )


def _require_table_field(
    payload: dict[str, object],
    table_name: str,
    field: str,
    probe: str,
) -> None:
    """Require one non-empty date-keyed response table with a price field."""
    table = payload.get(table_name)
    if not isinstance(table, dict) or not table:
        _raise_invalid_probe(probe)
    rows = cast("dict[str, object]", table)
    if not any(isinstance(row, dict) and field in row for row in rows.values()):
        _raise_invalid_probe(probe)


def _require_array_field(
    payload: dict[str, object],
    table_name: str,
    field: str,
    probe: str,
) -> None:
    """Require one non-empty object array response with a price field."""
    table = payload.get(table_name)
    if not isinstance(table, list) or not table:
        _raise_invalid_probe(probe)
    rows = cast("list[object]", table)
    if not any(isinstance(row, dict) and field in row for row in rows):
        _raise_invalid_probe(probe)


def _raise_invalid_probe(probe: str) -> None:
    """Raise a generic provider error for an unexpected validation response."""
    msg = f"Alpha Vantage devolvió una respuesta no válida durante la {probe}."
    raise AlphaVantageError(msg, AlphaVantageErrorCategory.GENERIC)
