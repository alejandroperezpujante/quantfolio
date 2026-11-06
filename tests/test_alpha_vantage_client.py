"""Tests for the Alpha Vantage HTTP client."""

import json
from typing import Self, cast
from urllib.parse import parse_qs, urlparse

import pytest

from quantfolio.sources.alpha_vantage import client as client_module
from quantfolio.sources.alpha_vantage.client import (
    ALPHA_VANTAGE_QUERY_URL,
    HTTP_TIMEOUT,
    AlphaVantageClient,
    AlphaVantageError,
    AlphaVantageErrorCategory,
)

API_KEY = "secret-key"

QUOTA_PHRASES = (
    "rate limit",
    "call frequency",
    "requests per day",
    "requests per minute",
    "requests per second",
)

ENTITLEMENT_PHRASES = (
    "premium endpoint",
    "premium api",
    "premium member",
    "entitlement",
)

CONTROL_FIELDS = ("Error Message", "Information", "Note")


class _FakeResponse:
    """Minimal context-manager replacement for a urlopen response."""

    def __init__(self, body: object, *, raw: bool = False) -> None:
        self._body = body
        self._raw = raw

    def read(self) -> bytes:
        """Return the encoded response body."""
        if self._raw:
            return cast("bytes", self._body)
        return json.dumps(self._body).encode()

    def __enter__(self) -> Self:
        """Enter the context manager."""
        return self

    def __exit__(self, *args: object) -> None:
        """Exit the context manager."""
        del args


def _install_response(monkeypatch: pytest.MonkeyPatch, payload: object) -> None:
    """Serve one JSON payload through the module-level urlopen."""

    def fake_urlopen(_url: str, timeout: int = HTTP_TIMEOUT) -> _FakeResponse:
        del timeout
        return _FakeResponse(payload)

    monkeypatch.setattr(client_module, "urlopen", fake_urlopen)


def get_error(payload: object) -> AlphaVantageError:
    """Return the error the client raises for one control payload."""
    with pytest.MonkeyPatch.context() as monkeypatch:
        _install_response(monkeypatch, payload)
        client = AlphaVantageClient(API_KEY)
        with pytest.raises(AlphaVantageError) as captured:
            client.get(function="TIME_SERIES_DAILY", symbol="IBM")
    return captured.value


def test_get_returns_the_decoded_object(monkeypatch: pytest.MonkeyPatch) -> None:
    """A JSON object body is returned unchanged."""
    payload = {"Meta Data": {"2. Symbol": "IBM"}, "Time Series (Daily)": {}}
    _install_response(monkeypatch, payload)

    assert AlphaVantageClient(API_KEY).get(function="TIME_SERIES_DAILY") == payload


def test_get_calls_the_constant_endpoint_with_exact_parameters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The request targets the HTTPS endpoint with JSON, the key and a 30 s timeout."""
    calls: list[tuple[str, int]] = []

    def fake_urlopen(url: str, timeout: int = HTTP_TIMEOUT) -> _FakeResponse:
        calls.append((url, timeout))
        return _FakeResponse({"Meta Data": {}})

    monkeypatch.setattr(client_module, "urlopen", fake_urlopen)

    AlphaVantageClient(API_KEY).get(function="TIME_SERIES_DAILY", symbol="IBM")

    assert len(calls) == 1
    url, timeout = calls[0]
    parsed = urlparse(url)
    assert parsed.scheme == "https"
    assert parsed.netloc == "www.alphavantage.co"
    assert parsed.path == "/query"
    assert parse_qs(parsed.query) == {
        "function": ["TIME_SERIES_DAILY"],
        "symbol": ["IBM"],
        "datatype": ["json"],
        "apikey": [API_KEY],
    }
    assert timeout == HTTP_TIMEOUT == 30


def test_get_forces_json_datatype_and_configured_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Caller parameters cannot override the datatype or the configured credential."""
    calls: list[str] = []

    def fake_urlopen(url: str, timeout: int = HTTP_TIMEOUT) -> _FakeResponse:
        del timeout
        calls.append(url)
        return _FakeResponse({"Meta Data": {}})

    monkeypatch.setattr(client_module, "urlopen", fake_urlopen)

    AlphaVantageClient(API_KEY).get(datatype="csv", apikey="other-key", symbol="IBM")

    query = parse_qs(urlparse(calls[0]).query)
    assert query["datatype"] == ["json"]
    assert query["apikey"] == [API_KEY]


def test_get_wraps_network_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Network failures surface as generic errors without the request URL or key."""

    def fake_urlopen(_url: str, timeout: int = HTTP_TIMEOUT) -> _FakeResponse:
        del timeout
        msg = f"offline fetching {ALPHA_VANTAGE_QUERY_URL}?apikey={API_KEY}"
        raise OSError(msg)

    monkeypatch.setattr(client_module, "urlopen", fake_urlopen)
    client = AlphaVantageClient(API_KEY)

    with pytest.raises(AlphaVantageError) as captured:
        client.get(symbol="IBM")

    error = captured.value
    assert error.category is AlphaVantageErrorCategory.GENERIC
    assert "No se pudo contactar" in str(error)
    assert API_KEY not in str(error)
    assert ALPHA_VANTAGE_QUERY_URL not in str(error)
    assert error.__cause__ is None


@pytest.mark.parametrize("body", [b"<html>error</html>", b""])
def test_get_wraps_invalid_json(
    monkeypatch: pytest.MonkeyPatch,
    body: bytes,
) -> None:
    """Undecodable bodies raise a generic error instead of a decoding error."""

    def fake_urlopen(_url: str, timeout: int = HTTP_TIMEOUT) -> _FakeResponse:
        del timeout
        return _FakeResponse(body, raw=True)

    monkeypatch.setattr(client_module, "urlopen", fake_urlopen)
    client = AlphaVantageClient(API_KEY)

    with pytest.raises(AlphaVantageError) as captured:
        client.get(symbol="IBM")

    assert captured.value.category is AlphaVantageErrorCategory.GENERIC
    assert "JSON" in str(captured.value)


@pytest.mark.parametrize("payload", [[1, 2], "text", None, 3.5])
def test_get_rejects_non_object_json(
    monkeypatch: pytest.MonkeyPatch,
    payload: object,
) -> None:
    """Only a top-level JSON object is accepted as a successful response."""
    _install_response(monkeypatch, payload)
    client = AlphaVantageClient(API_KEY)

    with pytest.raises(AlphaVantageError) as captured:
        client.get(symbol="IBM")

    assert captured.value.category is AlphaVantageErrorCategory.GENERIC


@pytest.mark.parametrize("field", CONTROL_FIELDS)
@pytest.mark.parametrize("phrase", QUOTA_PHRASES)
def test_control_quota_phrases(field: str, phrase: str) -> None:
    """Quota phrases are classified as quota in every control field."""
    payload = {field: f"{phrase.upper()} reached; try later"}

    assert get_error(payload).category is AlphaVantageErrorCategory.QUOTA


@pytest.mark.parametrize("field", CONTROL_FIELDS)
@pytest.mark.parametrize("phrase", ENTITLEMENT_PHRASES)
def test_control_entitlement_phrases(field: str, phrase: str) -> None:
    """Premium and entitlement phrases are classified as entitlement in every field."""
    payload = {field: f"This {phrase} needs a higher plan"}

    assert get_error(payload).category is AlphaVantageErrorCategory.ENTITLEMENT


@pytest.mark.parametrize("field", CONTROL_FIELDS)
def test_control_unrecognized_text_is_generic(field: str) -> None:
    """Unrecognized control text is a generic provider error, not a denial."""
    payload = {field: "Invalid API call"}

    assert get_error(payload).category is AlphaVantageErrorCategory.GENERIC


def test_control_quota_precedes_premium_words() -> None:
    """A quota message that advertises premium plans is still a quota error."""
    payload = {"Information": "25 requests per day reached; subscribe to premium endpoint plans"}
    error = get_error(payload)
    assert error.category is AlphaVantageErrorCategory.QUOTA


def test_control_fields_are_joined_across_the_response() -> None:
    """Quota detection considers every control field, not only the first one."""
    payload = {"Note": "premium endpoint plans", "Information": "rate limit reached"}

    assert get_error(payload).category is AlphaVantageErrorCategory.QUOTA


@pytest.mark.parametrize("value", [None, 42, ["rate limit"], {"text": "premium api"}])
def test_control_fields_only_use_string_values(value: object) -> None:
    """Non-string control values are ignored, so the error stays generic."""
    error = get_error({"Note": value})

    assert error.category is AlphaVantageErrorCategory.GENERIC


def test_errors_do_not_leak_api_key_or_query_url() -> None:
    """Spanish errors never embed the credential or the request URL."""
    error = get_error({"Error Message": "Invalid API call"})
    assert "secret-key" not in str(error)
    assert "https://www.alphavantage.co/query" not in str(error)


def test_category_is_read_only() -> None:
    """The error category cannot be reassigned after construction."""
    error = AlphaVantageError("mensaje", AlphaVantageErrorCategory.QUOTA)

    with pytest.raises(AttributeError):
        error.category = AlphaVantageErrorCategory.GENERIC  # type: ignore[misc]


def test_categories_are_strings() -> None:
    """Categories serialize as their documented string values."""
    assert [str(category) for category in AlphaVantageErrorCategory] == [
        "generic",
        "quota",
        "entitlement",
    ]
