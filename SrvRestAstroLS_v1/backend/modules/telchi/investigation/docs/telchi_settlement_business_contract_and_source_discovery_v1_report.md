# TELCHI — Settlement / cobranzas: business contract + source discovery V1

## Gate

`TELCHI_SETTLEMENT_BUSINESS_CONTRACT_AND_SOURCE_DISCOVERY_V1_PASS`

PASS significa que las fuentes, claves, relaciones, granularidades y límites necesarios están
demostrados y el componente puede diseñarse de forma defendible. **No significa que settlement esté
implementado ni publicado en Foundation.**

- Foundation vigente: `foundation_417c860c216805f18341bb741ee026e3`.
- SAP: `READ ONLY`.
- `SAP_QUERY_COUNT=46`.
- `SAP_WRITE_COUNT=0`.
- Contrato: `TELCHI_SETTLEMENT_BUSINESS_CONTRACT_V1.md`.
- Lineage: `TELCHI_SETTLEMENT_SOURCE_MAP_V1.md`.
- Evidencia estructurada: `validation/settlement_business_contract_source_discovery_v1/discovery_evidence.json`.

## A. Qué descubrimos

SAP sí conserva la realidad transaccional requerida, pero está repartida en tres capas diferentes:

1. `OINV/INV6/ORIN/OCTG`: obligación, cuotas, vencimiento y condición comercial;
2. `ORCT/RCT1/RCT2/RCT3/RCT4`: cobranza, aplicación directa y medios;
3. `OITR/ITR1`: efecto económico final, reconciliaciones, notas de crédito, pagos a cuenta y reversas.

La unión correcta de aplicación directa es `RCT2.DocNum → ORCT.DocEntry`; para una factura,
`RCT2.InvType=13` y `RCT2.DocEntry → OINV.DocEntry`. Se validó en 100% de 1.839.000 aplicaciones y
corrige una hipótesis investigativa histórica que usaba la dirección contraria. `RCT2.InvoiceId` no
es el identificador de factura en esta instancia.

El ledger de settlement es `OITR/ITR1`. No debe sumarse además de RCT2: RCT2 da lineage directo y
OITR/ITR1 da el efecto económico. Existen reconciliaciones N:N; por ello se preservan miembros y no se
inventa un reparto payment↔invoice cuando SAP no lo expresa.

La clave `source_system + object_type + doc_entry` es suficiente para documentos y pagos: no hubo
colisiones en `OINV`, `ORIN` ni `ORCT`. Reconciliaciones requieren
`source_system + reconciliation_id`. `RCT2` contiene duplicados físicamente indistinguibles y no tiene
line id; su grano defendible es la relación agregada pago-destino-cuota, con multiplicidad fuente.

## B. Qué podrá responder el futuro componente

A cierre de día y dentro de la cobertura SAP podrá responder:

- si una factura recibió uno o varios pagos y en qué fechas;
- si quedó impaga, parcial o totalmente cancelada;
- primera/última fecha de pago y fecha de cancelación total;
- días entre factura y cancelación;
- saldo actual y saldo histórico as-of;
- medios componentes de cada pago y pagos mixtos;
- pagos que cubren varias facturas y facturas cubiertas por varios pagos;
- participación de notas de crédito, asientos y reconciliaciones;
- cancelaciones y reversas;
- variantes observables de “contado”, una vez aprobada la regla comercial.

## C. Qué todavía no podrá responder

- estado intradía cuando creación y reversa comparten fecha;
- histórico anterior al 2022-03-31 observado;
- reparto de cada medio entre facturas dentro de un pago mixto;
- reparto pairwise de una reconciliación N:N no expresado por SAP;
- atribución exacta de NC por factura en componentes N:N sin vínculo adicional;
- identidad del comprador final cuando el documento usa un cliente genérico;
- UoM de ventas: es una deuda separada y settlement no depende de ella.

## D. Fuentes SAP necesarias

| Función | Fuentes |
|---|---|
| Documento/obligación | `OINV`, `INV6`, `ORIN` |
| Condición comercial | `OCTG` |
| Cobranza | `ORCT` |
| Aplicación directa | `RCT2` |
| Cheques/tarjetas | `RCT1`, `RCT3` |
| Aplicación a cuenta GL | `RCT4` |
| Settlement y reversas | `OITR`, `ITR1` |

## E. Modelo de datos mínimo

1. `settlement_document` — un documento comercial.
2. `settlement_document_installment` — una cuota.
3. `settlement_payment` — una cobranza.
4. `settlement_allocation` — relación agregada pago→destino/cuota.
5. `settlement_payment_method` — componente de medio sin aplanar pagos mixtos.
6. `settlement_reconciliation` — cabecera de reconciliación.
7. `settlement_reconciliation_member` — miembro exacto, sin pares inventados.
8. `payment_term` — dimensión contractual separada.

El componente será aditivo y enlazará `sales_document`/`credit_memo_document` por identidad nativa.
No modifica `sales`, `credit_memo`, `reference`, `oinm`, `oitw` ni `material_supply`.

## Casos reales comprobados

Solo se muestran identificadores técnicos y montos necesarios; no se exponen nombres, NIT, bancos ni
datos de tarjeta.

| # | Caso | Cadena observada |
|---:|---|---|
| 1 | Totalmente pagada el mismo día | invoice 11534591 (2026-09-27, Bs 3,52) → RCT2 → payment 2365723 (misma fecha, Bs 3,52) |
| 2 | Pagada posteriormente | invoice 11530921 (2026-09-23, Bs 83,16) → payment 2365191 (2026-09-26) |
| 3 | Pago parcial | invoice 11526331: total Bs 100,06 → pago Bs 100,00 → abierto Bs 0,06 |
| 4 | Todavía abierta | invoice 11534790: total/abierto Bs 160,52, pagado Bs 0 |
| 5 | Un pago→varias facturas | payment 2365191 Bs 249,48 → invoices 11530705, 11530918 y 11530921, Bs 83,16 cada una |
| 6 | Una factura←varios pagos | invoice 11533649 Bs 943,80 ← payments 2364806 Bs 943,00 + 2364808 Bs 0,80 |
| 7 | Nota de crédito aplicada | OITR 2654224 → ITR1 NC 21527 (C) + invoice 11533926 (D), Bs 1.915 |
| 8 | Reconciliación interna manual | OITR 2653938 (`IsSystem=N`) → payment 2364794 + invoice 11532585 + miembro 321, Bs 775 |
| 9 | Pago con varios medios | payment 2365945 Bs 21,83 = efectivo Bs 12,83 + transferencia Bs 9,00 |
| 10 | Pago cancelado | payment 2364901 Bs 427,00, fecha y cancelación 2026-09-26 → invoice 11533742 |

Además se midieron 14.759 pagos→múltiples facturas, 7.303 facturas←múltiples pagos, 12.623 pagos
mixtos y 3.076 reconciliaciones activas N:N.

## Control financiero

El control no usa la suma ingenua `RCT2 + ITR1`, que duplicaría settlement. Por documento y moneda:

```text
obligación ≈ monto reconciliado efectivo del miembro del documento + saldo abierto
```

Antes de exigir igualdad se separan NC, anticipos, descuentos, retenciones, gastos, diferencias,
asientos, cancelaciones y ejes local/FC/system. La tolerancia inicial es 0,01. Los medios sumaron el
total del pago dentro de tolerancia en 1.825.024/1.825.031 pagos activos; siete excepciones quedan
como cola explícita, no se corrigen artificialmente.

## PAYMENT_TERMS

La situación corresponde simultáneamente a:

- **A:** el dataset `reference.payment_terms` existe pero tiene 0 filas;
- **C:** la fuente real existe en SAP como `OCTG` y tiene 37 filas;
- **D:** el build de referencia que produjo CURRENT no incluyó `OCTG` entre sus fuentes SAP, por lo
  que publicó el schema vacío.

No es una dependencia de settlement. Corregir `payment_terms` permitirá `CASH_TERM`, pero no probará
pago efectivo. Debe resolverse en un gate aditivo de reference separado o junto a la implementación,
sin reabrir Foundation V1.

## F. Decisión pendiente sobre CONTADO

TELCHI debe aprobar una alternativa concreta:

- **A — `CASH_TERM`:** condición comercial configurada como contado;
- **B — `SAME_DAY_FULLY_SETTLED`:** obligación completamente cancelada el día del documento;
- **C — `IMMEDIATE_SETTLEMENT(N)`:** obligación completamente cancelada dentro de N días, indicando N;
- **D — otra definición escrita.**

`SAME_DAY_PAYMENT` y `EVENTUALLY_PAID` quedarán disponibles como hechos, pero no deben llamarse
contado sin aprobación.

## G. Siguiente gate recomendado

`TELCHI_SETTLEMENT_FOUNDATION_ADDITIVE_COMPONENT_V1`

Debe implementar las siete entidades transaccionales, poblar `payment_terms` desde `OCTG`, validar
las diez cadenas reales, reconciliar por moneda y publicar primero un candidato. Solo después de su
promoción debe reejecutarse CG2A como prueba de negocio. No consultar nuevamente CG2A antes de ese
gate.
