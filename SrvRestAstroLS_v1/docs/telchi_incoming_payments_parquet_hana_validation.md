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

## Tooling reproducible

El comparador genera métricas macro, alineación diaria y resumen mensual sin escribir archivos de datos.

```bash
cd SrvRestAstroLS_v1/backend
uv run --with pyarrow python scripts/compare_telchi_incoming_payments_parquet_hana.py
uv run --with pyarrow python scripts/compare_telchi_incoming_payments_parquet_hana.py --show-daily
```

La segunda variante imprime los 426 días ordenados para inspección puntual. Ninguna variante consulta HANA después de `PARQUET_MAX_DATE`.

## Conclusión

La clasificación final es `MATERIAL_HISTORICAL_DIFFERENCES`: la comparación es metodológicamente válida, pero solo 62,44% de los días coincide exactamente y falta un tramo continuo de 38 días en Parquet.

```text
TEAM360_TELCHI_INCOMING_PAYMENTS_PARQUET_HANA_PARITY_PARTIAL
```

Un gate posterior puede comparar `DocEntry` dentro de los 122 días compartidos con diferencias para separar documentos agregados, modificados, cancelados o ausentes, sin reescribir ninguna fuente.
