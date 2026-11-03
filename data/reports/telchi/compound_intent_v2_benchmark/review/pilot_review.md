# Paquete piloto para revision humana

Sin predicciones de candidatos. El gold describe la intencion del usuario.
Holdout de 20 turnos sellado y fuera de este paquete.

## S01_1 - conversacion S01, turno 1 (simple)

- **Mensaje original:** Ventas de mayo de 2026
- **Contexto anterior:** (sin turno previo)
- **Accion esperada:** EXECUTE
- **Independencia actual:** MODEL_ASSISTED_PROVISIONAL

| review_id | categoria | procedencia | requisito propuesto | evidencia literal |
| --- | --- | --- | --- | --- |
| `S01_1.metric` | metric | CURRENT_REQUEST | sales.net_amount | Ventas |
| `S01_1.time` | temporal_periodicity | CURRENT_REQUEST | 2026-05-01 -> 2026-06-01 | mayo de 2026 |

Notas del gold: (ninguna)

## S02_1 - conversacion S02, turno 1 (simple)

- **Mensaje original:** Dame las últimas 10 ventas registradas
- **Contexto anterior:** (sin turno previo)
- **Accion esperada:** EXECUTE
- **Independencia actual:** MODEL_ASSISTED_PROVISIONAL

| review_id | categoria | procedencia | requisito propuesto | evidencia literal |
| --- | --- | --- | --- | --- |
| `S02_1.metric` | metric | CURRENT_REQUEST | sales.latest_documents | últimas 10 ventas |
| `S02_1.limit` | metric | CURRENT_REQUEST | 10 | 10 |

Notas del gold: (ninguna)

## S03_1 - conversacion S03, turno 1 (simple)

- **Mensaje original:** ¿Cuál es el último mes con ventas registradas?
- **Contexto anterior:** (sin turno previo)
- **Accion esperada:** EXECUTE
- **Independencia actual:** MODEL_ASSISTED_PROVISIONAL

| review_id | categoria | procedencia | requisito propuesto | evidencia literal |
| --- | --- | --- | --- | --- |
| `S03_1.metric` | metric | CURRENT_REQUEST | sales.coverage | ventas registradas |
| `S03_1.gran` | temporal_periodicity | CURRENT_REQUEST | month | último mes |
| `S03_1.ref` | reference | CURRENT_REQUEST | Mes más reciente con datos disponibles | último mes |

Notas del gold: (ninguna)

## S04_1 - conversacion S04, turno 1 (simple)

- **Mensaje original:** Buscá Citrato de magnesio
- **Contexto anterior:** (sin turno previo)
- **Accion esperada:** EXECUTE
- **Independencia actual:** MODEL_ASSISTED_PROVISIONAL

| review_id | categoria | procedencia | requisito propuesto | evidencia literal |
| --- | --- | --- | --- | --- |
| `S04_1.metric` | metric | CURRENT_REQUEST | products.search | Buscá |
| `S04_1.product` | entity_product | CURRENT_REQUEST | Producto buscado: Citrato de magnesio | Citrato de magnesio |

Notas del gold: (ninguna)

## S05_1 - conversacion S05, turno 1 (simple)

- **Mensaje original:** Ventas de mayo de 2026
- **Contexto anterior:** (sin turno previo)
- **Accion esperada:** EXECUTE
- **Independencia actual:** MODEL_ASSISTED_PROVISIONAL

| review_id | categoria | procedencia | requisito propuesto | evidencia literal |
| --- | --- | --- | --- | --- |
| `S05_1.metric` | metric | CURRENT_REQUEST | sales.net_amount | Ventas |
| `S05_1.time` | temporal_periodicity | CURRENT_REQUEST | 2026-05-01 -> 2026-06-01 | mayo de 2026 |

Notas del gold: (ninguna)

## S05_2 - conversacion S05, turno 2 (simple)

- **Mensaje original:** ¿Y el mes anterior?
- **Contexto anterior:** Ventas de mayo de 2026
- **Accion esperada:** EXECUTE
- **Independencia actual:** MODEL_ASSISTED_PROVISIONAL

| review_id | categoria | procedencia | requisito propuesto | evidencia literal |
| --- | --- | --- | --- | --- |
| `S05_2.time` | temporal_periodicity | CURRENT_REQUEST | 2026-04-01 -> 2026-05-01 | el mes anterior |

Notas del gold: Desplazamiento relativo de mes; conserva la métrica del turno previo.

## S06_1 - conversacion S06, turno 1 (simple)

- **Mensaje original:** Quiero importes y cantidades
- **Contexto anterior:** (sin turno previo)
- **Accion esperada:** ASK
- **Independencia actual:** MODEL_ASSISTED_PROVISIONAL

| review_id | categoria | procedencia | requisito propuesto | evidencia literal |
| --- | --- | --- | --- | --- |
| `S06_1.importes` | metric | CURRENT_REQUEST | sales.net_amount | importes |
| `S06_1.cantidades` | metric | CURRENT_REQUEST | sales.source_top_items | cantidades |

Notas del gold: Sin período todavía; no bloquea, pide el dato faltante.

## S06_2 - conversacion S06, turno 2 (simple)

- **Mensaje original:** mayo de 2026
- **Contexto anterior:** Quiero importes y cantidades
- **Accion esperada:** EXECUTE
- **Independencia actual:** MODEL_ASSISTED_PROVISIONAL

| review_id | categoria | procedencia | requisito propuesto | evidencia literal |
| --- | --- | --- | --- | --- |
| `S06_2.time` | temporal_periodicity | CURRENT_REQUEST | 2026-05-01 -> 2026-06-01 | mayo de 2026 |
| `S06_2.inherited` | metric | INHERITED_CONTEXT | sales.net_amount | importes |

Notas del gold: Completa el período pendiente conservando importes/cantidades.

## ABRAHAM_001 - conversacion ABRAHAM_001, turno 1 (abraham)

- **Mensaje original:** ¿Cuántos clientes tenemos en horizontal, principalmente las farmacias, y cuánto se les vende por mes?
- **Contexto anterior:** (sin turno previo)
- **Accion esperada:** ASK
- **Independencia actual:** MODEL_ASSISTED_PROVISIONAL

| review_id | categoria | procedencia | requisito propuesto | evidencia literal |
| --- | --- | --- | --- | --- |
| `ABRAHAM_001.customers` | metric | CURRENT_REQUEST | customer_count | Cuántos clientes |
| `ABRAHAM_001.sales` | metric | CURRENT_REQUEST | sales.unspecified | cuánto se les vende |
| `ABRAHAM_001.channel` | segment_geography | CURRENT_REQUEST | HORIZONTAL | horizontal |
| `ABRAHAM_001.pharmacies` | segment_geography | CURRENT_REQUEST | farmacias | farmacias |
| `ABRAHAM_001.monthly` | temporal_periodicity | CURRENT_REQUEST | month | por mes |
| `ABRAHAM_001.ambiguity` | ambiguity | CURRENT_REQUEST | Población: clientes registrados vs compradores del período | Cuántos clientes |

Notas del gold: Ambigüedad de población; el canal horizontal es explícito.

## ABRAHAM_002 - conversacion ABRAHAM_002, turno 1 (abraham)

- **Mensaje original:** Venta de Citrato de magnesio en la paz y cochabamba, en la paz distribucion propia y en conchabamba lo hace L&S
- **Contexto anterior:** (sin turno previo)
- **Accion esperada:** ASK
- **Independencia actual:** MODEL_ASSISTED_PROVISIONAL

| review_id | categoria | procedencia | requisito propuesto | evidencia literal |
| --- | --- | --- | --- | --- |
| `ABRAHAM_002.geo_lp` | segment_geography | CURRENT_REQUEST | La Paz | la paz |
| `ABRAHAM_002.geo_cbba` | segment_geography | CURRENT_REQUEST | Cochabamba | cochabamba |
| `ABRAHAM_002.rel_lp` | relation | USER_ASSERTED_UNVERIFIED | Citrato de magnesio -> distribution -> propia (La Paz) [USER_ASSERTED_UNVERIFIED] | en la paz distribucion propia |
| `ABRAHAM_002.rel_cbba` | relation | USER_ASSERTED_UNVERIFIED | Citrato de magnesio -> distribution -> L&S (Cochabamba) [USER_ASSERTED_UNVERIFIED] | en conchabamba lo hace L&S |

Notas del gold: Tuplas (producto, distribuidor, geografía) afirmadas por el usuario; nunca certificadas.
