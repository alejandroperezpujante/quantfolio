"""Tests for currency conversion and rate selection."""

from typing import cast

import pandas as pd
import pytest

from quantfolio.currency import ExchangeRates
from quantfolio.models import PriceSeries
from quantfolio.portfolio import Portfolio
from tests.helpers import TRADING_DATES, StubSource


def _exchange_rates(
    rates: list[PriceSeries],
    *,
    max_age_days: int = 4,
) -> ExchangeRates:
    """Build a validated collection of exchange-rate series."""
    return ExchangeRates(rates=rates, max_age_days=max_age_days)


def _rate(
    pair: str,
    values: list[float],
    dates: list[str],
    *,
    source: str = "Manual rates",
) -> PriceSeries:
    """Build a pair series with explicitly supplied quote-currency metadata."""
    quote_currency = pair.rsplit("/", maxsplit=1)[1]
    return PriceSeries(
        ticker=f"FX:{pair}",
        prices=pd.Series(values, index=pd.DatetimeIndex(dates), dtype=float),
        source=source,
        quote_currency=quote_currency,
    )


def test_exchange_rates_resolve_identity_without_observations() -> None:
    """A currency is worth one unit of itself and needs no rate series."""
    rates = _exchange_rates([])

    factor, observations = rates.resolve_rate("EUR", "EUR", pd.Timestamp("2025-01-02"))

    assert factor == 1.0
    assert observations == ()


def test_exchange_rates_prefer_direct_rates_over_inverse_rates() -> None:
    """A supplied direct pair takes precedence when both orientations exist."""
    rates = _exchange_rates(
        [
            _rate("USD/EUR", [0.9], ["2025-01-02"]),
            _rate("EUR/USD", [2.0], ["2025-01-02"]),
        ]
    )

    factor, observations = rates.resolve_rate("USD", "EUR", pd.Timestamp("2025-01-02"))

    assert factor == pytest.approx(0.9)
    assert observations[0].pair == "FX:USD/EUR"
    assert observations[0].inverted is False


def test_exchange_rates_fall_back_to_inverse_when_direct_rate_is_stale() -> None:
    """A stale preferred pair does not block a fresh inverse observation."""
    rates = _exchange_rates(
        [
            _rate("USD/EUR", [0.9], ["2025-01-01"]),
            _rate("EUR/USD", [1.25], ["2025-01-06"]),
        ]
    )
    on_date = pd.Timestamp("2025-01-06")

    factor, observations = rates.resolve_rate("USD", "EUR", on_date)

    assert factor == pytest.approx(0.8)
    assert observations[0].pair == "FX:EUR/USD"
    assert observations[0].inverted is True


def test_exchange_rates_fall_back_to_inverse_when_direct_rate_is_future_dated() -> None:
    """A future preferred pair does not block an inverse observation on the date."""
    rates = _exchange_rates(
        [
            _rate("USD/EUR", [0.9], ["2025-01-08"]),
            _rate("EUR/USD", [1.25], ["2025-01-06"]),
        ]
    )
    on_date = pd.Timestamp("2025-01-06")

    factor, observations = rates.resolve_rate("USD", "EUR", on_date)

    assert factor == pytest.approx(0.8)
    assert observations[0].pair == "FX:EUR/USD"
    assert observations[0].inverted is True


def test_exchange_rates_fall_back_to_eur_pivot_when_direct_rate_is_stale() -> None:
    """A stale preferred pair does not block a fresh EUR-pivot cross rate."""
    rates = _exchange_rates(
        [
            _rate("USD/GBP", [0.7], ["2025-01-01"]),
            _rate("EUR/USD", [1.25], ["2025-01-06"]),
            _rate("EUR/GBP", [0.8], ["2025-01-06"]),
        ]
    )
    on_date = pd.Timestamp("2025-01-06")

    factor, observations = rates.resolve_rate("USD", "GBP", on_date)

    assert factor == pytest.approx(0.64)
    assert [row.pair for row in observations] == ["FX:EUR/USD", "FX:EUR/GBP"]


def test_exchange_rates_report_direct_staleness_when_fallback_is_also_stale() -> None:
    """When no route is usable, the preferred pair's staleness remains visible."""
    rates = _exchange_rates(
        [
            _rate("USD/GBP", [0.7], ["2025-01-01"]),
            _rate("EUR/USD", [1.25], ["2025-01-01"]),
        ]
    )
    on_date = pd.Timestamp("2025-01-06")

    with pytest.raises(ValueError, match="USD/GBP está obsoleto"):
        rates.resolve_rate("USD", "GBP", on_date)


def test_exchange_rates_report_direct_staleness_when_inverse_is_also_stale() -> None:
    """An unusable inverse does not replace the preferred pair's Spanish error."""
    rates = _exchange_rates(
        [
            _rate("USD/EUR", [0.9], ["2025-01-01"]),
            _rate("EUR/USD", [1.25], ["2025-01-01"]),
        ]
    )
    on_date = pd.Timestamp("2025-01-06")

    with pytest.raises(ValueError, match="USD/EUR está obsoleto"):
        rates.resolve_rate("USD", "EUR", on_date)


def test_exchange_rates_resolve_inverse_rate() -> None:
    """The inverse of a supplied pair converts in the opposite direction."""
    rates = _exchange_rates([_rate("EUR/USD", [1.25], ["2025-01-02"])])

    factor, observations = rates.resolve_rate("USD", "EUR", pd.Timestamp("2025-01-02"))

    assert factor == pytest.approx(0.8)
    assert observations[0].inverted is True


def test_exchange_rates_resolve_eur_pivot_cross_rate() -> None:
    """A non-EUR pair is composed from two independently selected EUR legs."""
    rates = _exchange_rates(
        [
            _rate("EUR/USD", [1.2], ["2025-01-02"]),
            _rate("EUR/GBP", [0.8], ["2025-01-02"]),
        ]
    )

    factor, observations = rates.resolve_rate("USD", "GBP", pd.Timestamp("2025-01-02"))

    assert factor == pytest.approx(2 / 3)
    assert len(observations) == 2
    assert [row.pair for row in observations] == ["FX:EUR/USD", "FX:EUR/GBP"]


def test_exchange_rates_prefer_direct_rates_over_eur_cross_rates() -> None:
    """An explicit direct pair wins over a derived EUR-pivot conversion."""
    rates = _exchange_rates(
        [
            _rate("USD/GBP", [0.7], ["2025-01-02"]),
            _rate("EUR/USD", [1.2], ["2025-01-02"]),
            _rate("EUR/GBP", [0.8], ["2025-01-02"]),
        ]
    )

    factor, observations = rates.resolve_rate("USD", "GBP", pd.Timestamp("2025-01-02"))

    assert factor == pytest.approx(0.7)
    assert len(observations) == 1
    assert observations[0].pair == "FX:USD/GBP"


def test_exchange_rates_carry_the_latest_observation_over_weekends() -> None:
    """The most recent non-future rate is carried over the weekend."""
    rates = _exchange_rates([_rate("USD/EUR", [0.9], ["2025-01-03"])])

    factor, observations = rates.resolve_rate("USD", "EUR", pd.Timestamp("2025-01-05"))

    assert factor == pytest.approx(0.9)
    assert observations[0].observation_date == pd.Timestamp("2025-01-03")
    assert observations[0].age_days == 2


def test_exchange_rates_accept_the_four_day_staleness_boundary() -> None:
    """A rate exactly four calendar days old is still valid by default."""
    rates = _exchange_rates([_rate("USD/EUR", [0.9], ["2025-01-03"])])

    factor, observations = rates.resolve_rate("USD", "EUR", pd.Timestamp("2025-01-07"))

    assert factor == pytest.approx(0.9)
    assert observations[0].age_days == 4


def test_exchange_rates_reject_rates_older_than_the_staleness_limit() -> None:
    """A rate five days old is stale under the default four-day policy."""
    rates = _exchange_rates([_rate("USD/EUR", [0.9], ["2025-01-03"])])

    on_date = pd.Timestamp("2025-01-08")
    with pytest.raises(ValueError, match="obsoleto"):
        rates.resolve_rate("USD", "EUR", on_date)


def test_exchange_rates_apply_staleness_limit_to_each_cross_leg() -> None:
    """A fresh first leg does not make an independently stale second leg usable."""
    rates = _exchange_rates(
        [
            _rate("EUR/USD", [1.2], ["2025-01-03"]),
            _rate("EUR/GBP", [0.8], ["2024-12-31"]),
        ]
    )

    on_date = pd.Timestamp("2025-01-05")
    with pytest.raises(ValueError, match="obsoleto"):
        rates.resolve_rate("USD", "GBP", on_date)


def test_exchange_rates_reject_future_only_observations() -> None:
    """A rate after an asset date is never used as look-ahead data."""
    rates = _exchange_rates([_rate("USD/EUR", [0.9], ["2025-01-03"])])

    on_date = pd.Timestamp("2025-01-02")
    with pytest.raises(ValueError, match="posterior"):
        rates.resolve_rate("USD", "EUR", on_date)


def test_exchange_rates_reject_missing_paths() -> None:
    """An absent direct, inverse or EUR-pivot route is rejected."""
    rates = _exchange_rates([])

    on_date = pd.Timestamp("2025-01-02")
    with pytest.raises(ValueError, match="No hay tipo de cambio"):
        rates.resolve_rate("USD", "EUR", on_date)


def test_exchange_rates_reject_duplicate_pairs_as_ambiguous() -> None:
    """Two supplied series for the same pair are ambiguous."""
    duplicate_rates = [
        _rate("USD/EUR", [0.9], ["2025-01-02"], source="Manual A"),
        _rate("USD/EUR", [0.9], ["2025-01-02"], source="Manual B"),
    ]
    with pytest.raises(ValueError, match="ambiguo"):
        _exchange_rates(duplicate_rates)


@pytest.mark.parametrize("max_age_days", [-1, True])
def test_exchange_rates_reject_invalid_age_limits(max_age_days: int) -> None:
    """The carry-forward policy must be a non-negative integer."""
    with pytest.raises(ValueError, match="max_age_days"):
        _exchange_rates([], max_age_days=max_age_days)


def test_exchange_rates_reject_mismatched_rate_quote_currency() -> None:
    """A rate series cannot contradict the quote currency in its pair identifier."""
    rate = PriceSeries(
        ticker="FX:USD/EUR",
        prices=pd.Series([0.9], index=pd.DatetimeIndex(["2025-01-02"])),
        quote_currency="USD",
    )

    with pytest.raises(ValueError, match="divisa cotizada"):
        _exchange_rates([rate])


@pytest.mark.parametrize("ticker", ["invalid", "FX:EUR/EUR"])
def test_exchange_rates_reject_malformed_or_identity_pairs(ticker: str) -> None:
    """Rate series need a valid non-identity ordered FX pair."""
    rate = PriceSeries(
        ticker=ticker,
        prices=pd.Series([1.0], index=pd.DatetimeIndex(["2025-01-02"])),
    )

    with pytest.raises(ValueError, match=r"par|formato"):
        _exchange_rates([rate])


def test_exchange_rates_reject_non_price_series_inputs() -> None:
    """The rate collection accepts only normalized PriceSeries objects."""
    invalid_rates = cast("list[PriceSeries]", [object()])
    with pytest.raises(TypeError, match="PriceSeries"):
        _exchange_rates(invalid_rates)


def test_exchange_rates_reject_mutated_invalid_rate_values() -> None:
    """A zero rate cannot be used even if a series is mutated after validation."""
    rate = _rate("USD/EUR", [0.9], ["2025-01-02"])
    rate.prices.iloc[0] = 0.0
    rates = _exchange_rates([rate])
    on_date = pd.Timestamp("2025-01-02")

    with pytest.raises(ValueError, match="positivo y finito"):
        rates.resolve_rate("USD", "EUR", on_date)


@pytest.mark.parametrize("invalid_rate", [0.0, float("inf"), float("nan")])
def test_exchange_rate_series_rejects_invalid_raw_observations(invalid_rate: float) -> None:
    """Invalid supplied observations cannot disappear during PriceSeries cleanup."""
    raw_prices = pd.Series(
        [0.9, invalid_rate],
        index=pd.DatetimeIndex(["2025-01-02", "2025-01-03"]),
    )

    with pytest.raises(ValueError, match=r"tipos de cambio.*positivos y finitos"):
        PriceSeries(
            ticker="FX:USD/EUR",
            prices=raw_prices,
            quote_currency="EUR",
        )


def test_exchange_rates_reject_a_missing_eur_cross_leg() -> None:
    """One available EUR-pivot leg cannot substitute for a missing second leg."""
    rates = _exchange_rates([_rate("EUR/USD", [1.2], ["2025-01-02"])])
    on_date = pd.Timestamp("2025-01-02")

    with pytest.raises(ValueError, match="No hay tipo de cambio"):
        rates.resolve_rate("USD", "GBP", on_date)


def test_exchange_rates_can_be_loaded_from_a_price_source() -> None:
    """Any provider implementing PriceSource can supply the rate collection."""
    rates = _exchange_rates([])
    loaded = type(rates).from_source(
        StubSource(TRADING_DATES),
        ["FX:EUR/USD"],
        "2025-01-02",
        "2025-01-08",
    )

    assert len(loaded.rates) == 1
    assert loaded.rates[0].source == "Stub"


def test_portfolio_golden_conversion_uses_reporting_prices_for_returns() -> None:
    """USD 100→110 and EUR-per-USD 0.90→0.95 yield EUR 90→104.50."""
    dates = pd.DatetimeIndex(["2025-01-02", "2025-01-03"])
    asset = PriceSeries(
        ticker="US_ASSET",
        prices=pd.Series([100.0, 110.0], index=dates),
        quote_currency="USD",
    )
    rates = _exchange_rates(
        [_rate("USD/EUR", [0.9, 0.95], [date.date().isoformat() for date in dates])]
    )
    portfolio = Portfolio(
        assets={asset.ticker: asset},
        weights={asset.ticker: 1.0},
        reporting_currency="EUR",
        exchange_rates=rates,
    )

    local_prices = portfolio.get_prices()
    reporting_prices = portfolio.get_reporting_prices()
    returns = portfolio.get_returns()

    assert list(local_prices[asset.ticker]) == [100.0, 110.0]
    assert list(reporting_prices[asset.ticker]) == [90.0, 104.5]
    assert returns.iloc[0, 0] == pytest.approx(104.5 / 90.0 - 1.0)
    assert portfolio.portfolio_returns().iloc[0] == pytest.approx(0.1611111111111111)


def test_portfolio_identity_conversion_needs_no_rates() -> None:
    """Assets already quoted in the reporting currency need no FX rates."""
    asset = PriceSeries(
        ticker="EU_ASSET",
        prices=pd.Series([10.0, 11.0], index=pd.DatetimeIndex(["2025-01-02", "2025-01-03"])),
        quote_currency="EUR",
    )
    portfolio = Portfolio(
        assets={asset.ticker: asset},
        weights={asset.ticker: 1.0},
        reporting_currency="EUR",
        exchange_rates=_exchange_rates([]),
    )

    pd.testing.assert_frame_equal(portfolio.get_reporting_prices(), portfolio.get_prices())
    diagnostics = portfolio.currency_conversion_diagnostics()
    assert diagnostics["pair"].tolist() == ["-", "-"]
    assert diagnostics["source"].tolist() == ["No requerida", "No requerida"]


def test_portfolio_rejects_a_missing_conversion_rate() -> None:
    """Currency-aware prices cannot be returned without an applicable FX path."""
    asset = PriceSeries(
        ticker="US_ASSET",
        prices=pd.Series([10.0, 11.0], index=pd.DatetimeIndex(["2025-01-02", "2025-01-03"])),
        quote_currency="USD",
    )
    portfolio = Portfolio(
        assets={asset.ticker: asset},
        weights={asset.ticker: 1.0},
        reporting_currency="EUR",
    )

    with pytest.raises(ValueError, match="No hay tipo de cambio"):
        portfolio.get_reporting_prices()


def test_portfolio_requires_reporting_currency_for_reporting_prices() -> None:
    """A legacy portfolio cannot request a converted view without a target currency."""
    asset = PriceSeries(
        ticker="UNKNOWN",
        prices=pd.Series([10.0, 11.0], index=pd.DatetimeIndex(["2025-01-02", "2025-01-03"])),
    )
    portfolio = Portfolio(assets={asset.ticker: asset}, weights={asset.ticker: 1.0})

    with pytest.raises(ValueError, match="divisa de reporte"):
        portfolio.get_reporting_prices()


def test_portfolio_requires_reporting_currency_when_rates_are_supplied() -> None:
    """Supplying FX data without a reporting currency is rejected instead of ignored."""
    asset = PriceSeries(
        ticker="UNKNOWN",
        prices=pd.Series([10.0, 11.0], index=pd.DatetimeIndex(["2025-01-02", "2025-01-03"])),
    )
    exchange_rates = _exchange_rates([_rate("USD/EUR", [0.9], ["2025-01-02"])])

    with pytest.raises(ValueError, match="indicar una divisa de reporte"):
        Portfolio(
            assets={asset.ticker: asset},
            weights={asset.ticker: 1.0},
            exchange_rates=exchange_rates,
        )


def test_portfolio_rejects_wrong_exchange_rates_collection_type() -> None:
    """Portfolio accepts the public ExchangeRates collection, not arbitrary objects."""
    asset = PriceSeries(
        ticker="UNKNOWN",
        prices=pd.Series([10.0, 11.0], index=pd.DatetimeIndex(["2025-01-02", "2025-01-03"])),
    )
    exchange_rates = cast("ExchangeRates", object())

    with pytest.raises(TypeError, match="ExchangeRates"):
        Portfolio(
            assets={asset.ticker: asset},
            weights={asset.ticker: 1.0},
            exchange_rates=exchange_rates,
        )


def test_portfolio_checks_quote_currency_before_conversion() -> None:
    """A mutated asset cannot enter a converted view without quote-currency metadata."""
    asset = PriceSeries(
        ticker="EU_ASSET",
        prices=pd.Series([10.0, 11.0], index=pd.DatetimeIndex(["2025-01-02", "2025-01-03"])),
        quote_currency="EUR",
    )
    portfolio = Portfolio(
        assets={asset.ticker: asset},
        weights={asset.ticker: 1.0},
        reporting_currency="EUR",
    )
    asset.quote_currency = None

    with pytest.raises(ValueError, match="no tiene divisa"):
        portfolio.get_reporting_prices()


def test_portfolio_rejects_missing_asset_currency_when_reporting_is_set() -> None:
    """Currency-aware portfolios require explicit quote currency on every asset."""
    asset = PriceSeries(
        ticker="UNKNOWN",
        prices=pd.Series([10.0, 11.0], index=pd.DatetimeIndex(["2025-01-02", "2025-01-03"])),
    )

    with pytest.raises(ValueError, match="divisa de cotización conocida"):
        Portfolio(
            assets={asset.ticker: asset},
            weights={asset.ticker: 1.0},
            reporting_currency="EUR",
        )


def test_portfolio_rejects_labeled_mixed_currencies_without_reporting_currency() -> None:
    """Labeled assets in different currencies cannot be combined silently."""
    dates = pd.DatetimeIndex(["2025-01-02", "2025-01-03"])
    assets = {
        "EU": PriceSeries("EU", pd.Series([10.0, 11.0], index=dates), quote_currency="EUR"),
        "US": PriceSeries("US", pd.Series([10.0, 11.0], index=dates), quote_currency="USD"),
    }

    with pytest.raises(ValueError, match="mezcla divisas"):
        Portfolio(assets=assets, weights={"EU": 0.5, "US": 0.5})


def test_portfolio_rejects_partial_currency_metadata_without_reporting_currency() -> None:
    """A labeled asset cannot be silently combined with a currency-unknown asset."""
    dates = pd.DatetimeIndex(["2025-01-02", "2025-01-03"])
    assets = {
        "EU": PriceSeries("EU", pd.Series([10.0, 11.0], index=dates), quote_currency="EUR"),
        "UNKNOWN": PriceSeries("UNKNOWN", pd.Series([10.0, 11.0], index=dates)),
    }

    with pytest.raises(ValueError, match="divisas conocidas y desconocidas"):
        Portfolio(assets=assets, weights={"EU": 0.5, "UNKNOWN": 0.5})


def test_portfolio_reporting_currency_is_normalized() -> None:
    """An explicit lowercase reporting code is normalized to its canonical form."""
    asset = PriceSeries(
        ticker="EU_ASSET",
        prices=pd.Series([10.0, 11.0], index=pd.DatetimeIndex(["2025-01-02", "2025-01-03"])),
        quote_currency="EUR",
    )
    portfolio = Portfolio(
        assets={asset.ticker: asset},
        weights={asset.ticker: 1.0},
        reporting_currency=" eur ",
    )

    assert portfolio.reporting_currency == "EUR"
