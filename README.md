# Quantfolio: Taller B1-T1 (MIAX 15)

**Quantfolio** es un *toolkit* modular en Python para la extracción multifuente de datos bursátiles, el análisis de
series de precios y la gestión y simulación de carteras mediante Monte Carlo. Su arquitectura desacopla la capa de
ingesta e integración de APIs de la capa de análisis y modelado, y normaliza la salida en objetos internos
homogéneos e interoperables: cualquier proveedor de datos devuelve los mismos objetos `PriceSeries`, de modo que
añadir una API nueva no altera el núcleo del sistema.

## Integrantes

Taller desarrollado por [Alejandro Pérez Pujante](https://github.com/alejandroperezpujante) y Antonio Alberto Presa
Ortega.

## Características principales

- **Ingesta multifuente** de acciones, índices, criptomonedas e indicadores macroeconómicos, con salida estandarizada
  (`PriceSeries`, `MacroSeries`).
- **Extracción por lotes**: `get_many()` descarga N series a partir de una lista de activos.
- **Caché CSV** opcional, aplicable sobre cualquier proveedor y reutilizada mientras el archivo cubre el intervalo
  solicitado.
- **Modelado con DataClasses**: `PriceSeries` calcula media y desviación típica automáticamente al instanciarse;
  `Portfolio` valida y normaliza las ponderaciones y agrega múltiples activos.
- **Análisis multimoneda diario**: convierte precios locales a una divisa de reporte antes de calcular
  rentabilidades, riesgo, gráficos e hipótesis de Monte Carlo, con trazabilidad de cada observación FX.
- **Limpieza y alineación temporal** explícitas, con diagnósticos de cobertura sobre fechas comunes.
- **Monte Carlo parametrizable** (trayectorias, horizonte, valor inicial, supuestos de rentabilidad y volatilidad y
  periodos por año), aplicable a un activo individual o a la cartera completa, con visualización de trayectorias y
  distribuciones.
- **Informes** Markdown parametrizables (`.report()`) y panel analítico de gráficos (`.plots_report()`).
- **Calidad de código**: tipado estricto (`mypy --strict`), `ruff` con `select = ["ALL"]` y las excepciones
  documentadas en `pyproject.toml`, pruebas sin red y cobertura de líneas y ramas del 100 %, hooks de
  pre-commit e integración continua en GitHub.

## Requisitos

- Python 3.14 (gestionado por `uv` a partir de `.python-version`).
- [`uv`](https://docs.astral.sh/uv/) como gestor del entorno y las dependencias.
- Conexión a internet para descargar datos de los proveedores. Las pruebas no la necesitan: todos los proveedores
  están simulados en la suite.

## Instalación paso a paso

```console
git clone https://github.com/alejandroperezpujante/quantfolio.git
cd quantfolio
uv sync
```

`uv sync` crea el entorno virtual, instala las dependencias y el paquete `quantfolio` en modo editable; no hace
falta configurar `PYTHONPATH` ni marcar carpetas como *sources root*.

### Desarrollo en Dev Container

El repositorio incluye un entorno Linux con Python 3.14, `uv` y las herramientas de calidad fijadas por
`uv.lock`, además de un servidor SonarQube local conectado a PostgreSQL. Requiere Docker con Docker Compose
y un IDE o servicio compatible con la especificación Dev Container (GitHub Codespaces y los IDE de JetBrains,
entre otros). La configuración está en `.devcontainer/devcontainer.json`, que esas herramientas leen para
construir y abrir el entorno. La primera creación construye la imagen e instala las dependencias; los
siguientes arranques reutilizan la imagen y los volúmenes del servidor.

Las herramientas `ruff`, `mypy` y `pre-commit` quedan instaladas y disponibles directamente en el `PATH`.
El entorno del proyecto se encuentra en `/home/developer/quantfolio-venv`; `uv sync --frozen` lo actualiza
según `uv.lock` sin volver a resolver versiones. Ejecuta las comprobaciones habituales con:

```console
ruff check .
ruff format --check .
mypy src tests
uv run pytest
uv run pre-commit run --all-files
```

SonarQube se publica en `http://localhost:9000`. En el primer acceso, inicia sesión con `admin` / `admin`,
cambia la contraseña y crea el proyecto con la clave `quantfolio`. En el modo conectado de SonarLint para
tu IDE, crea una conexión llamada `quantfolio-local` a `http://sonarqube:9000` y guarda un *user token*
generado en el servidor. La contraseña de administración y el token quedan en el almacenamiento local del
IDE, nunca en el repositorio. La contraseña de la base de datos se genera al crear el entorno y queda en el
archivo local ignorado `.devcontainer/sonar.env`.

El servidor local usa SonarQube Community Build y sus perfiles predeterminados; no replica automáticamente
los perfiles ni la puerta de calidad privados del servidor del equipo. El análisis en el editor es una ayuda
local; las comprobaciones obligatorias siguen siendo las de CI. Para ejecutar los seis cuadernos en orden y
sin sobrescribir los archivos fuente, usa:

```console
uv run jupyter nbconvert --to notebook --execute \
  --output-dir /tmp/quantfolio-notebooks notebooks/*.ipynb
```

La ejecución requiere acceso a Internet para consultar las fuentes de mercado y macroeconómicas; el cuaderno de
multidivisa usa una respuesta ECB guardada para poder ejecutarse sin red. Las pruebas de `pytest` también son
independientes de la red. Los datos descargados se guardan en la caché local.

## Uso

El punto de entrada reproducible del taller es el cuaderno
[`notebooks/quantfolio_demo.ipynb`](notebooks/quantfolio_demo.ipynb), que recorre la ingesta, el modelado, el
informe, los gráficos y las simulaciones de principio a fin:

```console
uv run jupyter lab notebooks/quantfolio_demo.ipynb
```

Los cuadernos fijan `END = "2026-11-06"` para que sus resultados sean reproducibles; como `END` es
exclusivo, ninguna observación de esa fecha entra en el análisis. La última fecha efectiva depende del
calendario y de la disponibilidad de cada proveedor, así que no tiene por qué coincidir entre mercados.

### Carteras por clase de activo

Cada clase tiene su propio cuaderno reproducible, con la misma estructura de ingesta, informe, gráficos y
Monte Carlo:

| Cuaderno | Universo | Anualización |
|---|---|---|
| [`portfolio_stocks.ipynb`](notebooks/portfolio_stocks.ipynb) | AAPL, JPM, JNJ, XOM, WMT | 252 sesiones |
| [`portfolio_indices.ipynb`](notebooks/portfolio_indices.ipynb) | SPY, QQQ, IWM, EFA, EEM | 252 sesiones |
| [`portfolio_fixed_income.ipynb`](notebooks/portfolio_fixed_income.ipynb) | SHY, IEF, TLT, LQD, HYG | 252 sesiones |
| [`portfolio_crypto.ipynb`](notebooks/portfolio_crypto.ipynb) | BTC/USD, ETH/USD, SOL/USD, ADA/USD | 365 días |
| [`portfolio_multi_currency.ipynb`](notebooks/portfolio_multi_currency.ipynb) | Activos didácticos EUR y USD; tipos ECB y manuales | Calendario diario |

Los cuatro cuadernos por clase de activo están denominados en USD para no mezclar divisas. El cuaderno de
multidivisa compara activos EUR y USD en una cartera con reporte EUR. El cuaderno de cripto usa 365 periodos
porque su calendario cotiza todos los días; el resto usa 252 sesiones.

### Ejemplo mínimo

```python
from quantfolio import AutoPortfolio, AutoPortfolioConfig, MonteCarloParameters

portfolio = AutoPortfolio(
    AutoPortfolioConfig(
        weights={"AAPL": 0.35, "SPY": 0.30, "IEF": 0.25, "BTC/USD": 0.10},
        start="2025-01-02",
    )
)
print(portfolio.report())
portfolio.plots_report()
simulations = portfolio.simulate_monte_carlo(
    MonteCarloParameters(n_paths=1_000, horizon=252, seed=42)
)
portfolio.plot_simulation(simulations)
```

`AutoPortfolio` obtiene los datos durante la construcción. Por defecto utiliza Yahoo para símbolos
ordinarios, Kraken para pares como `BTC/USD` y la caché CSV en `data/`. Si hay un proveedor alternativo
compatible, lo prueba con un aviso: los precios pueden tener ajustes o mercados distintos. Alpha Vantage
no comunica la divisa de sus acciones; si se utiliza como alternativa, indícala en `quote_currencies` y,
si también falta la unidad de los precios crudos, en `quote_units`.
Las carteras con varias divisas requieren `reporting_currency`. Los tipos pueden suministrarse manualmente
en `ExchangeRates` o descargarse automáticamente; sin `exchange_rates`, `AutoPortfolio` usa el BCE con
siete días de margen inicial y una antigüedad máxima predeterminada de cuatro días.

`AutoPortfolioConfig` admite `sources`, `provider_priorities` (familias `equity`, `crypto`, `index` y
`prefixed`), `ticker_priorities`, `provider_symbols`, `quote_currencies`, `quote_units` y
`asset_families` para personalizar la ingesta.
`quote_currencies` declara la divisa del activo; `quote_units` declara la unidad de los precios crudos del
proveedor (por ejemplo, `GBp` para peniques). Una unidad manual no vuelve a convertir una serie que el
proveedor ya normalizó. Si la divisa o la unidad indicadas contradicen los metadatos del proveedor, la
ingesta se detiene para ese activo: el conflicto no activa el proveedor alternativo ni reetiqueta datos.
`asset_families` fuerza la familia de un ticker ambiguo con los valores `equity`, `crypto`, `index` o
`prefixed`; las prioridades por ticker y `provider_symbols` siguen prevaleciendo. `BRK/B` se trata como
acción por defecto, mientras que un par con barra y una cotización alfanumérica de cuatro o más caracteres
exige `asset_families`. Los símbolos cripto compactos, como `ETHUSD`, no se clasifican por su forma: si
quieres tratarlos como cripto, declara `asset_families` y, si se usa Alpha Vantage como alternativa, un
`provider_symbols` como `CRYPTO:ETH/USD`: la biblioteca no adivina cómo dividirlos. En cripto, una cotización
solo se etiqueta como divisa si figura en la tabla fiat del BCE; `ETH/BTC`, `BTC/USDT` y cotizaciones
desconocidas quedan sin divisa. Sin conversión ni overrides, esos mercados siguen siendo válidos como
cartera heredada; para analizarlos en fiat se necesita una serie cuya cotización ya esté expresada en una
divisa admitida.
También permite configurar `cache_enabled`, `cache_dir`, `cache_ttl_days`, `cache_refresh`, `fx_source`,
`exchange_rates`, `fx_lookback_days` y `fx_max_age_days`. Las prioridades por ticker tienen precedencia
sobre las de familia. Usa `reporting_currency` para convertir precios. `end` es exclusivo.

`fx_max_age_days` fija cuántos días puede reutilizarse el último tipo disponible. Si se omite al
descargar tipos, se aplican cuatro días; si se aporta `exchange_rates`, se conserva el `max_age_days` de
la colección y cualquier valor explícito debe coincidir con él. La antigüedad efectiva también determina
el margen inicial de la descarga y la vigencia de la caché FX.

## Estructura del proyecto

```text
.
├── src/quantfolio/          # biblioteca: solo código importable y tipado
│   ├── __init__.py          # API pública
│   ├── constants.py         # constantes compartidas
│   ├── quote_metadata.py    # validación de divisas y unidades de cotización
│   ├── models.py            # PriceSeries y limpieza numérica
│   ├── auto_portfolio.py    # configuración e ingesta automática de carteras
│   ├── portfolio.py         # Portfolio: pesos, alineación, métricas, informes y Monte Carlo
│   ├── simulation.py        # motor GBM y MonteCarloParameters
│   ├── risk.py              # medidas puras de riesgo: drawdown, Sharpe, CAGR, VaR y CVaR
│   ├── validation.py        # validadores de entrada compartidos
│   ├── reporting.py         # informes Markdown y visualizaciones
│   ├── macro.py             # MacroSeries y proveedor FRED vía ALFRED (vintages)
│   ├── currency.py          # selección y conversión de tipos de cambio históricos
│   └── sources/             # contrato PriceSource + Yahoo, Kraken, ECB y caché CSV
│       ├── ecb.py           # proveedor de referencias diarias del ECB
│       └── alpha_vantage/   # proveedor opcional: cliente, capacidades y provider
├── notebooks/               # punto de entrada y carteras por clase de activo
│   ├── quantfolio_demo.ipynb
│   ├── portfolio_stocks.ipynb
│   ├── portfolio_indices.ipynb
│   ├── portfolio_fixed_income.ipynb
│   ├── portfolio_crypto.ipynb
│   └── portfolio_multi_currency.ipynb
├── tests/                   # suite sin red por capas: unit, contracts, integration y e2e
├── docs/                    # investigación de fondo y arquitectura
├── pyproject.toml           # dependencias y configuración de ruff, mypy y pytest
└── uv.lock                  # versiones fijadas de todas las dependencias
```

## Modelo de datos

### `PriceSeries`

DataClass que representa una serie temporal de precios con sus metadatos (`ticker`, `source`) y sus valores
(`prices`). Al instanciarse:

- valida ticker, tipo de serie e índice temporal (`DatetimeIndex`);
- convierte a numérico, elimina `NaN`, valores no finitos y precios no positivos, ordena el índice y elimina
  duplicados;
- calcula automáticamente `mean_price` (media) y `std_price` (desviación típica muestral), como exige el enunciado.
- puede registrar `quote_currency` y `quote_unit`. Los códigos se validan por su forma de tres letras, sin
  comprobar el registro ISO completo; en `quote_unit`, las grafías inequívocas GBX/GBp, ILA y ZAc se interpretan
  como GBP, ILS y ZAR multiplicando los precios por 0,01, y se conserva la unidad original para su trazabilidad.
  Yahoo obtiene la unidad desde sus metadatos; Kraken y Alpha Vantage reconocen la divisa de pares explícitos. Si no se conoce, proporciona la divisa manualmente. La caché antigua puede requerir `refresh=True`.

El método `summary(periods_per_year=252)` devuelve `mean_daily_return`, `daily_volatility`,
`annualized_return_approx`, `annualized_volatility`, `max_drawdown` y `sharpe_ratio`.

### `Portfolio`

Una **cartera de inversión** es una colección de activos junto con la fracción del capital invertido en cada uno
(las ponderaciones). `Portfolio` la modela con los diccionarios `assets` y `weights`, además de opciones de moneda:

- valida que cada activo tenga ponderación, que las claves coincidan con los tickers y que los pesos sean finitos y
  no negativos;
- **normaliza** las ponderaciones para que sumen 1 (acepta pesos arbitrarios como `{AAPL: 35, SPY: 25, ...}`);
- agrega los activos en una tabla de precios por fecha, calcula rentabilidades diarias ponderadas y estadísticos
  anualizados, y ofrece informe, gráficos y simulación de Monte Carlo.
- puede fijar `reporting_currency` y una colección `ExchangeRates`. `get_prices()` mantiene la vista local sobre
  la unión de calendarios; `get_reporting_prices()` aplica la conversión a esa unión estricta y
  `analysis_prices()` limita la conversión a las fechas comunes que alimentan las métricas y los análisis.
  `currency_conversion_diagnostics()` conserva la traza de la unión completa y
  `analysis_currency_conversion_diagnostics()` usa la misma ventana común que el informe. La conversión requiere
  divisa conocida en todos los activos; las carteras antiguas sin divisas siguen disponibles, y sus informes
  indican que no se evaluó la conversión.

`ExchangeRates` admite series `PriceSeries` manuales o `ExchangeRates.from_source(...)`. Los tickers usan el orden
`FX:AAA/BBB`: cada valor expresa unidades de `BBB` por una unidad de `AAA`. La resolución usa primero el par directo,
después el inverso y finalmente un cruce por EUR; si un par no tiene una observación anterior dentro del límite de
edad, prueba la siguiente ruta. Los valores no positivos o no finitos se rechazan. Por defecto acepta observaciones
de hasta cuatro días naturales de antigüedad y comprueba ese límite para cada tramo del cruce. Los diagnósticos y el informe conservan el proveedor,
el par y la fecha de cada tipo aplicado. Las fechas diarias no fijan un corte intradía común.

La cartera expone `max_drawdown()`, `sharpe_ratio(periods_per_year=...)`, `value_at_risk(confidence=...)` y
`conditional_value_at_risk(confidence=...)`, y `report()` acepta `risk_free_rate` y `confidence`.

## Ingesta multifuente

| Proveedor | Clase | Tipología | Autenticación | Ejemplos de ticker |
|---|---|---:|---|---|
| Yahoo Finance | `YahooFinanceSource` | acciones, ETF y índices | no | `AAPL`, `SPY`, `^GSPC`, `^IBEX` |
| Kraken | `KrakenSource` | criptomonedas (OHLC diario) | no | `BTC/USD`, `ETHUSD` |
| Alpha Vantage (opcional) | `AlphaVantageSource` | acciones, índices, FX, cripto y materias primas diarias | `ALPHA_VANTAGE_API_KEY` | `IBM`, `FX:EUR/USD`, `COMMODITY:WTI` |
| ECB Data Portal | `ECBExchangeRateSource` | tipos de cambio diarios EUR/otra divisa | no | `FX:EUR/USD` |
| FRED/ALFRED | `FredMacroSource` | indicadores macro y tipos de interés, con vintages punto-en-el-tiempo (`as_of`) | no | `DGS10`, `CPIAUCSL` |
| Caché CSV local | `CachedPriceSource` | envoltorio sobre cualquier proveedor | no | — |

Todos los proveedores de precios implementan el contrato `PriceSource` (`sources/base.py`) y devuelven objetos
`PriceSeries` idénticos y compatibles entre sí, con independencia de la API consultada. `get_many()` permite
descargar varias series a partir de una lista de activos (en lote, secuencial).

`ECBExchangeRateSource` implementa `PriceSource` para los pares EUR-first `FX:EUR/DIVISA`; devuelve unidades de la
divisa cotizada por EUR a partir del [API diario del ECB](https://data.ecb.europa.eu/help/api/data-examples).
Son tipos de referencia informativos, no precios de ejecución de bróker. La caché CSV conserva la divisa y la unidad
de cotización; los archivos antiguos se leen con esos metadatos desconocidos y no se completan por inferencia.

Las descargas macro (`FredMacroSource`) usan el endpoint de **ALFRED**, el archivo de vintages de FRED: sin vintage
solicitado sirve los mismos valores que FRED, y cada `MacroSeries` registra en su campo `vintage_date` el vintage del
que proceden los valores. `get_series(..., as_of="AAAA-MM-DD")` devuelve los valores publicados hasta esa fecha,
evitando el sesgo anticipado por revisiones y por el retraso de publicación de los indicadores; el parámetro `end`
de `get_series` es exclusivo, igual que en `PriceSource`. Si ALFRED sirve un vintage distinto del solicitado (por
ejemplo, cuando recorta una fecha futura hasta su último vintage disponible), `get_series` lanza un `ValueError`
para no etiquetar los valores con una fecha a la que no pertenecen.

`CachedPriceSource` envuelve a otro proveedor y guarda cada serie en `data/<namespace>/<ticker-saneado>.csv`
(por ejemplo, `BTC/USD` → `BTC-USD.csv`). El subdirectorio procede de `PriceSource.cache_namespace`, que por
defecto coincide con el nombre visible; Alpha Vantage lo especializa para separar la semántica de precio
(`alpha-vantage-free-v2`, `alpha-vantage-premium-v2`). Los directorios antiguos `alpha-vantage/` no identifican
esa semántica: se dejan intactos y se vuelven a descargar los datos. El archivo se reutiliza mientras empiece antes
de la fecha solicitada y su último dato siga vigente (margen configurable con `ttl_days`), y se reemplaza en caso
contrario o con `refresh=True`. El CSV guarda el ticker solicitado en una columna `ticker`, de forma que dos tickers
que sanean al mismo nombre de archivo nunca comparten precios; si la columna no coincide con el ticker pedido, la
entrada se trata como un fallo de caché. Los CSV escritos por versiones anteriores, sin la columna `ticker`, se
aceptan solo cuando el ticker no necesita saneado (el nombre del fichero coincide exactamente con el ticker); en
caso contrario la entrada cuenta como fallo de caché y se regenera. Si `AutoPortfolio` va a interpretar
monetariamente una entrada antigua sin divisa ni unidad conocidas, fuerza su refresco y no reutiliza el CSV
heredado si falla; cuando el refresco tampoco establece la unidad, hay que declararla en `quote_units`.

### Alpha Vantage opcional

`create_price_source_registry()` devuelve un registro inmutable con `yahoo`, `kraken` y, solo tras una validación
correcta, `alpha-vantage`. Configure la clave como variable de proceso (sin cargador `.env`):
`export ALPHA_VANTAGE_API_KEY='...'`. Si falta, está agotada o no es válida, se avisa en español y el trabajo sigue
con las fuentes disponibles, sin fallback automático.

| Ticker | Semántica diaria |
|---|---|
| `IBM` | free: bruto y compacto; premium: ajustado e histórico completo |
| `INDEX:SP500` / `INDEX:<símbolo>` | exige premium y autorización de índices |
| `FX:EUR/USD`, `CRYPTO:BTC/EUR` | FX histórico completo y cripto diaria |
| `COMMODITY:WTI`, `BRENT`, `NATURAL_GAS`, `GOLD`/`XAU`, `SILVER`/`XAG` | materias primas diarias admitidas |

La procedencia indica `free, raw` o `premium, adjusted` para acciones y `(<plan>, daily)` para el resto. El inicio
siempre valida la clave con una petición; con caché fresca usa una petición, y sin ella dos en free o tres en premium.
Las capacidades se almacenan 24 horas en `data/alpha-vantage/capabilities/` con una huella SHA-256. Una denegación
posterior rebaja el plan o deshabilita solo índices; no reintenta la petición ni pide datos de menor frecuencia.

Un cierre bruto y uno ajustado no son equivalentes: los ajustes incorporan eventos corporativos, como dividendos o
splits, y modifican la serie histórica. Yahoo descarga cierres ajustados (`auto_adjust=True`); para acciones, Alpha
Vantage entrega brutos en *free* y ajustados en *premium*. Mezclar ambas semánticas sin documentarlo altera las
rentabilidades y las comparaciones entre proveedores.

## Limpieza y alineación temporal

- La limpieza se aplica en `PriceSeries`: nada de `NaN`, valores no finitos, precios no positivos, índices sin
  ordenar o duplicados, ni marcas de zona horaria.
- La alineación entre activos con calendarios bursátiles distintos es **explícita**: `Portfolio.get_returns()` usa
  la **intersección** de fechas de negociación (inner join), de modo que cada rentabilidad se calcula con precios
  observados el mismo día en todos los activos. `get_prices()` conserva la unión de calendarios con `NaN` visibles.
- `alignment_summary()` cuantifica el efecto: fechas de la unión, fechas comunes y ratio de cobertura; el informe
  incorpora estos diagnósticos y avisa cuando la alineación descarta más del 10 % de las fechas.

## Validación de entradas (análisis y justificación)

El toolkit **restringe** los inputs por tres razones:

1. **Corrección analítica**: métricas como la rentabilidad logarítmica o la volatilidad dejan de ser válidas con
   precios negativos o nulos, y las covarianzas de cartera son falsas si los calendarios no están alineados.
   Aceptar esos datos produce resultados incorrectos que nadie detecta.
2. **Detección temprana de errores**: validar en el constructor (ticker vacío, `pandas.Series` incorrecta, índice
   que no es `DatetimeIndex`, claves y pesos incoherentes, parámetros fuera de rango) convierte errores de datos en
   excepciones inmediatas con mensajes claros en español; sin esa validación, el fallo aparece más tarde y es
   difícil de rastrear.
3. **Homogeneidad**: las restricciones definen el contrato interno (`PriceSeries`) que todos los proveedores
   cumplen, y son la base de la interoperabilidad entre APIs que pide el enunciado.

El coste asumido es que no se admiten series atípicas (p. ej. valores negativos, propios de precios de energía en
algunos mercados); la limitación es consciente y está documentada.

Los validadores compartidos viven en `quantfolio.validation`: la cartera, la serie de precios, el motor de
simulación y las medidas de riesgo los importan desde un único módulo, de modo que la misma entrada inválida
produce el mismo mensaje en español. Los chequeos con contexto propio (por ejemplo, los dos retornos que
necesita la estimación de los supuestos de Monte Carlo) conservan su mensaje específico.

## Simulación de Monte Carlo

El motor modela el valor de la cartera (o el precio de un activo) como un **movimiento browniano geométrico**
(GBM) discreto en periodos de $1/\text{periods\_per\_year}$ años, parametrizado con la **deriva del logaritmo**
$m$ (rentabilidad logarítmica media anualizada) y la volatilidad anualizada $\sigma$:

$$S_t = S_0 \exp\left(m t + \sigma W_t\right)$$

Con esta forma, los caminos simulados reproducen la deriva logarítmica estimada. Es equivalente a la
parametrización clásica de `docs/geometric-brownian-motion.md`,
$S_t = S_0 \exp\left((\mu - \tfrac{1}{2}\sigma^2)t + \sigma W_t\right)$, con
$\mu = m + \tfrac{1}{2}\sigma^2$ la deriva del proceso de precios; el precio esperado crece a $m + \tfrac{1}{2}\sigma^2$ anual.

| Parámetro (`MonteCarloParameters`) | Significado | Valor por defecto |
|---|---|---|
| `n_paths` | número de trayectorias | 1 000 |
| `horizon` | periodos simulados | 252 |
| `initial_value` | valor de partida | último precio (activo) / 10 000 (cartera) |
| `return_assumption` | deriva anualizada del logaritmo, $m$ | estimación histórica |
| `volatility_assumption` | volatilidad anualizada, $\sigma$ | estimación histórica |
| `seed` | semilla del generador | `None` (aleatorio) |
| `periods_per_year` | periodos por año para anualizar y fijar el paso temporal | 252 (365 para cripto) |

Los supuestos históricos se estiman con la media y la desviación típica de las rentabilidades logarítmicas diarias
multiplicadas por `periods_per_year` y $\sqrt{\text{periods\_per\_year}}$, respectivamente. La covarianza entre
activos entra en la simulación de la cartera a través de su volatilidad estimada, $w^{T}\Sigma w$. La simulación es
un **método de `Portfolio`** (`simulate_monte_carlo`) y también está disponible en `PriceSeries` para un activo
individual; `plot_simulation()` muestra las trayectorias y la distribución del valor final de una cartera o del
precio final de un activo. Los cuadernos de
acciones, índice y renta fija usan 252; el de cripto usa 365 y un horizonte de 365 pasos para representar un año
natural.

## Informes

- `Portfolio.report()` genera el informe Markdown parametrizable: composición, divisas y unidades locales, métricas históricas, calidad de los
  datos y advertencias de riesgo, con opciones `periods_per_year`, `include_quality`, `include_warnings`,
  `risk_free_rate` y `confidence`. Las advertencias se derivan del estado real de la cartera: cobertura de
  alineación, volatilidad elevada, caída profunda, concentración superior al 50 %, intervalos de varios días e
  historia corta.
- El informe incluye, además de la composición y las métricas básicas, la máxima caída
  histórica, el ratio de Sharpe, el VaR y el CVaR históricos al 95 %, la rentabilidad geométrica
  (CAGR), la deriva del logaritmo usada por Monte Carlo y el error estándar de la rentabilidad
  anualizada. `risk_free_rate` y `confidence` son parámetros del método.
- La sección de calidad muestra el periodo de la muestra, los años de historia, la cobertura por
  activo y el porcentaje de intervalos entre retornos que abarcan más de un día natural.
- `Portfolio.plots_report()` muestra el panel analítico en la divisa de reporte, si se configuró: evolución de precios **reajustada a base 100**,
  comparativa de rentabilidad acumulada, matriz de correlación y evolución del valor de la cartera (base 100).
- `PriceSeries.plot_simulation()` y `Portfolio.plot_simulation()` visualizan las trayectorias simuladas y la
  distribución final: del precio final en un activo y del valor final en una cartera.

## Arquitectura

El diagrama UML de clases y el flujo del sistema están en [`docs/architecture.md`](docs/architecture.md)
(diagramas Mermaid equivalentes a UML/FossFLOW, renderizables en GitHub).

## Calidad, pruebas e integración continua

```console
uv run ruff check .        # linter (todas las reglas, con las excepciones de pyproject.toml)
uv run ruff format --check .  # formato
uv run mypy src tests      # tipado estricto
uv run pytest              # pruebas + cobertura (falla por debajo del 100 %)
uv run pre-commit run --all-files  # quinta puerta, local (incluye hooks de higiene)
```

La suite vive en `tests/`, no toca la red (los proveedores se sustituyen por dobles) y se organiza por capas:
`unit` para fórmulas y modelos, `contracts` para la interfaz común de proveedores, `integration` para adaptadores y
composición, y `e2e` para flujos públicos y la ejecución real de los seis cuadernos. El criterio de propiedad,
los comandos por capa y las reglas de diseño están en [`tests/README.md`](tests/README.md); el destino de cada prueba
heredada está en [`docs/testing/legacy-suite-crosswalk.md`](docs/testing/legacy-suite-crosswalk.md). GitHub Actions
repite cuatro de los cinco controles (todos salvo `pre-commit`, que es una puerta local) en cada *pull request* y en
cada `push` a `main`
(flujo [`ci.yml`](.github/workflows/ci.yml)) y publica la evidencia de cada ejecución: un resumen en la página
del *run* y el artefacto `test-report` con `coverage.xml`, `junit.xml` y `test-summary.json`. En los *pull
requests* se añade un comentario con la evidencia consolidada de las pruebas y del análisis de calidad. La rama
`main` está protegida: los `push` directos están rechazados (también para la administración), toda contribución
llega mediante un *pull request* y sus dos comprobaciones obligatorias, `Quality gates` y `Strict analysis`,
deben pasar sobre la revisión exacta que se fusiona. No se exige revisión aprobatoria, así que cada autor puede
fusionar su propio *pull request* una vez que ambas comprobaciones están en verde.

### Análisis estático con SonarQube

El proyecto se analiza contra la instancia SonarQube del equipo con la configuración más estricta posible: los
perfiles de calidad `Python Strict` e `IPython Strict` (442 y 443 reglas activas respectivamente: todas las del
analizador) y el *quality gate* `Quantfolio Strict`, que exige cero incidencias, 100 % de cobertura de líneas y
ramas, 0 % de duplicación y calificaciones A/A/A, tanto en el código total como en el código nuevo. La única
excepción documentada es `python:S1722` («New-style classes should be used»), una regla heredada de Python 2 que
no aplica a Python 3 y que está desactivada en el perfil. La regla `ipython:S113` («Files should end with a
newline») está además excluida para los cuadernos: `ruff format`, obligatorio en los hooks de pre-commit,
normaliza el código de cada celda sin salto de línea final, por lo que la regla no puede satisfacerse en un
cuaderno formateado; la exclusión está declarada en `sonar-project.properties`.

```console
uv run pytest    # genera coverage.xml y junit.xml, los informes que consume el analizador
source ~/.config/sonar/quantfolio.env  # define SONAR_HOST_URL y SONAR_TOKEN (nunca se versionan)
sonar-scanner    # analiza src/ + notebooks/ + tests/ y falla si el quality gate no está en verde
```

La configuración del proyecto vive en [`sonar-project.properties`](sonar-project.properties); la URL del servidor
y el token de análisis se pasan por entorno para no versionar secretos.

### Integración continua del análisis

El flujo [`ci.yml`](.github/workflows/ci.yml) se ejecuta en cada *pull request* y en cada `push` a `main`. Su
trabajo `Quality gates` ejecuta cuatro de las cinco puertas locales (todas salvo `pre-commit`) y publica el
artefacto `test-report` (`coverage.xml`, `junit.xml` y `test-summary.json`); a continuación se invoca el flujo
reutilizable [`sonarqube.yml`](.github/workflows/sonarqube.yml), que descarga esos informes, analiza exactamente
la revisión validada (la fusión del *pull request* o el `push` a `main`) con `fetch-depth: 0` y registra esa
revisión en el análisis (`sonar.scm.revision`). Como el flujo del *pull request* solo ejecuta código de las
ramas del propio repositorio, las credenciales nunca se exponen a código de terceros.

El servidor SonarQube vive en la red Tailscale del equipo, así que el flujo se une a ella con
`tailscale/github-action` creando un nodo efímero etiquetado `tag:ci` (se elimina al terminar el trabajo). En
Tailscale hacen falta la etiqueta `tag:ci` con su `tagOwners` y una regla de acceso que la autorice hacia el
servicio `svc:sonar` en el puerto 443. En GitHub, el repositorio necesita estos ajustes, que nunca se versionan:

| Nombre | Tipo | Contenido |
|---|---|---|
| `TS_OAUTH_CLIENT_ID` | secreto | ID de un cliente OAuth de Tailscale con ámbito `auth_keys` y la etiqueta `tag:ci` |
| `TS_OAUTH_SECRET` | secreto | secreto del mismo cliente OAuth |
| `SONAR_TOKEN` | secreto | token de análisis del proyecto `quantfolio` |
| `SONAR_HOST_URL` | variable | URL tailnet de SonarQube (`https://sonar.<tailnet>.ts.net`) |

Los tres secretos deben existir además como secretos de Dependabot, para que sus *pull requests* también
pasen el análisis. Cuando el *quality gate* no está en verde, el paso del escáner falla (por
`sonar.qualitygate.wait=true`) y el flujo queda en rojo.

### Evidencia de cada ejecución

- **Resumen del *run***: el trabajo de pruebas publica commit, cobertura y desglose por capa y fichero; el análisis
  publica el estado del *quality gate* con todas sus condiciones, las incidencias abiertas por regla y fichero,
  la cobertura, la duplicación y la tarea de proceso (identificador del análisis y enlace al *dashboard*).
- **Artefactos descargables**: `test-report` (`coverage.xml`, `junit.xml`, `test-summary.json`) y `sonar-report`
  (`report-task.txt` y `gate-summary.json`), enlazados desde la página del *run*.
- **Comentario en el *pull request***: un comentario se actualiza con la evidencia consolidada (commit, estado de
  ambas comprobaciones, cobertura, recuento por capa, estado del *quality gate* y enlace al *dashboard*) cada
  vez que se publica una revisión nueva.
- **Análisis indexado en SonarQube**: el informe JUnit queda registrado en el servidor (`sonar.python.xunit.reportPath`),
  junto a la cobertura y a la revisión exacta analizada.

## Limitaciones y advertencias

- La conversión de divisas requiere una divisa de reporte, cotizaciones conocidas y tipos de cambio históricos:
  manuales en `ExchangeRates` o descargados automáticamente desde el BCE.

- Kraken solo conserva las últimas 720 velas diarias (≈2 años). Si `START` queda fuera de esa ventana,
  `KrakenSource` lanza un error explicativo y no devuelve una serie truncada. Para recuperar el cuaderno,
  adelanta `START` a una fecha concreta dentro de los últimos ~700 días (por ejemplo `2026-01-02`) y mantén la
  misma fecha en los demás cuadernos para conservar la comparabilidad.
- La descarga por lotes de `get_many()` es secuencial, no concurrente.
- Las rentabilidades históricas no garantizan resultados futuros, y el resultado de Monte Carlo depende de los
  supuestos utilizados.
- La simulación modela el valor agregado de la cartera con un único GBM cuyos parámetros incorporan la covarianza
  histórica; no simula trayectorias individuales por activo.
- Las carteras que mezclan calendarios (por ejemplo, cripto y acciones) calculan los retornos
  sobre la intersección de fechas; algunos intervalos entre retornos abarcan varios días naturales
  y la anualización con 252 o 365 periodos es aproximada. El informe muestra el porcentaje afectado.
  Una cartera de un solo calendario también puede superar el 5 % porque los fines de semana cuentan
  como días naturales, así que la advertencia describe ese porcentaje medido y no afirma que la
  cartera mezcle calendarios.
- Los proveedores externos pueden cambiar sus límites o interfaces (p. ej. Stooq pasó a exigir JavaScript durante
  el desarrollo del taller, por lo que se sustituyó por Kraken, que es una API pública sin clave).

## Correspondencia con el enunciado

| Bloque del taller | Implementación |
|---|---|
| Repositorio y despliegue *plug-and-play* | `pyproject.toml` + `uv.lock` (instalación con `uv sync`), README, `.gitignore`, CI. |
| Ingesta multifuente y salida estandarizada | `sources/` (Yahoo, Kraken, Alpha Vantage opcional, ECB, caché) devolviendo `PriceSeries`; `get_many()` en lote; FRED (`macro.py`, vintages ALFRED) como tipología adicional. |
| Modelado: series y cartera | `PriceSeries` (DataClass, estadísticos automáticos y metadatos de cotización), `ExchangeRates` y `Portfolio` (agregación y análisis opcional en divisa de reporte). |
| Motor Monte Carlo | `Portfolio.simulate_monte_carlo()` y `PriceSeries.simulate_monte_carlo()` con `MonteCarloParameters`; `plot_simulation()`. |
| Limpieza, preprocesado y reportes | Limpieza en `PriceSeries`; alineación explícita con diagnósticos; `.report()` y `.plots_report()`; sección de validación de entradas en este README. |
| Estructura y diagramado | `src/` solo biblioteca, `notebooks/` como entrada reproducible y `docs/architecture.md` con los diagramas. |

## Documentación de fondo

El directorio [`docs/`](docs/README.md) recopila el material de investigación que sustenta el diseño (índices,
volatilidad, GBM, Monte Carlo, matrices de covarianza, indicadores macro, proveedores de datos, etc.), con sus
fuentes.

## Licencia

Este proyecto se distribuye bajo la licencia **MIT**, en régimen de co-autoría. El texto completo y el aviso de
copyright de los coautores están en el archivo [`LICENSE`](LICENSE.txt).

Copyright (c) 2026 Alejandro Pérez Pujante y Antonio Alberto Presa Ortega.
