# Arquitectura de Quantfolio

Diagramas de la estructura de clases, las dependencias entre módulos y el flujo de datos del sistema. Los
diagramas están escritos en **Mermaid** (UML equivalente, renderizable directamente en GitHub); pueden editarse en
[FossFLOW](https://github.com/ai-8/fossflow), en [mermaid.live](https://mermaid.live) o en cualquier editor con
soporte de diagramas Mermaid.

## Diagrama de clases (UML)

```mermaid
classDiagram
    direction LR

    class PriceSeries {
        +str ticker
        +Series~float~ prices
        +str source
        +float mean_price
        +float std_price
        +simulate_monte_carlo(parameters) DataFrame
        +plot_simulation(simulations, max_paths) None
    }

    class Portfolio {
        +dict~str, PriceSeries~ assets
        +dict~str, float~ weights
        +get_prices() DataFrame
        +get_returns() DataFrame
        +alignment_summary() dict
        +portfolio_returns() Series
        +summary(periods_per_year) dict
        +simulate_monte_carlo(parameters) DataFrame
        +plot_simulation(simulations, max_paths) None
        +report(periods_per_year, include_quality, include_warnings) str
        +plots_report() None
    }

    class MonteCarloParameters {
        <<dataclass>>
        +int n_paths = 1000
        +int horizon = 252
        +float initial_value = None
        +float return_assumption = None
        +float volatility_assumption = None
        +int seed = None
    }

    class PriceSource {
        <<abstract>>
        +str name
        +get_prices(ticker, start, end) PriceSeries
        +get_many(tickers, start, end) dict
    }

    class YahooFinanceSource {
        acciones e índices
    }

    class KrakenSource {
        criptomonedas
    }

    class CachedPriceSource {
        +PriceSource source
        +Path cache_dir
        +int ttl_days
        +bool refresh
    }

    class MacroSeries {
        <<dataclass>>
        +str series_id
        +Series~float~ values
        +str source
    }

    class FredMacroSource {
        +get_series(series_id, start, end) MacroSeries
    }

    class simulation {
        <<module>>
        +simulate_gbm_paths(...) ndarray
        +annualized_log_assumptions(returns) tuple
        +paths_to_frame(paths) DataFrame
    }

    class reporting {
        <<module>>
        +render_portfolio_report(portfolio, ...) str
        +plot_portfolio_report(portfolio) None
        +plot_simulation_paths(simulations, max_paths) None
    }

    Portfolio o-- "1..*" PriceSeries : agrega
    Portfolio ..> MonteCarloParameters : configura
    Portfolio ..> simulation : delega
    Portfolio ..> reporting : delega
    PriceSeries ..> simulation : delega
    PriceSeries ..> reporting : delega
    YahooFinanceSource --|> PriceSource
    KrakenSource --|> PriceSource
    CachedPriceSource --|> PriceSource
    CachedPriceSource o-- "1" PriceSource : envuelve
    FredMacroSource ..> MacroSeries : produce
```

**Lectura del diagrama.** `PriceSource` es el contrato común de la capa de ingesta: los proveedores concretos
(Yahoo Finance, Kraken) lo implementan y `CachedPriceSource` lo decora sobre cualquier otro proveedor, de forma
que la capa de análisis nunca depende de una API concreta. `PriceSeries` y `Portfolio` son las DataClasses del
modelo; `MonteCarloParameters` concentra la parametrización del motor `simulation.py`, y `reporting.py` contiene
los helpers de Markdown y gráficos que los métodos públicos delegan. `FredMacroSource`/`MacroSeries` cubren la
tipología de datos adicional (macroeconomía y tipos de interés).

## Flujo del sistema

```mermaid
flowchart LR
    subgraph entrypoint["Punto de entrada (notebooks/)"]
        NB["assignment.ipynb"]
    end

    subgraph ingestion["Ingesta y estandarización (sources/, macro.py)"]
        YF["YahooFinanceSource<br/>acciones e índices"]
        KR["KrakenSource<br/>criptomonedas"]
        CA["CachedPriceSource<br/>caché CSV"]
        FR["FredMacroSource<br/>macro y tipos"]
    end

    PS["PriceSeries<br/>limpieza + estadísticos automáticos"]
    MS["MacroSeries"]
    PF["Portfolio<br/>pesos normalizados + alineación temporal"]
    MC["simulation.py<br/>GBM Monte Carlo"]
    RP["reporting.py<br/>informe Markdown + gráficos"]

    NB --> YF
    NB --> KR
    NB --> FR
    YF --> CA
    KR --> CA
    YF --> PS
    KR --> PS
    CA --> PS
    FR --> MS
    PS --> PF
    PF --> MC
    PF --> RP
    MC --> RP
```

**Flujo típico.** El cuaderno crea los proveedores y descarga las series (en lotes con `get_many()`, con caché
opcional). Cada proveedor normaliza su respuesta en `PriceSeries`, que limpia los datos y calcula sus estadísticos
al construirse. Con varias series se instancia `Portfolio`, que valida y normaliza los pesos y alinea los
calendarios. Sobre la cartera se calculan métricas, se genera el informe y los gráficos (`reporting.py`) y se lanza
la simulación Monte Carlo (`simulation.py`), cuyos resultados también se visualizan.

## Estructura de módulos

| Módulo | Responsabilidad |
|---|---|
| `quantfolio.models` | `PriceSeries` (limpieza, estadísticos automáticos) y utilidades numéricas. |
| `quantfolio.portfolio` | `Portfolio`: validación de pesos, alineación temporal, métricas, informe y Monte Carlo. |
| `quantfolio.simulation` | `MonteCarloParameters` y el motor GBM compartido por activo y cartera. |
| `quantfolio.reporting` | Generación del informe Markdown y de todas las visualizaciones. |
| `quantfolio.sources` | Contrato `PriceSource`, proveedores (Yahoo, Kraken) y caché CSV. |
| `quantfolio.macro` | `MacroSeries` y proveedor FRED para la tipología de datos adicional. |
| `quantfolio.constants` | Constantes compartidas (sesiones por año, umbrales de diagnóstico, etc.). |
