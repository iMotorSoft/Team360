# TELCHI — Compras → Ingreso a Almacén (PURCHASE_TO_WAREHOUSE_RECEIPT_RECONCILIATION_V1)

**Gate:** `TELCHI_PURCHASE_TO_WAREHOUSE_RECEIPT_RECONCILIATION_V1_PASS`
**Etapa:** `INVESTIGATION` · **Entity:** `TELCHI` · **Domain:** `COMPRAS_Y_ABASTECIMIENTO` + `STOCK_E_INVENTARIOS`
**Fuente:** Data Lake ONLY (`SAP_ACCESSED=NO`, `SAP_QUERY_COUNT=0`, `SAP_WRITE_COUNT=0`)
**Ventana analizada:** 2026-01-01 → 2026-09-23 (snapshot Data Lake as-of 2026-09-24/25)
**Foundation CURRENT:** `foundation_d222a203801cc84e9a14164d26aa67a0` (7 componentes lógicos)
**Evidencia:** `investigation/validation/purchase_to_warehouse_receipt_reconciliation_v1/evidence/summary_20261001T002820.json` + `po_line_reconciliation_20261001T002820.jsonl` (detalle línea a línea)
**Runner:** `investigation/validation/purchase_to_warehouse_receipt_reconciliation_v1/run_gate.py` · Tests: `test_reconciliation.py` (15 PASS)

---

## A. Respuesta ejecutiva

**Sí, en su inmensa mayoría: el 94,59 % de las líneas de compra del período reconcilia
exactamente —documento a documento y línea a línea— con su ingreso a almacén por la misma
cantidad, y el 99,99 % de las líneas de factura de compra con recepción también reconcilia
exactamente.**

De 16.355 líneas de compra inventariables (3.219 órdenes de compra válidas, 2026):

- **15.471 líneas (94,59 %) reconcilian exactamente** (15.460 en una sola recepción + 11
  mediante múltiples recepciones que suman exacto);
- **31 líneas (0,19 %) tienen recepción parcial** (faltan 594.155,58 unidades base);
- **8 líneas (0,05 %) tienen sobre-recepción** (exceso de 2.261,52 unidades base);
- **845 líneas (5,17 %) no tienen recepción**: de ellas, **779 están abiertas en SAP
  (DocStatus de línea `O`, pendientes de entrega; 734 son de septiembre 2026)** y solo
  **66 líneas cerradas sin recepción**, de las cuales **25 están respaldadas por una
  factura de compra válida sin ninguna recepción** (683.025 unidades base) — el
  subconjunto realmente anómalo;
- **0 líneas `NOT_DETERMINABLE`**: toda línea comparable tenía UoM compatible y relación
  documental explícita.

La relación **compra → recepción → almacén** se reconstruyó con evidencia documental
explícita (claves `BaseType/BaseEntry/BaseLine` nativas de SAP) en el 99,12 % de las
líneas de recepción válidas, con el almacén de ingreso preservado en cada línea y
corroboración física en OINM del **100 % de las líneas de recepción del universo
principal**.

---

## B. Evidencia cuantitativa

### B.1 Descubrimiento de datasets (paso previo obligatorio)

Inspección exclusiva del Data Lake; ningún nombre asumido:

| Dataset materializado | Filas | Rol |
| --- | ---: | --- |
| `raw/sap/TELCHI_DATALAKE_MATERIAL_SUPPLY_FACT_CAPTURE_V1/purchase_order` (OPOR) | 3.337 | Cabeceras de orden de compra |
| `.../purchase_order_line` (POR1) | 18.584 | Líneas de compra (cantidad, UoM, almacén planeado) |
| `.../purchase_receipt` (OPDN) | 3.471 | Cabeceras de recepción (GRPO) + flag de anulación |
| `.../purchase_receipt_line` (PDN1) | 16.921 | Líneas de recepción (base documental, cantidad, UoM, almacén) |
| `raw/sap/TELCHI_DATALAKE_MATERIAL_SUPPLY_PURCHASING_LINEAGE_V1/ap_invoice` (OPCH) | 6.169 | Facturas de compra (2026-01-01 → 09-23) |
| `.../ap_invoice_line` (PCH1) | 21.679 | Líneas de factura con `BaseEntry/BaseLine/BaseType` |
| `.../purchase_lineage_path` | 16.921 | Linaje PO→recepción derivado (validación cruzada) |
| `raw/sap/TELCHI_DATALAKE_MATERIAL_SUPPLY_LINEAGE_CLOSURE_V1` | 98 + 133 | Linaje histórico puntual (fuera de ventana) |
| Foundation `atomic.inventory_movement` (OINM) | 1.576.871 (1.536.724 en 2026) | Movimientos físicos: TT20 recepción 16.350; TT21 devolución 739; TT18 factura 64 |
| Foundation `reference` | products 42.073 · warehouses 133 · suppliers 2.130 | Ítems, almacenes, proveedores |
| Legacy mirror `raw/legacy/parquet/purchase-*.parq` | 121 archivos | Sistema legacy distinto; NO utilizado (opción de extensión) |

Foundation CURRENT contiene 7 componentes lógicos (`reference, sales, credit_memo, oinm,
oitw, material_supply, receivables_collections`); **no existe componente de compras en el
esquema `atomic`** (13 tablas). Los datasets de compras viven en `raw/` como extractos
aprobados del Data Lake → oportunidad de extensión de Foundation (ver §F).

### B.2 Universos y exclusiones

| Concepto | Cantidad |
| --- | ---: |
| Órdenes de compra totales / anuladas / válidas | 3.337 / 118 / 3.219 |
| Líneas de compra totales | 18.584 |
| Líneas de OC anuladas (excluidas) | 1.451 |
| Líneas no inventariables excluidas | 778 (de 258 líneas sin ítem/cantidad cero + 534 cargos de importación `I-*`; 14 ya estaban en OC anuladas) |
| **Universo principal (líneas de compra inventariables)** | **16.355** |
| Documentos de recepción totales / anulados / válidos | 3.471 / 112 / 3.359 |
| Líneas de recepción totales / anuladas / válidas | 16.921 / 702 / 16.219 |
| Líneas de recepción válidas enlazadas a línea de OC | 16.076 (99,12 %) |
| Líneas de recepción válidas sin enlace resoluble | 143 (0,88 %) |
| Facturas de compra (docs / líneas) | 6.169 / 21.679 (1.748 líneas anuladas) |
| Productos distintos en el universo principal | 5.401 |
| Proveedores distintos | 223 |
| Almacenes receptores | 13 |

Anulaciones: `CANCELED IN ('Y','C')` en recepciones. Validación empírica en OINM: cada
documento `Y` (original) tiene su par `C` con el mismo proveedor/fecha/monto y movimientos
netos cero (+1.000 / −1.000 en el mismo ítem), por lo que el par representa una recepción
anulada y ambos se excluyen.

### B.3 Clasificación por línea (granularidad documento + línea + ItemCode)

| Estado | Líneas de compra | % líneas | Cantidad comparable (unid. base) |
| --- | ---: | ---: | ---: |
| EXACT_RECEIPT | 15.460 | 94,53 % | 11.390.091,43 |
| MULTI_RECEIPT_COMPLETE | 11 | 0,07 % | 191.003,00 |
| PARTIAL_RECEIPT | 16 | 0,10 % | 361.780,00 |
| MULTI_RECEIPT_PARTIAL | 15 | 0,09 % | 1.065.624,00 |
| OVER_RECEIPT | 8 | 0,05 % | 66.830,00 |
| NO_RECEIPT | 845 | 5,17 % | 1.784.658,00 |
| NOT_DETERMINABLE | 0 | 0,00 % | 0 |
| **Total** | **16.355** | **100 %** | **14.859.986,43** |

("Cantidad comparable" = cantidad comprada en unidades base de artículo
(`Quantity × NumPerMsr`) de líneas con UoM compatible; 100 % de las líneas. Los porcentajes
pueden desviarse 0,01 pp por redondeo.)

Métricas adicionales:

| Métrica | Valor |
| --- | ---: |
| Documentos de compra analizados | 3.337 (3.219 válidos) |
| Líneas de inventario (recepción) analizadas | 16.921 (16.219 válidas) |
| Líneas con UoM compatible | 16.355 (100 %) |
| Líneas con UoM no resoluble | 0 |
| Cantidad total comprada comparable (base) | 14.859.986,43 |
| Cantidad total recibida comparable (base) | 12.483.434,37 |
| Delta absoluto (base) | −2.376.552,06 |
| % líneas completamente reconciliadas | **94,59 %** |
| Líneas con recepción múltiple / multi-almacén | 29 / 3 |
| Primera recepción: mediana / p90 / máximo | 0 días / 4 días / 197 días |

Desglose honesto por UoM (no se suman unidades incompatibles; tabla completa en evidencia):

| UoM de línea | Líneas | Comprado | Recibido |
| --- | ---: | ---: | ---: |
| UNI | 3.040 | 8.835.740 | 7.191.593 |
| FCOx1 | 2.788 | 70.172 | 63.291 |
| CAJAx30 | 1.473 | 16.680 | 14.999 |
| CAJAx100 | 1.010 | 14.511 | 13.568 |
| TBO | 820 | 17.955 | 16.159 |
| PAQx6 | 793 | 2.242 | 2.242 |

El delta total se descompone exactamente en: `NO_RECEIPT −1.784.658,00`
+ `parciales −594.155,58` + `sobre-recepción +2.261,52` = **−2.376.552,06**.

### B.4 Vista transaccional factura de compra ↔ recepción (prioridad del brief)

| Métrica | Valor |
| --- | ---: |
| Líneas de factura con enlace explícito a recepción y comparables | 16.100 |
| Exactas | 16.098 (**99,99 %**) |
| Parciales / en exceso | 2 / 0 |
| Líneas de factura basadas en OC (`BaseType=22`) | 16.399 |
| Líneas de factura directas sin OC (`BaseType=-1`) | 3.509 |
| Líneas de factura sin recepción enlazada | 3.831 (mayoría = facturas directas) |
| Temporalidad factura → recepción (16.100 líneas) | mediana **+1 día**; mismo día 4.055; posterior 12.022; **recepción antes de la factura: solo 23 (0,14 %)** |

---

## C. Excepciones (por impacto)

1. **845 líneas `NO_RECEIPT` (1.784.658 unid. base, 12,0 % de la cantidad comprada):**
   - **779 líneas abiertas (`O`)** — pendientes de entrega; 734 son de septiembre-2026
     (320.189 unid. base), coherentes con la fecha de corte 2026-09-23;
   - **66 líneas cerradas (`C`) sin recepción**, de las cuales:
     - **25 líneas con factura de compra válida y sin ninguna recepción**
       (683.025 unid. base) — anomalía más material: p. ej. OC 262002813 línea 0
       `L00219` 504.000 UNI (2026-08-19, proveedor PL000068) y OC 262002387 línea 0
       `L01010` 108.000 KG (2026-07-25);
     - 5 líneas con solo facturas anuladas;
     - 36 líneas sin factura ni recepción (línea cerrada sin documentos; el Data Lake no
       materializa historial de cambios de línea → se afirma la **ausencia de recepción
       documental**, no su causa).
2. **31 líneas parciales (−594.155,58 base):** OC 262001403 línea 0 `L00219` 301.500 →
   214.390 UNI (3 recepciones, LAB-M1, −87.110); OC 262001393 líneas 4/5/6 100.000 →
   48.500 UNI c/u (3 recepciones, LAB-M1); OC 262000249 líneas 0/1 50.000 → 12.000 UNI.
   Proveedores con más desvíos: PL000153 (13 líneas), PL000063 (13), PL000182 (7).
3. **8 líneas en exceso (+2.261,52 base):** OC 262000248 línea 0 65.000 → 67.000 UNI
   (5 recepciones; las facturas amparan 67.000 vs 65.000 de OC); OC 262001527 600 → 750;
   5 líneas KG de OC 262000384 con excesos de 4,82–63,42 KG (diferencias de pesaje).
4. **Recepciones sin relación documental suficiente: 143 líneas válidas (0,88 %)** —
   99 referencian líneas de factura anteriores al extracto (recepciones 2026-01-05 con
   facturas previas a 2026, `DocEntry` por debajo del mínimo materializado 41.960),
   38 resuelven a líneas de OC fuera de la extracción (OC anteriores a 2026),
   6 sin documento base (1 recepción directa válida). Se clasifican como cobertura
   declarada, nunca como `NO_RECEIPT` de otra línea.
5. **Recepción anterior a la compra: 119 líneas** (hasta −17 días; febrero-abril 2026) —
   la OC fue registrada después de la recepción (backdating documental). **Recepción muy
   tardía: 64 líneas >30 días (máximo 197 días)**, todas importaciones con destino
   ALM-IMP (despacho aduanero).
6. **Multi-almacén: 3 líneas** (OC 262001421 líneas 2/12/13: 2.000 / 45.000 / 45.000
   recibidas entre LAB-M1 y SAA-M1, todas exactas). **Multi-recepción: 29 líneas**
   (máximo 5 recepciones).
7. **Documentos anulados excluidos:** 118 OC (1.451 líneas) y 112 recepciones
   (702 líneas), verificados con par de reversión y movimiento neto cero en OINM.
8. **Devoluciones posteriores (OINM TT21, 2026):** 739 movimientos, 54.585 unid. base
   devueltas, 25 proveedores, 570 ítems, concentradas en `2A-DEV`. No transforman ninguna
   recepción válida en ausencia (correcto según el brief): p. ej. `M01823` recibido
   61.500 / devuelto 16.500; `L00002` recibido 170.000 / devuelto 10.000.
   **`NET_RECEIVED_AFTER_RETURNS` (agregado, evidencia secundaria):**
   12.483.434,37 − 54.585 = **12.428.849,37 unid. base** (≈ 0,44 % devuelto).

---

## D. Almacenes

Vista construida desde `PDN1.WhsCode` (almacén de la recepción), universo principal:

| Warehouse | Nombre | Compras recibidas (docs) | Líneas recepción | Líneas OC recibidas | Cantidades (UoM dominantes) | Diferencias |
| --- | --- | ---: | ---: | ---: | --- | ---: |
| 2A-AMD | Almacén Medicamentos 2A | 1.982 | 11.221 | 11.217 | FCOx1 63.100 · PZA 47.185 · ENV 16.490 | 1 |
| 2A-AMK | Almacén TelchiMarket 2A | 407 | 3.316 | 3.316 | UNI 15.472 · PAQx6 2.242 | 0 |
| LAB-M1 | Almacén Materia Prima | 356 | 693 | 657 | UNI 6.343.450 · LT 102.001,92 | 33 |
| ALM-IMP | Almacén de Importación | 28 | 92 | 92 | UNI 412.773 · KG 391.093 | 0 |
| LAB-T4 | Prod. Terminado MAGISTRAL | 49 | 66 | 62 | UNI 83.540 · BOLSA 2.630 | 3 |
| SAA-M1 | Prod. a Granel Saavedra | 37 | 66 | 62 | UNI 298.338 · LT 72.000 | 2 |
| LAB-C1 | Control de Calidad | 20 | 47 | 47 | ML 38.030 · GR 15.625 | 0 |
| 2A-MEI | Material de Escritorio | 19 | 21 | 21 | UNI 4.488 | 0 |
| 2A-MAG / LAB-T2 / 2A-MKT / LAB-T3 / SAA-T1 | (magistral, SENASAG, marketing, industrial, Saavedra PT) | 29 | 39 | 39 | ver evidencia | 0 |

"Notas: (i) cada almacén conserva sus líneas y cantidades por UoM — no se suman unidades
incompatibles; (ii) las 559 líneas de recepción de cargos de importación `I-*` (IVA, flete,
SENASAG, seguros, peajes) en ALM-IMP **no generan movimiento OINM** y se excluyen del
universo principal por no ser inventariables; (iii) `Diferencias` = líneas de OC recibidas
en ese almacén que no reconcilian exacto (parcial o exceso)."

---

## E. Qué significa (impacto operativo)

- El flujo documental real es **OC → factura de compra → recepción (GRPO basado en la
  factura)**: el 97,8 % de las líneas de recepción (16.542 de 16.921) toman como base una
  factura de compra (`BaseType=18`) y se enlazan a la OC a través de la línea de factura;
  solo 7 líneas son recepción directa sobre OC. La recepción sigue a la factura en 1–2
  días en la mediana: **la factura se emite antes que el ingreso físico documentado en
  ~75 % de los casos**.
- El control de inventario es sólido: 100 % de las líneas de recepción del universo
  principal tienen movimiento físico OINM con cantidad exacta (`× NumPerMsr`) y almacén
  idéntico.
- El riesgo operativo se concentra en **25 líneas facturadas sin recepción (683.025 unid.
  base)** y en **31 líneas parciales con 594.156 unid. base sin ingresar**, sobre todo en
  LAB-M1 (materia prima) y con tres proveedores (PL000153, PL000063, PL000182).
- Las 779 líneas abiertas sin recepción son mayoritariamente del corte de septiembre
  (pendiente natural), no un fallo de control.
- Las recepciones multi-almacén y multi-recepción existen pero son raras (3 y 29 líneas):
  la reconstrucción las preserva sin colapsarlas en agregados.

---

## F. Qué NO podemos afirmar (limitaciones reales del Data Lake)

- **Ventana 2026-01-01 → 2026-09-23**: no hay extracto de OC/OPDN anteriores a 2026;
  38 líneas de recepción resuelven a OC fuera de la extracción y 99 a líneas de factura
  anteriores al extracto (recepciones 2026-01-05 basadas en facturas previas a 2026;
  `DocEntry` < mínimo materializado 41.960). Fuera de ventana la relación no es evaluable
  → no se clasifica, no se inventa.
- **Sin verificación externa**: `SAP_ACCESSED=NO`. La completitud del extracto de
  recepciones se demostró **internamente** (todo movimiento TT20 de OINM tiene documento
  de recepción: 0 huérfanos; y 100 % de las líneas del universo principal tienen
  movimiento), pero no se contrastó contra SAP en esta ejecución.
- **Devoluciones no lineales**: OINM TT21 expone `base_ref` como número del documento de
  devolución sin crosswalk a DocEntry; no existe dataset de devoluciones (ORPD/RRD1) en el
  Data Lake → `NET_RECEIVED_AFTER_RETURNS` solo a nivel agregado/por ítem (evidencia
  secundaria), nunca a nivel de línea de OC.
- **Causa de cierre sin recepción**: no hay historial de cambios de línea de OC; se afirma
  "no existe recepción documental", no el motivo.
- **Almacén de la recepción** proviene de `PDN1.WhsCode` (documental). Para las 515
  líneas de recepción sin movimiento OINM (todas cargos `I-*`) no hay corroboración
  física; por eso quedan fuera del universo principal.
- **No se usó OITW** para demostrar ingresos históricos (describe estado, no evento).
- `purchase_lineage_path` se usó solo como validación cruzada: su derivado marcó 16.407
  líneas con PO y 514 sin PO resoluble (351 de otra cadena documental, 142 sin resolver,
  21 sin base) frente a 16.076 + 143 de la resolución propia; la diferencia se explica
  por líneas de OC fuera de ventana (recursión propia sobre cadenas de recepción).

### Oportunidad de extensión de Foundation (no es un fallo de la investigación)

Los datasets existen y son adecuados, pero no están publicados como componentes de
Foundation CURRENT (esquema `atomic` no tiene tablas de compras):

| Dataset | Entidad | Claves | Cobertura | Permitiría |
| --- | --- | --- | --- | --- |
| `TELCHI_DATALAKE_MATERIAL_SUPPLY_FACT_CAPTURE_V1/purchase_order(_line)` | OPOR/POR1 | `DocEntry+LineNum` | 2026-01-01 → 09-23, 3.337/18.584 filas | Compras como componente consultable |
| `.../purchase_receipt(_line)` | OPDN/PDN1 | `DocEntry+LineNum`, `BaseEntry/BaseLine` | 2026-01-05 → 09-23, 3.471/16.921 filas | Recepciones y almacén de ingreso |
| `TELCHI_DATALAKE_MATERIAL_SUPPLY_PURCHASING_LINEAGE_V1/ap_invoice(_line)` | OPCH/PCH1 | `DocEntry+LineNum` | 2026-01-01 → 09-23, 6.169/21.679 filas | Facturación de compra |

---

## G. Hallazgos no esperados (respaldados por evidencia)

1. **La recepción documental se crea a partir de la factura, no a partir de la OC**
   (16.542 de 16.921 líneas de recepción tienen `BaseType=18`): la secuencia típica es
   OC → factura → GRPO, con recepción el día siguiente a la factura (mediana +1 día).
2. **64,4 % de las líneas recibidas (9.992 de 15.510) ingresaron el mismo día de la OC**
   (mediana 0 días, p90 4 días), y 119 líneas muestran recepción **anterior** a la fecha
   de la OC (hasta −17 días): la OC se registra después del ingreso en esos casos.
3. **El 100 % de las recepciones sin movimiento físico son cargos de importación**
   (`I-*` en ALM-IMP, 559 líneas en 411 documentos): fletes, IVA, SENASAG, seguros
   y peajes se registran como GRPO sin entrada de inventario — por eso se separan del
   universo principal (regla de ítems no stockeables).
4. **Los "sobrees" de KG no son errores de reconciliación**: corresponden a diferencias
   de pesaje/merma (5 líneas de OC 262000384, +4,82 a +63,42 KG) y a facturas que amparan
   más cantidad que la OC (OC 262000248: 67.000 facturados/recebidos vs 65.000 pedidos).
5. **Control anti-falso positivo confirmado**: el subconjunto reconciliado suma
   11.581.094,4337 comprado = 11.581.094,4337 recibido (Δ = 0), mientras coexisten
   884 anomalías a nivel de línea (845 sin recepción + 31 parciales + 8 en exceso):
   cualquier análisis de totales globales ocultaría estas anomalías.

---

## H. Próximas preguntas naturales

Los resultados justifican (en este orden):

1. **¿Por qué 25 líneas de OC cerradas con factura válida no tienen recepción?**
   (683.025 unid. base; ¿recepción no registrada, drop shipment o cierre incorrecto?)
2. **¿Qué proveedores entregan parcialmente?** PL000153, PL000063 y PL000182 concentran
   33 de 39 líneas parciales/excedidas.
3. **¿Existen compras facturadas antes de ser recibidas?** Sí: 75 % de las líneas con
   recepción reciben después de la factura (23 excepciones inversas) — medible en detalle.
4. **¿Cuánto tarda cada compra en ingresar y qué partidas superan el plazo?** 64 líneas
   >30 días, todas importación con destino ALM-IMP (p90 = 4 días para el resto).
5. **¿Qué almacenes reciben diferencias?** LAB-M1 concentra 33 de las 39 líneas con
   diferencia (parcial/exceso).

---

## Controles anti-falso positivo (resumen)

| # | Control | Resultado |
| --- | ---: | --- |
| 1 | Relación documental explícita (`BaseType/BaseEntry/BaseLine`) | 16.114 líneas de recepción válidas resueltas (16.107 vía factura + 7 directas); 0 por coincidencia de fecha/proveedor/cantidad; 143 sin enlace resoluble (declaradas) |
| 2 | Mismo ItemCode en el enlace | 16.076 / 16.076 = 100 % |
| 3 | UoM compatible (`unitMsr` igual en OC y recepción) | 16.076 / 16.076 = 0 incompatibles |
| 4 | Recepción válida (anuladas excluidas) | 702 líneas anuladas excluidas; pares Y/C con movimiento neto cero |
| 5 | Movimiento no anulado y corroborado (OINM TT20) | 15.561 / 15.561 líneas del universo principal con cantidad exacta (`× NumPerMsr`) y almacén idéntico |
| 6 | Ausencia de duplicación por joins (fanout) | 0 violaciones (cada línea de recepción → a lo sumo 1 línea de OC; claves únicas) |
| 7 | Suma correcta en recepción múltiple | 29 líneas multi-recepción sumadas por línea; subconjunto exacto con Δ = 0,0000 |

**Gate final:** `TELCHI_PURCHASE_TO_WAREHOUSE_RECEIPT_RECONCILIATION_V1_PASS`
`SAP_ACCESSED=NO · SAP_QUERY_COUNT=0 · SAP_WRITE_COUNT=0 · DATA_LAKE_ONLY=YES`