# Quantfolio – Taller B1-T1 – MIAX 15

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
- **Limpieza y alineación temporal** explícitas, con diagnósticos de cobertura sobre fechas comunes.
- **Monte Carlo parametrizable** (trayectorias, horizonte, valor inicial, supuestos de rentabilidad y volatilidad y
  periodos por año), aplicable a un activo individual o a la cartera completa, con visualización de trayectorias y
  distribuciones.
- **Informes** Markdown parametrizables (`.report()`) y panel analítico de gráficos (`.plots_report()`).
- **Calidad de código**: tipado estricto (`mypy --strict`), `ruff` con `select = ["ALL"]` y las excepciones
  documentadas en `pyproject.toml`, pruebas sin red y cobertura de ramas ≥ 80 % (actual: 100 %), hooks de
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

## Uso

El punto de entrada reproducible del taller es el cuaderno
[`notebooks/quantfolio_demo.ipynb`](notebooks/quantfolio_demo.ipynb), que recorre la ingesta, el modelado, el
informe, los gráficos y las simulaciones de principio a fin:

```console
uv run jupyter lab notebooks/quantfolio_demo.ipynb
```

Los cuadernos fijan `END = "2026-11-06"` para que sus resultados sean reproducibles; como `END` es
exclusivo, la última sesión incluida es 2026-11-05 en todos los mercados.

### Carteras por clase de activo

Cada clase tiene su propio cuaderno reproducible, con la misma estructura de ingesta, informe, gráficos y
Monte Carlo:

| Cuaderno | Universo | Anualización |
|---|---|---|
| [`portfolio_stocks.ipynb`](notebooks/portfolio_stocks.ipynb) | AAPL, JPM, JNJ, XOM, WMT | 252 sesiones |
| [`portfolio_indices.ipynb`](notebooks/portfolio_indices.ipynb) | SPY, QQQ, IWM, EFA, EEM | 252 sesiones |
| [`portfolio_fixed_income.ipynb`](notebooks/portfolio_fixed_income.ipynb) | SHY, IEF, TLT, LQD, HYG | 252 sesiones |
| [`portfolio_crypto.ipynb`](notebooks/portfolio_crypto.ipynb) | BTC/USD, ETH/USD, SOL/USD, ADA/USD | 365 días |

Todos los ejemplos están denominados en USD para no mezclar divisas. El cuaderno de cripto usa 365 periodos
porque su calendario cotiza todos los días; el resto usa 252 sesiones.

### Ejemplo mínimo

```python
from quantfolio import (
    CachedPriceSource,
    KrakenSource,
    MonteCarloParameters,
    Portfolio,
    YahooFinanceSource,
)

yahoo = CachedPriceSource(YahooFinanceSource(), cache_dir="data")
kraken = KrakenSource()
assets = {
    **yahoo.get_many(["AAPL", "SPY", "IEF"], start="2025-01-02"),
    **kraken.get_many(["BTC/USD"], start="2025-01-02"),
}
portfolio = Portfolio(
    assets=assets,
    weights={"AAPL": 0.35, "SPY": 0.30, "IEF": 0.25, "BTC/USD": 0.10},
)

print(portfolio.report())  # informe Markdown
portfolio.plots_report()  # panel analítico de gráficos

simulations = portfolio.simulate_monte_carlo(
    MonteCarloParameters(n_paths=1_000, horizon=252, seed=42)
)
portfolio.plot_simulation(simulations)
```

## Estructura del proyecto

```text
.
├── src/quantfolio/          # biblioteca: solo código importable y tipado
│   ├── __init__.py          # API pública
│   ├── constants.py         # constantes compartidas
│   ├── models.py            # PriceSeries y limpieza numérica
│   ├── portfolio.py         # Portfolio: pesos, alineación, métricas, informes y Monte Carlo
│   ├── simulation.py        # motor GBM y MonteCarloParameters
│   ├── risk.py              # medidas puras de riesgo: drawdown, Sharpe, CAGR, VaR y CVaR
│   ├── validation.py        # validadores de entrada compartidos
│   ├── reporting.py         # informes Markdown y visualizaciones
│   ├── macro.py             # MacroSeries y proveedor FRED vía ALFRED (vintages)
│   └── sources/             # contrato PriceSource + Yahoo, Kraken y caché CSV
│       └── alpha_vantage/   # proveedor opcional: cliente, capacidades y provider
├── notebooks/               # punto de entrada y carteras por clase de activo
│   ├── quantfolio_demo.ipynb
│   ├── portfolio_stocks.ipynb
│   ├── portfolio_indices.ipynb
│   ├── portfolio_fixed_income.ipynb
│   └── portfolio_crypto.ipynb
├── tests/                   # suite sin red, con dobles de proveedor
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

El método `summary(periods_per_year=252)` devuelve `mean_daily_return`, `daily_volatility`,
`annualized_return_approx`, `annualized_volatility`, `max_drawdown` y `sharpe_ratio`.

### `Portfolio`

Un **cartera de inversión** es una colección de activos junto con la fracción del capital invertido en cada uno
(las ponderaciones). `Portfolio` la modela como una DataClass de dos diccionarios (`assets` y `weights`) y:

- valida que cada activo tenga ponderación, que las claves coincidan con los tickers y que los pesos sean finitos y
  no negativos;
- **normaliza** las ponderaciones para que sumen 1 (acepta pesos arbitrarios como `{AAPL: 35, SPY: 25, ...}`);
- agrega los activos en una tabla de precios por fecha, calcula rentabilidades diarias ponderadas y estadísticos
  anualizados, y ofrece informe, gráficos y simulación de Monte Carlo.

La cartera expone `max_drawdown()`, `sharpe_ratio(periods_per_year=...)`, `value_at_risk(confidence=...)` y
`conditional_value_at_risk(confidence=...)`, y `report()` acepta `risk_free_rate` y `confidence`.

## Ingesta multifuente

| Proveedor | Clase | Tipología | Autenticación | Ejemplos de ticker |
|---|---|---:|---|---|
| Yahoo Finance | `YahooFinanceSource` | acciones, ETF y índices | no | `AAPL`, `SPY`, `^GSPC`, `^IBEX` |
| Kraken | `KrakenSource` | criptomonedas (OHLC diario) | no | `BTC/USD`, `ETHUSD` |
| Alpha Vantage (opcional) | `AlphaVantageSource` | acciones, índices, FX, cripto y materias primas diarias | `ALPHA_VANTAGE_API_KEY` | `IBM`, `FX:EUR/USD`, `COMMODITY:WTI` |
| FRED/ALFRED | `FredMacroSource` | indicadores macro y tipos de interés, con vintages punto-en-el-tiempo (`as_of`) | no | `DGS10`, `CPIAUCSL` |
| Caché CSV local | `CachedPriceSource` | envoltorio sobre cualquier proveedor | no | — |

Todos los proveedores de precios implementan el contrato `PriceSource` (`sources/base.py`) y devuelven objetos
`PriceSeries` idénticos y compatibles entre sí, con independencia de la API consultada. `get_many()` permite
descargar varias series a partir de una lista de activos (en lote, secuencial).

Las descargas macro (`FredMacroSource`) usan el endpoint de **ALFRED**, el archivo de vintages de FRED: sin vintage
solicitado sirve los mismos valores que FRED, y cada `MacroSeries` registra en su campo `vintage_date` el vintage del
que proceden los valores. `get_series(..., as_of="AAAA-MM-DD")` devuelve los valores publicados hasta esa fecha,
evitando el sesgo anticipado por revisiones y por el retraso de publicación de los indicadores; el parámetro `end`
de `get_series` es exclusivo, igual que en `PriceSource`. Si ALFRED sirve un vintage distinto del solicitado —por
ejemplo, cuando recorta una fecha futura hasta su último vintage disponible—, `get_series` lanza un `ValueError` en
lugar de etiquetar los valores con una fecha a la que no pertenecen.

`CachedPriceSource` envuelve a otro proveedor y guarda cada serie en `data/<proveedor>/<ticker-saneado>.csv`
(por ejemplo, `BTC/USD` → `BTC-USD.csv`); el archivo se reutiliza mientras empiece antes de la fecha solicitada
y su último dato siga vigente (margen configurable con `ttl_days`), y se reemplaza en caso contrario o con
`refresh=True`. El CSV guarda el ticker solicitado en una columna `ticker`, de modo que dos tickers que sanean al
mismo nombre de archivo nunca comparten precios; si la columna no coincide con el ticker pedido, la entrada se
trata como un fallo de caché. Los CSV escritos por versiones anteriores, sin la columna `ticker`, se aceptan solo
cuando el ticker no necesita saneado (el nombre del fichero coincide exactamente con el ticker); en caso contrario
la entrada cuenta como fallo de caché y se regenera.

### Alpha Vantage opcional

`create_price_source_registry()` devuelve un registro inmutable con `yahoo`, `kraken` y, solo tras una validación
correcta, `alpha-vantage`. Configure la clave como variable de proceso (sin cargador `.env`):
`export ALPHA_VANTAGE_API_KEY='...'`. Si falta, está agotada o no es válida, se avisa en español y el trabajo sigue
con las fuentes disponibles; no hay fallback automático.

| Ticker | Semántica diaria |
|---|---|
| `IBM` | free: bruto y compacto; premium: ajustado e histórico completo |
| `INDEX:SP500` / `INDEX:<símbolo>` | exige premium y autorización de índices |
| `FX:EUR/USD`, `CRYPTO:BTC/EUR` | FX histórico completo y cripto diaria |
| `COMMODITY:WTI`, `BRENT`, `NATURAL_GAS`, `GOLD`/`XAU`, `SILVER`/`XAG` | materias primas diarias admitidas |

La procedencia indica `free, raw` o `premium, adjusted` para acciones y `(<plan>, daily)` para el resto. El inicio
siempre valida la clave con una petición; con caché fresca usa una petición, y sin ella dos en free o tres en premium.
Las capacidades se almacenan 24 horas en `data/alpha-vantage/capabilities/` con una huella SHA-256. Una denegación
posterior rebaja el plan o deshabilita solo índices, sin reintento ni datos de menor frecuencia.

## Limpieza y alineación temporal

- La limpieza se aplica en `PriceSeries`: nada de `NaN`, valores no finitos, precios no positivos, índices sin
  ordenar o duplicados, ni marcas de zona horaria.
- La alineación entre activos con calendarios bursátiles distintos es **explícita**: `Portfolio.get_returns()` usa
  la **intersección** de fechas de negociación (inner join), de modo que cada rentabilidad se calcula con precios
  observados el mismo día en todos los activos. `get_prices()` conserva la unión de calendarios con `NaN` visibles.
- `alignment_summary()` cuantifica el efecto: fechas de la unión, fechas comunes y ratio de cobertura; el informe
  incorpora estos diagnósticos y avisa cuando la alineación descarta más del 10 % de las fechas.

## Validación de entradas (análisis y justificación)

El toolkit **restringe** los inputs en lugar de admitir cualquier objeto con aspecto de serie temporal, por tres
razones:

1. **Corrección analítica**: métricas como la rentabilidad logarítmica o la volatilidad dejan de ser válidas con
   precios negativos o nulos, y las covarianzas de cartera son falsas si los calendarios no están alineados.
   Aceptar esos datos produce resultados silenciosamente incorrectos, el peor fallo posible en un contexto
   cuantitativo.
2. **Detección temprana de errores**: validar en el constructor (ticker vacío, `pandas.Series` incorrecta, índice
   que no es `DatetimeIndex`, claves y pesos incoherentes, parámetros fuera de rango) convierte errores de datos en
   excepciones inmediatas con mensajes claros en español, en lugar de fallos lejanos y opacos.
3. **Homogeneidad**: las restricciones definen el contrato interno (`PriceSeries`) que todos los proveedores
   cumplen, y son la base de la interoperabilidad entre APIs que pide el enunciado.

El coste asumido es que no se admiten series atípicas (p. ej. valores negativos, propios de precios de energía en
algunos mercados) — una limitación consciente y documentada en lugar de un comportamiento accidental.

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

- `Portfolio.report()` genera el informe Markdown parametrizable: composición, métricas históricas, calidad de los
  datos y advertencias de riesgo, con opciones `periods_per_year`, `include_quality`, `include_warnings`,
  `risk_free_rate` y `confidence`. Las advertencias se derivan del estado real de la cartera (cobertura de
  alineación, volatilidad elevada, caída profunda, concentración superior al 50 %, intervalos de varios días e
  historia corta), no de supuestos fijos.
- El informe incluye, además de la composición y las métricas básicas, la máxima caída
  histórica, el ratio de Sharpe, el VaR y el CVaR históricos al 95 %, la rentabilidad geométrica
  (CAGR), la deriva del logaritmo usada por Monte Carlo y el error estándar de la rentabilidad
  anualizada. `risk_free_rate` y `confidence` son parámetros del método.
- La sección de calidad muestra el periodo de la muestra, los años de historia, la cobertura por
  activo y el porcentaje de intervalos entre retornos que abarcan más de un día natural.
- `Portfolio.plots_report()` muestra el panel analítico: evolución de precios **reajustada a base 100**,
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
uv run pytest              # pruebas + cobertura (falla por debajo del 80 %)
uv run pre-commit run --all-files  # quinta puerta, local (incluye hooks de higiene)
```

La suite vive en `tests/`, no toca la red (los proveedores se sustituyen por dobles) y cubre validaciones,
limpieza, alineación, caché, simulaciones y generación de informes. GitHub Actions repite cuatro de los cinco
controles —todos salvo `pre-commit`, que es una puerta local— en cada *pull request* y en cada `push` a `main`
(flujo [`ci.yml`](.github/workflows/ci.yml)) y
publica la evidencia de cada ejecución: un resumen en la página del *run* y el artefacto `test-report` con
`coverage.xml`, `junit.xml` y `test-summary.json`. En los *pull requests* se añade además un comentario con la
evidencia consolidada de las pruebas y del análisis de calidad. La rama `main` está protegida: los `push`
directos están rechazados —también para la administración—, toda contribución llega mediante un *pull request*
y sus dos comprobaciones obligatorias, `Quality gates` y `Strict analysis`, deben pasar sobre la revisión
exacta que se fusiona. No se exige revisión aprobatoria, así que cada autor puede fusionar su propio *pull
request* una vez que ambas comprobaciones están en verde.

### Análisis estático con SonarQube

El proyecto se analiza contra la instancia SonarQube del equipo con la configuración más estricta posible: los
perfiles de calidad `Python Strict` e `IPython Strict` (442 y 443 reglas activas respectivamente: todas las del
analizador) y el *quality gate* `Quantfolio Strict`, que exige cero incidencias, 100 % de cobertura de líneas y
ramas, 0 % de duplicación y calificaciones A/A/A, tanto en el código total como en el código nuevo. La única
excepción documentada es `python:S1722` («New-style classes should be used»), una regla heredada de Python 2 que
no aplica a Python 3 y que está desactivada en el perfil. La regla `ipython:S113` («Files should end with a
newline») está además excluida para los cuadernos: `ruff format`, obligatorio en los hooks de pre-commit,
normaliza el código de cada celda sin salto de línea final, de modo que la regla no puede satisfacerse en un
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
la revisión validada —la fusión del *pull request* o el `push` a `main`— con `fetch-depth: 0` y registra esa
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

Los tres secretos deben existir además como secretos de Dependabot, de modo que sus *pull requests* también
pasen el análisis. Cuando el *quality gate* no está en verde, el paso del escáner falla (por
`sonar.qualitygate.wait=true`) y el flujo queda en rojo.

### Evidencia de cada ejecución

Cada ejecución deja rastro verificable de qué se comprobó y sobre qué revisión:

- **Resumen del *run***: el trabajo de pruebas publica commit, cobertura y desglose de la suite; el análisis
  publica el estado del *quality gate* con todas sus condiciones, las incidencias abiertas por regla y fichero,
  la cobertura, la duplicación y la tarea de proceso (identificador del análisis y enlace al *dashboard*).
- **Artefactos descargables**: `test-report` (`coverage.xml`, `junit.xml`, `test-summary.json`) y `sonar-report`
  (`report-task.txt` y `gate-summary.json`), enlazados desde la página del *run*.
- **Comentario en el *pull request***: un comentario se actualiza con la evidencia consolidada —commit, estado de
  ambas comprobaciones, cobertura, recuento de pruebas, estado del *quality gate* y enlace al *dashboard*— cada
  vez que se publica una revisión nueva.
- **Análisis indexado en SonarQube**: el informe JUnit queda registrado en el servidor (`sonar.python.xunit.reportPath`),
  junto a la cobertura y a la revisión exacta analizada.

La protección de la rama `main` exige que `Quality gates` y `Strict analysis` terminen en verde sobre la revisión
que se va a fusionar; el creador del *pull request* puede fusionarlo él mismo porque no se exige revisión
aprobatoria.

## Limitaciones y advertencias

- La biblioteca **no convierte divisas**: los ejemplos usan activos denominados en USD para que las
  comparaciones sean monetariamente homogéneas. Mezclar activos en otras monedas sigue siendo responsabilidad de
  quien construye la cartera.
- Kraken solo conserva las últimas 720 velas diarias (≈2 años). Si `START` queda fuera de esa ventana,
  `KrakenSource` lanza un error explicativo en lugar de devolver una serie truncada. Para recuperar el cuaderno,
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
| Ingesta multifuente y salida estandarizada | `sources/` (Yahoo, Kraken, Alpha Vantage opcional, caché) devolviendo `PriceSeries`; `get_many()` en lote; FRED (`macro.py`, vintages ALFRED) como tipología adicional. |
| Modelado: series y cartera | `PriceSeries` (DataClass, estadísticos automáticos) y `Portfolio` (agregación, pesos normalizados y correlaciones, calculadas en `plots_report`). |
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
