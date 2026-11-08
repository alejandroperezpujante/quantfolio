"""Daily reference exchange rates from the ECB Data Portal."""

import re
from io import StringIO
from typing import TYPE_CHECKING, cast
from urllib.parse import urlencode
from urllib.request import urlopen

import numpy as np
import pandas as pd

from quantfolio.models import PriceSeries
from quantfolio.sources.base import PriceSource, naive_timestamp, validate_ticker

if TYPE_CHECKING:
    from quantfolio.sources.base import DateLike

#: ECB Data Portal entry point for statistical observations.
ECB_DATA_URL = "https://data-api.ecb.europa.eu/service/data/EXR"

#: Timeout, in seconds, applied to requests.
HTTP_TIMEOUT = 30

_PAIR_PATTERN = re.compile(r"FX:([A-Z]{3})/([A-Z]{3})", re.IGNORECASE)


def _parse_pair(ticker: str) -> tuple[str, str, str]:
    """Return a canonical EUR-first pair from an ECB-style ticker."""
    symbol = validate_ticker(ticker)
    match = _PAIR_PATTERN.fullmatch(symbol)
    if match is None:
        msg = f"El ticker {symbol} debe usar el formato FX:EUR/DIVISA."
        raise ValueError(msg)
    base, quote = (code.upper() for code in match.groups())
    if base != "EUR":
        msg = "El proveedor ECB requiere EUR como primera divisa del par."
        raise ValueError(msg)
    if quote == "EUR":
        msg = "El proveedor ECB no ofrece un tipo de cambio EUR/EUR."
        raise ValueError(msg)
    return f"FX:{base}/{quote}", base, quote


def _fetch_csv(url: str, symbol: str) -> str:
    """Download and decode one ECB CSV response."""
    try:
        with urlopen(url, timeout=HTTP_TIMEOUT) as response:
            payload = cast("bytes", response.read())
            return payload.decode("utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        msg = f"No se pudo descargar la serie {symbol} del ECB: {exc}"
        raise ValueError(msg) from exc


class ECBExchangeRateSource(PriceSource):
    """Daily ECB reference rates, expressed as quote-currency units per EUR.

    These rates are informational reference rates, not broker execution prices. They are
    published as one unit of the first currency (EUR) in units of the second currency.
    """

    @property
    def name(self) -> str:
        """Return the human-readable provider name."""
        return "ECB reference rates"

    def get_prices(
        self,
        ticker: str,
        start: DateLike,
        end: DateLike | None = None,
    ) -> PriceSeries:
        """Return one daily EUR-first ECB reference-rate history.

        Args:
            ticker: Pair in ``FX:EUR/USD`` format.
            start: First observation date (inclusive).
            end: Last observation date (exclusive); defaults to the present.

        Returns:
            The normalized reference-rate series.

        Raises:
            ValueError: If the pair is unsupported, the date window is invalid, the request
                fails, or the response does not contain valid observations.

        """
        symbol, base, quote = _parse_pair(ticker)
        start_date = naive_timestamp(start).normalize()
        end_date = naive_timestamp(end).normalize() if end is not None else None
        if end_date is not None and end_date <= start_date:
            msg = "La fecha final debe ser posterior a la fecha inicial."
            raise ValueError(msg)

        params = {"startPeriod": start_date.date().isoformat(), "format": "csvdata"}
        if end_date is not None:
            params["endPeriod"] = (end_date - pd.Timedelta(days=1)).date().isoformat()
        series_key = f"D.{quote}.{base}.SP00.A"
        url = f"{ECB_DATA_URL}/{series_key}?{urlencode(params)}"
        payload = _fetch_csv(url, symbol)
        try:
            frame = pd.read_csv(
                StringIO(payload),
                dtype={"TIME_PERIOD": "string", "OBS_VALUE": "string"},
            )
        except ValueError as exc:
            msg = f"El ECB devolvió un CSV no válido para {symbol}."
            raise ValueError(msg) from exc
        if not {"TIME_PERIOD", "OBS_VALUE"}.issubset(frame.columns):
            msg = f"El CSV del ECB no contiene las columnas de fecha y valor para {symbol}."
            raise ValueError(msg)

        dates = pd.to_datetime(frame["TIME_PERIOD"], errors="coerce")
        values = pd.to_numeric(frame["OBS_VALUE"], errors="coerce")
        if (
            dates.isna().any()
            or values.isna().any()
            or not np.isfinite(values).all()
            or (values <= 0).any()
        ):
            msg = f"El ECB devolvió fechas o tipos de cambio no válidos para {symbol}."
            raise ValueError(msg)
        prices = pd.Series(
            values.to_numpy(dtype=float),
            index=pd.DatetimeIndex(dates),
            name=symbol,
        )
        asset = PriceSeries(
            ticker=symbol,
            prices=prices,
            source=self.name,
            quote_currency=quote,
        )
        window = asset.prices[asset.prices.index >= start_date]
        if end_date is not None:
            window = window[window.index < end_date]
        if window.empty:
            msg = f"No se han encontrado datos de {symbol} en el ECB para las fechas solicitadas."
            raise ValueError(msg)
        return PriceSeries(
            ticker=symbol,
            prices=window,
            source=self.name,
            quote_currency=quote,
        )
