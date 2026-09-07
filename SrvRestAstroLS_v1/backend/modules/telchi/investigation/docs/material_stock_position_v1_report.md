# TELCHI SAP — MATERIAL STOCK POSITION V1

**Gate:** `TELCHI_MATERIAL_STOCK_POSITION_V1_PASS`
**Date:** 2026-08-27
**HANA writes:** ZERO (READ ONLY)
**Domain:** COMPRAS / STOCK (Gate 2 del roadmap de abastecimiento)

---

## A. Resultado

**PASS** — Posición de stock confiable de materias primas, insumos, envases y
productos terminados por almacén y función logística, con semántica de
disponibilidad cerrada y reconciliación de ledger EXACTA.

---

## B. Semántica de stock — CERRADA

| Campo OITW | Semántica | Evidencia |
|---|---|---|
| `OnHand` | Stock físico neto (ledger) | 0 negativos; 32 locked |
| `IsCommited` | Comprometido a ventas/despachos abiertos | 487.292 uds, 1.355 filas |
| `OnOrder` | En órdenes de compra abiertas (no recibido) | 1.790.139 uds, 985 filas |
| `Consig` | Consignación | 78 filas, total -20.253 (anomalía) |
| `AvailablePhysical` | `OnHand - IsCommited` (SAP B1) | — |

`OnOrder` es una **capa separada** (ordenado no recibido); nunca se suma al
stock físico. `AVAILABLE_PHYSICAL_STOCK = OnHand - IsCommited`.

**Reconciliación ledger EXACTA** (P0.5):

```
OITW.OnHand == SUM(OINM.InQty) - SUM(OINM.OutQty)
```

Muestras: `L02475@LAB-M1` 447.891 == 447.891 · `L01003@LAB-T1` 24.278 ==
24.278 · `L03409@LAB-M1` 0 == 0 (diff = 0). OINM cubre 2022-03-31 → hoy;
el saldo de apertura de migración está contenido en el ledger.

---

## C. Taxonomía de 82 almacenes (P0.2)

Roles resueltos (evidencia: nombre + U_TYPE SAP/DMS + U_TIPO 01/03 + Inactive
+ residencia de producción/transferencias):

| Role | Count | Ejemplos |
|---|---:|---|
| MOBILE (DMS) | 16 | LAB-D0..D12, LPZ-D1/D2, LAB-DES |
| PRODUCTION | 9 | LAB-P1/P2/P3/P4, SAA-P1/P2(reac), MAG-P1, 2A-KIT |
| BRANCH (salón) | 8 | 2A-SAL, CM-SAL, DV-SAL, RC-SAL, UR-SAL, VI-SAL, 2A-SMK/AMK |
| DISTRIBUTION (Terbol, inactive) | 8 | BE/CBBA/CHQ/LPZ/OR/PO/SCZ/TJ-DT1 |
| FINISHED_GOOD | 8 | LAB-T1..T4, SAA-T1, MAG-T1, LPZ-T1, NTG-T1 |
| DAMAGED | 7 | 2A-DAN, CM-DAN, LAB-DAN, LPZ-DAN, SAA-DAN, LAB-T7, 2A-EXT |
| OTHER | 6 | ALM-CON, LAB-A1, 2A-MKT, 2A-MEI, LAB-VMP, DMS-PROF |
| TRANSIT | 5 | 01, SAP-R1, SAL-TRS, LAB-TRAN, 2A-TRAN |
| RAW_MATERIAL | 3 | LAB-M1, SAA-M1, MAG-M1 |
| DISPENSING | 3 | 2A-AMD, CM-AMD, 2A-MAG |
| RETURNS | 3 | 2A-DEV, DMS-DEV, LAB-T6 |
| IMPORT | 2 | ALM-IMP, LAB-IMP (U_TIPO=01) |
| QUARANTINE | 2 | LAB-C1 (CC), LAB-P5 (retención) |
| CONSIGNMENT / EXPIRED | 1 + 1 | LAB-T5 / LAB-T8 |

0 almacenes sin role (cobertura 82/82). Stock por warehouse role (OnHand):
LAB-M1 4,22 M · SAA-M1 2,61 M · LPZ-T1 2,37 M · 2A-AMD 1,29 M · resto menor.

---

## D. Clasificación de ítems (P0.3)

Reglas ordenadas, basadas en evidencia: producido (OWOR Type='S') → FG/SEMI;
componente de BOM (ITT1) → RAW/PACKAGING; grupo OITB + nombre (regex envases)
+ flags Invnt/Sell/Prchse. `OITB.ItemClass`/`RawMtrl` NO discriminan (todo
'2'/'N'), por lo que no se usan.

| Clase | Ítems | Evidencia |
|---|---:|---|
| TRADED_GOOD (reventa) | 12.082 | SellItem=Y & PrchseItem=Y (prefijo M) |
| PACKAGING (envases) | 1.728 | grupo 130 o nombre frasco/tapa/etiqueta |
| INPUT (insumo) | 1.039 | grupo 129/131/117/133 o Prchse+Invnt sin venta |
| FINISHED_GOOD | 704 | producido & vendible (OWOR + SellItem) |
| RAW_MATERIAL | 516 | componente BOM no producido (químicos) |
| SEMI_FINISHED | 192 | producido no vendible |
| SERVICE / OTHER | 6 / 1 | grupo 141 / activo fijo |
| **ITEM_CLASS_UNRESOLVED** | **525** | inventario sin señal clara (flag) |

---

## E. Invariantes (P0 Gate 2)

| Invariante | Resultado |
|---|---|
| OnHand no negativo | PASS (0) |
| ItemCode/WhsCode válidos (sin huérfanos) | PASS (0/0) |
| No duplicación ItemCode × WhsCode | PASS (0) |
| Roles de almacén resueltos | PASS (82/82) |
| UOM compatible (no sumar entre UOM) | GUARD en dominio |
| Ledger reconciliation | PASS (diff = 0 en muestras) |

---

## F. Casos trazadores (evidencia directa)

| Material | Stock físico | OnOrder (abierto) | Estado |
|---|---:|---:|---|
| Soda cáustica 25kg | 12.473 kg (SAA-M1 9.373, LAB-T3 3.100) | **108.000** (ALM-IMP) | OPEN_PURCHASE_POSITION |
| Cloruro de calcio 25kg | 301 kg | **92.000** (ALM-IMP) | OPEN_PURCHASE_POSITION |
| Benzoato de sodio 25kg | 22.867 kg | **31.500** (30.000 ALM-IMP + 1.500 SAA-P1) | OPEN_PURCHASE_POSITION |
| Frasco gotero 30mL | 106.770 | 40.800 (LAB-M1) | envase, committed-over-stock en LAB-P1 |
| Tapa gotero 30mL | 96.647 | 40.800 | envase |
| Contra-tapa gotero 30mL | 97.044 | 40.800 | envase |

El `OnOrder` vive en el almacén `ALM-IMP`/`LAB-IMP` (importación) y confirma la
posición abierta de compra del Gate 1. Los envases Matriplast muestran
`IsCommited=10.000 > OnHand=9.978` en LAB-P1 → `COMMITTED_OVER_STOCK`
(disponible negativo), señal real de tensión de stock.

---

## G. Anomalías / degradaciones

1. `Consig` total negativo (-20.253): consignación con devoluciones > entregado.
2. `ITEM_CLASS_UNRESOLVED` = 525 ítems (inventario sin señal de producción,
   BOM, envase ni grupo conocido) → no se fuerza clasificación.
3. `COMMITTED_OVER_STOCK` en envases gotero (LAB-P1).
4. Datos live: OnHand total varía levemente entre ejecuciones (alta continua).
5. UOM heterogéneas (UNI/FCO/KG/PZA/...): la suma solo es válida intra-UOM.

---

## H. Tests

| Suite | Resultado |
|---|---|
| test_stock_domain (nuevo, unit) | 20 PASS |
| Regresión producción (65) + purchases (22) + users/attribution (52) | 139 PASS |
| SQL contracts 3/3 ejecutan (validator real HANA) | PASS |
| Reconciliación ledger 3/3 muestras | PASS (diff 0) |
| `git diff --check` | OK |
| READ ONLY | PASS |

---

## I. Artefactos

```
sql/current/stock/warehouse_master_v1.sql
sql/current/stock/item_master_v1.sql
sql/current/stock/item_stock_position_v1.sql
validation/stock/stock_domain.py
validation/stock/material_stock_position_v1.py
validation/stock/test_stock_domain.py
docs/material_stock_position_v1_report.md
```

---

## J. Limitaciones

1. `IN_TRANSIT_UNRESOLVED` (heredado): `OnOrder` prueba "ordenado", no
   "embarcado/en tránsito/aduana".
2. `ITEM_CLASS_UNRESOLVED` para 525 ítems; requiere confirmación de negocio.
3. No se reconstruyó stock histórico completo (solo muestras de ledger); la
   semántica quedó demostrada por reconciliación exacta de muestra.

---

## K. Próximo gate recomendado

`TELCHI_FINISHED_GOODS_MATERIAL_EQUIVALENCE_V1` (Gate 3): convertir PT
existente a equivalentes de MP/insumos usando las recetas históricas ya
validadas (OWOR/WOR1 + ITT1), respetando UOM y sin doble conteo.
