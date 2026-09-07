# TELCHI SAP — PURCHASE DATA DISCOVERY V1

**Gate:** `TELCHI_PURCHASE_DATA_DISCOVERY_V1_PASS`
**Date:** 2026-08-27
**HANA writes:** ZERO (READ ONLY)
**Domain:** COMPRAS → MATERIA PRIMA → INSUMOS (Gate 1 del roadmap de abastecimiento)

---

## A. Resultado

**PASS** — Documentos, tablas, estados, fechas, proveedores, clasificación
local/importación, cadenas documentales y posición abierta de compras fueron
descubiertos y validados contra SAP HANA real.

---

## B. Inventario documental (census HANA 2026-08-27)

| Tabla | Rol | Filas | Cancelados |
|---|---:|---:|---|
| OPOR / POR1 | Orden de compra (PO) | 18,663 / 97,350 | 723 Y |
| OPCH / PCH1 | Factura proveedor (AP) | 32,131 / 113,981 | 1,152 Y + 1,152 C |
| OPDN / PDN1 | Entrada de mercadería (GR) | 19,633 / 89,967 | 304 Y + 304 C |
| OPRQ / PRQ1 | Solicitud de compra (PR) | 732 / 3,171 | 15 Y |
| ORPD / RPD1 | Devolución a proveedor | 3,907 / 4,279 | 45 Y + 45 C |
| OCRD (CardType='S') | Proveedores | 1,073 (1,053 válidos) | — |

Rango temporal: `2022-01-01` → `2026-08-27`. Grain documental:
`DocEntry` (header) + `DocEntry + LineNum` (línea).

---

## C. Clasificación operativa — U_TIPOCOMPRA

`OPOR.U_TIPOCOMPRA` es la clasificación operativa real (no un UDF vacío):

| Clase | Órdenes | Proveedores | Total BS | Semántica |
|---|---:|---:|---:|---|
| LF | 14,316 | 296 | 127,682,078 | Compra local general |
| LP | 1,941 | 123 | 592,154,679 | Envases/plásticos local (SOLUPLAST, DISEÑ-AR, MATRIPLAST, INTEXPLAST, MABATE) |
| IMP | 1,917 | 57 | 118,484,374 | Importación + logística (aduana, fletes, navieras, proveedores extranjeros) |
| SERV | 365 | 58 | 811,031 | Servicios |
| SAA | 124 | 18 | 3,382,645 | Interno |

Importadores reales (IMP 2026): HAINAN ZHONGXIN (CN, soda cáustica/cloruro de
calcio/benzoato), THOSCO THODE-SCOBEL, FLORAMATIC, USP, RODAO PLAST, más
despachantes y navieras locales (URUBO, MSC, HAPAG LLOYD, Coop. German Busch).
Código `PE*` = proveedor extranjero. `OCRD.Country` NO es confiable (1,062 'BO'
incluye importadores) → la evidencia de importación vive en el documento.

---

## D. Cadena documental — SEMÁNTICA CERRADA

```
OPOR (PO)
  → OPCH (PCH1.BaseType=22, BaseEntry=OPOR.DocEntry)    90,959/90,959 = 100%
      → OPDN (PDN1.BaseType=18, BaseEntry=OPCH.DocEntry)  87,577/87,577 = 100%
  → OPDN directo (PDN1.BaseType=22, BaseEntry=OPOR.DocEntry) 54/54 = 100%
```

Link SAP canónico: `BaseEntry → DocEntry` (entero). Las tablas de línea
además exponen `BaseRef`/`BaseDocNum` (el DocNum string del documento base) y
`BaseAtCard` (número del proveedor) como representaciones redundantes; no son
la relación de registro. Verificación P0.1: ambos joins coinciden 100%, pero
el vínculo inequívoco es `BaseEntry → DocEntry`.

Flujo operativo dominante: **PO → Factura → Entrada**. La entrada de mercadería
en Telchi se registra mayormente DESPUÉS de la factura del proveedor
(invoice-first), no la secuencia clásica SAP PO→GR→AP.

Líneas sin base: PCH1.BaseType=-1 = 17,215 (facturas directas, gastos/servicios
sin ItemCode); PDN1.BaseType=-1 = 104; 304 líneas PDN1 con otros BaseTypes
(referencias producción/transferencia, documentado).

---

## E. Evidencia temporal (base para lead time, Gate 5)

| Tramo | n | Negativos | P50 | P75 | P90 | Máx |
|---|---:|---:|---:|---:|---:|---:|
| PO → Factura | 86,238 | 30,010 | 0d | 1d | 3d | 230d |
| Factura → Entrada | 85,407 | 129 (0.15%) | 1d | 3d | 5d | 1,555d |

- Invariante `receipt_date >= invoice_date`: PASS (0.15% < tolerancia 0.5%;
  129 anomalías documentadas, hasta -61 días).
- **Anomalía BACKDATED_PO**: 30,010 líneas con factura anterior a la PO
  (2,300 PO distintas; magnitud -1..-7d mayoritaria, hasta -295d). Los POs se
  crean retroactivamente respecto de la factura en una parte material del
  flujo. Implicación: el lead time de importación NO debe basarse solo en
  `OPOR.DocDate`; Gate 5 deberá combinar `OPOR.DocDate` y `OPCH.DocDate` vs
  `OPDN.DocDate` y clasificar el patrón backdated.
- `OPOR.DocDueDate`: 100% cargado (fecha prometida); 1,910 POs con due > fecha
  orden (1-30d mayoritario), 16,609 same-day.

---

## F. Posición abierta (compras en tránsito / no recibidas)

33 POs abiertas (`DocStatus='O'`): **13 IMP + 20 LF**, con líneas abiertas
(`POR1.OpenQty > 0`):

- **IMP críticos**: HAINAN ZHONGXIN 5 POs (soda cáustica 108,000 kg; cloruro de
  calcio 92,000 kg; benzoato 26,000 kg; +2 POs 26,140/22,700 uds), THOSCO
  2 POs (ácido fosfórico 25,970 kg; 108,000 uds), FLORAMATIC 5,736, USP 951,
  FRANMAR 500, ASPB/AGEMED 1.
- **LF**: MATRIPLAST 337,060 (frascos/tapas), DISEÑ-AR 41,000, y 18 POs menores
  del 2026-08-25..27 (documents recién emitidos).
- `POR1.OpenQty`: 0 negativos; 97,079 líneas cerradas; 943 fully-open; **0
  líneas parcialmente abiertas** (OpenQty entre 0 y Quantity = 0).

**IN_TRANSIT_UNRESOLVED**: SAP solo distingue ORDERED (PO abierta) vs RECEIVED
(OPDN). No existen estados de embarque/aduana/disponibilidad. No inventar
estados.

---

## G. UDF/UDT importación — NO OPERATIVOS

| Campo | Fill (18,663) | Estado |
|---|---:|---|
| U_TIPOCOMPRA | 100% | OPERATIVO (clasificación local/import) |
| U_SOLCOMPRA | 0 | UNUSED |
| U_FECHEST_EMBR / U_FECHREAL_EMBR | 2 / 0 | UNUSED |
| U_FECHPRTO / U_FECHALM / U_FECHREAL_PRTO | 2 / 2 / 0 | UNUSED |
| U_INCOTERM / U_CODPAIS / U_PDESTINO / U_LDESTINO | 0 | UNUSED |
| U_CTRLCALIDAD | 0 | UNUSED |

UDT Retail One de compras (`@SO1_01COMPRA`, `@SO1_01COMPRADETALLE`,
`@SO1_01DEVOLCOMPRA`, `@SO1_01COMPRAWEB`, `@SO1_01FAVPROVEEDOR`,
`@SO1_01SUGERENCOMPRA`): **0 filas** — el módulo de compras opera en tablas SAP
estándar. Quality flag: `IMPORT_UDF_UNUSED`.

---

## H. Proveedores

- 1,073 proveedores, 1,053 validFor; 296 LF / 123 LP / 57 IMP / 58 SERV / 18 SAA.
- Top por órdenes: SAE (1,118), LAB. BAGO (709), DROGUERIA INTI (682),
  LAB. IFA (539), SOLUPLAST (459), TERBOL (455), URUBO/aduana (419).
- Moneda: OCRD 1,021 BS / 10 USD / 42 '##'; OPOR DocCur BS 18,395 / USD 268
  (267 de ellas IMP) — la moneda del documento corrobora la clase.

---

## I. Invariantes (P0 del dominio compras)

| Invariante | Resultado |
|---|---|
| CHAIN_LINKED (PO→Factura 100%, Factura→Entrada 100%) | PASS |
| OPEN_QTY_NON_NEGATIVE | PASS |
| RECEIPT_AFTER_INVOICE (0.15% < 0.5% tolerancia) | PASS |
| CANCELED Y/C pair (OPDN/OPCH/ORPD: Y==C) | PASS |

---

## J. Tests

| Suite | Resultado |
|---|---|
| test_purchase_data_discovery_domain (nuevo, unit) | 22 PASS |
| Regresión producción (65) + users/attribution (52) | 117 PASS |
| SQL contracts 8/8 ejecutan (validator real HANA) | PASS |
| `git diff --check` | OK |
| READ ONLY | PASS |

---

## K. Artefactos

```
sql/current/purchases/purchase_order_header_v1.sql
sql/current/purchases/purchase_order_line_v1.sql
sql/current/purchases/ap_invoice_v1.sql
sql/current/purchases/goods_receipt_v1.sql
sql/current/purchases/purchase_request_v1.sql
sql/current/purchases/purchase_return_v1.sql
sql/current/purchases/supplier_v1.sql
sql/current/purchases/purchase_document_chain_v1.sql
validation/purchases/purchase_domain.py
validation/purchases/purchase_data_discovery_v1.py
validation/purchases/test_purchase_data_discovery_domain.py
docs/purchase_data_discovery_v1_report.md
```

---

## L. Limitaciones / degradaciones

1. `IN_TRANSIT_UNRESOLVED`: solo ORDERED vs RECEIVED; sin estados aduana/embarque.
2. `IMPORT_UDF_UNUSED`: los UDF de fechas de embarque no se cargan; la
   clasificación importación depende de U_TIPOCOMPRA + proveedor + moneda.
3. `BACKDATED_PO`: 30,010 líneas factura-antes-que-PO; el lead time debe
   modelar este patrón (Gate 5).
4. `OCRD.Country` no sirve para identificar importadores.
5. UDTS Retail One de compras vacías: no hay fuente paralela de sugerencias.

---

## M. Casos de negocio encontrados (evidencia directa)

1. **Importaciones en tránsito críticas**: 13 POs IMP abiertas con material
   clave (soda cáustica 108 t, cloruro de calcio 92 t, ácido fosfórico,
   benzoato) sin factura ni entrada registrada (PO 2026-05..08).
2. **Envases bloqueando producción**: MATRIPLAST 337,060 unidades de
   frascos/tapas abiertas desde 2026-04-25 (PO 262001399) — candidato directo
   al concepto LIMITING_COMPONENT del roadmap.
3. **Backdated PO**: 2,300 POs con factura anterior — la fecha de PO no es
   confiable como fecha de decisión de compra sin clasificar el patrón.
4. **Cobertura futura**: la posición "ordenado pero no recibido" (OpenQty
   acumulada por ItemCode + OPDN pendiente) alimentará
   EQUIVALENT_MATERIAL_POSITION del Gate 7.

---

## N. Próximo gate recomendado

`TELCHI_MATERIAL_STOCK_POSITION_V1` — stock real por almacén (MP, insumos, PT)
con la clasificación de almacenes ya validada en producción (LAB-M1, SAA-T1,
2A-MAG, etc.), más `TELCHI_PURCHASE_LEAD_TIME_V1` (Gate 5) sobre la cadena
documental aquí cerrada.