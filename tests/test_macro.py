"""Tests for the FRED macro-series provider."""

from typing import cast

import pandas as pd
import pytest

from quantfolio.macro import FRED_CSV_URL, FredMacroSource, MacroSeries
from tests.helpers import TRADING_DATES


def test_fred_source_parses_csv(monkeypatch: pytest.MonkeyPatch) -> None:
    """FRED CSV responses are normalized, dropping missing observations."""

    def fake_read_csv(url: str, dtype: object) -> pd.DataFrame:
        assert url.startswith(FRED_CSV_URL)
        assert dtype is str
        assert "id=DGS10" in url
        assert "cosd=2025-01-02" in url
        assert "coed=2025-01-10" in url
        return pd.DataFrame(
            {
                "observation_date": ["2025-01-02", "2025-01-03", "2025-01-06"],
                "DGS10": [4.25, ".", 4.3],
            }
        )

    monkeypatch.setattr("quantfolio.macro.pd.read_csv", fake_read_csv)

    series = FredMacroSource().get_series("dgs10", "2025-01-02", "2025-01-10")

    assert series.series_id == "DGS10"
    assert series.source == "FRED"
    assert list(series.values) == [4.25, 4.3]


def test_fred_source_allows_optional_dates(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start and end dates are optional query parameters."""

    def fake_read_csv(url: str, dtype: object) -> pd.DataFrame:
        assert url.endswith("id=CPIAUCSL")
        assert dtype is str
        return pd.DataFrame({"observation_date": ["2025-01-01"], "CPIAUCSL": [315.0]})

    monkeypatch.setattr("quantfolio.macro.pd.read_csv", fake_read_csv)

    series = FredMacroSource().get_series("CPIAUCSL")

    assert len(series.values) == 1


def test_fred_source_rejects_empty_payloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty CSV responses raise a clear error."""

    def fake_read_csv(_url: str, dtype: object) -> pd.DataFrame:
        del dtype
        return pd.DataFrame()

    monkeypatch.setattr("quantfolio.macro.pd.read_csv", fake_read_csv)

    source = FredMacroSource()

    with pytest.raises(ValueError, match="No se han encontrado"):
        source.get_series("DGS10")


def test_fred_source_rejects_missing_value_column(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Responses without a value column are rejected."""

    def fake_read_csv(_url: str, dtype: object) -> pd.DataFrame:
        del dtype
        return pd.DataFrame({"observation_date": ["2025-01-02"]})

    monkeypatch.setattr("quantfolio.macro.pd.read_csv", fake_read_csv)

    source = FredMacroSource()

    with pytest.raises(ValueError, match="No se han encontrado"):
        source.get_series("DGS10")


def test_fred_source_wraps_download_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Network errors are reported as download errors."""

    def fake_read_csv(_url: str, dtype: object) -> pd.DataFrame:
        del dtype
        msg = "offline"
        raise OSError(msg)

    monkeypatch.setattr("quantfolio.macro.pd.read_csv", fake_read_csv)

    source = FredMacroSource()

    with pytest.raises(ValueError, match="No se pudo descargar"):
        source.get_series("DGS10")


def test_fred_source_rejects_empty_identifiers() -> None:
    """The series identifier cannot be blank."""
    source = FredMacroSource()

    with pytest.raises(ValueError, match="identificador"):
        source.get_series("   ")


def test_macro_series_rejects_empty_identifiers() -> None:
    """MacroSeries validates its identifier."""
    values = pd.Series([1.0], index=TRADING_DATES[:1])

    with pytest.raises(ValueError, match="identificador"):
        MacroSeries(series_id="  ", values=values)


def test_macro_series_rejects_non_series_values() -> None:
    """MacroSeries requires a pandas Series."""
    values = cast("pd.Series[float]", [1.0])

    with pytest.raises(TypeError, match=r"pandas\.Series"):
        MacroSeries(series_id="DGS10", values=values)


def test_macro_series_rejects_empty_values() -> None:
    """MacroSeries requires at least one observation."""
    values = cast("pd.Series[float]", pd.Series([], dtype=float))

    with pytest.raises(ValueError, match="vacía"):
        MacroSeries(series_id="DGS10", values=values)


def test_macro_series_rejects_series_without_valid_values() -> None:
    """MacroSeries requires at least one numeric observation."""
    values = cast(
        "pd.Series[float]",
        pd.Series([".", "n/a"], index=TRADING_DATES[:2]),
    )

    with pytest.raises(ValueError, match="valores válidos"):
        MacroSeries(series_id="DGS10", values=values)


def test_macro_series_keeps_negative_values() -> None:
    """Negative rates are valid macroeconomic observations."""
    values = pd.Series([-0.5, 0.25], index=TRADING_DATES[:2])

    series = MacroSeries(series_id="DGS10", values=values)

    assert list(series.values) == [-0.5, 0.25]
