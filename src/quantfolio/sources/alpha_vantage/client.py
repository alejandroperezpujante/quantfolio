"""HTTP client and control-response classification for the Alpha Vantage API."""

import json
from enum import StrEnum
from typing import TYPE_CHECKING, cast
from urllib.parse import urlencode
from urllib.request import urlopen

if TYPE_CHECKING:
    from collections.abc import Mapping

ALPHA_VANTAGE_QUERY_URL = "https://www.alphavantage.co/query"

#: Timeout, in seconds, applied to Alpha Vantage requests.
HTTP_TIMEOUT = 30

#: Control fields that carry a provider message instead of market data.
_CONTROL_FIELDS = ("Error Message", "Information", "Note")

#: Phrases that identify an exhausted quota or rate limit.
_QUOTA_PHRASES = (
    "rate limit",
    "call frequency",
    "requests per day",
    "requests per minute",
    "requests per second",
)

#: Phrases that identify an endpoint the configured key is not entitled to.
_ENTITLEMENT_PHRASES = (
    "premium endpoint",
    "premium api",
    "premium member",
    "entitlement",
)

_QUOTA_MESSAGE = (
    "Alpha Vantage ha alcanzado el límite de peticiones de la clave configurada. "
    "Espera antes de reintentar o revisa el plan de la cuenta."
)
_ENTITLEMENT_MESSAGE = (
    "La clave de Alpha Vantage no tiene acceso a este endpoint porque requiere un plan superior."
)
_GENERIC_MESSAGE = "Alpha Vantage devolvió un error no reconocido para esta petición."


class AlphaVantageErrorCategory(StrEnum):
    """Classification of a control response returned by Alpha Vantage."""

    GENERIC = "generic"
    QUOTA = "quota"
    ENTITLEMENT = "entitlement"


class AlphaVantageError(ValueError):
    """Error raised when Alpha Vantage cannot serve a request.

    Messages are user-facing and never embed the API key or the request URL.
    """

    def __init__(
        self,
        message: str,
        category: AlphaVantageErrorCategory = AlphaVantageErrorCategory.GENERIC,
    ) -> None:
        """Store the message and its classification.

        Args:
            message: Spanish description of the failure.
            category: Classification used by callers to decide capability downgrades.

        """
        super().__init__(message)
        self._category = category

    @property
    def category(self) -> AlphaVantageErrorCategory:
        """Return the error classification."""
        return self._category


def _control_error(payload: Mapping[str, object]) -> AlphaVantageError | None:
    """Return the error describing a control response, if the payload has one.

    Quota phrases are matched before entitlement phrases because quota messages often
    advertise premium plans, which must not be read as an entitlement denial.

    Args:
        payload: Decoded JSON body returned by the endpoint.

    Returns:
        The classified error, or ``None`` when the payload carries no control field.

    """
    values = [payload[field] for field in _CONTROL_FIELDS if field in payload]
    if not values:
        return None
    text = " ".join(value.strip().lower() for value in values if isinstance(value, str))
    if any(phrase in text for phrase in _QUOTA_PHRASES):
        category = AlphaVantageErrorCategory.QUOTA
        message = _QUOTA_MESSAGE
    elif any(phrase in text for phrase in _ENTITLEMENT_PHRASES):
        category = AlphaVantageErrorCategory.ENTITLEMENT
        message = _ENTITLEMENT_MESSAGE
    else:
        category = AlphaVantageErrorCategory.GENERIC
        message = _GENERIC_MESSAGE
    return AlphaVantageError(message, category)


class AlphaVantageClient:
    """Minimal JSON client for the Alpha Vantage REST API."""

    def __init__(self, api_key: str) -> None:
        """Store the credential used to authenticate every request.

        Args:
            api_key: Alpha Vantage API key, kept out of every error message.

        """
        self._api_key = api_key

    def get(self, **parameters: str) -> dict[str, object]:
        """Return the decoded JSON object of one API call.

        Args:
            **parameters: Endpoint parameters such as ``function`` and ``symbol``.
                ``datatype`` is always ``json`` and ``apikey`` is always the configured
                credential, so callers cannot override either of them.

        Returns:
            The response body, guaranteed to be a JSON object without control fields.

        Raises:
            AlphaVantageError: If the request fails, the body is not a JSON object, or
                the provider answers with a control field instead of market data.

        """
        query = {**parameters, "datatype": "json", "apikey": self._api_key}
        url = f"{ALPHA_VANTAGE_QUERY_URL}?{urlencode(query)}"
        try:
            with urlopen(url, timeout=HTTP_TIMEOUT) as response:
                payload: object = json.load(response)
        except OSError as exc:
            # The original error may embed the credential-bearing URL in its message,
            # so it is deliberately not chained to the user-facing error.
            msg = f"No se pudo contactar con Alpha Vantage ({type(exc).__name__})."
            raise AlphaVantageError(msg) from None
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            msg = f"Alpha Vantage devolvió una respuesta JSON no válida ({type(exc).__name__})."
            raise AlphaVantageError(msg) from None
        if not isinstance(payload, dict):
            msg = "Alpha Vantage devolvió una respuesta JSON que no es un objeto."
            raise AlphaVantageError(msg)
        body = cast("dict[str, object]", payload)
        error = _control_error(body)
        if error is not None:
            raise error
        return body
