# Productos con movimiento real — análisis offline

Resultado parcial en cobertura empresarial; cálculo completo para la evidencia local acreditada. Sin consultas HANA ni publicación.

| Métrica | Productos |
| --- | ---: |
| Productos únicos vendidos | 6581 |
| Productos con devoluciones | 1466 |
| Ventas o devoluciones | 6581 |
| Producción efectiva acreditada (componentes) | 971 |
| Ventas/devoluciones y producción | 154 |
| Total único con movimiento | 7398 |
| Actividad últimos 24 meses | 7398 |
| Actividad histórica anterior (puede solapar) | 0 |
| Solo histórica anterior | 0 |
| Cubiertos por captura U_FormaFarmac | 4187 |
| Pendientes HANA del universo acreditado | 3211 |
| Sin clasificación física explícita | 6481 |
| Capturados sin movimiento acreditado | 5813 |

## Distribución física

Códigos originales observados sobre el universo operativo; pendiente no equivale a NULL. Solo 1, 2 y 3 son explícitos.

| Código original JSON | Productos |
| --- | ---: |
| `"0"` | 3256 |
| `"1"` | 465 |
| `"2"` | 63 |
| `"3"` | 389 |
| `"4"` | 13 |
| `"5"` | 1 |
| No observado (pendiente) | 3211 |

## Cobertura y límites

Corte analítico 2026-10-29; últimos 24 meses desde 2024-10-29 inclusive. Fechas observadas, no garantía de continuidad.

| Familia | Primera fecha | Última fecha | Líneas |
| --- | --- | --- | ---: |
| production_consumption | 2026-01-05 | 2026-09-23 | 28750 |
| sales | 2026-01-01 | 2026-09-24 | 715017 |
| sales_return | 2026-01-01 | 2026-09-23 | 9423 |

- Universe is a verified lower bound, not the entire enterprise catalog.
- Production receipts OIGN/IGN1 unavailable; finished products cannot be accredited from open OWOR or generic OINM 59.
- Production consumption from local raw 2026 captures, not Foundation; earlier OWOR linkage outside captured window remains unaccredited.
- Sales credit memo is documentary return evidence, not independent proof of physical stock receipt; canceled/zero/nonpositive lines excluded.
- Observed first/last dates do not prove continuous historical completeness. Credit memos and production lack pre-2026 history; sources stop in September, not October 29.
- Historical headers are not historical ItemCode coverage: all accredited item lines here are 2026. Zero older products is NOT proof of no earlier business activity.
- Historical and recent sets overlap; historical_only is the disjoint older-only set.
- Captured without activity means no evidence in inspected coverage, never nonexistent or erroneous import.
- Physical attributes are current observations, not historical backfill. Coverage includes observed NULL/unknown; only original codes 1,2,3 are explicit.

## Evidencia y captura futura

Los artefactos conservan claves originales, fechas, documentos, origen y hashes; no alteran Atomic, Reference, Foundation ni capturas anteriores.

- `report.json`: inventario, schemas, exclusiones, cobertura, integridad y métricas.
- `evidence.parquet`: todas las evidencias por documento/línea.
- `products.json`: universo único ordenado y cruces por ItemCode.
- `selective_plan.json`: parámetros por lote, límites y protocolo; NO ejecutable ni autorizado.
- `captured_without_activity.json`: sin evidencia local, no artículos erróneos.

Foundation fijada: `foundation_afd08d9eca6a725be53cdc3f9d5709c9`, snapshot `1408`. Checkpoint: `7b8bbb992fcb83e3d0ec4ae4951084fad90fa12e5c7761ce0f408bf9b7b69099`.

El extractor keyset existente no acepta esta selección: sus fingerprints no son compatibles. Se requiere adaptación autorizada y gate de recuperación antes de ejecutar el plan; no se ha rebajado ningún control.

Los encabezados OINV llegan a 2022, pero sus líneas no acreditan productos anteriores a 2026: el cero histórico es falta de cobertura, no ausencia empresarial. Hay 43 claves operativas ausentes de Reference; se preservan sin inventar identidad canónica.

NULL observado: 0; códigos desconocidos observados: 0. Los no observados quedan separados.
