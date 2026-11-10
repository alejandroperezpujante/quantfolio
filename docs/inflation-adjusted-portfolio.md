# Análisis de la cartera en poder adquisitivo

La vista real es opcional. La cartera conserva sus métricas nominales y, cuando recibe un índice de precios, añade
una comparación mensual en la divisa de reporte. El usuario debe elegir un índice adecuado para esa divisa. Quantfolio
no lo descarga automáticamente ni supone que el IPC de otra economía sirva como equivalente.

## Índice de precios y fórmula

`inflation_index` debe ser un `MacroSeries` con niveles mensuales de un índice de precios y una observación positiva
por mes de referencia. No sirve una tasa interanual de inflación, una serie diaria ni un nivel expresado como
variación porcentual. También se rechaza un índice con meses duplicados o con huecos entre el primer y el último mes.
Las fechas originales del IPC se interpretan como meses de referencia y la salida se etiqueta con el último día de
cada mes.

La cartera calcula primero la rentabilidad de cada activo en la divisa de reporte y la pondera. Después compone los
rendimientos diarios de la cartera dentro de cada mes y aplica:

$$
R^{\mathrm{real}}_t = \frac{1 + R^{\mathrm{nominal}}_t}{I_t / I_{t-1}} - 1,
$$

donde $I_t$ es el nivel del índice de precios para el mes $t$. Se exige una `reporting_currency` explícita. Las
columnas nominal y real del informe cubren exactamente los mismos meses y muestran rentabilidad acumulada, CAGR,
volatilidad anualizada a partir de rendimientos mensuales y máxima caída. Si solo coincide un mes, se presenta la
rentabilidad acumulada y las demás medidas figuran como «No disponible».

Cada rendimiento mensual necesita cierres de cartera al final de ese mes y del anterior. Se omite el primer mes si
no hay un cierre previo completo, y el último si la historia termina antes del cierre mensual. Los meses interiores
incompletos se rechazan. En calendarios sin negociación de fin de semana se toma el último día laborable de lunes a
viernes; si la serie incluye cotizaciones de fin de semana, se exige el último día natural. Esta aproximación no
aplica los festivos de cada mercado, por lo que puede excluir conservadoramente un mes cuyo último día laborable fuera
festivo.

El IPC se publica después de su mes de referencia. Por eso, el último mes de rentabilidad puede quedar fuera del
informe real aunque ya existan precios de mercado. El informe muestra el identificador de la serie, su vintage si se
conoce y el periodo comparado. Los resultados históricos son retrospectivos: el vintage más reciente puede incluir
revisiones y no representa necesariamente la información disponible en cada fecha pasada. Para un análisis punto en
el tiempo, `FredMacroSource.get_series(..., as_of=...)` permite solicitar un vintage concreto; su fecha limita los
meses que existían en esa publicación.

La convención de precios de cada proveedor también importa. Yahoo usa el cierre ajustado por dividendos y
desdoblamientos (`auto_adjust=True`). Alpha Vantage puede entregar cierre bruto en el plan gratuito y ajustado en el
premium. Kraken aporta cierres de velas sin flujos de caja. La deflactación transforma la rentabilidad que ya
proporciona cada fuente y no añade dividendos o cupones ausentes.

## Escenario de Monte Carlo

`simulate_real_monte_carlo(parameters, annual_inflation_rate=0.03)` conserva exactamente las trayectorias nominales
generadas con los mismos parámetros y semilla. Para el paso $s$ y $p$ periodos por año, divide cada valor por
$(1+\pi)^{s/p}$, con una tasa fija $\pi > -1$. El resultado queda etiquetado en `DataFrame.attrs["scenario"]` como
escenario de poder adquisitivo con inflación fija. La inflación no modifica la rentabilidad simulada de los activos,
sus correlaciones ni su volatilidad; solo cambia la unidad de medida de las trayectorias. No es una previsión de
inflación ni una cartera de cobertura de inflación.

El cuaderno [`portfolio_stocks.ipynb`](../notebooks/portfolio_stocks.ipynb) muestra una cartera en USD con el índice
mensual no desestacionalizado [`CPIAUCNS`](https://fred.stlouisfed.org/series/CPIAUCNS). El
[BLS](https://www.bls.gov/cpi/factsheets/escalation.htm) explica el uso de los periodos mensuales de referencia. La
fórmula exacta de rentabilidad real coincide con la empleada en esta
[investigación de asignación de activos](https://www.mit.edu/~kothari/attach/KS%20Inflation%20paper%20March%202000.pdf).
