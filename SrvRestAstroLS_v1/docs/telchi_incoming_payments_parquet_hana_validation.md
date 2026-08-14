# Cobros Telchi: Parquet histórico vs. SAP HANA actual

Esta validación compara los cobros históricos preservados con la definición exacta del extractor SAP original. Todo el análisis es read-only y termina en la última fecha presente dentro de los datos Parquet.

## Resultado

La comparación terminó correctamente y demostró diferencias históricas materiales. No se modificó HANA, no se reescribió Parquet y no se atribuye la divergencia a una fuente sin evidencia adicional.

```text
RESULTADO: PARTIAL
CONCLUSION: MATERIAL_HISTORICAL_DIFFERENCES
```

La mayor concentración coincide con un corte del histórico: marzo de 2023 termina el día 23, abril de 2023 no tiene archivo y mayo vuelve a estar presente.

## Fuente y definición histórica

La función completa `makePaymentRange` se encuentra en `Insiding/DataScience/sapb1Tools01.py` del repositorio Telchi. `makePayment` escribía un Parquet mensual llamado `paymentB1-YYYY-MM-DD.parq`.

| Atributo | Definición legacy reproducida |
| --- | --- |
| Objeto SAP | `TELCHI.ORCT` |
| Joins | Ninguno |
| Fecha | `DocDate` |
| Importe local | `DocTotal` |
| Importe moneda extranjera | `DocTotalFC`, preservado pero no usado como total local |
| Clave documental | `DocEntry` |
| Número visible | `DocNum` |
| Moneda | El extractor no proyectaba `DocCurr` |
| Signo | Sin transformación |
| Cancelación | Sin filtro; conserva `Canceled='N'` y `Canceled='Y'` |
| Filtro | `DocDate >= inicio` y `DocDate <= fin 23:59:59` |
| Transformación Python | Deriva `YMD`, `YM` y `Y` desde `DocDate` |

La consulta HANA del comparador conserva esa semántica: no excluye cancelados ni cambia el campo monetario.

## Dataset Parquet

El Data Lake operativo contiene 13 archivos `paymentB1-*.parq`. La copia paralela `DS0` es byte a byte idéntica para los mismos archivos; la comparación usa el path configurado por el código legacy, `DS/`.

```text
/media/issajar/DEVELOP/Projects/telchi/Insiding/DataScience/DS/paymentB1-*.parq
```

El schema tiene 23 columnas:

```text
TransId, CashSum, TrsfrSum, CreditSum, CheckSum,
DocTotal, DocTotalFC, DocEntry, DocNum, DocType, Canceled,
DocDate, DocTime, DocDueDate, TaxDate,
ClientCode, ClientName, Ref1, Comments, JrnlMemo,
YMD, YM, Y
```

`DocTotal` está serializado como `double`; el comparador convierte cada valor mediante texto a `Decimal` y normaliza a dos decimales. HANA no presentó importes `DocTotal` con fracciones menores a centavo en la ventana.

## Rango temporal

Los límites Parquet se calcularon leyendo `DocDate` de las filas, no interpretando los nombres de archivo.

```text
PARQUET MIN:      2022-04-01
PARQUET MAX:      2023-05-31

HANA MIN:         2022-03-31
HANA MAX:         2026-08-13

COMPARISON START: 2022-04-01
COMPARISON END:   2023-05-31
```

La condición obligatoria quedó comprobada:

```text
COMPARISON END = PARQUET MAX DATE
```

Ningún dato HANA posterior al 2023-05-31 forma parte de las métricas de paridad.

## Comparación macro

Una fila equivale a un documento en ambas fuentes: `DocEntry` es no nulo y único en los 368.552 registros Parquet, y HANA conserva la misma cardinalidad fila/documento en la ventana.

| Métrica | Parquet | HANA | HANA - Parquet |
| --- | ---: | ---: | ---: |
| Filas | 368.552 | 411.874 | +43.322 |
| Documentos | 368.552 | 411.874 | +43.322 |
| `DocTotal` | 105.845.204,41 | 120.783.607,48 | +14.938.403,07 |

El Parquet representa el 89,48% de las filas y el 87,63% del importe HANA actual dentro de la misma ventana. Estos porcentajes miden cobertura macro, no identidad documental completa.

La distribución de cancelación también cambió:

| Estado | Parquet filas | HANA filas |
| --- | ---: | ---: |
| `Canceled='N'` | 366.393 | 409.433 |
| `Canceled='Y'` | 2.159 | 2.441 |

## Comparación diaria

Se alinearon todos los días naturales entre ambos límites. Un día es MATCH solo si filas, documentos e importe a centavo coinciden simultáneamente.

```text
TOTAL DAYS COMPARED:              426
MATCHING DAYS:                    266
DIFFERENT DAYS:                   160
EXACT MATCHING DAYS PCT:        62,44%

FIRST DIFFERENCE DATE:     2022-04-01
LAST MATCH BEFORE DIFF:           NONE
FIRST MATCH DATE:           2022-04-02
LAST MATCH DATE:            2023-03-05
LAST DIFFERENCE DATE:       2023-05-31
```

La primera fecha del rango ya diverge, por lo que no existe un match anterior a la primera diferencia. Los matches y diferencias son dispersos hasta marzo de 2023; luego aparece el corte continuo.

## Tipos de diferencia

Las clasificaciones son por fecha y no realizan todavía reconciliación completa por `DocEntry`.

| Clasificación | Días |
| --- | ---: |
| MATCH | 266 |
| ROW_COUNT_DIFF | 122 |
| DOCUMENT_COUNT_DIFF | 122 |
| AMOUNT_DIFF | 122 |
| HANA_ONLY | 38 |
| PARQUET_ONLY | 0 |
| ROUNDING_ONLY | 0 |
| NEEDS_DETAIL_ANALYSIS | 0 |

En los 160 días divergentes, HANA siempre tiene más filas y más importe que el Parquet. No existe ninguna fecha con datos Parquet y cero datos HANA.

Los 38 días `HANA_ONLY` forman una ventana continua:

```text
2023-03-24 → 2023-04-30
```

Este tramo explica 42.898 de las 43.322 filas adicionales y 10.511.005,49 de los 14.938.403,07 de diferencia monetaria total.

## Resumen mensual

Todos los meses de la ventana tienen alguna diferencia. Marzo y abril de 2023 concentran la falta física de cobertura; en los demás meses las diferencias son menores pero reales.

| Mes | Parquet filas | HANA filas | Δ filas | Parquet importe | HANA importe | Δ importe |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2022-04 | 22.964 | 22.971 | +7 | 7.174.630,92 | 7.194.183,81 | +19.552,89 |
| 2022-05 | 27.688 | 27.700 | +12 | 7.289.721,20 | 7.468.007,84 | +178.286,64 |
| 2022-06 | 28.398 | 28.406 | +8 | 9.211.190,09 | 9.435.366,09 | +224.176,00 |
| 2022-07 | 28.395 | 28.398 | +3 | 7.059.617,20 | 7.069.948,99 | +10.331,79 |
| 2022-08 | 29.719 | 29.721 | +2 | 8.332.762,16 | 8.332.907,89 | +145,73 |
| 2022-09 | 29.719 | 29.722 | +3 | 10.512.894,49 | 10.513.076,31 | +181,82 |
| 2022-10 | 26.178 | 26.181 | +3 | 6.912.292,93 | 6.912.759,74 | +466,81 |
| 2022-11 | 19.729 | 19.750 | +21 | 5.943.389,22 | 6.717.524,16 | +774.134,94 |
| 2022-12 | 32.822 | 32.973 | +151 | 10.758.584,77 | 12.567.810,48 | +1.809.225,71 |
| 2023-01 | 32.880 | 32.902 | +22 | 9.519.978,76 | 9.629.257,48 | +109.278,72 |
| 2023-02 | 29.310 | 29.319 | +9 | 8.679.068,79 | 8.839.666,32 | +160.597,53 |
| 2023-03 | 25.596 | 36.385 | +10.789 | 6.189.998,07 | 9.635.636,01 | +3.445.637,94 |
| 2023-04 | 0 | 32.109 | +32.109 | 0,00 | 7.065.367,55 | +7.065.367,55 |
| 2023-05 | 35.154 | 35.337 | +183 | 8.261.075,81 | 9.402.094,81 | +1.141.019,00 |

No se aplicó tolerancia monetaria para convertir diferencias reales en matches. La comparación usa precisión de centavo porque ambas fuentes observadas tienen esa escala efectiva.

## Interpretación técnica

El patrón combina diferencias dispersas con una discontinuidad física clara. No es válido describirlo solo como redondeo ni como una pérdida uniforme de HANA.

- El Parquet contiene datos continuos entre 2022-04-01 y 2023-03-23, salvo diferencias diarias pequeñas o puntuales.
- No existe archivo de abril de 2023 y el archivo de marzo termina ocho días antes del fin de mes.
- El histórico vuelve a existir en mayo de 2023, pero ese mes también tiene 183 documentos menos y 1.141.019,00 menos que HANA actual.
- Diciembre de 2022 presenta un delta monetario material aun con solo 151 documentos adicionales.
- No hay fechas `PARQUET_ONLY`; sí hay 38 fechas `HANA_ONLY`.
- Esta fase no demuestra todavía si todos los `DocEntry` Parquet permanecen en HANA dentro de fechas compartidas; eso requiere el gate de reconciliación documental.

HANA es la verdad operativa actual y Parquet es evidencia histórica preservada. El incidente histórico de Telchi puede explicar revisiones o pérdidas, pero esta auditoría no asigna causalidad.

## Reconciliación documental

La segunda fase comparó cada `DocEntry`, mantuvo separado el período sin archivo y usó los timestamps SAP y del filesystem solo como evidencia diagnóstica. No modificó datos ni intentó reconstruir el histórico.

### Paridad en fechas compartidas

El universo compartido contiene únicamente fechas con al menos una fila en ambas fuentes. Hay 386 fechas compartidas, 38 fechas solo HANA y dos fechas sin cobros en ninguna fuente dentro de la ventana completa.

| Conjunto documental | Documentos |
| --- | ---: |
| Parquet en fechas compartidas | 368.552 |
| HANA en fechas compartidas | 370.238 |
| `BOTH` | 368.552 |
| `PARQUET_ONLY` | 0 |
| `HANA_ONLY` | 1.686 |

`DocEntry` es único globalmente y por día en las dos fuentes. Todos los documentos preservados siguen existiendo actualmente en HANA; la diferencia de presencia en días compartidos es enteramente `HANA_ONLY`.

### Estado del mismo DocEntry

Los 368.552 documentos comunes se compararon sobre los 20 campos que realmente escribió `makePaymentRange`. Las categorías de campo son no excluyentes: una cancelación también puede cambiar el memo contable.

| Resultado | Documentos |
| --- | ---: |
| Todos los campos exactos | 368.486 |
| Cualquier campo modificado | 66 |
| `DocTotal` o `DocTotalFC` modificado | 0 |
| `DocDate` modificado | 0 |
| `Canceled` modificado | 52 |
| Otro campo modificado | 66 |

Los campos distintos son `JrnlMemo` en 63 documentos, `Canceled` en 52, `Comments` en 5 y `TaxDate` en 2. No cambió ningún importe local/moneda extranjera ni la fecha documental de los `DocEntry` comunes.

La cronología por `UpdateDate` y `UpdateTS` clasifica 54 de los 66 cambios como posteriores a la marca temporal del snapshot. Incluye 40 de las 52 cancelaciones. Los otros 12 cambios, todos con cancelación distinta, quedan como `DOCUMENT_CHANGE_TIMING_UNRESOLVED`; el mtime por sí solo no permite afirmar cuándo cambió HANA.

### Diferencias compartidas por mes

Las diferencias anteriores a marzo de 2023 son pequeñas y siempre HANA-only. La columna de cambios cuenta documentos comunes cuyo estado actual difiere del snapshot.

| Mes | Parquet-only | HANA-only | Mismo DocEntry modificado |
| --- | ---: | ---: | ---: |
| 2022-04 | 0 | 7 | 7 |
| 2022-05 | 0 | 12 | 7 |
| 2022-06 | 0 | 8 | 7 |
| 2022-07 | 0 | 3 | 3 |
| 2022-08 | 0 | 2 | 2 |
| 2022-09 | 0 | 3 | 3 |
| 2022-10 | 0 | 3 | 0 |
| 2022-11 | 0 | 21 | 3 |
| 2022-12 | 0 | 151 | 7 |
| 2023-01 | 0 | 22 | 2 |
| 2023-02 | 0 | 9 | 4 |
| 2023-03, días 1 a 23 | 0 | 1.262 | 14 |
| 2023-05 | 0 | 183 | 7 |

### Período físicamente ausente

El hueco real contiene 41.636 documentos HANA: 9.527 del 24 al 31 de marzo y 32.109 de abril. La aproximación macro anterior de 42.898 mezclaba esos documentos con los 1.262 HANA-only de los días compartidos de marzo.

```text
START:              2023-03-24
END:                2023-04-30
DAYS:               38
HANA DOCUMENTS:     41.636
APRIL FILE STATE:   MISSING_PARQUET_FILE
MARCH FILE STATE:   PARTIAL_MONTH_WRITE (lógico, no truncamiento físico)
ROOT CAUSE:         MISSING_PARQUET_PERIOD
```

El archivo `paymentB1-2023-03-31.parq` tiene mtime `2023-03-23 12:00:34`, pero sus datos terminan el 23 de marzo. Es un archivo Parquet válido de un row group con 25.596 filas: fue nombrado con fin de mes aunque se produjo durante el mes. No existe archivo de abril, ni vacío ni con otro nombre, y mayo vuelve completo desde el día 1.

### Validación de la consulta legacy

La consulta histórica y la fuente HANA simple produjeron exactamente los mismos conjuntos dentro de la ventana. Esta prueba evalúa el SQL hoy; no pretende reconstruir el estado que tenía HANA en cada ejecución histórica.

```text
LEGACY QUERY STRUCTURE:      SELECT directo de TELCHI.ORCT
                             DocDate >= inicio
                             DocDate <= fin 23:59:59
EXECUTES TODAY:              YES
LEGACY DOCUMENTS:            411.874
CURRENT SOURCE DOCUMENTS:    411.874
SYMMETRIC DIFFERENCE:        0
KNOWN QUERY OMISSIONS:       0
CONCLUSION:                  LEGACY_QUERY_VALID
```

No hay joins, filtros de cancelación, paginación ni transformaciones que puedan retirar filas. El SQL construido por interpolación es deuda de implementación, pero no explica la divergencia observada.

### Auditoría del guardado legacy

El código disponible construye rangos mensuales inclusivos, obtiene todo el `DataFrame` y sobrescribe directamente el nombre mensual mediante `pandas.DataFrame.to_parquet(..., engine='pyarrow')`.

| Atributo | Evidencia |
| --- | --- |
| Estrategia | Rango mensual completo |
| Append | No |
| Overwrite | Sí, si ya existe el mismo nombre |
| Escritura atómica | No; no usa temporal más rename |
| Validación poswrite | No |
| Error handling | `except` amplio; mensaje genérico; `makePaymentRange` retorna `None` |
| Scheduler de cobros | No encontrado; `makePayment()` está comentado en `main` |
| Archivo abril 2023 | Ausente |
| Archivo marzo 2023 | Válido físicamente, incompleto semánticamente por ejecución el día 23 |

Los mtimes revelan ejecuciones manuales o backfills, no snapshots de fin de cada mes: abril a noviembre de 2022 se escribieron secuencialmente el 5 de diciembre de 2022; febrero y marzo de 2023 se escribieron el 23 de marzo; mayo y diciembre se observan el 28 de septiembre de 2023. El birth time posterior corresponde a copia y no se usó como fecha de generación.

El writer tiene riesgo de overwrite no atómico y errores silenciosos, pero los 13 archivos presentes son Parquet válidos. No hay evidencia para asignar documentos concretos a `PARQUET_SAVE_OMISSION`; el fallo demostrado es de cobertura/ejecución, no corrupción selectiva dentro del archivo.

### Análisis de HANA-only

Los 1.686 HANA-only de fechas compartidas se clasificaron comparando `CreateDate/CreateTS`, `UpdateDate/UpdateTS`, mtime y techo de `DocEntry` del archivo mensual. El mtime es evidencia operativa conservada, no una prueba criptográfica del instante de snapshot.

| Causa de presencia | Documentos | % de los 43.322 adicionales |
| --- | ---: | ---: |
| `MISSING_PARQUET_PERIOD` | 41.636 | 96,11% |
| `DOCUMENT_CREATED_LATER` | 1.277 | 2,95% |
| `RESTORED_OR_REINTRODUCED_POSSIBLE` | 406 | 0,94% |
| `DOCUMENT_UPDATED_LATER` | 3 | 0,01% |
| `LEGACY_QUERY_OMISSION` demostrado | 0 | 0,00% |
| `PARQUET_SAVE_OMISSION` demostrado | 0 | 0,00% |

Los 406 casos posibles de restauración tienen fecha de creación no posterior al mtime, pero su `DocEntry` supera el máximo preservado en el archivo mensual correspondiente. Esto demuestra que no estaban en el conjunto capturado; no demuestra por sí solo restauración ni la causa del incidente.

Los 1.277 `DOCUMENT_CREATED_LATER` tienen alta SAP posterior a la evidencia temporal del archivo. Los tres `DOCUMENT_UPDATED_LATER` existían por timestamp de creación, pero su actualización posterior hace que el estado histórico preciso no pueda reconstruirse desde ORCT actual.

### Conclusión de causa raíz

La diferencia combina un hueco físico dominante con documentos incorporados o reintroducidos posteriormente en HANA. La consulta legacy continúa siendo compatible; el guardado era frágil, pero no hay omisiones selectivas demostradas dentro de archivos existentes.

En términos simples:

- 41.636 documentos faltan por cobertura física: marzo fue cortado el día 23 y abril no tiene archivo;
- 1.277 documentos fueron creados después de la evidencia temporal del snapshot;
- 406 son compatibles con restauración/reintroducción porque exceden el techo de identidad capturado, sin afirmar el incidente como causa;
- 3 tienen una actualización posterior relevante;
- 66 documentos preservados cambiaron de estado/campos, 52 por cancelación, pero ninguno cambió `DocTotal`, `DocTotalFC` o `DocDate`;
- cero documentos pueden atribuirse con evidencia a una omisión de la query o a una omisión selectiva del writer.

La causa principal es una combinación de `HUECOS_FÍSICOS` y `CAMBIOS_POSTERIORES_EN_HANA`. El mecanismo disponible apunta a `SYNC_NOT_EXECUTED` para abril y a una ejecución prematura para marzo; no existe log que permita precisar por qué se interrumpió esa secuencia.

## Tooling reproducible

El comparador genera métricas macro, alineación diaria y resumen mensual sin escribir archivos de datos.

```bash
cd SrvRestAstroLS_v1/backend
uv run --with pyarrow python scripts/compare_telchi_incoming_payments_parquet_hana.py
uv run --with pyarrow python scripts/compare_telchi_incoming_payments_parquet_hana.py --show-daily
uv run --with pyarrow python scripts/reconcile_telchi_incoming_payments_documents.py
uv run --with pyarrow python scripts/reconcile_telchi_incoming_payments_documents.py --show-samples
```

La segunda variante imprime los 426 días ordenados para inspección puntual. Ninguna variante consulta HANA después de `PARQUET_MAX_DATE`.

## Conclusión

La clasificación final es `MATERIAL_HISTORICAL_DIFFERENCES`: la comparación es metodológicamente válida, pero solo 62,44% de los días coincide exactamente y falta un tramo continuo de 38 días en Parquet.

```text
TEAM360_TELCHI_INCOMING_PAYMENTS_PARQUET_HANA_PARITY_PARTIAL
```

La reconciliación documental cerró sin casos de identidad, fecha o importe sin explicación. Quedan 12 cambios de estado cuya fecha exacta no puede resolverse con el mtime y 406 altas actuales cuya restauración es posible, pero no demostrable desde estas fuentes.

```text
TEAM360_TELCHI_INCOMING_PAYMENTS_DOCUMENT_RECONCILIATION_PASS
```
