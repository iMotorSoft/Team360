# TELCHI — Purchase / Material Planning V1

**Gate global:** `TELCHI_PURCHASE_MATERIAL_PLANNING_V1_DEGRADED` (cierre técnico
determinístico PASS; smoke SQL HANA pendiente)
**Estado:** freeze pendiente de smoke SQL HANA read-only
**Snapshot de cierre:** 2026-08

## A. Objetivo

Cerrar Gates 1–10 como baseline estable, verificable, explicable y trazable,
dejando una salida neutral para la futura reunión ejecutiva semanal.

## B. Arquitectura analítica

La cadena existente permanece intacta: purchase discovery → stock → equivalencia
FG/material → capacidad terminal → lead time → estacionalidad/forecast →
waterfall de cobertura → risk engine → backtest anti-hindsight → executive
cases. El validator global sólo comprueba contratos entre capas; no duplica
ningún motor.

## C. Gates 1–10 certificados

`TELCHI_PURCHASE_DATA_DISCOVERY_V1_PASS`,
`TELCHI_MATERIAL_STOCK_POSITION_V1_PASS`,
`TELCHI_FINISHED_GOODS_MATERIAL_EQUIVALENCE_V1_PASS`,
`TELCHI_MAX_PRODUCIBLE_BY_COMPONENT_V1_PASS`,
`TELCHI_PURCHASE_LEAD_TIME_V1_PASS`,
`TELCHI_PRODUCT_SEASONALITY_V1_PASS`,
`TELCHI_EQUIVALENT_MATERIAL_COVERAGE_V1_PASS`,
`TELCHI_PURCHASE_RISK_ENGINE_V1_PASS`,
`TELCHI_PURCHASE_DECISION_BACKTEST_V1_PASS`, y
`TELCHI_PURCHASE_EXECUTIVE_CASES_V1_PASS` permanecen certificados y sin cambio
semántico.

## D–F. Fuentes y semánticas críticas

SAP/HANA estándar es la fuente actual; `POR1.OpenQty` es la posición documental
de compra abierta. `OITW.OnOrder` no se suma como suministro adicional. Stock
físico, FG utilizable, equivalente ya transformado, producción adicional,
open purchase y demanda futura son capas distintas. La expansión BOM llega al
componente terminal; los componentes compartidos quedan
`SHARED_COMPONENT_ALLOCATION_UNRESOLVED`.

Lead time documental y físico no se confunden; importación conserva p90≈82d
como evidencia observada, no regla universal. Safety buffer es heurístico.

## G. Evidencia cuantitativa

- 267 tests históricos: PASS.
- 2 tests globales: PASS; 12 contratos globales: PASS.
- Casos backtest: 40 (10 componentes × 4 snapshots), early warning 12/14 = 86%.
- 226 FG con `PRODUCTION_BLOCKED` por packaging/insumos secundarios.
- HANA writes: 0; TCP local PASS, smoke SQL incompleto/interrumpido tras >60s
  (no se declara PASS de contratos SQL globales).

## H. Casos ejecutivos trazadores

Benzoato `L01785` → `BUY_NOW`; soda `L01010` → cantidad cubierta +
`IMPORT_DELAY_RISK`; cloruro `L01821` → cubierto por equivalente en PT; gotero
→ no limitante; bronceador `L03124` → `SEASONAL`, pico enero, sep–feb,
`EXCESS_STOCK` (≈1,59x); packaging → `PRODUCTION_BLOCKED`.

## I–J. Backtest y limitaciones

Se conserva el backtest sin hindsight y sus cuatro veredictos: EARLY_WARNING 14,
CONSISTENT 10, MISSED_PURCHASE 9, OVERBUY 7. Limitaciones: warehouse RAW local,
intermitencia subestimada, open purchase as-of-T incompleto y transferencias
históricas que pueden producir saldos negativos. `stock=0 + demand=0` no es
`OVERBUY`; queda como no-demanda/consistente.

## K. Quality flags

Se propagan sólo cuando aplican: `IN_TRANSIT_UNRESOLVED`,
`IMPORT_DELAY_RISK`, `SUPPLIER_RISK`, `UOM_UNRESOLVED`,
`POTENTIAL_STOCKOUT_CENSORED_DEMAND`, `PRODUCTION_BLOCKED` y
`SEASONALITY_UNCERTAIN`.

## L. Tests y runner

Ejecutar `./.venv/bin/python -m validation.run_purchase_material_planning_v1`.
El runner informa baseline histórico por separado, contratos globales, estado
HANA (requiere smoke manual del operador), invariantes y freeze; escribe
`validation/purchase_material_planning_v1_gate.json`.

La interfaz `ExecutiveCase.to_dict()` añade `case_id`, `domain`, `decision`,
`severity`, `summary`, `action_code`, `affected_items`, `critical_date`,
`snapshot_date`, `reason_code`, `evidence` y `traceability`, sin acoplar la
presentación a SAP.

## M. Cómo reanudar

Tras completar el smoke SQL HANA, marcar
`TELCHI_PURCHASE_MATERIAL_PLANNING_V1_PASS` y congelar formalmente. Luego, sólo
bugs, regresiones, nuevos datos/casos o un requerimiento explícito pueden abrir
V1. La futura capa `TELCHI_WEEKLY_EXECUTIVE_CASES` debe consumir este
contrato; no se implementa en este gate. Para HANA, el operador debe iniciar
manualmente el runtime con `./scripts/run-podman.sh start`; este agente no lo
ejecuta.

## Qué no cambió

No se modificaron Parquet legacy, ciclo de vida Podman/VPN, SQL productivo ni
canales UI/notificaciones. No se realizaron operaciones Git.
