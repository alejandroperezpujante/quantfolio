"""Macroeconomic time series from FRED.

The series are downloaded from ALFRED, FRED's archival endpoint: it serves
FRED's vintages and, when no vintage is requested, the same latest values
FRED serves today.
"""

import re
from dataclasses import dataclass
from typing import cast
from urllib.parse import urlencode

import pandas as pd

from quantfolio.models import clean_numeric_series
from quantfolio.sources.base import DateLike, naive_timestamp

#: Base URL of the keyless ALFRED CSV export. ALFRED is FRED's archival
#: endpoint: it serves FRED's vintages and, when no vintage is requested,
#: the same latest values FRED serves today.
ALFRED_CSV_URL = "https://alfred.stlouisfed.org/graph/alfredgraph.csv"

#: Minimum number of columns expected in the ALFRED CSV export (date and value).
FRED_CSV_COLUMNS = 2


def _parse_vintage_column(value_column: str) -> pd.Timestamp | None:
    """Extract the vintage date embedded in an ALFRED value column name.

    Args:
        value_column: Column name of the CSV export, for example
            ``"CPIAUCSL_20250315"``.

    Returns:
        The vintage date when the text after the last underscore is strictly
        eight digits parsable as ``%Y%m%d``, otherwise ``None``.

    """
    suffix = value_column.rsplit("_", maxsplit=1)[-1]
    if re.fullmatch(r"[0-9]{8}", suffix) is None:
        return None
    try:
        return pd.to_datetime(suffix, format="%Y%m%d")
    except ValueError:
        return None


def _resolve_vintage(
    identifier: str,
    value_column: str,
    requested: pd.Timestamp | None,
) -> pd.Timestamp | None:
    """Resolve the vintage to stamp, validating it against the requested date.

    Args:
        identifier: FRED identifier, used in the error message.
        value_column: Column name of the CSV export, for example
            ``"CPIAUCSL_20250315"``.
        requested: Vintage the caller asked for, or ``None`` when no ``as_of``
            was given.

    Returns:
        The vintage the response actually carries: the parsed suffix when the
        column names one, the requested date otherwise. ``None`` means
        unspecified.

    Raises:
        ValueError: If the endpoint served a vintage other than the requested
            one. ALFRED clamps out-of-range requests to its latest vintage, so
            a mismatch means the stamped vintage would not be the requested
            one.

    """
    parsed = _parse_vintage_column(value_column)
    if requested is None:
        return parsed
    if parsed is not None and parsed != requested:
        msg = (
            f"ALFRED devolvió el vintage {parsed:%Y-%m-%d} en lugar del "
            f"solicitado {requested:%Y-%m-%d} para la serie {identifier}."
        )
        raise ValueError(msg)
    return parsed if parsed is not None else requested


@dataclass
class MacroSeries:
    """A macroeconomic indicator downloaded from FRED.

    Attributes:
        series_id: FRED identifier, for example ``"DGS10"``.
        values: Indicator values indexed by observation date.
        source: Human-readable name of the provider.
        vintage_date: Vintage the values represent — the point-in-time view.
            ``None`` means unspecified.

    """

    series_id: str
    values: pd.Series[float]
    source: str = "FRED"
    vintage_date: pd.Timestamp | None = None

    def __post_init__(self) -> None:
        """Validate and clean the downloaded values.

        Raises:
            TypeError: If ``values`` is not a ``pandas.Series``.
            ValueError: If the identifier is empty or the series has no valid values.

        """
        if not isinstance(self.series_id, str) or not self.series_id.strip():
            msg = "El identificador de la serie no puede estar vacío."
            raise ValueError(msg)
        if not isinstance(cast("object", self.values), pd.Series):
            msg = "values debe ser una pandas.Series."
            raise TypeError(msg)
        if self.values.empty:
            msg = "La serie macroeconómica no puede estar vacía."
            raise ValueError(msg)
        cleaned = clean_numeric_series(self.values)
        if cleaned.empty:
            msg = "La serie macroeconómica no contiene valores válidos."
            raise ValueError(msg)
        self.values = cleaned


class FredMacroSource:
    """Client for the keyless ALFRED CSV export endpoint (FRED's archive)."""

    @property
    def name(self) -> str:
        """Return the provider name."""
        return "FRED"

    def get_series(
        self,
        series_id: str,
        start: DateLike | None = None,
        end: DateLike | None = None,
        as_of: DateLike | None = None,
    ) -> MacroSeries:
        """Download a macroeconomic series.

        Args:
            series_id: FRED identifier, for example ``"DGS10"`` or ``"CPIAUCSL"``.
            start: First observation date (inclusive).
            end: Last observation date (exclusive).
            as_of: Vintage date; the values are those published on that date
                (point-in-time, ALFRED). Defaults to the latest vintage. The
                vintage the endpoint actually serves must match this date; a
                mismatch (for example, ALFRED clamping an out-of-range
                request to its latest vintage) raises ``ValueError``.

        Returns:
            The normalized macro series.

        Raises:
            ValueError: If the identifier is empty, the endpoint returns no
                usable data, or the served vintage differs from ``as_of``.

        """
        identifier = series_id.strip().upper() if isinstance(series_id, str) else ""
        if not identifier:
            msg = "El identificador de la serie no puede estar vacío."
            raise ValueError(msg)
        params = {"id": identifier}
        if start is not None:
            params["cosd"] = pd.Timestamp(start).strftime("%Y-%m-%d")
        if end is not None:
            params["coed"] = pd.Timestamp(end).strftime("%Y-%m-%d")
        requested: pd.Timestamp | None = None
        if as_of is not None:
            requested = naive_timestamp(as_of).normalize()
            params["vintage_date"] = requested.strftime("%Y-%m-%d")
        try:
            data = pd.read_csv(f"{ALFRED_CSV_URL}?{urlencode(params)}", dtype=str)
        except (OSError, ValueError) as exc:
            msg = f"No se pudo descargar la serie {identifier} de FRED: {exc}"
            raise ValueError(msg) from exc
        if data.empty or len(data.columns) < FRED_CSV_COLUMNS:
            msg = f"No se han encontrado datos para la serie {identifier} en FRED."
            raise ValueError(msg)
        date_column = data.columns[0]
        value_column = data.columns[1]
        vintage = _resolve_vintage(identifier, value_column, requested)
        dates = pd.to_datetime(data[date_column], errors="coerce")
        values = cast(
            "pd.Series[float]",
            pd.Series(
                pd.to_numeric(data[value_column], errors="coerce").to_numpy(),
                index=pd.DatetimeIndex(dates),
                name=identifier,
            ),
        )
        values = values[values.index.notna()]
        if end is not None:
            values = values[values.index < naive_timestamp(end)]
        if values.empty:
            msg = f"No se han encontrado datos para la serie {identifier} en FRED."
            raise ValueError(msg)
        return MacroSeries(
            series_id=identifier,
            values=values,
            source=self.name,
            vintage_date=vintage,
        )
