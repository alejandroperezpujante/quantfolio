"""Markdown reports and analytical plots for portfolios and simulations."""

from typing import TYPE_CHECKING

import matplotlib.pyplot as plt

from quantfolio.constants import (
    ALIGNMENT_COVERAGE_WARNING_THRESHOLD,
    PERFORMANCE_BASE,
    SHORT_HISTORY_WARNING_THRESHOLD,
    TRADING_DAYS_PER_YEAR,
)

if TYPE_CHECKING:
    import pandas as pd

    from quantfolio.portfolio import Portfolio


# The report exposes each documented option as a keyword argument, so its public signature is
# intentionally wider than the default Pylint limit.
def render_portfolio_report(  # noqa: PLR0913
    portfolio: Portfolio,
    *,
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
    include_quality: bool = True,
    include_warnings: bool = True,
    risk_free_rate: float = 0.0,
    confidence: float = 0.95,
) -> str:
    """Render a portfolio report as structured Markdown.

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
    metrics = portfolio.summary(periods_per_year=periods_per_year)
    returns = portfolio.portfolio_returns()
    quality = portfolio.alignment_summary()
    drawdown = portfolio.max_drawdown()
    sharpe = portfolio.sharpe_ratio(
        risk_free_rate=risk_free_rate,
        periods_per_year=periods_per_year,
    )
    value_at_risk = portfolio.value_at_risk(confidence=confidence)
    conditional_value_at_risk = portfolio.conditional_value_at_risk(confidence=confidence)

    lines = [
        "# Informe de la cartera",
        "",
        "## 1. Composición",
        "",
        "| Activo | Peso |",
        "|---|---:|",
    ]
    lines.extend(f"| {ticker} | {weight:.2%} |" for ticker, weight in portfolio.weights.items())
    lines.extend(
        [
            "",
            "## 2. Métricas históricas",
            "",
            "| Métrica | Valor |",
            "|---|---:|",
            f"| Rentabilidad media diaria | {metrics['mean_daily_return']:.4%} |",
            f"| Volatilidad diaria | {metrics['daily_volatility']:.4%} |",
            f"| Rentabilidad anualizada aproximada | {metrics['annualized_return_approx']:.2%} |",
            f"| Volatilidad anualizada | {metrics['annualized_volatility']:.2%} |",
            f"| Máxima caída histórica | {drawdown:.2%} |",
            f"| Ratio de Sharpe (rf={risk_free_rate:.2%}) | {sharpe:.2f} |",
            f"| VaR histórico diario ({confidence:.0%}) | {value_at_risk:.2%} |",
            f"| CVaR histórico diario ({confidence:.0%}) | {conditional_value_at_risk:.2%} |",
        ]
    )
    lines.extend(
        [
            "",
            "_Un VaR o CVaR negativo indica que el cuantil de la cola es una ganancia._",
        ]
    )

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
        section += 1

    if include_warnings:
        lines.extend(["", f"## {section}. Advertencias de riesgo", ""])
        lines.extend(
            f"- {warning}" for warning in _collect_risk_warnings(portfolio, quality, returns)
        )

    return "\n".join(lines)


def _collect_risk_warnings(
    portfolio: Portfolio,
    quality: dict[str, float | int],
    returns: pd.Series[float],
) -> list[str]:
    """Return the risk warnings derived from the current portfolio state."""
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
