"""Markdown reports and analytical plots for portfolios and simulations."""

import math
from typing import TYPE_CHECKING

import matplotlib.pyplot as plt

from quantfolio.constants import (
    ALIGNMENT_COVERAGE_WARNING_THRESHOLD,
    CONCENTRATION_WARNING_THRESHOLD,
    DRAWDOWN_WARNING_THRESHOLD,
    HIGH_VOLATILITY_WARNING_THRESHOLD,
    PERFORMANCE_BASE,
    SHORT_HISTORY_WARNING_THRESHOLD,
    TRADING_DAYS_PER_YEAR,
)
from quantfolio.risk import compound_annual_growth, drift_standard_error
from quantfolio.simulation import annualized_log_assumptions

if TYPE_CHECKING:
    import pandas as pd

    from quantfolio.portfolio import Portfolio


def render_portfolio_report(
    portfolio: Portfolio,
    *,
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
    include_quality: bool = True,
    include_warnings: bool = True,
    risk_free_rate: float = 0.0,
    confidence: float = 0.95,
) -> str:
    """Render a portfolio report as structured Markdown.

    The report degrades gracefully: when the aligned sample is too short to estimate the
    metrics, or their computation overflows, the metrics section is replaced by an
    explanatory note and the risk warnings skip the volatility and drawdown checks.

    Args:
        portfolio: Portfolio to report on.
        periods_per_year: Number of trading periods per year used to annualize the mean return,
            the volatility and the Sharpe ratio; the VaR and the CVaR are expressed per return
            period (daily in the examples).
        include_quality: Whether to include the data-quality diagnostics section.
        include_warnings: Whether to include the risk-warnings section.
        risk_free_rate: Annual risk-free rate used by the Sharpe ratio.
        confidence: Confidence level of the value-at-risk measures.

    Returns:
        Markdown text with composition, metrics, diagnostics and risk warnings.

    """
    returns = portfolio.portfolio_returns()
    quality = portfolio.alignment_summary()
    metrics: dict[str, float] | None = None
    max_drawdown: float | None = None
    metrics_lines = [
        "",
        "## 2. Métricas históricas",
        "",
        "No hay suficientes observaciones para calcular métricas históricas.",
    ]
    try:
        metrics = portfolio.summary(periods_per_year=periods_per_year)
        max_drawdown = portfolio.max_drawdown()
        metrics_lines = _render_metrics_section(
            portfolio,
            metrics=metrics,
            returns=returns,
            periods_per_year=periods_per_year,
            risk_free_rate=risk_free_rate,
            confidence=confidence,
        )
    except ValueError, OverflowError:
        metrics = None
        max_drawdown = None

    lines = [
        "# Informe de la cartera",
        "",
        "## 1. Composición",
        "",
        "| Activo | Peso |",
        "|---|---:|",
    ]
    lines.extend(f"| {ticker} | {weight:.2%} |" for ticker, weight in portfolio.weights.items())
    lines.extend(metrics_lines)

    section = 3
    if include_quality:
        lines.extend(
            [
                "",
                f"## {section}. Calidad de los datos",
                "",
                f"- Activos: {len(portfolio.assets)}",
                f"- Fechas en la unión de calendarios: {quality['union_dates']}",
                f"- Fechas comunes a todos los activos: {quality['common_dates']}",
                f"- Cobertura tras la alineación: {quality['coverage']:.1%}",
                f"- Observaciones de rentabilidad: {len(returns)}",
            ]
        )
        start = returns.index.min()
        end = returns.index.max()
        years = len(returns) / periods_per_year
        lines.extend(
            [
                f"- Periodo de la muestra: {start:%Y-%m-%d} → {end:%Y-%m-%d}",
                f"- Años de historia: {years:.2f}",
                "",
                "**Cobertura por activo**",
                "",
                "| Activo | Observaciones | Inicio | Fin |",
                "|---|---:|---|---|",
            ]
        )
        lines.extend(
            f"| {ticker} | {len(asset.prices)} | "
            f"{asset.prices.index.min():%Y-%m-%d} | {asset.prices.index.max():%Y-%m-%d} |"
            for ticker, asset in portfolio.assets.items()
        )
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


def _render_metrics_section(
    portfolio: Portfolio,
    *,
    metrics: dict[str, float],
    returns: pd.Series[float],
    periods_per_year: int,
    risk_free_rate: float,
    confidence: float,
) -> list[str]:
    """Render the historical metrics table and its explanatory notes.

    Args:
        portfolio: Portfolio being reported, which supplies the risk measures.
        metrics: Statistics returned by ``Portfolio.summary``.
        returns: Portfolio returns used to annualize the drift and the growth measures.
        periods_per_year: Number of trading periods per year used to annualize.
        risk_free_rate: Annual risk-free rate used by the Sharpe ratio.
        confidence: Confidence level of the value-at-risk measures.

    Returns:
        Markdown lines of the metrics section, table and notes included.

    """
    max_drawdown = portfolio.max_drawdown()
    sharpe = portfolio.sharpe_ratio(
        risk_free_rate=risk_free_rate,
        periods_per_year=periods_per_year,
    )
    value_at_risk = portfolio.value_at_risk(confidence=confidence)
    conditional_value_at_risk = portfolio.conditional_value_at_risk(confidence=confidence)
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
        f"| VaR histórico diario ({confidence:.0%}) | {value_at_risk:.2%} |",
        f"| CVaR histórico diario ({confidence:.0%}) | {conditional_value_at_risk:.2%} |",
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
        risk_warnings.append(
            f"La muestra histórica es corta: solo hay {len(returns)} observaciones de rentabilidad."
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
    prices = portfolio.get_prices().dropna(how="any")
    returns = portfolio.get_returns()
    figure, axes = plt.subplots(2, 2, figsize=(14, 10))

    prices_axis = axes[0, 0]
    normalized_prices = prices.divide(prices.iloc[0]).multiply(PERFORMANCE_BASE)
    normalized_prices.plot(ax=prices_axis)
    prices_axis.set_title(f"Evolución de precios (base {PERFORMANCE_BASE:.0f})")
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


def plot_simulation_paths(simulations: pd.DataFrame, *, max_paths: int = 100) -> None:
    """Display simulated trajectories and the distribution of final values.

    Args:
        simulations: Path matrix returned by a ``simulate_monte_carlo`` method.
        max_paths: Maximum number of trajectories to draw.

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
    trajectory_axis.set_ylabel("Valor de la cartera")

    distribution_axis = axes[1]
    final_values = simulations.iloc[-1]
    distribution_axis.hist(final_values, bins=40)
    distribution_axis.axvline(final_values.median(), linestyle="--", label="Mediana")
    distribution_axis.set_title("Distribución del valor final")
    distribution_axis.set_xlabel("Valor final")
    distribution_axis.set_ylabel("Número de escenarios")
    distribution_axis.legend()

    figure.tight_layout()
    plt.show()
