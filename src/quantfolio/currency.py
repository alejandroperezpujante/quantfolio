"""Currency codes, historical exchange-rate selection and conversion metadata."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import cast

import pandas as pd

from quantfolio.models import PriceSeries
from quantfolio.quote_metadata import _normalize_currency_code
from quantfolio.sources.base import DateLike, PriceSource, naive_timestamp

_PAIR_PATTERN = re.compile(r"FX:([A-Z]{3})/([A-Z]{3})", re.IGNORECASE)


class _RateUnavailableError(ValueError):
    """An available pair has no rate observation usable on the requested date."""


def _parse_pair(ticker: str) -> tuple[str, str]:
    """Return a canonical ordered pair from an FX PriceSeries ticker."""
    match = _PAIR_PATTERN.fullmatch(ticker)
    if match is None:
        msg = f"La serie de tipo de cambio {ticker!r} debe usar el formato FX:AAA/BBB."
        raise ValueError(msg)
    base, quote = (code.upper() for code in match.groups())
    if base == quote:
        msg = f"El par de divisas {base}/{quote} no representa una conversión válida."
        raise ValueError(msg)
    return base, quote


@dataclass(frozen=True)
class ExchangeRateObservation:
    """One historical rate observation used to convert a portfolio price.

    Attributes:
        pair: Supplied pair ticker, with the observation's original orientation.
        source: Provider or manual-input provenance.
        from_currency: Currency being converted by this leg.
        to_currency: Currency received from this leg.
        observation_date: Date of the selected rate observation.
        age_days: Calendar days between the asset and rate observations.
        rate: Positive rate value as supplied by the source series.
        applied_rate: Rate factor applied in the requested direction.
        inverted: Whether the source series was inverted for this conversion leg.

    """

    pair: str
    source: str
    from_currency: str
    to_currency: str
    observation_date: pd.Timestamp
    age_days: int
    rate: float
    applied_rate: float
    inverted: bool


@dataclass(frozen=True, init=False, eq=False)
class ExchangeRates:
    """Collection of historical FX ``PriceSeries`` with a bounded carry-forward.

    Rate tickers identify the ordered pair: ``FX:EUR/USD`` stores USD units per EUR.
    ``resolve_rate`` prefers a direct pair, then its inverse, and finally a two-leg EUR
    cross. Each selected observation must be on or before the requested date and no more
    than ``max_age_days`` calendar days old. Collections compare by identity because their
    public rate series contain mutable pandas objects, and they are deliberately unhashable.

    Args:
        rates: Mapping or iterable of rate series returned by a ``PriceSource`` or supplied
            manually.
        max_age_days: Maximum calendar age accepted for each rate observation; defaults to 4.

    """

    rates: tuple[PriceSeries, ...]
    max_age_days: int
    _pairs: dict[tuple[str, str], PriceSeries] = field(repr=False, compare=False)
    __hash__ = None  # type: ignore[assignment]

    def __init__(
        self,
        rates: Mapping[str, PriceSeries] | Iterable[PriceSeries] = (),
        *,
        max_age_days: int = 4,
    ) -> None:
        """Validate and index the supplied pair series."""
        if isinstance(max_age_days, bool) or not isinstance(max_age_days, int) or max_age_days < 0:
            msg = "max_age_days debe ser un entero no negativo."
            raise ValueError(msg)
        series = tuple(rates.values()) if isinstance(rates, Mapping) else tuple(rates)
        pair_map: dict[tuple[str, str], PriceSeries] = {}
        for rate_series in series:
            if not isinstance(rate_series, PriceSeries):
                msg = "Cada tipo de cambio debe ser una instancia de PriceSeries."
                raise TypeError(msg)
            pair = _parse_pair(rate_series.ticker)
            if rate_series.quote_currency is not None and rate_series.quote_currency != pair[1]:
                msg = f"La divisa cotizada de {rate_series.ticker} no coincide con el par indicado."
                raise ValueError(msg)
            if pair in pair_map:
                msg = f"El par {pair[0]}/{pair[1]} es ambiguo: hay más de una serie suministrada."
                raise ValueError(msg)
            pair_map[pair] = rate_series
        object.__setattr__(self, "rates", series)
        object.__setattr__(self, "max_age_days", max_age_days)
        object.__setattr__(self, "_pairs", pair_map)

    @classmethod
    def from_source(
        cls,
        source: PriceSource,
        pairs: Sequence[str],
        start: DateLike,
        end: DateLike | None = None,
        *,
        max_age_days: int = 4,
    ) -> ExchangeRates:
        """Fetch rate series through the common ``PriceSource`` contract.

        Args:
            source: Provider that understands the requested pair tickers.
            pairs: Ordered FX pair tickers to fetch.
            start: First observation date (inclusive).
            end: Last observation date (exclusive).
            max_age_days: Maximum accepted carry-forward age per FX leg.

        Returns:
            An ``ExchangeRates`` collection backed by the fetched provider series.

        """
        return cls(source.get_many(pairs, start, end), max_age_days=max_age_days)

    def resolve_rate(
        self,
        from_currency: str,
        to_currency: str,
        on_date: DateLike,
    ) -> tuple[float, tuple[ExchangeRateObservation, ...]]:
        """Return the conversion factor and the selected rate observations.

        Args:
            from_currency: Currency to convert from.
            to_currency: Currency to convert to.
            on_date: Asset observation date for which rates are required.

        Returns:
            Pair of the number of target units per source unit and rate trace records.

        Raises:
            ValueError: If no usable direct, inverse or EUR-pivot route exists, a rate is
                stale or future-dated, or a rate is not positive and finite.

        """
        source = _normalize_currency_code(from_currency, "La divisa de origen")
        target = _normalize_currency_code(to_currency, "La divisa de destino")
        date_stamp = naive_timestamp(on_date)
        if pd.isna(cast("pd.Timestamp | None", date_stamp)):
            msg = "La fecha de conversión debe ser una fecha válida."
            raise ValueError(msg)
        date = date_stamp.normalize()
        if source == target:
            return 1.0, ()

        return self._resolve_rate_with_fallback(source, target, date)

    def _resolve_rate_with_fallback(
        self,
        source: str,
        target: str,
        date: pd.Timestamp,
    ) -> tuple[float, tuple[ExchangeRateObservation, ...]]:
        """Try direct and EUR-pivot routes, retaining the preferred route's error."""
        unavailable_error: _RateUnavailableError | None = None
        try:
            direct = self._resolve_leg(source, target, date)
        except _RateUnavailableError as exc:
            unavailable_error = exc
            direct = None
        if direct is not None:
            factor, observation = direct
            return factor, (observation,)

        try:
            cross_rate = self._resolve_eur_pivot(source, target, date)
        except _RateUnavailableError as exc:
            if unavailable_error is None:
                unavailable_error = exc
        else:
            if cross_rate is not None:
                return cross_rate

        if unavailable_error is not None:
            raise unavailable_error

        msg = f"No hay tipo de cambio disponible para {source}/{target} el {date:%Y-%m-%d}."
        raise ValueError(msg)

    def _resolve_eur_pivot(
        self,
        source: str,
        target: str,
        date: pd.Timestamp,
    ) -> tuple[float, tuple[ExchangeRateObservation, ...]] | None:
        """Resolve a cross-currency pair through independently checked EUR legs."""
        if source == "EUR" or target == "EUR":
            return None
        source_to_eur = self._resolve_leg(source, "EUR", date)
        eur_to_target = self._resolve_leg("EUR", target, date)
        if source_to_eur is None or eur_to_target is None:
            return None
        first_factor, first_observation = source_to_eur
        second_factor, second_observation = eur_to_target
        return first_factor * second_factor, (first_observation, second_observation)

    def _resolve_leg(
        self,
        from_currency: str,
        to_currency: str,
        on_date: pd.Timestamp,
    ) -> tuple[float, ExchangeRateObservation] | None:
        """Resolve one direct or inverse rate leg, checking its age independently."""
        direct_pair = (from_currency, to_currency)
        inverse_pair = (to_currency, from_currency)
        unavailable_error: _RateUnavailableError | None = None
        for pair, inverted in (direct_pair, False), (inverse_pair, True):
            rate_series = self._pairs.get(pair)
            if rate_series is None:
                continue
            try:
                return self._rate_observation(
                    rate_series,
                    from_currency,
                    to_currency,
                    on_date,
                    inverted=inverted,
                )
            except _RateUnavailableError as exc:
                if unavailable_error is None:
                    unavailable_error = exc
        if unavailable_error is not None:
            raise unavailable_error
        return None

    def _rate_observation(
        self,
        series: PriceSeries,
        from_currency: str,
        to_currency: str,
        on_date: pd.Timestamp,
        *,
        inverted: bool,
    ) -> tuple[float, ExchangeRateObservation]:
        """Select one non-future observation and validate its value and calendar age."""
        pair = _parse_pair(series.ticker)
        position = int(series.prices.index.searchsorted(on_date, side="right")) - 1
        if position < 0:
            msg = f"No hay observaciones de {pair[0]}/{pair[1]} en o antes del {on_date:%Y-%m-%d}."
            raise _RateUnavailableError(msg)
        observation_date = pd.Timestamp(series.prices.index[position])
        age_days = (on_date - observation_date.normalize()).days
        if age_days > self.max_age_days:
            msg = (
                f"El tipo de cambio {pair[0]}/{pair[1]} está obsoleto: "
                f"tiene {age_days} días y el máximo es {self.max_age_days}."
            )
            raise _RateUnavailableError(msg)
        rate = float(series.prices.iloc[position])
        if not math.isfinite(rate) or rate <= 0:
            msg = f"El tipo de cambio {pair[0]}/{pair[1]} debe ser positivo y finito."
            raise ValueError(msg)
        applied_rate = 1.0 / rate if inverted else rate
        observation = ExchangeRateObservation(
            pair=f"FX:{pair[0]}/{pair[1]}",
            source=series.source,
            from_currency=from_currency,
            to_currency=to_currency,
            observation_date=observation_date,
            age_days=age_days,
            rate=rate,
            applied_rate=applied_rate,
            inverted=inverted,
        )
        return applied_rate, observation
