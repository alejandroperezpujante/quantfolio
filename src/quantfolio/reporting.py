"""Markdown reports and analytical plots for portfolios and simulations."""

import math
from typing import TYPE_CHECKING, cast

import matplotlib.pyplot as plt

from quantfolio.constants import (
    ALIGNMENT_COVERAGE_WARNING_THRESHOLD,
    CONCENTRATION_WARNING_THRESHOLD,
    DRAWDOWN_WARNING_THRESHOLD,
    HIGH_VOLATILITY_WARNING_THRESHOLD,
    MIN_OBSERVATIONS,
    MULTI_DAY_RETURNS_WARNING_THRESHOLD,
    PERFORMANCE_BASE,
    SHORT_HISTORY_WARNING_THRESHOLD,
    TRADING_DAYS_PER_YEAR,
)
from quantfolio.risk import (
    compound_annual_growth,
    drift_standard_error,
    historical_cvar,
    historical_var,
    sharpe_ratio,
)
from quantfolio.risk import (
    max_drawdown as max_drawdown_of_returns,
)
from quantfolio.simulation import annualized_log_assumptions
from quantfolio.validation import (
    validate_confidence,
    validate_periods_per_year,
    validate_risk_free_rate,
)

if TYPE_CHECKING:
    import pandas as pd

    from quantfolio.macro import MacroSeries
    from quantfolio.models import PriceSeries
    from quantfolio.portfolio import Portfolio

#: Human-readable name of the return period implied by periods_per_year.
_PERIOD_LABELS: dict[int, str] = {
    252: "diario",
    365: "diario",
    52: "semanal",
    12: "mensual",
    4: "trimestral",
    1: "anual",
}


def _period_label(periods_per_year: int) -> str:
    """Return the human-readable name of a return period.

    Args:
        periods_per_year: Number of return periods in a year.

    Returns:
        Name of the period, or "por periodo" when the factor has no common name.

    """
    return _PERIOD_LABELS.get(periods_per_year, "por periodo")


def _quote_currency_label(asset: PriceSeries) -> str:
    """Return the known currency and original quote unit for a report row."""
    currency = asset.quote_currency or "desconocida"
    if asset.quote_unit is not None and asset.quote_unit != asset.quote_currency:
        return f"{currency} ({asset.quote_unit})"
    return currency


def render_portfolio_report(
    portfolio: Portfolio,
    *,
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
    include_quality: bool = True,
    include_warnings: bool = True,
    risk_free_rate: float = 0.0,
    confidence: float = 0.95,
    inflation_index: MacroSeries | None = None,
) -> str:
    """Render a portfolio report as structured Markdown.

    When the aligned sample is too short to estimate the metrics, or their computation
    overflows, the metrics section is replaced by an explanatory note and the risk warnings
    skip the volatility and drawdown checks. A one-return sample is reported this way;
    assets with disjoint calendars still raise from ``portfolio_returns()``.

    Args:
        portfolio: Portfolio to report on.
        periods_per_year: Number of trading periods per year used to annualize the mean return,
            the volatility and the Sharpe ratio; the VaR and the CVaR are expressed per return
            period and their label follows this factor (252 or 365 read "diario", 52 "semanal",
            12 "mensual", 4 "trimestral", 1 "anual", anything else "por periodo"). It must match
            the sampling frequency of the price data.
        include_quality: Whether to include the data-quality diagnostics section.
        include_warnings: Whether to include the risk-warnings section.
        risk_free_rate: Annual risk-free rate used by the Sharpe ratio.
        confidence: Confidence level of the value-at-risk measures.
        inflation_index: Optional monthly price-index levels supplied by the caller.

    Returns:
        Markdown text with composition, metrics, diagnostics and risk warnings.

    Raises:
        ValueError: If ``periods_per_year`` is not positive, ``confidence`` is not strictly
            between zero and one, or ``risk_free_rate`` is not finite.

    """
    validate_periods_per_year(periods_per_year)
    validate_confidence(confidence)
    validate_risk_free_rate(risk_free_rate)
    returns = portfolio.portfolio_returns()
    quality = portfolio.alignment_summary()
    metrics: dict[str, float] | None = None
    max_drawdown: float | None = None
    metrics_note = "No hay suficientes observaciones para calcular métricas históricas."
    metrics_lines: list[str] | None = None
    try:
        metrics = portfolio.summary(periods_per_year=periods_per_year)
        max_drawdown = max_drawdown_of_returns(returns)
        metrics_lines = _render_metrics_section(
            metrics=metrics,
            returns=returns,
            periods_per_year=periods_per_year,
            risk_free_rate=risk_free_rate,
            confidence=confidence,
            max_drawdown=max_drawdown,
        )
    except ValueError:
        metrics = None
        max_drawdown = None
    except OverflowError:
        metrics = None
        max_drawdown = None
        metrics_note = "Las métricas no se pueden representar: rentabilidad extrema."
    if metrics_lines is None:
        metrics_lines = ["", "## 2. Métricas históricas", "", metrics_note]

    lines = [
        "# Informe de la cartera",
        "",
        "## 1. Composición",
        "",
        "| Activo | Divisa local | Peso |",
        "|---|---|---:|",
    ]
    lines.extend(
        f"| {ticker} | {_quote_currency_label(portfolio.assets[ticker])} | {weight:.2%} |"
        for ticker, weight in portfolio.weights.items()
    )
    if portfolio.reporting_currency is None:
        currency_note = (
            "_La conversión de divisas no se ha evaluado; el análisis conserva la divisa local._"
        )
        lines.extend(
            [
                "",
                currency_note,
            ]
        )
    else:
        lines.extend(["", f"- Divisa de reporte: {portfolio.reporting_currency}."])
    lines.extend(metrics_lines)

    section = 3
    if inflation_index is not None:
        lines.extend(_render_inflation_section(portfolio, inflation_index, section=section))
        section += 1
    if include_quality:
        lines.extend(
            _render_quality_section(
                portfolio,
                quality=quality,
                returns=returns,
                periods_per_year=periods_per_year,
                section=section,
            )
        )
        section += 1

    if portfolio.reporting_currency is not None:
        lines.extend(_render_currency_conversion_section(portfolio, section=section))
        section += 1

    if include_warnings:
        lines.extend(["", f"## {section}. Advertencias de riesgo", ""])
        lines.extend(
            f"- {warning}"
            for warning in _collect_risk_warnings(
                portfolio,
                quality,
                returns,
                metrics,
                max_drawdown,
            )
        )

    return "\n".join(lines)


def _render_inflation_section(
    portfolio: Portfolio,
    inflation_index: MacroSeries,
    *,
    section: int,
) -> list[str]:
    """Compare nominal and CPI-deflated metrics over identical monthly observations."""
    matched = portfolio.monthly_inflation_comparison(inflation_index)
    vintage = (
        f"{inflation_index.vintage_date:%Y-%m-%d}"
        if inflation_index.vintage_date is not None
        else "no especificado"
    )
    lines = [
        "",
        f"## {section}. Poder adquisitivo e inflación",
        "",
        f"- Índice de precios: {inflation_index.series_id} ({inflation_index.source}).",
        f"- Vintage: {vintage}.",
        (
            f"- Meses comparados: {matched.index.min():%Y-%m-%d} → "
            f"{matched.index.max():%Y-%m-%d} ({len(matched)} observaciones)."
        ),
        "- La comparación es retrospectiva; el IPC publicado puede retrasarse y revisarse.",
        "- Los meses sin cierres de cartera completos se excluyen de la comparación.",
        "",
        "| Métrica | Nominal | Real (poder adquisitivo) |",
        "|---|---:|---:|",
    ]
    nominal = matched["nominal"]
    real = matched["real"]
    nominal_growth = cast("float", (1.0 + nominal).prod()) - 1.0
    real_growth = cast("float", (1.0 + real).prod()) - 1.0
    lines.append(f"| Rentabilidad acumulada | {nominal_growth:.2%} | {real_growth:.2%} |")
    if len(matched) < MIN_OBSERVATIONS:
        lines.extend(
            f"| {label} | No disponible | No disponible |"
            for label in ("CAGR", "Volatilidad anualizada mensual", "Máxima caída")
        )
        return lines
    lines.extend(
        [
            (
                f"| CAGR | {compound_annual_growth(nominal, periods_per_year=12):.2%} | "
                f"{compound_annual_growth(real, periods_per_year=12):.2%} |"
            ),
            (
                f"| Volatilidad anualizada mensual | "
                f"{nominal.std(ddof=1) * math.sqrt(12):.2%} | "
                f"{real.std(ddof=1) * math.sqrt(12):.2%} |"
            ),
            (
                f"| Máxima caída | {max_drawdown_of_returns(nominal):.2%} | "
                f"{max_drawdown_of_returns(real):.2%} |"
            ),
        ]
    )
    return lines


def _render_currency_conversion_section(portfolio: Portfolio, *, section: int) -> list[str]:
    """Render rate provenance, observation dates and carried observations."""
    diagnostics = portfolio.analysis_currency_conversion_diagnostics()
    lines = [
        "",
        f"## {section}. Conversión de divisas",
        "",
        (
            "| Activo | Par | Fuente | Primera observación | Última observación | "
            "Observaciones | Arrastres |"
        ),
        "|---|---|---|---|---|---:|---:|",
    ]
    for ticker in portfolio.assets:
        asset_rows = diagnostics[diagnostics["asset"] == ticker]
        groups = asset_rows.groupby(["pair", "source"], sort=False)
        for (pair, source), rows in groups:
            first_observation = rows["rate_date"].min()
            last_observation = rows["rate_date"].max()
            observation_count = int(rows["rate_date"].nunique())
            carry_forwards = int(rows["carried_forward"].sum())
            lines.append(
                f"| {ticker} | {pair} | {source} | {first_observation:%Y-%m-%d} | "
                f"{last_observation:%Y-%m-%d} | {observation_count} | {carry_forwards} |"
            )
    lines.extend(
        [
            "",
            (
                "_Los tipos de referencia, como los publicados por el BCE, son informativos; "
                "no son precios de ejecución de un bróker._"
            ),
            "_Las fechas diarias no establecen un corte intradía común entre mercados._",
        ]
    )
    return lines


def _render_quality_section(
    portfolio: Portfolio,
    *,
    quality: dict[str, float | int],
    returns: pd.Series[float],
    periods_per_year: int,
    section: int,
) -> list[str]:
    """Render the data-quality diagnostics section.

    Args:
        portfolio: Portfolio being reported, which supplies the per-asset coverage.
        quality: Alignment summary returned by ``Portfolio.alignment_summary``.
        returns: Portfolio returns, used for the sample length and its date range.
        periods_per_year: Number of trading periods per year used to express the history.
        section: Number assigned to the section in the report.

    Returns:
        Markdown lines of the quality section, per-asset coverage table included.

    """
    start = returns.index.min()
    end = returns.index.max()
    years = len(returns) / periods_per_year
    max_gap_days = quality["max_gap_days"]
    max_gap_unit = "día" if max_gap_days == 1 else "días"
    lines = [
        "",
        f"## {section}. Calidad de los datos",
        "",
        f"- Activos: {len(portfolio.assets)}",
        f"- Fechas en la unión de calendarios: {quality['union_dates']}",
        f"- Fechas comunes a todos los activos: {quality['common_dates']}",
        f"- Cobertura tras la alineación: {quality['coverage']:.1%}",
        (
            f"- Intervalos entre retornos que abarcan más de un día natural: "
            f"{quality['multi_day_share']:.1%} (máximo {max_gap_days} {max_gap_unit})"
        ),
        f"- Observaciones de rentabilidad: {len(returns)}",
        f"- Periodo de la muestra: {start:%Y-%m-%d} → {end:%Y-%m-%d}",
        f"- Años de historia: {years:.2f}",
        "",
        "**Cobertura por activo**",
        "",
        "| Activo | Observaciones | Inicio | Fin |",
        "|---|---:|---|---|",
    ]
    lines.extend(
        f"| {ticker} | {len(asset.prices)} | "
        f"{asset.prices.index.min():%Y-%m-%d} | {asset.prices.index.max():%Y-%m-%d} |"
        for ticker, asset in portfolio.assets.items()
    )
    return lines


def _render_metrics_section(
    *,
    metrics: dict[str, float],
    returns: pd.Series[float],
    periods_per_year: int,
    risk_free_rate: float,
    confidence: float,
    max_drawdown: float,
) -> list[str]:
    """Render the historical metrics table and its explanatory notes.

    Args:
        metrics: Statistics returned by ``Portfolio.summary``.
        returns: Aligned portfolio returns, already held by the report.
        periods_per_year: Number of trading periods per year used to annualize.
        risk_free_rate: Annual risk-free rate used by the Sharpe ratio.
        confidence: Confidence level of the value-at-risk measures.
        max_drawdown: Maximum drawdown already computed from ``returns``.

    Returns:
        Markdown lines of the metrics section, table and notes included.

    """
    sharpe = sharpe_ratio(
        returns,
        risk_free_rate=risk_free_rate,
        periods_per_year=periods_per_year,
    )
    value_at_risk = historical_var(returns, confidence=confidence)
    conditional_value_at_risk = historical_cvar(returns, confidence=confidence)
    period_label = _period_label(periods_per_year)
    standard_error = drift_standard_error(returns, periods_per_year=periods_per_year)
    point_estimate = metrics["annualized_return_approx"]
    lower = point_estimate - 1.96 * standard_error
    upper = point_estimate + 1.96 * standard_error
    cagr = compound_annual_growth(returns, periods_per_year=periods_per_year)
    log_drift, _ = annualized_log_assumptions(returns, periods_per_year=periods_per_year)
    median_growth = math.exp(log_drift) - 1.0
    return [
        "",
        "## 2. Métricas históricas",
        "",
        "| Métrica | Valor |",
        "|---|---:|",
        f"| Rentabilidad media diaria | {metrics['mean_daily_return']:.4%} |",
        f"| Volatilidad diaria | {metrics['daily_volatility']:.4%} |",
        f"| Rentabilidad anualizada aproximada | {metrics['annualized_return_approx']:.2%} |",
        f"| Volatilidad anualizada | {metrics['annualized_volatility']:.2%} |",
        f"| Error estándar de la rentabilidad anualizada | {standard_error:.2%} |",
        f"| IC 95% de la rentabilidad anualizada | {lower:.2%} - {upper:.2%} |",
        f"| Rentabilidad geométrica (CAGR) | {cagr:.2%} |",
        f"| Deriva del logaritmo usada por Monte Carlo | {log_drift:.2%} |",
        f"| Crecimiento mediano implícito (exp(m)-1) | {median_growth:.2%} |",
        f"| Máxima caída histórica | {max_drawdown:.2%} |",
        f"| Ratio de Sharpe (rf={risk_free_rate:.2%}) | {sharpe:.2f} |",
        f"| VaR histórico {period_label} ({confidence:.0%}) | {value_at_risk:.2%} |",
        f"| CVaR histórico {period_label} ({confidence:.0%}) | {conditional_value_at_risk:.2%} |",
        "",
        "_Un VaR o CVaR negativo indica que el cuantil de la cola es una ganancia._",
        "",
        (
            "_La simulación usa la deriva del logaritmo; su mediana crece a exp(m)-1, "
            "no a la rentabilidad aritmética._"
        ),
    ]


def _collect_risk_warnings(
    portfolio: Portfolio,
    quality: dict[str, float | int],
    returns: pd.Series[float],
    metrics: dict[str, float] | None,
    max_drawdown: float | None,
) -> list[str]:
    """Return the risk warnings derived from the current portfolio state.

    Args:
        portfolio: Portfolio being reported.
        quality: Alignment summary returned by ``Portfolio.alignment_summary``.
        returns: Portfolio returns used to detect a short sample.
        metrics: Statistics returned by ``Portfolio.summary``, or ``None`` when they could not
            be estimated; the volatility warning is skipped in that case.
        max_drawdown: Maximum drawdown of the portfolio, or ``None`` when it could not be
            estimated; the drawdown warning is skipped in that case.

    Returns:
        Warnings about alignment, concentration, risk and sample length.

    """
    risk_warnings = [
        "Las rentabilidades históricas no garantizan resultados futuros.",
        "La simulación de Monte Carlo depende de los supuestos de rentabilidad y volatilidad.",
    ]
    coverage = float(quality["coverage"])
    if coverage < ALIGNMENT_COVERAGE_WARNING_THRESHOLD:
        risk_warnings.append(
            f"La alineación temporal descarta el {(1.0 - coverage):.1%} de las fechas; "
            "las métricas solo usan días hábiles comunes a todos los activos."
        )
    multi_day_share = float(quality["multi_day_share"])
    if multi_day_share > MULTI_DAY_RETURNS_WARNING_THRESHOLD:
        risk_warnings.append(
            f"El {multi_day_share:.1%} de los intervalos entre retornos abarca "
            "más de un día natural; la anualización con 252 o 365 periodos es aproximada."
        )
    if len(portfolio.assets) == 1:
        risk_warnings.append(
            "La cartera concentra toda la inversión en un único activo: no hay diversificación."
        )
    if (
        metrics is not None
        and metrics["annualized_volatility"] >= HIGH_VOLATILITY_WARNING_THRESHOLD
    ):
        risk_warnings.append(
            f"La volatilidad anualizada es {metrics['annualized_volatility']:.1%}; "
            "la cartera se comporta como un activo de alto riesgo."
        )
    if max_drawdown is not None and max_drawdown <= DRAWDOWN_WARNING_THRESHOLD:
        risk_warnings.append(
            f"La máxima caída histórica es {max_drawdown:.1%}; "
            "la simulación puede subestimar episodios de estrés."
        )
    top_ticker, top_weight = max(portfolio.weights.items(), key=lambda item: item[1])
    if len(portfolio.assets) > 1 and top_weight > CONCENTRATION_WARNING_THRESHOLD:
        risk_warnings.append(
            f"{top_ticker} concentra el {top_weight:.1%} de la cartera; "
            "la diversificación es limitada."
        )
    if len(returns) < SHORT_HISTORY_WARNING_THRESHOLD:
        observations = "observación" if len(returns) == 1 else "observaciones"
        risk_warnings.append(
            f"La muestra histórica es corta: solo hay {len(returns)} {observations} "
            "de rentabilidad."
        )
    return risk_warnings


def plot_portfolio_report(portfolio: Portfolio) -> None:
    """Display the analytical dashboard of a portfolio.

    The dashboard shows the aligned price evolution rebased to 100, the cumulative return
    comparison, the correlation matrix and the evolution of a portfolio invested at a base
    value of 100.

    Args:
        portfolio: Portfolio to plot.

    """
    prices = portfolio.analysis_prices().dropna(how="any")
    returns = portfolio.get_returns()
    figure, axes = plt.subplots(2, 2, figsize=(14, 10))

    prices_axis = axes[0, 0]
    normalized_prices = prices.divide(prices.iloc[0]).multiply(PERFORMANCE_BASE)
    normalized_prices.plot(ax=prices_axis)
    title = f"Evolución de precios (base {PERFORMANCE_BASE:.0f})"
    if portfolio.reporting_currency is not None:
        title = (
            f"Evolución de precios en {portfolio.reporting_currency} (base {PERFORMANCE_BASE:.0f})"
        )
    prices_axis.set_title(title)
    prices_axis.set_xlabel("Fecha")
    prices_axis.set_ylabel(f"Precio relativo (base {PERFORMANCE_BASE:.0f})")

    cumulative_axis = axes[0, 1]
    ((1.0 + returns).cumprod() - 1.0).plot(ax=cumulative_axis)
    cumulative_axis.set_title("Rentabilidad acumulada por activo")
    cumulative_axis.set_xlabel("Fecha")
    cumulative_axis.set_ylabel("Rentabilidad")

    correlation_axis = axes[1, 0]
    correlation = returns.corr()
    image = correlation_axis.imshow(
        correlation.to_numpy(),
        vmin=-1.0,
        vmax=1.0,
        aspect="auto",
    )
    correlation_axis.set_title("Correlación entre activos")
    correlation_axis.set_xticks(
        range(len(correlation.columns)),
        labels=correlation.columns,
        rotation=45,
        ha="right",
    )
    correlation_axis.set_yticks(range(len(correlation.index)), labels=correlation.index)
    figure.colorbar(image, ax=correlation_axis)

    value_axis = axes[1, 1]
    portfolio_values = PERFORMANCE_BASE * (1.0 + portfolio.portfolio_returns()).cumprod()
    portfolio_values.plot(ax=value_axis)
    value_axis.set_title(f"Evolución del valor de la cartera (base {PERFORMANCE_BASE:.0f})")
    value_axis.set_xlabel("Fecha")
    value_axis.set_ylabel("Valor")

    figure.tight_layout()
    plt.show()


def plot_simulation_paths(
    simulations: pd.DataFrame,
    *,
    max_paths: int = 100,
    value_label: str = "Valor de la cartera",
    final_label: str = "valor final",
) -> None:
    """Display simulated trajectories and the distribution of final values.

    Args:
        simulations: Path matrix returned by a ``simulate_monte_carlo`` method.
        max_paths: Maximum number of trajectories to draw.
        value_label: Label of the trajectory axis, which names the simulated quantity.
        final_label: Label of the final-value axis and of the distribution title, which names
            the simulated quantity at the end of the horizon.

    Raises:
        ValueError: If there are no simulations or ``max_paths`` is not positive.

    """
    if simulations.empty:
        msg = "No hay simulaciones para representar."
        raise ValueError(msg)
    if max_paths < 1:
        msg = "max_paths debe ser mayor que cero."
        raise ValueError(msg)

    figure, axes = plt.subplots(1, 2, figsize=(14, 5))

    trajectory_axis = axes[0]
    simulations.iloc[:, :max_paths].plot(ax=trajectory_axis, legend=False, alpha=0.35)
    trajectory_axis.set_title("Trayectorias simuladas")
    trajectory_axis.set_xlabel("Sesiones")
    trajectory_axis.set_ylabel(value_label)

    distribution_axis = axes[1]
    final_values = simulations.iloc[-1]
    distribution_axis.hist(final_values, bins=40)
    distribution_axis.axvline(final_values.median(), linestyle="--", label="Mediana")
    distribution_axis.set_title(f"Distribución del {final_label}")
    distribution_axis.set_xlabel(final_label.capitalize())
    distribution_axis.set_ylabel("Número de escenarios")
    distribution_axis.legend()

    figure.tight_layout()
    plt.show()
