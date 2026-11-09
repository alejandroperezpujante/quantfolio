"""Canonical currency codes and unambiguous quote-unit metadata."""

import re

#: Fiat currencies for which the ECB publishes daily euro reference rates.
ECB_FIAT_CURRENCIES: frozenset[str] = frozenset(
    {
        "AUD",
        "BGN",
        "BRL",
        "CAD",
        "CHF",
        "CNY",
        "CZK",
        "DKK",
        "EUR",
        "GBP",
        "HKD",
        "HUF",
        "IDR",
        "ILS",
        "INR",
        "ISK",
        "JPY",
        "KRW",
        "MXN",
        "MYR",
        "NOK",
        "NZD",
        "PHP",
        "PLN",
        "RON",
        "SEK",
        "SGD",
        "THB",
        "TRY",
        "USD",
        "ZAR",
    }
)

_MINOR_UNITS: dict[str, tuple[str, float]] = {
    "GBX": ("GBP", 0.01),
    "ILA": ("ILS", 0.01),
    "ZAC": ("ZAR", 0.01),
}


def _normalize_currency_code(value: object, label: str) -> str:
    """Return a canonical three-letter currency code after validating its shape."""
    if not isinstance(value, str):
        msg = f"{label} debe ser un texto."
        raise TypeError(msg)
    original = value.strip()
    code = original.upper()
    unit_alias = original == "GBp" or original.casefold() in {"gbx", "ila", "zac"}
    ambiguous_gbp = original.casefold() == "gbp" and original != "GBP"
    if unit_alias or ambiguous_gbp:
        msg = (
            f"{label} no puede ser la unidad de cotización {original!r}; "
            "usa la divisa canónica y declara la unidad en quote_unit."
        )
        raise ValueError(msg)
    if not re.fullmatch(r"[A-Z]{3}", code):
        msg = f"{label} debe ser un código de tres letras."
        raise ValueError(msg)
    return code


def _normalize_quote_unit(value: object) -> tuple[str, str, float]:
    """Return the original unit, its canonical currency and its conversion factor."""
    if not isinstance(value, str) or not value.strip():
        msg = "La unidad de cotización debe ser un texto no vacío."
        raise ValueError(msg)
    unit = value.strip()
    if unit == "GBp":
        normalized = (unit, "GBP", 0.01)
    elif unit == "GBP":
        normalized = (unit, "GBP", 1.0)
    elif unit.upper() in _MINOR_UNITS:
        currency, factor = _MINOR_UNITS[unit.upper()]
        normalized = (unit, currency, factor)
    else:
        if unit.casefold() == "gbp":
            msg = (
                "La unidad de cotización 'Gbp' es ambigua; "
                "usa 'GBp' para peniques o 'GBP' para libras."
            )
            raise ValueError(msg)
        normalized = (unit, _normalize_currency_code(unit, "La unidad de cotización"), 1.0)
    return normalized


def _normalize_quote_metadata(
    quote_currency: str | None,
    quote_unit: str | None,
) -> tuple[str | None, str | None, float]:
    """Validate quote metadata and return its canonical currency and unit factor."""
    unit_currency: str | None = None
    unit_factor = 1.0
    normalized_unit = quote_unit
    if quote_unit is not None:
        normalized_unit, unit_currency, unit_factor = _normalize_quote_unit(quote_unit)
    normalized_currency = (
        _normalize_currency_code(quote_currency, "La divisa de cotización")
        if quote_currency is not None
        else unit_currency
    )
    if unit_currency is not None and normalized_currency != unit_currency:
        msg = "La unidad de cotización no coincide con la divisa indicada."
        raise ValueError(msg)
    return normalized_currency, normalized_unit, unit_factor
