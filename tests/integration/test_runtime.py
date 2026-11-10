"""Runtime composition of the public market-data source registry."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from quantfolio.runtime import create_price_source_registry
from quantfolio.sources import (
    AlphaVantagePlan,
    AlphaVantageSource,
    KrakenSource,
    YahooFinanceSource,
)
from quantfolio.sources.alpha_vantage.client import AlphaVantageError, AlphaVantageErrorCategory


def _alpha_source() -> AlphaVantageSource:
    return AlphaVantageSource("test-key", plan=AlphaVantagePlan.FREE, indexes_enabled=False)


@pytest.mark.parametrize("value", [None, "   "])
def test_registry_without_alpha_key_warns_and_keeps_default_sources(
    monkeypatch: pytest.MonkeyPatch,
    value: str | None,
) -> None:
    """Missing or blank credentials produce only Yahoo and Kraken, without discovery."""
    discovery_attempted = False

    def discover(*_args: object, **_kwargs: object) -> AlphaVantageSource:
        nonlocal discovery_attempted
        discovery_attempted = True
        return _alpha_source()

    monkeypatch.setattr("quantfolio.runtime.create_alpha_vantage_source", discover)
    environ = {} if value is None else {"ALPHA_VANTAGE_API_KEY": value}

    with pytest.warns(RuntimeWarning, match="ALPHA_VANTAGE_API_KEY"):
        registry = create_price_source_registry(environ=environ)

    assert set(registry) == {"yahoo", "kraken"}
    assert isinstance(registry["yahoo"], YahooFinanceSource)
    assert isinstance(registry["kraken"], KrakenSource)
    assert not discovery_attempted


def test_registry_registers_valid_alpha_source_and_forwards_cache_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A successful discovery is keyed by the documented provider identifier."""
    source = _alpha_source()
    received: list[tuple[str, Path]] = []

    def discover(api_key: str, *, cache_dir: str | Path) -> AlphaVantageSource:
        received.append((api_key, Path(cache_dir)))
        return source

    monkeypatch.setattr("quantfolio.runtime.create_alpha_vantage_source", discover)
    registry = create_price_source_registry(
        cache_dir=tmp_path,
        environ={"ALPHA_VANTAGE_API_KEY": "configured-key"},
    )

    assert registry["alpha-vantage"] is source
    assert received == [("configured-key", tmp_path)]


def test_registry_survives_alpha_initialization_failure_and_is_immutable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Optional failure warns but never removes or mutates the base provider selection."""
    error = AlphaVantageError("Clave no válida.", AlphaVantageErrorCategory.GENERIC)

    def fail(*_args: object, **_kwargs: object) -> AlphaVantageSource:
        raise error

    monkeypatch.setattr("quantfolio.runtime.create_alpha_vantage_source", fail)
    with pytest.warns(RuntimeWarning, match="Alpha Vantage"):
        registry = create_price_source_registry(environ={"ALPHA_VANTAGE_API_KEY": "bad"})

    assert "alpha-vantage" not in registry
    with pytest.raises(TypeError):
        registry["yahoo"] = _alpha_source()  # type: ignore[index]


def test_registry_reads_process_environment_at_call_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The default environment is not captured when the module is imported."""
    source = _alpha_source()
    monkeypatch.setattr("quantfolio.runtime.create_alpha_vantage_source", lambda *_a, **_k: source)
    monkeypatch.setattr(os, "environ", {"ALPHA_VANTAGE_API_KEY": "live-key"})

    assert create_price_source_registry()["alpha-vantage"] is source
