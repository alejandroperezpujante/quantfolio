"""Historical exchange-rate selection and currency-aware portfolio conversion."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pandas as pd
import pytest

from quantfolio.currency import ExchangeRateObservation, ExchangeRates
from quantfolio.models import PriceSeries
from quantfolio.portfolio import Portfolio
from tests.support.builders import make_series
from tests.support.sources import table_source

if TYPE_CHECKING:
    from quantfolio.sources import DateLike


def _rate(
    pair: str,
    values: list[float],
    dates: list[str],
    *,
    source: str = "Manual rates",
) -> PriceSeries:
    """Build a validated rate series whose quote metadata matches its pair."""
    return make_series(
        f"FX:{pair}",
        values,
        dates=dates,
        source=source,
        quote_currency=pair[-3:],
    )


def _rates(*series: PriceSeries, max_age_days: int = 4) -> ExchangeRates:
    """Build an ExchangeRates collection from public series."""
    return ExchangeRates(series, max_age_days=max_age_days)


def _conversion_portfolio(
    *,
    max_age_days: int = 4,
    rate_count: int = 4,
) -> tuple[Portfolio, pd.DatetimeIndex]:
    """Return EUR/USD assets whose only shared dates begin on the third USD date."""
    usd_dates = pd.DatetimeIndex(
        ["2025-01-02", "2025-01-03", "2025-01-06", "2025-01-07", "2025-01-08", "2025-01-09"]
    )
    common_dates = usd_dates[2:]
    usd = PriceSeries(
        "US",
        pd.Series([80.0, 90.0, 100.0, 110.0, 100.0, 120.0], index=usd_dates),
        quote_currency="USD",
    )
    eur = PriceSeries(
        "EU",
        pd.Series([100.0, 101.0, 99.0, 104.0], index=common_dates),
        quote_currency="EUR",
    )
    rate = _rate(
        "USD/EUR",
        [0.9, 0.95, 0.92, 0.91][:rate_count],
        [date.date().isoformat() for date in common_dates[:rate_count]],
    )
    return (
        Portfolio(
            assets={"US": usd, "EU": eur},
            weights={"US": 0.5, "EU": 0.5},
            reporting_currency="EUR",
            exchange_rates=_rates(rate, max_age_days=max_age_days),
        ),
        common_dates,
    )


def test_identity_conversion_needs_no_rate_and_reports_it_as_not_required() -> None:
    """A currency converts to itself with no observations or diagnostics lookup."""
    rates = _rates()
    factor, observations = rates.resolve_rate(" eur ", "EUR", "2025-01-02")
    eur = PriceSeries(
        "EU",
        pd.Series([100.0, 110.0], index=pd.DatetimeIndex(["2025-01-02", "2025-01-03"])),
        quote_currency="EUR",
    )
    portfolio = Portfolio(
        assets={"EU": eur},
        weights={"EU": 1.0},
        reporting_currency="EUR",
        exchange_rates=rates,
    )

    assert factor == 1.0
    assert observations == ()
    pd.testing.assert_frame_equal(portfolio.get_prices(), portfolio.get_reporting_prices())
    diagnostics = portfolio.currency_conversion_diagnostics()
    assert diagnostics["pair"].tolist() == ["-", "-"]
    assert diagnostics["source"].tolist() == ["No requerida", "No requerida"]


def test_direct_rate_wins_when_both_orientations_are_available() -> None:
    """A direct observation is preferred while preserving its provenance."""
    rates = _rates(
        _rate("USD/EUR", [0.9], ["2025-01-02"]),
        _rate("EUR/USD", [2.0], ["2025-01-02"]),
    )

    factor, observations = rates.resolve_rate("USD", "EUR", pd.Timestamp("2025-01-02"))

    assert factor == pytest.approx(0.9)
    assert observations[0].pair == "FX:USD/EUR"
    assert observations[0].inverted is False


@pytest.mark.parametrize("direct_date", ["2025-01-01", "2025-01-08"])
def test_inverse_rate_can_cover_a_stale_or_future_direct_observation(direct_date: str) -> None:
    """Each orientation is evaluated independently before falling back."""
    rates = _rates(
        _rate("USD/EUR", [0.9], [direct_date]),
        _rate("EUR/USD", [1.25], ["2025-01-06"]),
    )

    factor, observations = rates.resolve_rate("USD", "EUR", "2025-01-06")

    assert factor == pytest.approx(0.8)
    assert observations[0].pair == "FX:EUR/USD"
    assert observations[0].inverted is True


def test_both_stale_orientations_retain_the_preferred_public_error() -> None:
    """When direct and inverse observations are both stale, the direct error is reported."""
    rates = _rates(
        _rate("USD/EUR", [0.9], ["2025-01-01"]),
        _rate("EUR/USD", [1.1], ["2025-01-01"]),
    )

    with pytest.raises(ValueError, match="USD/EUR está obsoleto"):
        rates.resolve_rate("USD", "EUR", "2025-01-10")


def test_eur_pivot_builds_cross_rates_and_direct_pairs_still_win() -> None:
    """Non-EUR conversions use two independently selected EUR legs unless direct data exists."""
    cross = _rates(
        _rate("EUR/USD", [1.2], ["2025-01-02"]),
        _rate("EUR/GBP", [0.8], ["2025-01-02"]),
    )
    factor, observations = cross.resolve_rate("USD", "GBP", "2025-01-02")
    assert factor == pytest.approx(2 / 3)
    assert [row.pair for row in observations] == ["FX:EUR/USD", "FX:EUR/GBP"]

    direct = _rates(
        _rate("USD/GBP", [0.7], ["2025-01-02"]),
        _rate("EUR/USD", [1.2], ["2025-01-02"]),
        _rate("EUR/GBP", [0.8], ["2025-01-02"]),
    )
    factor, observations = direct.resolve_rate("USD", "GBP", "2025-01-02")
    assert factor == pytest.approx(0.7)
    assert len(observations) == 1


@pytest.mark.parametrize(
    ("rates", "message"),
    [
        (
            _rates(
                _rate("USD/GBP", [0.7], ["2025-01-01"]),
                _rate("EUR/USD", [1.25], ["2025-01-01"]),
            ),
            "USD/GBP está obsoleto",
        ),
        (_rates(_rate("EUR/USD", [1.2], ["2025-01-02"])), "No hay tipo de cambio"),
        (_rates(), "No hay tipo de cambio"),
    ],
)
def test_unavailable_routes_surface_the_most_specific_public_error(
    rates: ExchangeRates,
    message: str,
) -> None:
    """Preferred staleness is retained; incomplete crosses and absent paths are explicit."""
    with pytest.raises(ValueError, match=message):
        rates.resolve_rate("USD", "GBP", "2025-01-06")


def test_latest_non_future_rate_carries_across_weekends_and_the_age_boundary() -> None:
    """Friday rates serve weekend and four-day-old observations, but not five days."""
    rates = _rates(_rate("USD/EUR", [0.9], ["2025-01-03"]))

    weekend, weekend_rows = rates.resolve_rate("USD", "EUR", "2025-01-05")
    boundary, boundary_rows = rates.resolve_rate("USD", "EUR", "2025-01-07")
    assert weekend == boundary == pytest.approx(0.9)
    assert weekend_rows[0].age_days == 2
    assert boundary_rows[0].age_days == 4

    with pytest.raises(ValueError, match=r"obsoleto.*5 días.*4"):
        rates.resolve_rate("USD", "EUR", "2025-01-08")


def test_each_eur_cross_leg_has_its_own_staleness_limit() -> None:
    """A fresh first leg cannot mask a stale second leg."""
    rates = _rates(
        _rate("EUR/USD", [1.2], ["2025-01-03"]),
        _rate("EUR/GBP", [0.8], ["2024-12-31"]),
    )
    with pytest.raises(ValueError, match="obsoleto"):
        rates.resolve_rate("USD", "GBP", "2025-01-05")


def test_future_rates_are_never_used_as_look_ahead_observations() -> None:
    """A value dated after the asset observation is unavailable."""
    rates = _rates(_rate("USD/EUR", [0.9], ["2025-01-03"]))
    with pytest.raises(ValueError, match=r"No hay observaciones.*en o antes"):
        rates.resolve_rate("USD", "EUR", "2025-01-02")


@pytest.mark.parametrize("invalid_date", [None, pd.NaT])
def test_conversion_rejects_missing_dates(invalid_date: object) -> None:
    """Null observation dates fail before pair selection."""
    rates = _rates(_rate("USD/EUR", [0.9], ["2025-01-02"]))
    missing_date = cast("DateLike", invalid_date)
    with pytest.raises(ValueError, match="fecha de conversión"):
        rates.resolve_rate("USD", "EUR", missing_date)


@pytest.mark.parametrize("max_age_days", [-1, True])
def test_exchange_rates_require_a_non_negative_integer_age(max_age_days: int) -> None:
    """The carry-forward policy cannot be negative or a boolean."""
    with pytest.raises(ValueError, match="max_age_days"):
        _rates(max_age_days=max_age_days)


def test_exchange_rates_reject_ambiguous_mismatched_or_invalid_pair_series() -> None:
    """Every supplied series must identify one coherent, unique FX pair."""
    duplicate = [
        _rate("USD/EUR", [0.9], ["2025-01-02"], source="A"),
        _rate("USD/EUR", [0.9], ["2025-01-02"], source="B"),
    ]
    with pytest.raises(ValueError, match="ambiguo"):
        _rates(*duplicate)

    mismatched = make_series(
        "FX:USD/EUR",
        [0.9],
        dates=["2025-01-02"],
        quote_currency="USD",
    )
    with pytest.raises(ValueError, match="divisa cotizada"):
        _rates(mismatched)

    for ticker in ("invalid", "FX:EUR/EUR"):
        invalid = make_series(ticker, [1.0], dates=["2025-01-02"])
        with pytest.raises(ValueError, match=r"par|formato"):
            _rates(invalid)

    invalid_rates = cast("tuple[PriceSeries, ...]", (object(),))
    with pytest.raises(TypeError, match="PriceSeries"):
        ExchangeRates(invalid_rates)


def test_exchange_rates_reject_rates_mutated_to_non_positive_or_non_finite_values() -> None:
    """A series changed after PriceSeries validation cannot enable an invalid conversion."""
    rate = _rate("USD/EUR", [0.9], ["2025-01-02"])
    rate.prices.iloc[0] = 0.0
    rates = _rates(rate)
    with pytest.raises(ValueError, match="positivo y finito"):
        rates.resolve_rate("USD", "EUR", "2025-01-02")


def test_exchange_rates_load_through_the_price_source_contract() -> None:
    """ExchangeRates.from_source delegates batch requests to any public provider."""
    values = make_series("FX:EUR/USD", [1.1, 1.2], dates=["2025-01-02", "2025-01-03"])
    source = table_source("Scripted FX", {"FX:EUR/USD": values})

    loaded = ExchangeRates.from_source(
        source,
        ["FX:EUR/USD"],
        "2025-01-02",
        "2025-01-04",
    )

    assert len(loaded.rates) == 1
    assert loaded.rates[0].source == "Stub"


def test_portfolio_returns_use_reporting_currency_prices() -> None:
    """A USD asset is converted before its return and portfolio contribution are measured."""
    dates = pd.DatetimeIndex(["2025-01-02", "2025-01-03"])
    asset = PriceSeries(
        "US",
        pd.Series([100.0, 110.0], index=dates),
        quote_currency="USD",
    )
    rate = _rate("USD/EUR", [0.9, 0.95], ["2025-01-02", "2025-01-03"])
    portfolio = Portfolio(
        assets={"US": asset},
        weights={"US": 1.0},
        reporting_currency="EUR",
        exchange_rates=_rates(rate),
    )

    assert list(portfolio.get_prices()["US"]) == [100.0, 110.0]
    assert list(portfolio.get_reporting_prices()["US"]) == [90.0, 104.5]
    assert portfolio.get_returns().iloc[0, 0] == pytest.approx(104.5 / 90.0 - 1.0)
    assert portfolio.portfolio_returns().iloc[0] == pytest.approx(104.5 / 90.0 - 1.0)


def test_portfolio_analytics_convert_only_common_dates_while_full_view_requires_all() -> None:
    """Common-date analytics ignore excluded dates, but the full reporting view does not."""
    portfolio, common_dates = _conversion_portfolio()

    returns = portfolio.get_returns()
    assert list(returns.index) == list(common_dates[1:])
    alignment = portfolio.alignment_summary()
    assert alignment["union_dates"] == 6
    assert alignment["common_dates"] == 4
    with pytest.raises(ValueError, match="2025-01-02"):
        portfolio.get_reporting_prices()


@pytest.mark.parametrize(("last_date", "valid"), [("2025-01-10", True), ("2025-01-11", False)])
def test_portfolio_uses_the_four_day_rate_carry_limit(last_date: str, *, valid: bool) -> None:
    """Portfolio analytics share the collection's exact carry-forward boundary."""
    dates = pd.DatetimeIndex(["2025-01-06", "2025-01-07", last_date])
    asset = PriceSeries("US", pd.Series([100.0, 110.0, 120.0], index=dates), quote_currency="USD")
    portfolio = Portfolio(
        assets={"US": asset},
        weights={"US": 1.0},
        reporting_currency="EUR",
        exchange_rates=_rates(_rate("USD/EUR", [0.9], ["2025-01-06"])),
    )

    if valid:
        assert len(portfolio.get_returns()) == 2
    else:
        with pytest.raises(ValueError, match="obsoleto"):
            portfolio.get_returns()


def test_missing_rate_on_a_shared_asset_date_fails_before_later_dates() -> None:
    """Conversion reports the shared-date staleness rather than an excluded early date."""
    portfolio, _ = _conversion_portfolio(max_age_days=0, rate_count=3)
    with pytest.raises(ValueError, match="obsoleto") as captured:
        portfolio.get_returns()
    assert "2025-01-02" not in str(captured.value)


def test_portfolio_requires_a_reporting_target_for_conversion() -> None:
    """Legacy portfolios and supplied-rate portfolios cannot silently convert."""
    asset = PriceSeries(
        "UNKNOWN",
        pd.Series([10.0, 11.0], index=pd.DatetimeIndex(["2025-01-02", "2025-01-03"])),
    )
    portfolio = Portfolio(assets={"UNKNOWN": asset}, weights={"UNKNOWN": 1.0})
    with pytest.raises(ValueError, match="divisa de reporte"):
        portfolio.get_reporting_prices()

    exchange_rates = _rates(_rate("USD/EUR", [0.9], ["2025-01-02"]))
    with pytest.raises(ValueError, match="indicar una divisa de reporte"):
        Portfolio(
            assets={"UNKNOWN": asset},
            weights={"UNKNOWN": 1.0},
            exchange_rates=exchange_rates,
        )


def test_portfolio_validates_rate_collection_and_asset_currency_metadata() -> None:
    """Wrong collection types and missing asset currencies fail before conversion."""
    asset = PriceSeries(
        "UNKNOWN",
        pd.Series([10.0, 11.0], index=pd.DatetimeIndex(["2025-01-02", "2025-01-03"])),
    )
    invalid_rates = cast("ExchangeRates", object())
    with pytest.raises(TypeError, match="ExchangeRates"):
        Portfolio(
            assets={"UNKNOWN": asset},
            weights={"UNKNOWN": 1.0},
            exchange_rates=invalid_rates,
        )
    with pytest.raises(ValueError, match="divisa de cotización conocida"):
        Portfolio(
            assets={"UNKNOWN": asset},
            weights={"UNKNOWN": 1.0},
            reporting_currency="EUR",
        )


def test_mutated_asset_without_currency_is_rejected_by_the_converted_view() -> None:
    """A previously valid asset cannot lose its currency and enter conversion."""
    asset = PriceSeries(
        "EU",
        pd.Series([10.0, 11.0], index=pd.DatetimeIndex(["2025-01-02", "2025-01-03"])),
        quote_currency="EUR",
    )
    portfolio = Portfolio(assets={"EU": asset}, weights={"EU": 1.0}, reporting_currency="EUR")
    asset.quote_currency = None

    with pytest.raises(ValueError, match="no tiene divisa"):
        portfolio.get_reporting_prices()


def test_portfolio_rejects_mixed_or_partial_currency_metadata_without_a_target() -> None:
    """Different known currencies and known/unknown mixes cannot be combined silently."""
    dates = pd.DatetimeIndex(["2025-01-02", "2025-01-03"])
    eur = PriceSeries("EU", pd.Series([10.0, 11.0], index=dates), quote_currency="EUR")
    usd = PriceSeries("US", pd.Series([10.0, 11.0], index=dates), quote_currency="USD")
    unknown = PriceSeries("UNKNOWN", pd.Series([10.0, 11.0], index=dates))

    with pytest.raises(ValueError, match="mezcla divisas"):
        Portfolio(assets={"EU": eur, "US": usd}, weights={"EU": 0.5, "US": 0.5})
    with pytest.raises(ValueError, match="conocidas y desconocidas"):
        Portfolio(assets={"EU": eur, "UNKNOWN": unknown}, weights={"EU": 0.5, "UNKNOWN": 0.5})


def test_reporting_currency_and_asset_metadata_are_normalized_on_the_portfolio() -> None:
    """The public portfolio stores canonical reporting metadata without changing local prices."""
    asset = make_series(
        "EU", [10.0, 11.0], dates=["2025-01-02", "2025-01-03"], quote_currency="eur"
    )
    portfolio = Portfolio(
        assets={"EU": asset},
        weights={"EU": 1.0},
        reporting_currency=" eur ",
    )

    assert portfolio.reporting_currency == "EUR"
    assert portfolio.assets["EU"].quote_currency == "EUR"


def test_exchange_rate_observation_exposes_traceable_rate_metadata() -> None:
    """Selected rates retain pair, source, calendar age, inversion and applied factor."""
    rates = _rates(_rate("EUR/USD", [1.25], ["2025-01-03"], source="ECB"))
    factor, observations = rates.resolve_rate("USD", "EUR", "2025-01-05")
    observation = observations[0]

    assert factor == pytest.approx(0.8)
    assert observation == ExchangeRateObservation(
        pair="FX:EUR/USD",
        source="ECB",
        from_currency="USD",
        to_currency="EUR",
        observation_date=pd.Timestamp("2025-01-03"),
        age_days=2,
        rate=1.25,
        applied_rate=0.8,
        inverted=True,
    )
