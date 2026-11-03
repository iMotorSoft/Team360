# TelchiAI — distribución cabecera/líneas y contrato monetario

Investigación READ ONLY y diseño DEVELOPMENT autorizado en `feature/console-backend-core`. Investigación completada en su universo; capability BLOCKED por contrato de denominación, no por ausencia de conciliación completa.

## Resultado ejecutivo

Las diferencias son recurrentes, no excepcionales ni explicadas principalmente por unos pocos documentos. El patrón porcentual es fuerte, pero su causa contable sigue sin acreditarse.

- 29.429 de 30.301 facturas activas tienen diferencia mayor a 0,01: **97,1222 %**. Sólo 872 (2,8778 %) están dentro de ese umbral.
- Diferencia neta cabeceras menos líneas: **842.748,21**; suma absoluta: **897.070,85**. No confundirlas: los importes negativos compensan parcialmente los positivos.
- Las 10/50/100 mayores discrepancias absolutas reúnen **8,1467 % / 19,2042 % / 25,7079 %** del total absoluto. No aparece una concentración del 90 % en esos documentos.
- 20.794 facturas presentan un residuo/DocTotal que redondea a **13,00 %**. Es una HIPÓTESIS_COMPATIBLE con un componente proporcional, no una identificación de impuesto.
- Materia prima: suma de campo `line_total` **839.582,63**, 34 productos, 526 líneas, **495 facturas**, clasificación VALIDATED. Es una observación reproducida, no un neto ni una capability habilitada.
- No se habilitó el importe comercial: falta acreditar independientemente la denominación de LineTotal frente a la columna publicada de moneda. La autorización del owner elimina la espera de decisión de producto; no sustituye esa evidencia semántica.

## Fuente y comparabilidad

La [corrida final](distribution-r3.json) conserva todo el SQL, resultados Decimal, esquemas, linaje, hash del runner y crosswalk. r1/r2 se preservan como iteraciones previas; r3 es la evidencia vigente.

- Foundation `foundation_afd08d9eca6a725be53cdc3f9d5709c9`, snapshot 1408; lectura mediante FoundationReader, nunca latest Atomic. Manifest base 1322.
- Período DocDate `[2026-09-01,2026-10-01)`. Facturas observadas hasta 24/09, NC hasta 23/09. No se certifica septiembre completo ni datos hasta hoy.
- Reference `v2_reference_closure_2088d5885204313a`; clasificación `v2_product_business_type_f9c1130d852ccb61`; crosswalk SHA-256 `7fcfef912cc8ef46868e03b56f90b61da13c08e951c453abc0483690edc36e10`.
- Fuentes tipadas SAP_B1_HANA: OINV/INV1 y, separadamente, ORIN/RIN1. Join por fuente y DocEntry dentro de cada par; grano de línea incluye tabla y LineNum. No ventas/producción ni colisiones OINV/ORIN.
- Cero claves duplicadas/nulas de cabecera/línea y cero líneas huérfanas en la publicación completa de cada par. Los huérfanos no podrían asignarse al período desde una fecha de cabecera inexistente.
- Cero cabeceras del período sin líneas. Cero discrepancias moneda/captura/source_as_of entre cada cabecera y sus líneas activas. Importes no nulos y casteables; una moneda publicada BS en este universo.
- Estos controles acreditan comparabilidad técnica de campos; no son evidencia independiente de la denominación monetaria de LineTotal ni prueba de integridad contable de SAP. Publicación común tampoco implica que las capturas de ventas y NC sean simultáneas.
- 42.147 códigos de crosswalk únicos; 100 % de líneas observadas hacen match. Hay 24.835 líneas de factura de calidad distinta de VALIDATED (SUPPORTED o PROVISIONAL); no todas las categorías tienen la calidad de RAW_MATERIAL. Desglose completo en JSON.

## Distribución por importe

Se usa `delta=DocTotal−SUM(LineTotal)` y materialidad estricta `ABS(delta)>0,01`. Importes en el campo fuente del universo con moneda publicada BS; sin ajustes ni conversiones.

| ABS(delta) | Facturas | % facturas | Delta neta | Suma absoluta |
| --- | ---: | ---: | ---: | ---: |
| ≤0,01 | 872 | 2,8778 | −0,03 | 0,09 |
| (0,01; 1] | 1.951 | 6,4387 | 1.138,70 | 1.149,34 |
| (1; 10] | 15.036 | 49,6221 | 68.404,45 | 70.125,27 |
| (10; 100] | 11.135 | 36,7480 | 314.653,64 | 330.836,74 |
| (100; 1.000] | 1.223 | 4,0362 | 255.070,15 | 278.892,99 |
| >1.000 | 84 | 0,2772 | 203.481,30 | 216.066,42 |
| Total | 30.301 | 100 | 842.748,21 | 897.070,85 |

28.999 facturas tienen delta material positiva y 430 negativa. La suma de todas las deltas positivas es 869.909,53 y de todas las negativas −27.161,32; estas sumas incluyen residuos inmateriales con signo.

## Distribución porcentual y patrones

Denominador: `ABS(DocTotal)`. Se separan primero los documentos inmateriales; cabeceras cero se separarían sin división por cero. No se observaron cabeceras cero activas.

| ABS(delta)/ABS(DocTotal) | Facturas | % facturas | Delta neta |
| --- | ---: | ---: | ---: |
| Inmaterial (≤0,01 de importe) | 872 | 2,8778 | −0,03 |
| ≤1 % material | 0 | 0 | 0 |
| (1; 5] % | 56 | 0,1848 | 2.435,62 |
| (5; 10] % | 1.625 | 5,3629 | 34.209,26 |
| (10; 15] % | 27.648 | 91,2445 | 816.278,24 |
| (15; 25] % | 0 | 0 | 0 |
| >25 % | 100 | 0,3300 | −10.174,88 |

Patrones firmados, redondeados a dos decimales de porcentaje: 13,00 % en 20.794 facturas; 12,99 % en 2.057; 13,01 % en 1.141; 8,42 % en 902; −11,11 % en 223. La redondez del patrón no acredita una tasa fiscal ni su base.

## Concentración y dimensiones

Ranking por ABS(delta), con desempate DocEntry determinístico. Se reportan ambos denominadores para no inflar ni confundir la concentración por compensaciones de signo.

| Top facturas | Aporte neto | Aporte absoluto | % delta neta | % suma absoluta |
| --- | ---: | ---: | ---: | ---: |
| 10 | 73.081,98 | 73.081,98 | 8,6719 | 8,1467 |
| 50 | 164.759,28 | 172.275,22 | 19,5502 | 19,2042 |
| 100 | 218.032,54 | 230.617,66 | 25,8716 | 25,7079 |

| Composición documental | Facturas | Con diferencia | % con diferencia | Delta neta |
| --- | ---: | ---: | ---: | ---: |
| Una categoría | 22.019 | 21.420 | 97,2796 | 436.214,40 |
| Múltiples categorías | 8.282 | 8.009 | 96,7037 | 406.533,81 |

- Frecuencia diaria: hay diferencias en todos los 24 días con facturas observadas; entre 93,3858 % y 100 % de las facturas de cada día. El día 24 tiene sólo 12 facturas: no inferir jornada completa.
- Cliente: agrupación por CardCode publicado, no por nombre ni identidad fiscal inferida. Los diez códigos de cliente de mayor suma absoluta reúnen 47,7878 % de ésta. Se exportan sólo ranks y agregados, sin claves/nombres. No concluir que códigos genéricos equivalen a personas distintas.
- Canal: sólo HORIZONTAL tiene status CONFIRMED: 2.235 facturas, todas con diferencia; delta 199.712,18. Las 25.977 SUPPORTED y 2.089 sin status no se distribuyen como canales acreditados ni se reinterpretan como sucursales.
- Sucursal: no hay atribución documental de cabecera acreditada para este análisis. No se equipara depósito de línea con sucursal ni se duplica DocTotal entre depósitos.

## Ejemplos documentales reales

Identificadores mínimos para reproducir el drill-down; sin clientes, nombres, teléfonos ni productos. Fuente, captura y claves completas permanecen en el JSON de auditoría.

| Tipo / DocEntry | Fecha | Cabecera | Líneas | Diferencia | Categorías |
| --- | --- | ---: | ---: | ---: | ---: |
| OINV / 11522279 | 16/09/2026 | 122.513,30 | 106.586,57 | 15.926,73 | 2 |
| OINV / 11520705 | 15/09/2026 | 94.500,00 | 82.215,00 | 12.285,00 | 1 |
| OINV / 11507904 | 05/09/2026 | 33.241,04 | 35.392,90 | −2.151,86 | 2 |
| ORIN / 21411 | 14/09/2026 | 34.836,70 | 30.307,93 | 4.528,77 | 2 |
| ORIN / 21212 | 05/09/2026 | 33.241,04 | 35.392,90 | −2.151,86 | 2 |

La coincidencia de valores entre factura/NC no acredita por sí sola una relación base. No se distribuye el residuo de una factura mixta entre categorías.

## Causas y campos disponibles

Se distingue lo que demuestra Foundation de lo que exige evidencia fuente adicional. No se modifica Foundation ni se consultó SAP para completar campos ausentes.

| Componente | Evidencia disponible | Clasificación |
| --- | --- | --- |
| Duplicación, huérfanos, linaje cabecera/línea | Controles cero en el universo comparado | CAUSA_VERIFICADA: ninguna de estas causas encontrada; no explica el residuo |
| Anulaciones | Una OINV Y y una C, cada una 87,50 de cabecera y 76,13 de líneas | Exclusión verificada; no explica delta activa |
| Componente proporcional | Moda de residuo/DocTotal alrededor del 13 % y otros patrones | HIPÓTESIS_COMPATIBLE; no impuesto identificado |
| Impuestos por documento/línea | No publicados en las relaciones Foundation comparadas | NO_DETERMINABLE_CON_DATOS_ACTUALES |
| Descuentos de cabecera/línea | No publicados con base/porcentaje en estas relaciones | NO_DETERMINABLE_CON_DATOS_ACTUALES |
| Gastos, ajustes y redondeos | Sin descomposición documental publicada | NO_DETERMINABLE_CON_DATOS_ACTUALES |
| Monedas | DocCur→cabecera.currency; LineCurrency→línea.currency; totales sistema/FX de cabecera y NC | Valores BS coincidentes verificados; denominación LineTotal no acreditada independientemente |
| Diferencia de extracción frente a SAP | No hubo lectura SAP ni cotejo raw independiente nuevo | NO_DETERMINABLE; igualdad interna de linaje no prueba paridad fuente |

No hay una causa monetaria específica CAUSA_VERIFICADA ni importe explicado atribuible a impuestos/descuentos: **el residuo completo permanece sin descomposición causal acreditada**. No significa que todo sea error.

Revisión del productor: `datalake/sql.py` captura para ventas VatPrcnt, LineVatSum, LineDiscPrcnt, LineRate y TotalSumSy/TotalFrgn; `_sales_candidate` de `create_initial.py` no publica esos campos en sales_line. Su disponibilidad potencial en raw no autoriza mezclarlos sin validar correspondencia exacta de publicación/captura y contrato. No se escaneó raw ni se afirmó que esos campos no existan en SAP.

## Notas de crédito y devoluciones

NC se estudia separadamente; no se resta de la categoría ni se confunde con devolución física. Su distribución es recurrente y más concentrada que la de facturas.

- 224 NC activas / 1.071 líneas; 202 con diferencia (90,1786 %) y 22 sin diferencia material. Cabeceras 328.670,24; líneas 302.320,17; delta 26.350,07; suma absoluta 30.905,79.
- Top 10/50/100: 57,7142 % / 82,1925 % / 93,4586 % de la suma absoluta. Top 10 aporta 51,3597 % de la delta neta. Tablas de rangos, porcentaje, fecha, calidad y composición en JSON.
- Materia prima: 8 líneas, 6 productos, 7 NC; campo line_total 16.317,71, separado del importe factura. No se publica su resta como neto.
- Se reutiliza la investigación previa con la misma publicación/snapshot y pares tipados: 1.006 líneas BaseType=13 enlazadas a factura/producto; 64 standalone BaseType=−1; una BaseType=16 (devolución) sin cadena acreditada. No se reejecuta por ritual un análisis no invalidado.
- La [evidencia previa de vínculos](../business-categories-sales-v1/reconciliation-r2.json) conserva SQL y procedencia. No existe aquí contrato probado de devoluciones ni reconstrucción de venta original. `CREDIT_NOTES=UNRESOLVED` refiere a semántica neta/atribución completa, no a imposibilidad de leer sus importes.

## Capacidad, FULL_ACCESS y Presidencia

El [contrato propuesto](../../../../SrvRestAstroLS_v1/backend/modules/telchi/datalake/CATEGORY_LINE_AMOUNT_V1.md) especifica nombre, entradas, salidas, calidad, aislamiento, permisos y condiciones de desbloqueo sin implementar un motor paralelo.

- No se añade código runtime ni se ocultan cifras investigativas en una capability: el runner no es importado por runtime. La cifra de materia prima queda verificada como suma de campo, no acreditada como respuesta monetaria BS.
- Bloqueo preciso: Foundation publica INV1.Currency como moneda de línea; falta acreditar documentalmente la denominación de INV1.LineTotal y la moneda local aplicable a esta entidad/publicación. Coincidencia de códigos BS no sustituye ese contrato. No se exige conciliación perfecta para desbloquear.
- [Inventario real Console DEV READ ONLY](access-r1.json): cero perfiles en telchi_dev; ningún rol/perfil Presidencia por código o etiqueta en la búsqueda; ocho roles comerciales específicos; ninguna category capability registrada. La búsqueda no acredita identidades de Presidencia ni inspecciona producción.
- Piloto: un FULL_ACCESS scoped activo; ocho permisos efectivos del catálogo vigente; workspace ajeno devuelve vacío. No se amplía el resolver ni se aplica un permiso por categoría.
- Test del resolver compartido en PostgreSQL con tablas TEMP de sesión y rollback: PASS; valida alta dinámica sin nuevo grant individual, disabled, módulo, tenant/workspace, usuario, revocación e inactividad. No toca filas operacionales ni prueba una nueva capability inexistente.
- Presidencia: integración requerida con Console/Auth; perfil de lectura Telchi para las dos identidades confirmadas por el owner, idénticos permisos efectivos, sin administración/escritura/global/FULL_ACCESS automático. Sin asignaciones ni modificación silenciosa del resolver.

## Luna real y validaciones

La [sonda Luna](luna-r1.json) hace preflight real y seis turnos sin acceso empresarial ni transporte. Cinco turnos PASS y uno FAIL; no se reintentó para conseguir un PASS.

- Provider OpenAI directo, modelo devuelto `gpt-5.6-luna`, esfuerzo medium verificado; sin fallback. Preflight PASS, por lo que el fallo posterior no se clasifica como ambiental.
- Fallo observado: «Buscame el producto L01128» emitió EXECUTE con `/metric=null` y requested_metrics products.search. State Engine rechazó sin commit. No se atribuye causalidad a esta investigación, que no modificó runtime, ni se cambia el motor para aceptar propuestas inválidas.
- Categorías monetarias y continuidad, búsqueda textual y separación de consumo PASS en alcance interpretativo. No se probó una respuesta monetaria nueva ni una sesión autenticada de Presidencia. `REAL_LUNA=FAIL` para la corrida completa.
- 83 tests focalizados PASS: 13 nuevos de SQL investigativo y 70 existentes de categorías/contrato comercial. Incluyen mixtas, source/type collisions, períodos, anulaciones, linaje, moneda, faltantes, materialidad, duplicados y clasificación sin match. No son una certificación de RBAC de capability nueva.
- Un test PostgreSQL temporal de FULL_ACCESS PASS adicional. Validaciones documentales y revisión final se registran en validations.json.
- Incidencia corregida del runner: alias SQL reservado `day` produjo ParserException antes de persistir evidencia; se cambió a document_day. No hubo writes a Foundation ni defecto de datos demostrado. Una llamada a `python` no existía; se usó python3 sin instalar nada.

Comandos desde backend, con salidas nuevas no sobrescritas:

```bash
uv run python -m modules.telchi.investigation.validation.business_categories_sales_v1.distribution --output ../../data/reports/telchi/category-line-amount-reconciliation-v1/distribution-r3.json
uv run python -m modules.telchi.investigation.validation.business_categories_sales_v1.access_audit --output ../../data/reports/telchi/category-line-amount-reconciliation-v1/access-r1.json
uv run pytest modules/telchi/investigation/validation/business_categories_sales_v1/test_distribution.py modules/telchi/assistant/tests/test_business_categories.py modules/telchi/assistant/tests/test_sales_business_contract.py -q
uv run python -m modules.telchi.assistant.tests.live_business_categories --output ../../data/reports/telchi/category-line-amount-reconciliation-v1/luna-r1.json
```

El test PG se ejecutó cargando únicamente el env local existente en el proceso hijo y `TEAM360_FULL_ACCESS_POSTGRES_TEST=1`, seguido por `pytest tests/test_console_scoped_full_access_postgres.py -q`. Sin mostrar secretos, migrar ni modificar servicios.

## Estado de entrega

Los estados separan medición investigativa, contrato comercial, acceso existente y validación no alcanzada. La tarea completa no se declara PASS ni cumple aún el criterio de consulta ejecutiva en runtime.

```text
DOCUMENTS_ANALYZED=30301
DOCUMENTS_WITH_DIFFERENCE=29429
PERCENT_WITH_DIFFERENCE=97.122207
DOCUMENTS_WITHOUT_MATERIAL_DIFFERENCE=872
PERCENT_WITHOUT_MATERIAL_DIFFERENCE=2.877793
AGGREGATE_DIFFERENCE=842748.21
ABSOLUTE_DIFFERENCE_TOTAL=897070.85
TOP_10_CONCENTRATION=8.146734% absolute / 8.671864% net
TOP_50_CONCENTRATION=19.204193% absolute / 19.550238% net
TOP_100_CONCENTRATION=25.707854% absolute / 25.871611% net
RECONCILIATION_CAUSES=UNRESOLVED
CREDIT_NOTES=UNRESOLVED
CATEGORY_LINE_AMOUNT=BLOCKED
RAW_MATERIAL_SEPTEMBER_AMOUNT=VERIFIED (field sum only; commercial contract UNAVAILABLE)
CURRENCY=UNKNOWN (LineTotal denomination; published header/line codes BS VERIFIED)
BUSINESS_SEMANTICS=PARTIAL
FULL_ACCESS=BLOCKED (new capability; existing scoped resolver PASS)
PRESIDENCIA_ACCESS=NOT_IMPLEMENTED
RBAC_AND_ISOLATION=PASS (existing resolver and temporary fixtures only; new capability NOT_IMPLEMENTED)
REAL_LUNA=FAIL
SIX_GATES=STALE
READY_FOR_MANUAL_WHATSAPP=NO
```

## Recursos, impacto y próximo paso

Presupuesto conservador: una conexión/runner a la vez, DuckDB un thread, 256 MB, sin spill; consultas Foundation acotadas y un inventario PostgreSQL local con timeout de cinco segundos.

Host inicial: load 1,85/3,49/3,82 sobre 8 cores, ~5,5 GB disponibles, swap ~604 MB estable, CPU ociosa 63–71 % en muestras. Capacidad segura para el alcance acotado; no se lanzaron suites globales, browsers ni servidores.

```text
HOST_PREFLIGHT=SAFE
RESOURCE_GUARD=PASS
CONCURRENCY_USED=1
UNRELATED_PROCESSES_TERMINATED=0
ENVIRONMENTAL_ABORTS=0
OWN_PROCESSES_LEFT_RUNNING=0
```

Impacto transversal: sólo lectura de Console/resolver y Foundation; no cambios de autenticación, migraciones, permisos, clasificación, datos SAP, infraestructura, CURRENT, Meta, Cloudflare, Evolution, frontend o State Engine. Sin iniciar/detener servicios, WhatsApp, commit ni push. Cambios preexistentes preservados.

Próximo paso: acreditar denominación LineTotal/moneda local en evidencia fuente exacta, implementar el contrato acotado sin exigir conciliación completa y coordinar perfil Presidencia con Console. Después, integrar drill-down autorizado, corregir por separado la propuesta inválida de Luna y reacreditar los gates afectados. No promover ni ampliar accesos mientras esto siga pendiente.
