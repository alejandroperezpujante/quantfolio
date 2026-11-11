"""Markdown report content and analytical plot behavior."""

from __future__ import annotations

from typing import TYPE_CHECKING

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from quantfolio.currency import ExchangeRates
from quantfolio.models import PriceSeries
from quantfolio.portfolio import Portfolio
from quantfolio.reporting import plot_simulation_paths
from tests.support.builders import make_series

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(autouse=True)
def _close_figures(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Close every figure after each test to keep the suite headless."""
    monkeypatch.setattr(plt, "show", lambda: None)
    yield
    plt.close("all")


def _stable_portfolio(count: int = 35) -> Portfolio:
    """Return two co-moving assets on the same business-day calendar."""
    values = [100.0 + position for position in range(count)]
    return Portfolio(
        assets={
            "AAA": make_series("AAA", values),
            "BBB": make_series("BBB", [value * 2.0 for value in values]),
        },
        weights={"AAA": 0.5, "BBB": 0.5},
    )


def _volatile_concentrated_portfolio() -> Portfolio:
    """Return a short, concentrated sample with high volatility and a deep decline."""
    values = [100.0, 125.0, 70.0, 120.0, 60.0, 110.0, 55.0, 105.0, 50.0, 95.0, 45.0]
    return Portfolio(
        assets={
            "AAA": make_series("AAA", values),
            "BBB": make_series("BBB", list(reversed(values))),
            "CCC": make_series("CCC", [10.0] * len(values)),
        },
        weights={"AAA": 0.8, "BBB": 0.1, "CCC": 0.1},
    )


def _reporting_currency_portfolio() -> Portfolio:
    """Return a portfolio whose USD and GBP assets are converted into EUR."""
    dates = pd.DatetimeIndex(["2025-01-02", "2025-01-03", "2025-01-06", "2025-01-07"])
    assets = {
        "US_ASSET": PriceSeries(
            "US_ASSET",
            pd.Series([100.0, 101.0, 102.0, 103.0], index=dates),
            quote_currency="USD",
        ),
        "GB_ASSET": PriceSeries(
            "GB_ASSET",
            pd.Series([50.0, 51.0, 52.0, 53.0], index=dates),
            quote_currency="GBP",
        ),
        "EU_ASSET": PriceSeries(
            "EU_ASSET",
            pd.Series([10.0, 10.5, 11.0, 11.5], index=dates),
            quote_currency="EUR",
        ),
    }
    rates = ExchangeRates(
        [
            make_series(
                "FX:USD/EUR",
                [0.9, 0.91, 0.92, 0.93],
                dates=dates,
                source="Manual FX",
                quote_currency="EUR",
            ),
            make_series(
                "FX:GBP/EUR",
                [1.2, 1.21, 1.22, 1.23],
                dates=dates,
                source="ECB reference rates",
                quote_currency="EUR",
            ),
        ]
    )
    return Portfolio(
        assets=assets,
        weights=dict.fromkeys(assets, 1.0),
        reporting_currency="EUR",
        exchange_rates=rates,
    )


def test_report_presents_unique_required_sections_and_supplied_metrics() -> None:
    """A complete report has one composition, metrics and quality section."""
    report = _stable_portfolio().report(risk_free_rate=0.02, confidence=0.9)

    assert report.startswith("# Informe de la cartera")
    for heading in (
        "## 1. Composición",
        "## 2. Métricas históricas",
        "## 3. Calidad de los datos",
        "## 4. Advertencias de riesgo",
    ):
        assert report.count(heading) == 1
    assert "| Ratio de Sharpe (rf=2.00%) |" in report
    assert "VaR histórico diario (90%)" in report
    assert "CVaR histórico diario (90%)" in report
    assert "- Activos: 2" in report
    assert "**Cobertura por activo**" in report


@pytest.mark.parametrize(
    ("periods_per_year", "label"),
    [(365, "diario"), (52, "semanal"), (12, "mensual"), (4, "trimestral"), (1, "anual")],
)
def test_report_labels_tail_risk_with_the_configured_calendar(
    periods_per_year: int,
    label: str,
) -> None:
    """VaR and CVaR names follow the supplied return frequency."""
    report = _stable_portfolio().report(periods_per_year=periods_per_year)

    assert f"VaR histórico {label} (95%)" in report
    assert f"CVaR histórico {label} (95%)" in report


def test_report_omits_optional_sections_and_keeps_the_currency_section_numbered() -> None:
    """Disabling optional diagnostics still produces a coherent numbered document."""
    report = _reporting_currency_portfolio().report(
        include_quality=False,
        include_warnings=False,
    )

    assert "## 1. Composición" in report
    assert "## 2. Métricas históricas" in report
    assert "## 3. Conversión de divisas" in report
    assert "Calidad de los datos" not in report
    assert "Advertencias de riesgo" not in report


def test_report_discloses_conversion_provenance_identity_rows_and_intraday_limits() -> None:
    """Converted assets name their rate source while same-currency assets are explicit."""
    report = _reporting_currency_portfolio().report(include_quality=False)
    usd_row = next(line for line in report.splitlines() if "FX:USD/EUR" in line)
    gbp_row = next(line for line in report.splitlines() if "FX:GBP/EUR" in line)
    identity_row = next(line for line in report.splitlines() if "No requerida" in line)

    assert "- Divisa de reporte: EUR." in report
    assert "| US_ASSET | FX:USD/EUR | Manual FX |" in usd_row
    assert "| GB_ASSET | FX:GBP/EUR | ECB reference rates |" in gbp_row
    assert identity_row == "| EU_ASSET | - | No requerida | 2025-01-02 | 2025-01-07 | 4 | 0 |"
    assert "no son precios de ejecución" in report
    assert "corte intradía" in report


def test_report_marks_unassessed_currency_and_an_original_minor_unit() -> None:
    """A missing reporting currency is disclosed and GBX remains visible beside GBP."""
    asset = PriceSeries(
        "VOD.L",
        pd.Series(
            [120.0, 125.0, 130.0],
            index=pd.DatetimeIndex(["2025-01-02", "2025-01-03", "2025-01-06"]),
        ),
        quote_unit="GBX",
    )
    unknown = make_series("UNKNOWN", [10.0, 11.0, 12.0])
    unit_report = Portfolio(assets={"VOD.L": asset}, weights={"VOD.L": 1.0}).report(
        include_quality=False, include_warnings=False
    )
    unknown_report = Portfolio(assets={"UNKNOWN": unknown}, weights={"UNKNOWN": 1.0}).report(
        include_quality=False, include_warnings=False
    )

    assert "| VOD.L | GBP (GBX) | 100.00% |" in unit_report
    assert "| UNKNOWN | desconocida | 100.00% |" in unknown_report
    assert "La conversión de divisas no se ha evaluado" in " ".join(unknown_report.split())


def test_report_warns_about_calendar_gaps_concentration_risk_and_short_history() -> None:
    """Risk warnings reflect every observable portfolio weakness in the report."""
    report = _volatile_concentrated_portfolio().report()

    assert "más de un día natural" in report
    assert "AAA concentra el 80.0%" in report
    assert "volatilidad anualizada" in report
    assert "máxima caída histórica" in report
    assert "solo hay 10 observaciones de rentabilidad" in report


def test_report_warns_when_alignment_discards_dates() -> None:
    """A mixed-start portfolio explains the cost of the common-calendar intersection."""
    prices = [10.0 + position for position in range(11)]
    portfolio = Portfolio(
        assets={
            "AAA": make_series("AAA", prices),
            "BBB": make_series("BBB", prices[:6], start=5),
        },
        weights={"AAA": 0.5, "BBB": 0.5},
    )

    report = portfolio.report(include_quality=False)

    assert "La alineación temporal descarta el 45.5%" in report


def test_report_flags_a_single_asset_as_undiversified() -> None:
    """A one-asset portfolio warns about its total concentration."""
    report = Portfolio(
        assets={"AAA": make_series("AAA", [10.0 + position for position in range(35)])},
        weights={"AAA": 1.0},
    ).report()

    assert "no hay diversificación" in report


def test_report_explains_unrepresentable_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    """Extreme values degrade the metrics section instead of aborting the report."""

    def overflow(_self: Portfolio, **_: object) -> dict[str, float]:
        raise OverflowError

    monkeypatch.setattr(Portfolio, "summary", overflow)
    report = _stable_portfolio().report()

    assert "Las métricas no se pueden representar: rentabilidad extrema." in report
    assert "## 2. Métricas históricas" in report
    assert "## 3. Calidad de los datos" in report


def test_currency_free_portfolios_expose_empty_diagnostic_frames() -> None:
    """A currency-free portfolio returns stable empty traces in both diagnostics views."""
    portfolio = _stable_portfolio()

    union = portfolio.currency_conversion_diagnostics()
    analysis = portfolio.analysis_currency_conversion_diagnostics()

    for diagnostics in (union, analysis):
        assert diagnostics.empty
        assert "leg_index" in diagnostics.columns
        assert diagnostics.columns[0] == "asset"


def test_dashboard_rebases_local_prices_and_labels_every_panel() -> None:
    """A currency-free dashboard uses base 100 and names the analytical panels."""
    _stable_portfolio().plots_report()
    titles = {axis.get_title() for axis in plt.gcf().axes}

    assert "Evolución de precios (base 100)" in titles
    assert "Rentabilidad acumulada por activo" in titles
    assert "Correlación entre activos" in titles
    assert "Evolución del valor de la cartera (base 100)" in titles


def test_dashboard_uses_reporting_currency_prices_and_common_dates() -> None:
    """Converted prices drive the dashboard and staggered assets share a rebased origin."""
    _reporting_currency_portfolio().plots_report()
    price_axis = next(
        axis
        for axis in plt.gcf().axes
        if axis.get_title() == "Evolución de precios en EUR (base 100)"
    )
    starts = [float(np.asarray(line.get_ydata(), dtype=float)[0]) for line in price_axis.lines]

    assert starts == pytest.approx([100.0, 100.0, 100.0])
    for line in price_axis.lines:
        assert not np.isnan(np.asarray(line.get_ydata(), dtype=float)).any()


@pytest.mark.parametrize(
    ("final_label", "value_label", "expected_title"),
    [
        ("valor final", "Valor de la cartera", "Distribución del valor final"),
        ("precio final", "Precio", "Distribución del precio final"),
    ],
)
def test_simulation_plot_names_the_quantity_for_portfolios_and_prices(
    final_label: str,
    value_label: str,
    expected_title: str,
) -> None:
    """The chart vocabulary changes with the simulated public object."""
    simulations = pd.DataFrame(np.linspace(100.0, 120.0, 30).reshape(6, 5))

    plot_simulation_paths(
        simulations,
        max_paths=2,
        value_label=value_label,
        final_label=final_label,
    )

    assert plt.gcf().axes[0].get_ylabel() == value_label
    assert plt.gcf().axes[1].get_title() == expected_title


@pytest.mark.parametrize(
    ("simulations", "max_paths", "message"),
    [(pd.DataFrame(), 1, "simulaciones"), (pd.DataFrame(np.ones((3, 2))), 0, "max_paths")],
)
def test_simulation_plot_rejects_unrepresentable_inputs(
    simulations: pd.DataFrame,
    max_paths: int,
    message: str,
) -> None:
    """Empty matrices and non-positive path selections raise ``ValueError``."""
    with pytest.raises(ValueError, match=message):
        plot_simulation_paths(simulations, max_paths=max_paths)
