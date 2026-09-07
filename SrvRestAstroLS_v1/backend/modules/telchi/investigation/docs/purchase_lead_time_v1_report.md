# TELCHI SAP — PURCHASE LEAD TIME V1

**Gate:** `TELCHI_PURCHASE_LEAD_TIME_V1_PASS`
**Date:** 2026-08-27
**HANA writes:** ZERO (READ ONLY)
**Domain:** COMPRAS / LEAD TIME (Gate 5 del roadmap)

---

## A. Resultado

**PASS** — Lead time de compra medido sobre la cadena documental real, con
granularidad de línea, recepciones parciales soportadas, ciclo cancelado
preservado, y separación explícita entre lead time documental y físico.

---

## B. Semántica cerrada

| Concepto | Definición |
|---|---|
| PO grain | `POR1.DocEntry + LineNum` (0 colisiones) |
| Receipt grain | `PDN1.DocEntry + LineNum` (0 colisiones) |
| Document linkage | PO→invoice `PCH1.BaseType=22, BaseEntry=POR1.DocEntry, BaseLine=POR1.LineNum` (90.782/90.998 = 99,8%); invoice→receipt `PDN1.BaseType=18, BaseEntry=OPCH.DocEntry, BaseLine=PCH1.LineNum` (87.616/87.616 = 100%) |
| Order date | `OPOR.DocDate` (con flag `BACKDATED_PO`) |
| Receipt date | `OPDN.DocDate` |
| First receipt | MIN(receipt date) |
| Full receipt | fecha donde recepción acumulada ≥ ordenada |

Cadena invoice-first (Gate 1): `OPOR → OPCH → OPDN`; directo PO→receipt
marginal (54 líneas `BaseType=22`).

---

## C. Cobertura

| Métrica | Valor |
|---|---:|
| PO líneas (no canceladas) | 88.238 |
| FULL_RECEIVED | 84.552 |
| PARTIAL_RECEIPT | 166 |
| OPEN_UNRECEIVED | 241 |
| CLOSED_WITHOUT_FULL_RECEIPT | 3.279 (2.654 items + 656 servicios) |
| Recepciones sin PO lineage | 8 |

---

## D. Lead time

**Global (first receipt, PO→receipt):**

| | días |
|---|---:|
| n | 84.718 |
| mediana | 0 |
| p75 | 2 |
| p90 | 5 |
| mean | 3,67 |
| min / max | -147 / 1.555 |

**Por `U_TIPOCOMPRA` (first receipt):**

| Tipo | n | mediana | p75 | p90 | mean |
|---|---:|---:|---:|---:|---:|
| LF (local) | 77.221 | 0 | 2 | 4 | 1,54 |
| LP (envases) | 3.038 | 7 | 17 | 43 | 19,2 |
| IMP (importación) | 4.292 | 2 | 14 | **82** | 30,5 |
| SAA | 167 | 7 | 15 | 34 | 15,9 |

---

## E. Supplier

- 11.077 pares ItemCode×CardCode; **1.076 ítems multi-proveedor**.
- Distribución de muestra: USABLE 4.777 · LOW 3.262 · VERY_LOW 3.038.
- Top proveedores (n, mediana, p90): PL000032 (7.812, 0, 4) · PL000017 (5.859,
  0, 2) · PL000026 (3.565, 1, 7) · PL000001 (2.350, 0, 3, max 165) ·
  PL000042 (1.620, 0, 7, max 153).

---

## F. Componentes críticos (Gate 4) — lead time de compra

| Componente | n | mediana | p90 | Interpretación |
|---|---:|---:|---:|---|
| L00205 (etiqueta MP) | 10 | 2 | 10 | repone rápido |
| L00838 (precinto) | 7 | 3 | 34 | p90 elevado |
| L00219 (tapa PET) | 12 | 13 | 113 | alta dispersión |
| L00097 (frasco 1L) | 74 | 4 | 110 | lead time largo en p90 |

---

## G. Anomalías

1. **NEGATIVE_LEAD_TIME**: 382 eventos (0,45%), mediana -5, max -147 →
   patrón `BACKDATED_PO` (factura/recepción anteriores a la fecha de PO).
   No normalizados silenciosamente.
2. Recepción sin PO lineage: 8 líneas (clasificadas `RECEIPT_WITHOUT_PO`).
3. CLOSED_WITHOUT_FULL_RECEIPT: 3.279 (líneas cerradas sin recepción; 656 son
   servicios).
4. Outliers extremos: max 1.555 días (importación, trazable, no eliminado).

---

## H. Procurement mode

PURCHASED 9.804 · PRODUCED 889 · MIXED 7. Los semi-elaborados producidos NO
reciben lead time de compra ficticio.

---

## I. Hallazgo ejecutivo central

**El lead time documental NO es el lead time físico de suministro.**

- Local (LF): mediana 0, p90 4 días → la PO se emite junto/después de la
  factura (invoice-first + backdated), no mide el ciclo físico real.
- Importación (IMP): mediana 2, p90 **82 días** → sí refleja el ciclo real de
  importación.
- **Open PO age** (proxy físico): 241 líneas abiertas, p90 97 días, max 124;
  IMP abiertas promedio 57,6 días.

`PHYSICAL_SUPPLY_LEAD_TIME` = UNRESOLVED para completados locales (PO.DocDate
es administrativa); para importaciones es observable vía p90=82d y open-age.

---

## J. Runtime / invariantes

HANA/VPN/Podman: sin cambios; HANA_WRITES = 0. Invariantes:
`first_lead <= full_lead` (test); negativos controlados (test); partial
soportado (test); no doble conteo por joins 1:N (grain único verificado).

---

## K. Tests

| Suite | Resultado |
|---|---|
| test_lead_time_domain (nuevo, unit) | 9 PASS |
| Regresión production 65 + purchases 22 + stock 20 + equivalence 15 + capacity 13 + users 52 | 187 PASS |
| SQL contract 1/1 ejecuta | PASS |
| `git diff --check` | OK |
| READ ONLY | PASS |

---

## L. Artefactos

```
sql/current/lead_time/purchase_lead_time_event_v1.sql
validation/lead_time/lead_time_domain.py
validation/lead_time/purchase_lead_time_v1.py
validation/lead_time/test_lead_time_domain.py
docs/purchase_lead_time_v1_report.md
```

---

## M. Próximo gate recomendado

`TELCHI_PRODUCT_SEASONALITY_V1` (Gate 6): demanda histórica por ItemCode/mes/
año, clasificación STABLE/SEASONAL/GROWING/DECLINING/INTERMITTENT, con
P0 en BRONCEADORES y baselines de forecast + backtesting.
