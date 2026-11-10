# Suite de pruebas

La suite está organizada por **responsabilidad observable**, no por un reflejo mecánico de la estructura de
`src/`. Recoge **307 casos** desde 204 funciones y mantiene una única puerta de calidad con cobertura del
100 % de líneas y ramas.

## Propiedad de cada capa

| Capa | Responsabilidad | Ejemplos |
|---|---|---|
| `unit/` | Fórmulas puras, modelos, normalización y validación, sin dobles de transporte. | `PriceSeries`, `MacroSeries`, riesgo, GBM, validadores. |
| `contracts/` | Garantías compartidas por toda implementación pública de `PriceSource`. | Identidad, ventana semántica, lotes, rechazo de tickers vacíos y guardia de implementaciones. |
| `integration/` | Detalles del adaptador, composición entre subsistemas y degradación controlada. | Parseo de proveedores, caché, FRED/ALFRED, divisas, AutoPortfolio, informes y gráficos. |
| `e2e/` | Flujos públicos completos y ejecución real de los seis cuadernos. | Cartera multimoneda y rentabilidades reales ajustadas por inflación. |
| `support/` | Infraestructura determinista compartida; no contiene pruebas recogidas por pytest. | Constructores, fuentes guionizadas, transportes falsos y ejecutor de cuadernos. |

Una garantía vive en la capa más baja que pueda demostrarla de forma directa. Si afecta a todos los proveedores,
pertenece a `contracts/`; el comportamiento exclusivo de un protocolo se prueba una sola vez en `integration/`.
Un `e2e` se reserva para una composición pública que aporta valor por sí misma, no para repetir el detalle de una
capa inferior.

El inventario de la migración y el destino de cada una de las 438 funciones heredadas están en
[`docs/testing/legacy-suite-crosswalk.md`](../docs/testing/legacy-suite-crosswalk.md).

## Reglas de diseño

- Toda prueba es offline. Los transportes de Yahoo, Kraken, Alpha Vantage, FRED y ECB se sustituyen por dobles
  deterministas y los cuadernos bloquean además `socket.create_connection` y `socket.getaddrinfo`.
- No se importan símbolos privados de producción (`_first_column`, `_CheckedPriceSource` ni nombres con prefijo
  `_`). El comportamiento se ejerce a través de modelos, proveedores y flujos públicos.
- No se cuentan llamadas para fijar el orden o el número de pasos internos de una implementación. Se permite
  observar la frontera pública de un proveedor o transporte cuando la garantía sea «no debe existir E/S»,
  «la petición va a esta familia» o «la caché debe reutilizar o refrescar», nunca para congelar el grafo de llamadas.
- Los dobles viven en `tests/support/`; no se duplican clases de proveedor o payloads completos en cada módulo.
- Las pruebas no dependen del reloj, de la red, de credenciales ni de un backend gráfico interactivo. Matplotlib usa
  `Agg` y los tests cierran las figuras que abren.
- No se añaden marcadores de capa: cada capa se ejecuta por ruta, de modo que la suite completa sigue siendo una sola
  puerta para CI.

## Ejecución

```console
uv run pytest                         # suite completa + cobertura exigida al 100 %
uv run pytest tests/unit              # fórmulas, modelos y validación
uv run pytest tests/contracts         # contrato común de proveedores
uv run pytest tests/integration       # adaptadores y composición
uv run pytest tests/e2e               # flujos públicos y cuadernos offline
```

Pytest escribe `coverage.xml`, `junit.xml` y el resumen usado por CI. La configuración de cobertura es de ramas y
`--cov-fail-under=100`; una capa ejecutada por separado puede no cubrir todo el paquete, pero la puerta completa sí.

## Infraestructura compartida

- `support/builders.py`: calendarios, series de precios, series macro y CPI deterministas.
- `support/sources.py`: fuentes guionizadas con ventana semántica y respuestas explícitas.
- `support/transports.py`: dobles de Yahoo, Kraken, Alpha Vantage, FRED y ECB.
- `support/providers.py`: matriz de los cinco casos públicos de `PriceSource` usada por el contrato.
- `support/notebooks.py`: ejecución directa de las celdas de código, en un espacio de nombres nuevo y un directorio
  temporal, con todos los transportes simulados. No requiere `nbclient` ni una red activa.

Al añadir un proveedor público, debe incorporarse a `contract_cases()` y `public_source_classes()` para que la
guardia del contrato falle si queda fuera. Al añadir un cuaderno, debe incorporarse a `NOTEBOOKS` para obtener
ejecución offline y la política de formato. Al migrar o retirar una prueba, el cruce de la suite heredada debe
actualizarse en el mismo cambio.
