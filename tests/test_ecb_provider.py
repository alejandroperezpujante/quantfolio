"""Tests for the ECB daily reference exchange-rate source."""

from __future__ import annotations

from typing import TYPE_CHECKING, Self
from urllib.parse import parse_qs, urlparse

import pytest

from quantfolio.sources.ecb import ECBExchangeRateSource

if TYPE_CHECKING:
    from quantfolio.sources.base import PriceSource


def _new_source() -> PriceSource:
    """Build the ECB provider."""
    return ECBExchangeRateSource()


class _FakeResponse:
    """Small context manager for mocked ECB CSV responses."""

    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def read(self) -> bytes:
        """Return the configured response body."""
        return self.payload

    def __enter__(self) -> Self:
        """Enter the response context."""
        return self

    def __exit__(self, *_args: object) -> None:
        """Close the fake response context."""


def _install_response(
    monkeypatch: pytest.MonkeyPatch,
    payload: str,
) -> tuple[PriceSource, list[str]]:
    """Replace ECB HTTP access and return the requested URLs."""
    source = _new_source()
    urls: list[str] = []

    def fake_urlopen(url: str, timeout: int) -> _FakeResponse:
        assert timeout == 30
        urls.append(url)
        return _FakeResponse(payload.encode())

    monkeypatch.setattr("quantfolio.sources.ecb.urlopen", fake_urlopen)
    return source, urls


def test_ecb_source_parses_daily_rates_and_exclusive_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The EUR-first pair maps to the ECB series key and respects the date window."""
    payload = (
        "TIME_PERIOD,OBS_VALUE\n"
        "2025-01-01,1.02\n"
        "2025-01-02,1.03\n"
        "2025-01-03,1.04\n"
        "2025-01-06,1.05\n"
        "2025-01-07,1.06\n"
    )
    source, urls = _install_response(monkeypatch, payload)

    asset = source.get_prices("FX:EUR/USD", "2025-01-02", "2025-01-07")

    request = urlparse(urls[0])
    query = parse_qs(request.query)
    assert request.path.endswith("/EXR/D.USD.EUR.SP00.A")
    assert query == {
        "startPeriod": ["2025-01-02"],
        "endPeriod": ["2025-01-06"],
        "format": ["csvdata"],
    }
    assert asset.ticker == "FX:EUR/USD"
    assert asset.source == "ECB reference rates"
    assert asset.quote_currency == "USD"
    assert list(asset.prices) == [1.03, 1.04, 1.05]


def test_ecb_source_normalizes_pair_case_and_omits_open_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pair codes are canonicalized and an open-ended request omits endPeriod."""
    source, urls = _install_response(
        monkeypatch,
        "TIME_PERIOD,OBS_VALUE\n2025-01-02,1.03\n",
    )

    asset = source.get_prices("fx:eur/usd", "2025-01-02")

    assert asset.ticker == "FX:EUR/USD"
    assert "endPeriod" not in parse_qs(urlparse(urls[0]).query)


@pytest.mark.parametrize(
    ("ticker", "message"),
    [
        ("FX:USD/EUR", "EUR como primera"),
        ("FX:EURUSD", "formato"),
        ("FX:EUR/EUR", "EUR/EUR"),
    ],
)
def test_ecb_source_rejects_unsupported_pairs(ticker: str, message: str) -> None:
    """Only valid EUR-first ECB exchange-rate pairs are accepted."""
    source = _new_source()
    with pytest.raises(ValueError, match=message):
        source.get_prices(ticker, "2025-01-02")


def test_ecb_source_rejects_an_empty_requested_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rows outside the requested dates do not become rate observations."""
    source, _urls = _install_response(
        monkeypatch,
        "TIME_PERIOD,OBS_VALUE\n2025-01-01,1.02\n",
    )

    with pytest.raises(ValueError, match="No se han encontrado datos"):
        source.get_prices("FX:EUR/USD", "2025-01-02", "2025-01-04")


@pytest.mark.parametrize(
    ("payload", "message"),
    [("", "CSV"), ("TIME_PERIOD,VALUE\n2025-01-02,1.02\n", "columnas")],
)
def test_ecb_source_rejects_malformed_responses(
    monkeypatch: pytest.MonkeyPatch,
    payload: str,
    message: str,
) -> None:
    """Empty CSV and responses without required fields produce Spanish errors."""
    source, _urls = _install_response(monkeypatch, payload)

    with pytest.raises(ValueError, match=message):
        source.get_prices("FX:EUR/USD", "2025-01-02")


def test_ecb_source_rejects_invalid_exchange_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-positive and non-numeric ECB observations are not silently carried."""
    source, _urls = _install_response(
        monkeypatch,
        "TIME_PERIOD,OBS_VALUE\n2025-01-02,0\n2025-01-03,invalid\n",
    )

    with pytest.raises(ValueError, match="tipos de cambio no válidos"):
        source.get_prices("FX:EUR/USD", "2025-01-02")


def test_ecb_source_rejects_infinite_exchange_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Infinite response values are invalid rather than silently removed."""
    source, _urls = _install_response(
        monkeypatch,
        "TIME_PERIOD,OBS_VALUE\n2025-01-02,1.02\n2025-01-03,inf\n",
    )

    with pytest.raises(ValueError, match="tipos de cambio no válidos"):
        source.get_prices("FX:EUR/USD", "2025-01-02")


def test_ecb_source_rejects_a_non_positive_date_window() -> None:
    """A daily exclusive end must be later than the requested start."""
    source = _new_source()
    with pytest.raises(ValueError, match="posterior a la fecha inicial"):
        source.get_prices("FX:EUR/USD", "2025-01-02", "2025-01-02")


def test_ecb_source_reports_network_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """HTTP failures are translated into a Spanish provider error."""

    def fail_urlopen(_url: str, timeout: int) -> _FakeResponse:
        assert timeout == 30
        msg = "offline"
        raise OSError(msg)

    source = _new_source()
    monkeypatch.setattr("quantfolio.sources.ecb.urlopen", fail_urlopen)

    with pytest.raises(ValueError, match="No se pudo descargar"):
        source.get_prices("FX:EUR/USD", "2025-01-02")
