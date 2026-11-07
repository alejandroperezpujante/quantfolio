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
        +summary(periods_per_year) dict
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
        +return_gaps() Series
        +summary(periods_per_year) dict
        +max_drawdown() float
        +sharpe_ratio(risk_free_rate, periods_per_year) float
        +value_at_risk(confidence) float
        +conditional_value_at_risk(confidence) float
        +simulate_monte_carlo(parameters) DataFrame
        +plot_simulation(simulations, max_paths) None
        +report(periods_per_year, include_quality, include_warnings, risk_free_rate, confidence) str
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
        +int periods_per_year = 252
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

    class AlphaVantageSource {
        activos diarios opcionales
    }

    class runtime {
        +create_price_source_registry() Mapping
    }

    class AlphaVantageCapabilityStore {
        caché de capacidades de 24 horas
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
        +Timestamp~None~ vintage_date
    }

    class FredMacroSource {
        +get_series(series_id, start, end, as_of) MacroSeries
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
        +plot_simulation_paths(simulations, max_paths, value_label, final_label) None
    }

    Portfolio o-- "1..*" PriceSeries : agrega
    Portfolio ..> MonteCarloParameters : configura
    Portfolio ..> simulation : delega
    Portfolio ..> reporting : delega
    PriceSeries ..> simulation : delega
    PriceSeries ..> reporting : delega
    YahooFinanceSource --|> PriceSource
    KrakenSource --|> PriceSource
    AlphaVantageSource --|> PriceSource
    CachedPriceSource --|> PriceSource
    CachedPriceSource o-- "1" PriceSource : envuelve
    FredMacroSource ..> MacroSeries : produce
```

**Lectura del diagrama.** `PriceSource` es el contrato común de la capa de ingesta: los proveedores concretos
(Yahoo Finance, Kraken y Alpha Vantage) lo implementan y `CachedPriceSource` lo decora sobre cualquier otro proveedor, de forma
que la capa de análisis nunca depende de una API concreta. `PriceSeries` y `Portfolio` son las DataClasses del
modelo; `MonteCarloParameters` concentra la parametrización del motor `simulation.py`, y `reporting.py` contiene
los helpers de Markdown y gráficos que los métodos públicos delegan. `FredMacroSource`/`MacroSeries` cubren la
tipología de datos adicional (macroeconomía y tipos de interés): las descargas pasan por el endpoint de archivo de
ALFRED, cada `MacroSeries` registra en `vintage_date` el vintage del que proceden sus valores y `as_of` recupera los
valores punto-en-el-tiempo publicados hasta una fecha; si el vintage servido no coincide con el solicitado, la
descarga falla con `ValueError` en lugar de etiquetar mal la serie.

## Flujo del sistema

```mermaid
flowchart LR
    subgraph entrypoint["Punto de entrada (notebooks/)"]
        NB["quantfolio_demo.ipynb<br/>portfolio_stocks.ipynb<br/>portfolio_indices.ipynb<br/>portfolio_fixed_income.ipynb<br/>portfolio_crypto.ipynb"]
    end

    subgraph ingestion["Ingesta y estandarización (sources/, macro.py)"]
        YF["YahooFinanceSource<br/>acciones e índices"]
        KR["KrakenSource<br/>criptomonedas"]
        AV["AlphaVantageSource<br/>activos diarios opcionales"]
        RT["runtime.py<br/>registro inmutable"]
        CP["capabilities.py<br/>validación y caché"]
        CA["CachedPriceSource<br/>caché CSV"]
        FR["FredMacroSource<br/>macro y tipos"]
    end

    PS["PriceSeries<br/>limpieza + estadísticos automáticos"]
    MS["MacroSeries"]
    PF["Portfolio<br/>pesos normalizados + alineación temporal"]
    MC["simulation.py<br/>GBM Monte Carlo"]
    RP["reporting.py<br/>informe Markdown + gráficos"]

    NB --> RT
    RT --> YF
    RT --> KR
    RT --> AV
    RT --> CP
    NB --> FR
    YF --> CA
    KR --> CA
    YF --> PS
    KR --> PS
    AV --> PS
    CA --> PS
    FR --> MS
    PS --> PF
    PF --> MC
    PF --> RP
    MC --> RP
```

**Flujo típico.** Los cuadernos crean los proveedores y descargan las series (en lotes con `get_many()`, con
caché opcional). Cada proveedor normaliza su respuesta en `PriceSeries`, que limpia los datos y calcula sus
estadísticos al construirse. Con varias series se instancia `Portfolio`, que valida y normaliza los pesos y alinea
los calendarios. Sobre la cartera se calculan métricas, se genera el informe y los gráficos (`reporting.py`) y se
lanza la simulación Monte Carlo (`simulation.py`), cuyos resultados también se visualizan. Los cuadernos
`portfolio_*.ipynb` aíslan cada clase de activo; `quantfolio_demo.ipynb` recorre el toolkit completo y compara las
cuatro clases en una cartera diversificada.

## Estructura de módulos

| Módulo | Responsabilidad |
|---|---|
| `quantfolio.models` | `PriceSeries` (limpieza, estadísticos automáticos) y utilidades numéricas. |
| `quantfolio.portfolio` | `Portfolio`: validación de pesos, alineación temporal, métricas, informe y Monte Carlo. |
| `quantfolio.risk` | Medidas de riesgo puras: drawdown, Sharpe, CAGR, error estándar de la deriva y VaR/CVaR históricos. |
| `quantfolio.validation` | Validadores de entrada compartidos (periodos, confianza, tasa libre de riesgo y rentabilidades). |
| `quantfolio.simulation` | `MonteCarloParameters` y el motor GBM compartido por activo y cartera. |
| `quantfolio.reporting` | Generación del informe Markdown y de todas las visualizaciones. |
| `quantfolio.sources` | Contrato `PriceSource`, proveedores (Yahoo, Kraken, Alpha Vantage) y caché CSV. |
| `quantfolio.runtime` | Registro inmutable y descubrimiento opcional de Alpha Vantage; FRED permanece separado. |
| `quantfolio.macro` | `MacroSeries` y proveedor FRED vía ALFRED, con vintages punto-en-el-tiempo, para la tipología de datos adicional. |
| `quantfolio.constants` | Constantes compartidas (sesiones por año, umbrales de diagnóstico, etc.). |
