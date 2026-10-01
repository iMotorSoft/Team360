# TELCHI — Purchasing Foundation Promotion Implementation Plan V1

Este plan convierte el diseño de promoción en una secuencia reversible. No ejecuta publicación, no modifica Foundation CURRENT y no crea un candidato físico en esta fase.

**Target lógico:** `TELCHI_PURCHASING_FOUNDATION_V1`\
**Input contractual:** `TELCHI_PURCHASING_ANALYTICAL_CONTRACT_V1`\
**Gate actual:** `TELCHI_PURCHASING_VALIDATED_KNOWLEDGE_PROMOTION_V1_PASS`\
**Promotion required:** `YES`

## 1. Precondiciones y límites

La implementación debe vivir fuera de `investigation/`, preservar la investigación como baseline y escribir datasets físicos solamente en `DATA_ROOT` aprobado.

- Foundation CURRENT permanece intacta hasta el gate final.
- El componente candidato no puede importar runners de `investigation/` en runtime.
- No se consulta ni modifica SAP/HANA para cerrar esta promoción.
- No se reescriben migraciones aplicadas ni se cambian consumidores globales en esta fase.
- La publicación se identifica por `publication_id`, no por una ruta física.
- Si la cobertura no permite resolver una relación, se publica el estado unknown correspondiente.

## 2. Fases y criterios de salida

Cada fase tiene un artefacto verificable y una condición explícita de no avance.

### Fase 1 — Atomic publication

Publicar un candidato atómico con las seis relaciones documentales source-native y sus manifests de cobertura.

**Alcance:** `purchase_order`, `purchase_order_line`, `purchase_receipt`, `purchase_receipt_line`, `ap_invoice`, `ap_invoice_line`.\
**Salida:** `publication_id`, schema version, snapshot/as-of, row counts, source hashes y cobertura por entidad.

**No avanzar si:** falta una clave, el header no cubre la línea, hay duplicados o se mezclan hechos derivados en el schema atómico.

### Fase 2 — Lineage derivation

Construir `purchasing_document_lineage` y `purchase_inventory_receipt` con un resolver versionado y collision-safe.

**Controles obligatorios:** `BaseType/BaseEntry/BaseLine`, `trans_type`, `doc_line_num`, `ItemCode`, `CardCode` cuando esté presente, depth/cycle y path de resolución.\
**Salida:** filas `RESOLVED`, `UNRESOLVED`, `OUT_OF_COVERAGE` y razones.

**No avanzar si:** `base_ref` se usa solo, existe fanout no explicado o se convierten candidatos por cantidad/fecha en vínculos.

### Fase 3 — Validation

Ejecutar controles de contrato, calidad y cobertura sobre el mismo snapshot que originó las investigaciones.

**Mínimos:** unicidad; no fanout; ItemCode; BaseEntry/BaseLine; cancelaciones; UoM; warehouse; cantidades; multi-receipt; OINM TT20/TT18; unknown behavior.\
**Salida:** reporte de validación con pass/fail por invariant y conteos de `UNRESOLVED`.

**No avanzar si:** un failure se oculta con fallback o los límites temporales no están en el manifiesto.

### Fase 4 — Gold cases

Incorporar los diez gold cases definidos en el reporte de promoción y el contrato.

**Salida:** fixture canónica, expected JSON, resultado actual y `gold_hash`.\
**Casos:** exacto, multi-receipt exacto, parcial, exceso, AP directa, TT18 sin GRPO, cancelación/reversa, sin recepción, colisión `base_ref`, multi-warehouse.

**No avanzar si:** falta un identificador fuente, el expected depende de una ruta física o un caso unresolved se fuerza a resolved.

### Fase 5 — Candidate Foundation

Crear una publicación candidata separada, sin actualizar CURRENT.

**Forma mínima:** un componente lógico `purchasing` con seis facts atómicos y dos relaciones derivadas; reutilizar `reference` y `inventory_movement` existentes mediante publicación/provenance.\
**Salida:** manifiesto candidato, publication record, hashes, schema/contract version y estado `CANDIDATE`.

**No avanzar si:** la publicación requiere duplicar `inventory_movement`, materializa categorías causales o modifica el manifiesto CURRENT.

### Fase 6 — Parity checks

Comparar candidato contra las dos investigaciones cerradas usando la misma ventana y inputs.

**Paridad esperada:**

- 16.355 líneas del universo principal y clasificación equivalente;
- 15.471 líneas completamente reconciliadas;
- 29 multi-receipt y 3 multi-warehouse;
- 0 fanout, 0 ItemCode mismatch y 0 UoM incompatibles en la cohorte comparable;
- 25 AP targets, 683.025 unidades, 10 categorías y 2 TT18 lines;
- 30 candidatos rechazados y 0 receipt links a los 25 targets;
- colisión `262000261` separada por familia documental;
- diferencias explicadas solo por canonicalización, cobertura o redondeo documentado.

**Salida:** `PINNED_VS_CANDIDATE_RESULT_MATCH` y diff analítico firmado.

**No avanzar si:** hay diferencia inesperada, cambio de categoría, fanout o pérdida de provenance.

### Fase 7 — Promotion gate

Solicitar una ventana explícita de promoción para comparar y publicar, manteniendo el candidato y CURRENT separados.

El gate debe confirmar publication id, snapshot/as-of, schema/contract version, gold hash, provenance, tests focalizados, parity, cobertura, unknown behavior y ausencia de cambios SAP.

**Salida:** `TELCHI_PURCHASING_FOUNDATION_V1_PASS` o `..._DEGRADED`/`..._BLOCKED` con reason codes.

No se debe emitir PASS de promoción productiva por un HTTP 200, una lectura del manifiesto o una sola query correcta.

### Fase 8 — CURRENT update

Actualizar CURRENT únicamente después del gate específico de promoción y con una operación de publicación auditable.

**Salida:** nuevo `foundation_publication_id`, manifiesto CURRENT, estado anterior `SUPERSEDED`, hash de gold productivo y evidencia de rollback/preservación.

Esta fase no forma parte de la evaluación actual y requiere autorización independiente.

## 3. Diseño de componentes mínimo

La estructura mínima evita cinco componentes independientes y conserva separación atomic/derived.

| Capa | Contenido | Tratamiento |
|---|---|---|
| Atomic | seis relaciones de PO, receipt y AP | source-native, una por header/line |
| Reference | products, warehouses, suppliers | reutilizar publicación existente |
| Atomic existente | inventory movement | reutilizar publicación existente, sin duplicar |
| Derived | `purchasing_document_lineage` | aristas por línea y path |
| Derived | `purchase_inventory_receipt` | atribución de movement a línea |
| Rule | quantities/status/business flags | cálculo determinista, no fuente |

`purchase_order`, `purchase_receipt` y `ap_invoice` no deben convertirse en componentes físicos separados salvo que una decisión posterior demuestre una necesidad de ownership o ciclo de vida distinto.

## 4. Repositorio y ownership

El plan es una tarea Telchi de investigation/development diseñada sobre el módulo local; no autoriza cambios globales o productivos.

- Diseño y evidencia: `backend/modules/telchi/investigation/docs/`.
- Futura implementación: `backend/modules/telchi/` fuera de `investigation/`.
- Datos físicos: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi` (`DATA_ROOT`, DATA ONLY).
- CURRENT y operaciones de publicación: requieren gate/ventana explícita.
- `Foundation CURRENT` y manifiestos productivos: no editar durante las fases 1–6.

Cualquier necesidad de tocar paths `GLOBAL`, migraciones, registries, lockfiles o producción debe detenerse y coordinarse antes de editar.

## 5. Test matrix

Los tests se separan entre unitarios puros, validación de datos y parity para no confundir una ejecución focalizada con una publicación válida.

| Suite | Propósito | Gate |
|---|---|---|
| Resolver unit tests | BaseType paths, cycles, missing base, collision guard | Fases 2–3 |
| Atomic contract tests | claves, grain, nullability y coverage | Fases 1–3 |
| Derived invariant tests | fanout, ItemCode, UoM, warehouse, quantities | Fase 3 |
| OINM crosswalk tests | TT20/TT18, line, item, supplier, unresolved | Fases 2–3 |
| Gold tests | diez fixtures y `gold_hash` | Fase 4 |
| Snapshot parity | igualdad contra reportes de investigación | Fase 6 |
| Publication manifest tests | provenance, versions, status transitions | Fases 5–7 |

Los conteos de un snapshot son expected de parity, no invariantes universales. Las invariantes son las reglas de identidad, resolución y failure behavior.

## 6. Rollback y failure behavior

Una publicación candidata debe poder descartarse sin tocar CURRENT ni reescribir evidencia histórica.

- Fallo atomic: descartar candidate publication y conservar source snapshot.
- Fallo lineage: marcar candidate `REJECTED` con reason code; no emitir relaciones parciales como resolved.
- Fallo parity: detener gate y conservar diff.
- Fallo gold: no promover; actualizar diseño solo mediante nueva versión.
- Fallo de cobertura: publicar `DEGRADED` o bloquear, nunca extender ventana silenciosamente.
- Fallo de manifest: no cambiar CURRENT.

No hacer rollback destructivo de una publicación ya auditada; cambiar estado mediante nueva publicación superseding cuando exista una promoción real.

## 7. Criterio de listo para promoción

El candidato está listo solo cuando el contrato sea ejecutable y todos los límites observados estén representados en datos y manifest.

Checklist:

- [ ] resolver `base_ref` collision-safe implementado;
- [ ] `DocEntry + LineNum` y source keys únicos;
- [ ] cobertura temporal por entidad publicada;
- [ ] unresolved/out-of-coverage explícitos;
- [ ] cancelaciones y reversas preservadas;
- [ ] UoM y cantidad base auditables;
- [ ] warehouse documental y movimiento preservados;
- [ ] multi-receipt/multi-warehouse sin colapsar;
- [ ] TT20/TT18 crosswalk validado;
- [ ] diez gold cases y `gold_hash`;
- [ ] parity sin diferencias inesperadas;
- [ ] consumer contract sin rutas físicas;
- [ ] ventana de promoción autorizada;
- [ ] Foundation CURRENT aún no modificada antes del gate.

## 8. Próximo paso autorizado

El siguiente paso recomendado es implementar solamente el candidato fuera de CURRENT y ejecutar fases 1–4 con una ventana `DEVELOPMENT` explícita. La promoción a CURRENT y la publicación productiva quedan fuera de esta evaluación.
