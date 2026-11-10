"""FRED/ALFRED CSV parsing, vintages and public macro-series behavior."""

from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from quantfolio.macro import ALFRED_CSV_URL, FredMacroSource


def test_fred_normalizes_csv_values_and_preserves_optional_vintage_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CSV levels become numeric observations and a dated value column carries the vintage."""
    urls: list[str] = []

    def read_csv(url: str, dtype: object) -> pd.DataFrame:
        assert dtype is str
        urls.append(url)
        return pd.DataFrame(
            {
                "observation_date": ["2025-01-02", "2025-01-03", "2025-01-06"],
                "DGS10_20250315": [4.25, ".", 4.3],
            }
        )

    monkeypatch.setattr("quantfolio.macro.pd.read_csv", read_csv)
    series = FredMacroSource().get_series(" dgs10 ", "2025-01-02", "2025-01-10")

    assert series.series_id == "DGS10"
    assert list(series.values) == [4.25, 4.3]
    assert list(series.index_levels.index) == [
        pd.Timestamp("2025-01-02"),
        pd.Timestamp("2025-01-06"),
    ]
    assert series.vintage_date == pd.Timestamp("2025-03-15")
    assert urls[0].startswith(ALFRED_CSV_URL)
    assert "cosd=2025-01-02" in urls[0]
    assert "coed=2025-01-10" in urls[0]


def test_fred_optional_dates_and_as_of_are_encoded_without_losing_release_gaps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The keyless request omits absent bounds and pins the requested ALFRED vintage."""
    requested_urls: list[str] = []

    def read_csv(url: str, dtype: object) -> pd.DataFrame:
        assert dtype is str
        requested_urls.append(url)
        return pd.DataFrame(
            {
                "observation_date": ["2025-02-01", "2025-04-01"],
                "CPIAUCSL_20250315": [319.086, 320.0],
            }
        )

    monkeypatch.setattr("quantfolio.macro.pd.read_csv", read_csv)
    series = FredMacroSource().get_series("CPIAUCSL", as_of=dt.date(2025, 3, 15))

    assert requested_urls == [f"{ALFRED_CSV_URL}?id=CPIAUCSL&vintage_date=2025-03-15"]
    assert list(series.index_levels.index) == [
        pd.Timestamp("2025-02-01"),
        pd.Timestamp("2025-04-01"),
    ]
    assert series.vintage_date == pd.Timestamp("2025-03-15")


def test_fred_uses_the_requested_vintage_when_the_response_omits_the_suffix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An undated response still records the explicitly requested point-in-time view."""

    def read_csv(_url: str, dtype: object) -> pd.DataFrame:
        assert dtype is str
        return pd.DataFrame({"observation_date": ["2025-01-02"], "DGS10": [4.25]})

    monkeypatch.setattr("quantfolio.macro.pd.read_csv", read_csv)
    pinned = FredMacroSource().get_series("DGS10", as_of="2025-03-15")
    latest = FredMacroSource().get_series("DGS10")

    assert pinned.vintage_date == pd.Timestamp("2025-03-15")
    assert latest.vintage_date is None


def test_fred_rejects_a_response_vintage_that_differs_from_the_requested_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ALFRED clamping to its latest vintage is surfaced rather than mislabelled."""

    def read_csv(_url: str, dtype: object) -> pd.DataFrame:
        assert dtype is str
        return pd.DataFrame({"observation_date": ["2026-10-28"], "DGS10_20261030": [5.05]})

    monkeypatch.setattr("quantfolio.macro.pd.read_csv", read_csv)
    source = FredMacroSource()
    with pytest.raises(ValueError, match=r"2026-10-30.*2025-03-15.*DGS10"):
        source.get_series("DGS10", as_of="2025-03-15")


@pytest.mark.parametrize("end", ["2025-01-10", dt.date(2025, 1, 10), pd.Timestamp("2025-01-10")])
def test_fred_end_is_exclusive_for_every_supported_date_type(
    monkeypatch: pytest.MonkeyPatch,
    end: str | dt.date | pd.Timestamp,
) -> None:
    """The public end bound excludes an observation exactly on the boundary."""

    def read_csv(url: str, dtype: object) -> pd.DataFrame:
        assert dtype is str
        assert "coed=2025-01-10" in url
        return pd.DataFrame(
            {
                "observation_date": ["2025-01-09", "2025-01-10"],
                "DGS10_20250315": [4.27, 4.3],
            }
        )

    monkeypatch.setattr("quantfolio.macro.pd.read_csv", read_csv)
    series = FredMacroSource().get_series("DGS10", "2025-01-02", end)

    assert list(series.values) == [4.27]


@pytest.mark.parametrize(
    ("frame", "message"),
    [
        (pd.DataFrame(), "No se han encontrado datos"),
        (pd.DataFrame({"observation_date": ["2025-01-02"]}), "No se han encontrado datos"),
        (
            pd.DataFrame({"observation_date": ["2025-01-02"], "DGS10_20250315": ["."]}),
            "valores válidos",
        ),
    ],
)
def test_fred_rejects_empty_malformed_or_unusable_csv(
    monkeypatch: pytest.MonkeyPatch,
    frame: pd.DataFrame,
    message: str,
) -> None:
    """Missing columns and windows without numeric observations raise a Spanish error."""

    def read_csv(_url: str, dtype: object) -> pd.DataFrame:
        assert dtype is str
        return frame

    monkeypatch.setattr("quantfolio.macro.pd.read_csv", read_csv)
    source = FredMacroSource()
    with pytest.raises(ValueError, match=message):
        source.get_series("DGS10")


def test_fred_wraps_transport_failures_and_rejects_blank_identifiers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Network errors remain chained download errors and blank ids never touch transport."""

    def read_csv(_url: str, dtype: object) -> pd.DataFrame:
        del dtype
        msg = "offline"
        raise OSError(msg)

    monkeypatch.setattr("quantfolio.macro.pd.read_csv", read_csv)
    source = FredMacroSource()
    with pytest.raises(ValueError, match="No se pudo descargar") as captured:
        source.get_series("DGS10")
    assert isinstance(captured.value.__cause__, OSError)
    with pytest.raises(ValueError, match="identificador"):
        source.get_series("   ")


def test_fred_keeps_negative_levels_such_as_negative_yields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Macro levels remain signed, including negative interest rates."""
    frame = pd.DataFrame(
        {
            "observation_date": ["2025-01-02", "2025-01-03"],
            "DGS10_20250315": ["-0.5", "0.25"],
        }
    )
    monkeypatch.setattr("quantfolio.macro.pd.read_csv", lambda *_args, **_kwargs: frame)

    series = FredMacroSource().get_series("DGS10")

    assert list(series.values) == [-0.5, 0.25]


def test_fred_ignores_an_eight_digit_suffix_that_is_not_a_calendar_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A malformed vintage-looking column remains an undated latest observation."""
    frame = pd.DataFrame({"observation_date": ["2025-01-02"], "DGS10_20251301": ["4.2"]})
    monkeypatch.setattr("quantfolio.macro.pd.read_csv", lambda *_args, **_kwargs: frame)

    series = FredMacroSource().get_series("DGS10")

    assert series.vintage_date is None
    assert list(series.values) == [4.2]


def test_fred_reports_a_window_that_contains_only_the_exclusive_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-empty response entirely beyond ``end`` is still an empty public window."""
    frame = pd.DataFrame({"observation_date": ["2025-01-10"], "DGS10_20250315": ["4.2"]})
    monkeypatch.setattr("quantfolio.macro.pd.read_csv", lambda *_args, **_kwargs: frame)

    source = FredMacroSource()
    with pytest.raises(ValueError, match="No se han encontrado datos"):
        source.get_series("DGS10", end="2025-01-10")
