"""Macroeconomic time series from FRED."""

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast
from urllib.parse import urlencode

import pandas as pd

from quantfolio.models import clean_numeric_series

if TYPE_CHECKING:
    from quantfolio.sources.base import DateLike

FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"

#: Minimum number of columns expected in the FRED CSV export (date and value).
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
    """Client for the keyless FRED CSV export endpoint."""

    @property
    def name(self) -> str:
        """Return the provider name."""
        return "FRED"

    def get_series(
        self,
        series_id: str,
        start: DateLike | None = None,
        end: DateLike | None = None,
    ) -> MacroSeries:
        """Download a macroeconomic series.

        Args:
            series_id: FRED identifier, for example ``"DGS10"`` or ``"CPIAUCSL"``.
            start: First observation date (inclusive).
            end: Last observation date (inclusive).

        Returns:
            The normalized macro series.

        Raises:
            ValueError: If the identifier is empty or the endpoint returns no usable data.

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
        try:
            data = pd.read_csv(f"{FRED_CSV_URL}?{urlencode(params)}", dtype=str)
        except (OSError, ValueError) as exc:
            msg = f"No se pudo descargar la serie {identifier} de FRED: {exc}"
            raise ValueError(msg) from exc
        if data.empty or len(data.columns) < FRED_CSV_COLUMNS:
            msg = f"No se han encontrado datos para la serie {identifier} en FRED."
            raise ValueError(msg)
        date_column = data.columns[0]
        value_column = data.columns[1]
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
        return MacroSeries(series_id=identifier, values=values, source=self.name)
