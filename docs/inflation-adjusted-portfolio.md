# Análisis de la cartera en poder adquisitivo

La vista real es optativa. La cartera conserva sus métricas nominales habituales y, cuando se aporta un índice de precios, añade una comparación mensual en la divisa de reporte. El usuario debe elegir un índice adecuado para esa divisa; Quantfolio no lo descarga automáticamente ni supone que un IPC de otra economía sea equivalente.

## Índice y fórmula

`inflation_index` debe ser un `MacroSeries` de **niveles mensuales de un índice de precios**, con una observación positiva por mes de referencia. Una tasa interanual de inflación, una serie diaria o un nivel ya expresado como variación porcentual no sirve. Se rechazan meses duplicados o interiores ausentes. Las fechas originales del IPC se interpretan como meses de referencia; la salida se etiqueta con el último día de cada mes.

La cartera calcula primero los rendimientos de cada activo en su divisa de reporte y los agrega según sus ponderaciones. Después compone los rendimientos diarios de la cartera dentro de cada mes y aplica:

$$
R^{\mathrm{real}}_t = \frac{1 + R^{\mathrm{nominal}}_t}{I_t / I_{t-1}} - 1,
$$

donde $I_t$ es el nivel del índice de precios para el mes $t$. Se exige `reporting_currency` explícita. La comparación del informe usa exactamente los mismos meses para las columnas nominal y real: rentabilidad acumulada, CAGR, volatilidad anualizada a partir de rendimientos mensuales y máxima caída. Con un único mes coincidente, solo se presenta la rentabilidad acumulada; las otras medidas figuran como «No disponible».

Cada rendimiento mensual necesita cierres de cartera al final de ese mes y del anterior. Se omite el primer mes si no existe un cierre previo completo, así como el último si la historia termina antes del cierre mensual. Se rechazan meses interiores incompletos. Para calendarios sin negociación en fin de semana se toma el último día laborable de lunes a viernes; si la serie tiene cotizaciones en fin de semana se exige el último día natural. Esta aproximación no incorpora festivos específicos de cada mercado y puede excluir conservadoramente un mes cuyo último día laborable fue festivo.

El IPC se publica después de su mes de referencia. Por ello, el último mes de rentabilidad puede quedar fuera del informe real aunque ya existan precios de mercado. El informe muestra el identificador de la serie, su vintage si se conoce y el periodo efectivamente comparado. Los resultados históricos son **retrospectivos**: el vintage más reciente puede incorporar revisiones y no representa necesariamente la información disponible en cada fecha pasada. Para un análisis punto en el tiempo, se puede pedir un vintage concreto con `FredMacroSource.get_series(..., as_of=...)`; su fecha limita los meses que existían en esa publicación.

La convención de precios de cada proveedor también importa. Yahoo usa el cierre ajustado por dividendos y desdoblamientos (`auto_adjust=True`); Alpha Vantage puede entregar cierre bruto en el plan gratuito y ajustado en el premium; Kraken aporta cierres de velas sin flujos de caja. La deflactación transforma las rentabilidades que ya proporciona cada fuente y no añade dividendos o cupones ausentes.

## Escenario de Monte Carlo

`simulate_real_monte_carlo(parameters, annual_inflation_rate=0.03)` conserva exactamente las trayectorias nominales generadas con los mismos parámetros y semilla. Para el paso $s$ y $p$ periodos por año, divide cada valor por $(1+\pi)^{s/p}$, con una tasa fija $\pi > -1$. El resultado queda etiquetado en `DataFrame.attrs["scenario"]` como escenario de poder adquisitivo con inflación fija. La inflación **no modifica** los rendimientos simulados de los activos, sus correlaciones ni su volatilidad; solo cambia la unidad de medida de las trayectorias. No es una previsión de inflación ni una cartera de cobertura de inflación.

El cuaderno [`portfolio_stocks.ipynb`](../notebooks/portfolio_stocks.ipynb) muestra una cartera USD con el índice mensual no desestacionalizado [`CPIAUCNS`](https://fred.stlouisfed.org/series/CPIAUCNS). El [BLS](https://www.bls.gov/cpi/factsheets/escalation.htm) describe el uso de los periodos mensuales de referencia; la fórmula exacta de rendimientos reales coincide con la empleada en [investigación de asignación de activos](https://www.mit.edu/~kothari/attach/KS%20Inflation%20paper%20March%202000.pdf).
