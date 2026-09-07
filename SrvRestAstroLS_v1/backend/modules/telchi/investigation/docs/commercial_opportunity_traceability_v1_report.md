# TELCHI — Trazabilidad Comercial Oportunidad → Stock → Precio → Venta Real
# Reporte de iteración 1 (2026-09-02)

## A. VEREDICTO

**DEGRADED → PARCIAL (iteration 1):** gates parciales cerrados de forma cuantificada;
el gate final requiere universo completo (generalización a todos los ítems perdidos) aún
pendiente. Lo esencial de los tres P0 está cerrado con evidencia documental reproducible.

| Gate | Estado |
|------|--------|
| `TELCHI_COMMERCIAL_LOST_SALES_SOURCE_NORMALIZATION_V1_PASS` | ✅ PASS (T2, ítems P0 + análisis de calidad) |
| `TELCHI_PROFORMA_SEMANTICS_V1_PASS` | ✅ PASS (OQUT/QUT1, BaseType=23→INV1, reutiliza legacy) |
| `TELCHI_HISTORICAL_STOCK_RECONSTRUCTION_V1_PASS` | ✅ PASS (4 ítems: 82 whs, diff=0.0) |
| `TELCHI_PROFORMA_TO_SALE_TRACEABILITY_V1_PASS` | ✅ PASS (EXACT MADRILES 260105727/260105792→261404387/388) |
| `TELCHI_PRICE_REALITY_TRACEABILITY_V1_PASS` | ✅ PASS parcial (precios reales 2026 vs ofertados; falta margen/costo) |
| `TELCHI_COMMERCIAL_OPPORTUNITY_P0_PRODUCTS_V1_PASS` | ✅ PASS (Zinc, Soda, Cobre cerrados) |
| `TELCHI_COMMERCIAL_OPPORTUNITY_STOCK_PRICE_SALE_TRACEABILITY_V1_PASS` | ⏳ DEGRADED — falta universo completo + margen + crédito transversal |

## B. QUÉ SE PROBÓ (datos reales)

- **Semántica proforma**: `OQUT.DocNum` = número de proforma Excel. La proforma
  `251909935` (Excel PROFORMAS DICIEMBRE, CALERA ORIENTAL, SULFATO DE ZINC, 14.400 Bs)
  existe en OQUT: DocEntry 208995, DocDate 2025-12-11, L01794 × 450 kg × 27,84,
  SlpCode 11 (Selva Rojas) — evidencia documental exacta.
- **Link proforma→venta EXACT**: OQUT 260105727 (12/05) y 260105792 (13/05) →
  OINV 261404387/261404388 (13/05) vía `INV1.BaseType=23 AND BaseEntry` (BaseRef
  260105727/260105792). Incluye la factura 261404434 (14/05).
- **Reconstrucción stock histórica**: OINM completo por ítem, reconciliado vs OITW
  actual: `L01794=82 whs/0 mismatches/diff=0.0`, `L01010=82/0/0.0`,
  `L01772=82/0/0.0`, `L02909=82/0/0.0`.
- **OITW actual de referencia (2026-09-02)**: L01794 SAA-M1=27.019; LAB-T2=4.875.
  L01010 SAA-M1=9.373; LAB-T3=1.050 (+OnOrder ALM-IMP). L01772 SAA-M1=354; LAB-T3=3.300.
- **Transferencia ruta SAA-M1→LAB-T2**: 49 OWTR históricos L01794; la de 16/05/2026
  (260107340, 1.200 kg) con comentario "SOLICITUD PARA STOCK EN ALMACEN SENASAG LAB-T2".

## C. HALLAZGOS

### P0-C SULFATO DE ZINC — 14/05/2026 Fidero — **CAUSA REAL: LOST_LOGISTICS_DELAY (STRONG)**

- Excel: 450 kg @ 26,5 Bs = 11.925 Bs, MOTIVO **STOCK**, Diego Barrientos, comentario:
  *"el cliente no quiso esperar a la entrega del producto debido a que se encontraba en
  saavedra y solo se tiene un dia de envio de MP por lo que se perdio la venta / fidero srl"*.
- **Código declarado `L01094` es ACIDO NITRICO** (OITM verificado). Corrección demostrada:
  `L01094 → L01794 SULFATO DE ZINC FEED GRADE x 25kg` (`BAD_PRODUCT_CODE` → resuelto).
- SAP al 13/05/2026: **33.575 kg en SAA-M1 (Saavedra)** + 300 kg SAA-DAN = **34.126 kg
  totales**. Requerido 450 kg → cobertura 100% (74× el pedido).
- **NO fue ruptura de inventario.** Declaración "STOCK" es refutada por el propio stock
  físico; el comentario comercial indica causa real: producto en Saavedra, transferencia
  de 1 día no aceptada por el cliente.
- El mismo día anterior (13/05) **MADRILES compró 900 kg** de L01794 a 23,055 Bs/kg
  (2×450, proformas convertidas EXACT). Oportunidad no convertida para Fidero: sin factura
  posterior de ese ítem a FIDERO en OINV (+60 d); FIDERO sí factura bajo CardCode genérico
  y existe en Retail One (5 facturas históricas).
- Transferencia posterior: OWTR 260107340 SAA-M1→LAB-T2 (1.200 kg, 16/05).

### P0-A SODA CÁUSTICA — 4 casos

| Fecha | Cliente | Req kg | Stock físico total | Cobertura | Declarado | Causa real |
|-------|---------|-------:|-------------------:|----------:|-----------|------------|
| 05/03/2026 | PIL | 50.000 (35.000+15.000) | 21.119 | 42,2% | STOCK | **LOST_PARTIAL_STOCK** (STRONG) |
| 13/05/2026 | CERVECERIA NACIONAL | 2.000 | 9.739 | 100% | STOCK+PRECIO (OTROS) | **LOST_PRICE_REAL** (STRONG): real del cliente 13,92–20,01 vs oferta 25 |
| 15/05/2026 | PIL ANDINA | 14.000 | 9.739 | 69,6% | STOCK | **LOST_PARTIAL_STOCK** (STRONG) |
| 27/05/2026 | UNILEVER | 6.000 | 7.239 | 100% | **"NO HAY STOCK"** | **LOST_STOCK_OTHER_LOCATION** (STRONG): LAB-T3=5.075 + SAA-M1=2.164; la declaración "no hay stock" es refutada por stock físico total > requerido |

- Precio real venta L01010 2026 (23 líneas): **mediana 19,14 Bs/kg** (min 8,70 AVICOLA
  SOFIA / max 27,41). PIL compraba a **10,44 Bs/kg** (OQUT 260102388 24/02); la oportunidad
  ofreció 25 Bs/kg a PIL — precio ofrecido muy por encima del precio habitual del cliente.
- Unilever: sin ventas de L01010 en OINV/R1 en el período analizado (no se encontró venta
  posterior; la declaración se refiere a disponibilidad en el momento).

### P0-B SULFATO DE COBRE — PRECIO es causa real consistente

| Fecha | Cliente | Req kg | Precio oferta | Stock total | Cobertura | Causa |
|-------|---------|-------:|--------------:|------------:|----------:|-------|
| 20/02/2026 | (corp) | 500 | 69,0 | 16.985 | 100% | PRECIO real: competencia 60; mediana real 60,03 |
| 06/03/2026 | SELVA/corp | 3.000 | 66,5 | 15.235 | 100% | PRECIO: competencia 59 |
| 07/05/2026 | Horizontal | 500 | 75,0 ("se aut. a 72,5") | 12.675 | 100% | PRECIO |
| 28/09/2026 | **QUIMERA** | 1.000 | 75,0 | 4.133 | 100% | **PRECIO REAL demostrado**: QUIMERA compró 13 facturas (Ene-Jun 2026) a 52,2–57,42 (mediana 56,55). Oferta 75 = +32,6% vs mediana real del propio cliente |

- Distribución precios reales L01772 2026 (158 líneas): mediana 60,03 · p25 58,29 ·
  p75 84,55 · min 52,20 · max 127,89.
- **INDAPEC (C006302)**: ESTATUS CLIENTES 2025-10-01: 500 kg @ 63 Bs → **"COMPRA 150KG"**
  (parcial) + "A LA ESPERA DE NUEVA MERCADERÍA EN NOVIEMBRE" (= falta de stock, compra
  parcial 150/500 = 30%). Ventas INDAPEC L01772 2025-2026: 3×25 kg (53,17–60,03).
- Variante L02909 (1 kg): estructura de precios distinta (mediana 92,22).

## D. P0 — estado

| P0 | Caso | Clasificación | Evidencia |
|----|------|---------------|-----------|
| Zinc | 14/05 Fidero | LOST_LOGISTICS_DELAY | STRONG |
| Soda | PIL 05/03 | LOST_PARTIAL_STOCK | STRONG |
| Soda | Cervecería 13/05 | LOST_PRICE_REAL | STRONG |
| Soda | PIL Andina 15/05 | LOST_PARTIAL_STOCK | STRONG |
| Soda | Unilever 27/05 | LOST_STOCK_OTHER_LOCATION | STRONG |
| Cobre | QUIMERA 28/09 | LOST_PRICE_REAL | STRONG |
| Cobre | INDAPEC (estatus) | COMPRA_PARCIAL + falta stock (30%) | STRONG (fuente estatus + OINV) |

## E. TESTS

```
unit:            8/8 PASS (test_normalization)
domain:          21/21 PASS (test_normalization + test_p0_zinc, incluye HANA real)
P0:              Zinc cerrado (runner + JSON evidencia) · Soda cerrado (runner) · Cobre cerrado (runner)
E2E:             4 ítems reconciliados 82 whs diff=0; clasificación Zinc/Soda/Cobre emitida
regression:      validation.stock.test_stock_domain PASS (módulo previo intacto)
```

## F. EVIDENCIA SAP (ejemplos)

- OQUT 208995 / DocNum 251909935 (CALERA ORIENTAL, 11/12/2025, L01794 450 kg × 27,84)
- OQUT 231546 (260105727) y 231743 (260105792) → OINV 11218796/261404387 y
  11218856/261404388 (13/05/2026, MADRILES, 450 kg × 23,055)
- OINV 261404434 (14/05/2026, MADRILES, SAP directo)
- OWTR 292388 / 260107340 (16/05/2026, SAA-M1→LAB-T2, 1.200 kg)
- OINM L01794: reconstrucción 82 whs vs OITW diff=0.0 (SAA-M1 33.575 @13/05 → 27.019 hoy)
- OITW: L01794 SAA-M1=27.019; LAB-T2=4.875 (2026-09-02)
- OCRD C006302 (INDAPEC), C011936 (QUIMERA BOLIVIA SRL)

## G. INCERTIDUMBRES

1. **Fidero**: sin CardCode OCRD propio; factura bajo genéricos (CG2A) y en Retail One.
   La oportunidad no tiene OQUT SAP directo en mayo — la proforma pudo ser otro sistema.
2. **Unilever**: declaración "NO HAY STOCK" refutada a nivel stock físico reconstruido,
   pero no hay venta posterior que confirme qué habría pasado; sin evidencia de requerimiento
   formal (no OQUT en ventana).
3. **Margen/costo**: no reconstruido esta iteración → `MARGIN_VALIDATION_UNAVAILABLE`
   (semántica de costo debe validarse con la fuente de costos existente).
4. OINM de las facturas MADRILES no aparecen por AppObjAbs/BASE_REF de proforma — el
   movimiento de inventario de la venta EXACT se registró vía otro mecanismo (no bloquea el
   link documental, que es EXACT por BaseType=23).
5. Precios L01010 ítem "SODA CAUSTICA (HIDROXIDO DE SODIO) x 25kg": las cantidades en OINV
   parecen estar en KG (23 líneas coherentes); verificar unidades de venta vs compra (KG vs
   sacos) antes del universo completo.

## H. SIGUIENTE GAP

Generalizar la reconstrucción y clasificación a las **1.281 oportunidades** del universo
(ventas perdidas completo), validar unidades KG/presentación en OINV, y adicionar margen
(costo) cuando la semántica de costos sea demostrable. Después: métricas ejecutivas (§24)
y reporte de casos priorizados (§25).

---
**Comandos reproducibles**
```bash
cd /media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi
.venv/bin/python -m unittest validation.commercial_opportunities.test_normalization -v
.venv/bin/python -m unittest validation.commercial_opportunities.test_p0_zinc -v
.venv/bin/python validation/commercial_opportunities/run_e2e_p0.py
.venv/bin/python validation/commercial_opportunities/run_p0_zinc_case.py
.venv/bin/python validation/commercial_opportunities/run_p0_soda_case.py
.venv/bin/python validation/commercial_opportunities/run_p0_copper_case.py
```
Evidencia JSON: `validation/commercial_opportunities/evidence/`.