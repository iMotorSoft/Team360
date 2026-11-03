# Universo operativo Telchi V2 — offline

Unión trazable de movimientos y recetas productivas locales. Cobertura empresarial parcial; no es el catálogo completo de Telchi. Sin consultas HANA.

| Métrica | Artículos únicos |
| --- | ---: |
| has_sales | 6581 |
| has_sales_returns | 1466 |
| has_production_consumption | 971 |
| has_production_receipt | 0 |
| is_bom_parent | 1031 |
| is_bom_component | 1293 |
| is_multilevel_bom_component | 388 |
| total_unique | 8001 |
| movement_only_baseline | 7398 |
| exclusively_bom | 603 |
| covered | 4759 |
| pending | 3242 |
| explicit_physical | 1276 |
| observed_not_explicit | 3483 |
| missing_reference | 43 |
| select_queries | 130 |
| query_blocks | 26 |
| captured_without_observed_movement | 5813 |
| captured_outside_universe | 5241 |

## Recetas y movimientos

OITT/ITT1 acreditados por hashes y schemas; solo TreeType=P y componentes Type=4 integran recetas productivas. Se conservan también cabeceras y líneas excluidas.

- Cabeceras por tipo: {'S': 23, 'P': 1031}. Líneas por tipo: {'4': 5055, '290': 2925}.
- Caminos simples: 7728; ciclos detectados: 0; truncamiento: NO.
- Vigencia productiva: desconocida. No se infiere de fechas de creación/actualización.
- Recepciones OIGN/IGN1: cobertura pendiente; cero acreditados no significa cero reales.

Intersecciones (incluyen triple):

- sales_or_returns & production_effective: 154.
- sales_or_returns & production_bom: 708.
- production_effective & production_bom: 905.
- sales_or_returns & production_effective & production_bom: 145.

## Clasificación física

Solo códigos SAP 1, 2 y 3 acreditan estado físico; NULL y desconocidos se preservan. Pendiente no es NULL. No hay inferencia por nombre ni receta.

| Código original JSON | Artículos | % capturados operativos | % universo |
| --- | ---: | ---: | ---: |
| `"0"` | 3469 | 72.893465 | 43.35708 |
| `"1"` | 693 | 14.561883 | 8.661417 |
| `"2"` | 93 | 1.954192 | 1.162355 |
| `"3"` | 490 | 10.296281 | 6.124234 |
| `"4"` | 13 | 0.273167 | 0.16248 |
| `"5"` | 1 | 0.021013 | 0.012498 |

Denominadores: capturados operativos=4759; universo=8001. Pendientes=3242. Porcentajes: `{'captured_of_operational': 59.480065, 'explicit_of_operational': 15.948006, 'explicit_of_captured_operational': 26.812356}`.

## Fuentes y límites temporales

Se reacreditaron los documentos locales mediante el analizador V1 sin modificarlo. El inventario detallado incluye schemas, cancelaciones, duplicados, snapshots y hashes.

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
- Production BOM universe uses OITT.TreeType=P only. Sales BOM S is retained separately, never labeled production recipe.
- ITT1.Type=4 is an item; Type=290 is a resource, excluded from ItemCode union but preserved in excluded lines.
- BOM captured 2026-09-25, not necessarily currently valid. CreateDate/UpdateDate do not establish effective validity.
- Production receipts are unavailable, not evidence that zero finished products were received.
- BOM membership does not imply consumption, ingredient category, physical state or recent activity.
- All simple paths and cycle-closing edges are preserved; cycles are not recursively expanded. No quantity/UoM inference.
- Selective ledger is offline tested. No network runner exists here; future pacing, latency, deadline, closure and device guards require transport integration validation.
- A completed selective fetch with missing keys records NOT_RETURNED, not deletion; interrupted fetch must not be committed.
- Exact pending list and SELECT count apply only to accredited local universe. Future receipt or BOM evidence can expand it.

## Captura selectiva futura

Plan congelado por SHA-256, SQL parametrizado IN y checkpoint por lote solicitado, incompatible deliberadamente con keyset. No ejecutable contra HANA en esta etapa.

- 3242 claves exactas; 130 SELECT; 26 bloques, hasta 5 SELECT por bloque.
- Máximo 25 claves/SELECT; una conexión; sin paralelismo ni reintentos; pausas de 10 s entre consultas y 30 s entre bloques; HANA 1,5 s; persistencia 10 s.
- Ledger separado con intent durable previo al SELECT, bloqueo de reintento ante resultado incierto, journal completo, hashes, fsync, exclusión de directorio, validación de correspondencia y recuperación idempotente offline.
- Guard cooperativo con reserva de cierre/recuperación; no abortar fsync en curso. El futuro runner debe reutilizar controles específicos del dispositivo, no decidir solo por iowait global.
- Antes de ejecutar: nueva autorización, destino privado nuevo y gate de integración de latencia/pacing/cierre de cursor y conexión. No usar este plan con el runner keyset.

## Artefactos y validación

La evidencia generada no publica ni modifica Reference, Foundation, CURRENT, Atomic ni capturas previas. Resultado: 145 tests PASS, cinco gates LAT PASS y git diff --check PASS; comandos y límites en validation.json.

- `products.json`: identidad única, indicadores independientes y evidencia por pertenencia.
- `bom_evidence.json`: cabeceras, aristas, caminos multinivel, ciclos y exclusiones.
- `activity_reaccredited/`: evidencia documental Parquet y reporte V1 reacreditados.
- `report.json`: métricas, fuentes, hashes, límites y claves sin Reference (sin inventar canónicas).
- `selective_plan.json`: lista exacta, parámetros por lote y controles futuros.
- `captured_outside_universe.json`: sin evidencia en este universo, nunca inválidos.
