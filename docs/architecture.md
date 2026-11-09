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
        +str quote_currency
        +str quote_unit
        +float mean_price
        +float std_price
        +summary(periods_per_year) dict
        +simulate_monte_carlo(parameters) DataFrame
        +plot_simulation(simulations, max_paths) None
    }

    class AutoPortfolio {
        +AutoPortfolio(config)
    }

    class AutoPortfolioConfig {
        +Mapping~str, float~ weights
        +DateLike start
        +DateLike end
        +str reporting_currency
        +Mapping~str, str~ quote_currencies
        +Mapping~str, str~ quote_units
        +Mapping~str, str~ asset_families
        +ExchangeRates exchange_rates
        +int fx_lookback_days
        +int~None~ fx_max_age_days
    }

    class Portfolio {
        +dict~str, PriceSeries~ assets
        +dict~str, float~ weights
        +str reporting_currency
        +ExchangeRates exchange_rates
        +get_prices() DataFrame
        +get_reporting_prices() DataFrame
        +analysis_prices() DataFrame
        +currency_conversion_diagnostics() DataFrame
        +analysis_currency_conversion_diagnostics() DataFrame
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

    class ExchangeRates {
        +tuple~PriceSeries~ rates
        +int max_age_days = 4
        +from_source(source, pairs, start, end, max_age_days) ExchangeRates
        +resolve_rate(from_currency, to_currency, on_date) tuple
    }

    class ExchangeRateObservation {
        +str pair
        +str source
        +str from_currency
        +str to_currency
        +Timestamp observation_date
        +int age_days
        +float rate
        +float applied_rate
        +bool inverted
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

    class ECBExchangeRateSource {
        pares EUR-first diarios
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

    AutoPortfolio --|> Portfolio
    AutoPortfolio ..> AutoPortfolioConfig : configura
    AutoPortfolio ..> PriceSource : obtiene datos
    Portfolio o-- "1..*" PriceSeries : agrega
    Portfolio o-- ExchangeRates : aplica factores de conversión
    ExchangeRates ..> ExchangeRateObservation : registra
    ExchangeRates o-- "0..*" PriceSeries : tipos históricos
    Portfolio ..> MonteCarloParameters : configura
    Portfolio ..> simulation : delega
    Portfolio ..> reporting : delega
    PriceSeries ..> simulation : delega
    PriceSeries ..> reporting : delega
    YahooFinanceSource --|> PriceSource
    KrakenSource --|> PriceSource
    ECBExchangeRateSource --|> PriceSource
    AlphaVantageSource --|> PriceSource
    CachedPriceSource --|> PriceSource
    CachedPriceSource o-- "1" PriceSource : envuelve
    FredMacroSource ..> MacroSeries : produce
```

**Lectura del diagrama.** `PriceSource` es el contrato común de la capa de ingesta: los proveedores concretos
(Yahoo Finance, Kraken, Alpha Vantage y ECB) lo implementan y `CachedPriceSource` lo decora sobre cualquier otro proveedor, de forma
que la capa de análisis nunca depende de una API concreta. `PriceSeries` y `Portfolio` son las DataClasses del
modelo; `MonteCarloParameters` concentra la parametrización del motor `simulation.py`, y `reporting.py` contiene
los helpers de Markdown y gráficos que los métodos públicos delegan. `FredMacroSource`/`MacroSeries` cubren la
tipología de datos adicional (macroeconomía y tipos de interés): las descargas pasan por el endpoint de archivo de
ALFRED, cada `MacroSeries` registra en `vintage_date` el vintage del que proceden sus valores y `as_of` recupera los
valores punto-en-el-tiempo publicados hasta una fecha; si el vintage servido no coincide con el solicitado, la
descarga falla con `ValueError` en lugar de etiquetar mal la serie.

`AutoPortfolioConfig` permite declarar `quote_currencies` y `quote_units` para completar la procedencia
monetaria, y `asset_families` para resolver tickers ambiguos. Los tipos pueden aportarse manualmente en
`exchange_rates` o descargarse automáticamente cuando se omite esa colección. `max_age_days` limita la
antigüedad de cada observación; `fx_max_age_days` fija el valor efectivo para una descarga y debe coincidir
con la colección cuando ambos se proporcionan. `Portfolio.get_reporting_prices()` y
`currency_conversion_diagnostics()` conservan la vista estricta sobre la unión de calendarios;
`analysis_prices()` y `analysis_currency_conversion_diagnostics()` limitan la conversión y su traza a las fechas
comunes usadas por las métricas y el informe.

## Flujo del sistema

```mermaid
flowchart LR
    subgraph entrypoint["Punto de entrada (notebooks/)"]
        NB["quantfolio_demo.ipynb<br/>portfolio_stocks.ipynb<br/>portfolio_indices.ipynb<br/>portfolio_fixed_income.ipynb<br/>portfolio_crypto.ipynb<br/>portfolio_multi_currency.ipynb"]
    end

    subgraph ingestion["Ingesta y estandarización (sources/, macro.py)"]
        YF["YahooFinanceSource<br/>acciones e índices"]
        KR["KrakenSource<br/>criptomonedas"]
        ECB["ECBExchangeRateSource<br/>tipos EUR-first"]
        AV["AlphaVantageSource<br/>activos diarios opcionales"]
        RT["runtime.py<br/>registro inmutable"]
        CP["alpha_vantage/capabilities.py<br/>validación y caché"]
        CA["CachedPriceSource<br/>caché CSV"]
        FR["FredMacroSource<br/>macro y tipos"]
    end

    PS["PriceSeries<br/>limpieza + estadísticos automáticos"]
    ER["currency.py<br/>selecciona tipos + trazabilidad"]
    MS["MacroSeries"]
    PF["Portfolio<br/>aplica conversión + alineación temporal"]
    MC["simulation.py<br/>GBM Monte Carlo"]
    RP["reporting.py<br/>informe Markdown + gráficos"]

    NB --> RT
    RT --> YF
    RT --> KR
    RT --> AV
    RT --> CP
    NB --> FR
    NB --> ECB
    YF --> CA
    KR --> CA
    YF --> PS
    KR --> PS
    ECB --> PS
    AV --> PS
    CA --> PS
    FR --> MS
    PS --> PF
    PS --> ER
    ER --> PF
    PF --> MC
    PF --> RP
    MC --> RP
```

**Flujo típico.** Los cuadernos crean los proveedores y descargan las series (en lotes con `get_many()`, con
caché opcional). Cada proveedor normaliza su respuesta en `PriceSeries`, que limpia los datos y calcula sus
estadísticos al construirse. Con varias series se instancia `Portfolio`, que valida y normaliza los pesos y alinea
los calendarios. Si se declara una divisa de reporte, `currency.py` selecciona tipos históricos directos, inversos o
cruzados por EUR y registra cada tramo utilizado. `Portfolio` aplica a los precios los factores seleccionados por
`currency.py` antes del análisis. Sobre la cartera se calculan métricas, se genera el informe y los gráficos
(`reporting.py`) y se lanza la simulación Monte Carlo
(`simulation.py`), cuyos resultados también se visualizan. Los cuadernos
`portfolio_*.ipynb` aíslan cada clase de activo; `quantfolio_demo.ipynb` recorre el toolkit completo y compara las
cuatro clases en una cartera diversificada.

## Estructura de módulos

| Módulo | Responsabilidad |
|---|---|
| `quantfolio.models` | `PriceSeries` (limpieza, estadísticos y metadatos de cotización) y utilidades numéricas. |
| `quantfolio.quote_metadata` | Validación compartida de códigos de divisa y unidades de cotización sin ciclos de importación. |
| `quantfolio.currency` | `ExchangeRates`: selección directa, inversa o cruzada de tipos históricos y trazabilidad de cada tramo. |
| `quantfolio.auto_portfolio` | Construcción automática, selección de proveedores, caché y tipos de cambio. |
| `quantfolio.portfolio` | `Portfolio`: validación de pesos, aplicación de la conversión seleccionada por `currency.py`, alineación temporal, métricas, informe y Monte Carlo. |
| `quantfolio.risk` | Medidas de riesgo puras: drawdown, Sharpe, CAGR, error estándar de la deriva y VaR/CVaR históricos. |
| `quantfolio.validation` | Validadores de entrada compartidos (periodos, confianza, tasa libre de riesgo y rentabilidades). |
| `quantfolio.simulation` | `MonteCarloParameters` y el motor GBM compartido por activo y cartera. |
| `quantfolio.reporting` | Generación del informe Markdown y de todas las visualizaciones. |
| `quantfolio.sources` | Contrato `PriceSource`, proveedores (Yahoo, Kraken, ECB) y caché CSV. |
| `quantfolio.sources.alpha_vantage` | Proveedor opcional de Alpha Vantage: cliente HTTP, capacidades y adaptador `PriceSource`. |
| `quantfolio.runtime` | Registro inmutable y descubrimiento opcional de Alpha Vantage; FRED permanece separado. |
| `quantfolio.macro` | `MacroSeries` y proveedor FRED vía ALFRED, con vintages punto-en-el-tiempo, para la tipología de datos adicional. |
| `quantfolio.constants` | Constantes compartidas (sesiones por año, umbrales de diagnóstico, etc.). |
