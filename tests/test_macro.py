"""Tests for the FRED macro-series provider."""

import datetime as dt
from typing import cast

import pandas as pd
import pytest

from quantfolio.macro import (
    ALFRED_CSV_URL,
    FredMacroSource,
    MacroSeries,
    _parse_vintage_column,
)
from tests.helpers import TRADING_DATES


def test_macro_series_defaults_to_unspecified_vintage() -> None:
    """MacroSeries without an explicit vintage records none."""
    values = pd.Series([1.0], index=TRADING_DATES[:1])
    series = MacroSeries(series_id="DGS10", values=values)
    assert series.vintage_date is None


def test_macro_series_stores_vintage_date() -> None:
    """MacroSeries keeps the vintage the values represent."""
    values = pd.Series([1.0], index=TRADING_DATES[:1])
    series = MacroSeries(series_id="DGS10", values=values, vintage_date=pd.Timestamp("2025-03-15"))
    assert series.vintage_date == pd.Timestamp("2025-03-15")


def test_parse_vintage_column_reads_eight_digit_suffix() -> None:
    """ALFRED value columns embed the vintage as a YYYYMMDD suffix."""
    assert _parse_vintage_column("CPIAUCSL_20250315") == pd.Timestamp("2025-03-15")


@pytest.mark.parametrize(
    "value_column",
    [
        "CPIAUCSL",
        "CPIAUCSL_2025031",
        "CPIAUCSL_abcdabcd",
        "CPIAUCSL_20251315",
    ],
)
def test_parse_vintage_column_rejects_missing_or_malformed_suffix(value_column: str) -> None:
    """Columns without a strict YYYYMMDD suffix yield no vintage."""
    assert _parse_vintage_column(value_column) is None


def test_fred_source_parses_csv(monkeypatch: pytest.MonkeyPatch) -> None:
    """FRED CSV responses are normalized, dropping missing observations."""

    def fake_read_csv(url: str, dtype: object) -> pd.DataFrame:
        assert url.startswith(ALFRED_CSV_URL)
        assert dtype is str
        assert "id=DGS10" in url
        assert "cosd=2025-01-02" in url
        assert "coed=2025-01-10" in url
        assert "vintage_date" not in url
        return pd.DataFrame(
            {
                "observation_date": ["2025-01-02", "2025-01-03", "2025-01-06"],
                "DGS10_20250315": [4.25, ".", 4.3],
            }
        )

    monkeypatch.setattr("quantfolio.macro.pd.read_csv", fake_read_csv)

    series = FredMacroSource().get_series("dgs10", "2025-01-02", "2025-01-10")

    assert series.series_id == "DGS10"
    assert series.source == "FRED"
    assert series.vintage_date == pd.Timestamp("2025-03-15")
    assert list(series.values) == [4.25, 4.3]


def test_fred_source_allows_optional_dates(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start and end dates are optional query parameters."""

    def fake_read_csv(url: str, dtype: object) -> pd.DataFrame:
        assert url.endswith("id=CPIAUCSL")
        assert dtype is str
        return pd.DataFrame({"observation_date": ["2025-01-01"], "CPIAUCSL_20261030": [315.0]})

    monkeypatch.setattr("quantfolio.macro.pd.read_csv", fake_read_csv)

    series = FredMacroSource().get_series("CPIAUCSL")

    assert len(series.values) == 1
    assert series.vintage_date == pd.Timestamp("2026-10-30")


@pytest.mark.parametrize("as_of", ["2025-03-15", dt.date(2025, 3, 15)])
def test_fred_source_pins_vintage_with_as_of(
    monkeypatch: pytest.MonkeyPatch, as_of: str | dt.date
) -> None:
    """as_of pins the ALFRED vintage and stamps the provenance."""

    def fake_read_csv(url: str, dtype: object) -> pd.DataFrame:
        assert dtype is str
        assert "id=DGS10" in url
        assert "vintage_date=2025-03-15" in url
        return pd.DataFrame({"observation_date": ["2025-03-13"], "DGS10_20250315": [4.27]})

    monkeypatch.setattr("quantfolio.macro.pd.read_csv", fake_read_csv)
    series = FredMacroSource().get_series("DGS10", as_of=as_of)
    assert series.vintage_date == pd.Timestamp("2025-03-15")


def test_fred_source_vintage_falls_back_to_none_on_unparsable_column(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A response column without a vintage suffix leaves the vintage unspecified."""

    def fake_read_csv(_url: str, dtype: object) -> pd.DataFrame:
        del dtype
        return pd.DataFrame({"observation_date": ["2025-01-02"], "DGS10": [4.25]})

    monkeypatch.setattr("quantfolio.macro.pd.read_csv", fake_read_csv)
    series = FredMacroSource().get_series("DGS10")
    assert series.vintage_date is None


def test_fred_source_vintage_preserves_release_gaps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Observations not published at the vintage stay absent: no reindexing, no fill."""

    def fake_read_csv(_url: str, dtype: object) -> pd.DataFrame:
        del dtype
        return pd.DataFrame(
            {
                "observation_date": ["2025-01-01", "2025-02-01"],
                "CPIAUCSL_20250315": [319.086, 319.775],
            }
        )

    monkeypatch.setattr("quantfolio.macro.pd.read_csv", fake_read_csv)
    series = FredMacroSource().get_series(
        "CPIAUCSL", start="2025-01-01", end="2025-03-31", as_of="2025-03-15"
    )
    assert len(series.values) == 2
    # PD011 is a false positive: this accesses the MacroSeries dataclass field of
    # that name, not the deprecated pandas Series.values.
    assert series.values.index.max() == pd.Timestamp("2025-02-01")  # noqa: PD011


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
