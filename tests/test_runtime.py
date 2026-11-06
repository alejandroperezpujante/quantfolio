"""Tests for runtime composition of the market-data source registry."""

import os
from pathlib import Path

import pytest

from quantfolio.runtime import create_price_source_registry
from quantfolio.sources import KrakenSource, YahooFinanceSource
from quantfolio.sources.alpha_vantage.capabilities import AlphaVantagePlan
from quantfolio.sources.alpha_vantage.client import (
    AlphaVantageError,
    AlphaVantageErrorCategory,
)
from quantfolio.sources.alpha_vantage.provider import AlphaVantageSource


def alpha_source() -> AlphaVantageSource:
    """Return a configured source without performing any HTTP request."""
    return AlphaVantageSource("test-key", plan=AlphaVantagePlan.FREE, indexes_enabled=False)


@pytest.mark.parametrize("value", [None, "   "])
def test_missing_or_blank_key_warns_without_discovery(
    monkeypatch: pytest.MonkeyPatch,
    value: str | None,
) -> None:
    """An absent optional credential preserves the default providers."""
    discovered = False

    def fail_discovery(*_args: object, **_kwargs: object) -> AlphaVantageSource:
        nonlocal discovered
        discovered = True
        return alpha_source()

    monkeypatch.setattr("quantfolio.runtime.create_alpha_vantage_source", fail_discovery)
    environ = {} if value is None else {"ALPHA_VANTAGE_API_KEY": value}

    with pytest.warns(RuntimeWarning, match="ALPHA_VANTAGE_API_KEY"):
        registry = create_price_source_registry(environ=environ)

    assert discovered is False
    assert set(registry) == {"kraken", "yahoo"}


def test_valid_key_registers_alpha_vantage(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A discovered optional source is registered under its explicit identifier."""
    source = alpha_source()
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


def test_registry_preserves_existing_sources_when_alpha_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Optional discovery failure never removes Yahoo or Kraken."""
    error = AlphaVantageError("Clave no válida.", AlphaVantageErrorCategory.GENERIC)

    def fail_discovery(*_args: object, **_kwargs: object) -> AlphaVantageSource:
        raise error

    monkeypatch.setattr("quantfolio.runtime.create_alpha_vantage_source", fail_discovery)

    with pytest.warns(RuntimeWarning, match="Alpha Vantage"):
        registry = create_price_source_registry(environ={"ALPHA_VANTAGE_API_KEY": "bad"})

    assert isinstance(registry["yahoo"], YahooFinanceSource)
    assert isinstance(registry["kraken"], KrakenSource)
    assert "alpha-vantage" not in registry


def test_default_environment_is_read_at_call_time(monkeypatch: pytest.MonkeyPatch) -> None:
    """Changes to the process environment affect subsequent registry construction."""
    source = alpha_source()
    monkeypatch.setattr(
        "quantfolio.runtime.create_alpha_vantage_source",
        lambda *_args, **_kwargs: source,
    )
    monkeypatch.setattr(os, "environ", {"ALPHA_VANTAGE_API_KEY": "live-key"})

    registry = create_price_source_registry()

    assert registry["alpha-vantage"] is source


def test_registry_is_immutable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Consumers cannot replace the runtime source selection."""
    monkeypatch.setattr(
        "quantfolio.runtime.create_alpha_vantage_source",
        lambda *_args, **_kwargs: alpha_source(),
    )

    registry = create_price_source_registry(environ={"ALPHA_VANTAGE_API_KEY": "key"})

    with pytest.raises(TypeError):
        registry["yahoo"] = alpha_source()  # type: ignore[index]
