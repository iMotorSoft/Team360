# TELCHI — Compras Facturadas sin Recepción de Almacén (AP_INVOICED_WITHOUT_WAREHOUSE_RECEIPT_V1)

Esta investigación explica caso por caso las 25 líneas de compra cerradas y facturadas sin recepción de almacén (683.025 unidades base), con una sola categoría por línea. Gate: PASS, sin acceso a SAP/HANA.

## 1. Objetivo y alcance

El objetivo es discriminar "sin GRPO documental" de "sin movimiento físico" sobre el universo heredado de la reconciliación compras → recepción, sin consultar sistemas fuente en línea.

- **Pregunta**: ¿por qué 25 líneas de OC con `LineStatus='C'`, `OpenQty=0` y factura de compra válida (`BaseType=22`) no tienen recepción de almacén asociada?
- **Granularidad**: documento + línea + `ItemCode` (nunca agregado por proveedor o fecha).
- **Salida exigida**: exactamente una categoría de las 10 definidas por el brief por cada línea, evidencia por línea, gate verificable y este reporte.
- **Fuera de alcance**: causal humana de las excepciones, estado de pago real, inspección física de almacén y cualquier consulta a SAP/HANA.

## 2. Fuentes, ventana y restricciones

Todo el análisis se resuelve dentro del Data Lake Telchi con foundation `foundation_d222a203801cc84e9a14164d26aa67a0` y con los mismos límites de ventana que el gate anterior.

| Fuente | Dataset / tabla | Ventana usada |
| --- | --- | --- |
| Purchase lineage | `TELCHI_DATALAKE_MATERIAL_SUPPLY_PURCHASING_LINEAGE_V1` (`ap_invoice`, `ap_invoice_line`) | facturas 2026-01-01 → 2026-09-23 |
| Fact capture | `TELCHI_DATALAKE_MATERIAL_SUPPLY_FACT_CAPTURE_V1` (`purchase_order`, `purchase_order_line`, `purchase_receipt`, `purchase_receipt_line`, `production_order`, `production_issue`) | OC 2026-01-01 → 2026-09-23; recepciones 2026-01-05 → 2026-09-23 |
| Movimientos | `telchi.atomic.inventory_movement` (OINM) | tabla completa 2022-03-31 → 2026-09-24; filas por `ItemCode` desde 2026-01-01, filas por `base_ref` de factura sin límite de fecha |
| Referencia | `reference/products` (grupo de producto, UoM) | snapshot vigente |

Restricciones cumplidas y verificadas en la evidencia: `SAP_ACCESSED=NO`, `SAP_QUERY_COUNT=0`, `SAP_WRITE_COUNT=0`. Sin fallback a SAP/HANA: lo que el Data Lake no materializa se declara `NOT_DETERMINABLE` o limitación, nunca se rellena con supuestos.

## 3. Universo derivado (25 líneas / 683.025 unidades base)

El universo se reconstruye desde la investigación previa y se re-verifica íntegro antes de clasificar.

- Línea de OC con `LineStatus='C'` y `OpenQty=0`, sin recepción asociada (por cualquier camino: `BaseType=22` a la OC, `BaseType=18` a la factura, `BaseType=20` a otra recepción, o recepción directa), incluyendo recepciones anuladas en la búsqueda.
- Línea de factura de compra con `BaseType='22'`, encabezado `CANCELED='N'` y línea de factura válida.
- Controles del universo: **25 líneas**, **683.025 unidades base**, 23 `ItemCode` distintos, todos inventariables (KG/UNI/LT, sin prefijo `I-`), 0 claves duplicadas, 0 `ItemCode` nulos, 0 líneas de OC o factura inválidas, 0 desajustes de cantidad entre factura y OC.

Encabezados de factura: 7 en estado `C` y 3 en `O`; **las 25 líneas de factura están en `LineStatus='O'` con `OpenQty` completo**, es decir no hay pago ni reconciliación parcial de línea materializado en el extracto. Las 25 líneas de OC están en `C` con `OpenQty=0`: la OC se cerró por facturación, no por recepción.

## 4. Regla de decisión aplicada

La clasificación es una función pura `classify()` con orden estricto de primer coincidente, de modo que la evidencia documental gana siempre sobre la ausencia de evidencia.

1. `purchase_reversal` o documento anulado → `CANCELLED_OR_REVERSED`.
2. `non_inventory_exception` (prefijo `I-` / grupo no inventariable) → `NON_INVENTORY_EXCEPTION`.
3. `receipt_window_covers_po=False` (la OC queda fuera de la ventana de recepciones) → `HISTORICAL_LINEAGE_GAP`.
4. `receipts_outside_window>0` (recepción existente fuera de la ventana) → `RECEIPT_OUTSIDE_WINDOW`.
5. UoM incompatible entre OC y recepción → `QUANTITY_UOM_ISSUE`.
6. `receipts_via_lineage>0` o `receipts_direct_to_po>0` o `receipts_direct_to_invoice>0` → `RECEIPT_FOUND_ALTERNATE_LINEAGE`.
7. `linked_inbound_base>0` (entrada de inventario atribuible a la línea) → `INVENTORY_ENTRY_WITHOUT_GRPO`.
8. `advance_invoice_evidence=True` (regex `ANTICIPAD` en comentario de factura u OC) o `import_invoice_evidence=True` (`DocCur != 'BS'`) → `DIRECT_AP_INVOICE_NO_GRPO`.
9. Caso determinable sin evidencia de los puntos 7 y 8 → `TRUE_INVOICED_WITHOUT_RECEIPT`.
10. Resto → `NOT_DETERMINABLE`.

La distinción clave de esta investigación es la 7 frente a la 9: una línea con entrada de inventario sin documento GRPO **sí entró a almacén** (aunque el documento correcto falte), mientras que `TRUE_INVOICED_WITHOUT_RECEIPT` no tiene ni documento ni movimiento.

## 5. Evidencia documental por línea

La evidencia documental se recoge de los comentarios de OC y factura y de la moneda del documento, sin interpretación libre.

| Evidencia | Líneas | Unidades base | OC / factura | Señal objetiva |
| --- | ---: | ---: | --- | --- |
| Factura anticipo (4 líneas) | 4 | 539.000 | 262002089 / 262003870, 262002090 / 262003872, 262002091 / 262003874, 262002813 / 262005268 | Comentario con `FACTURA ANTICIPADA` / `SOLICITUD DE FACTURA ANTICIPADA`; en los tres primeros la factura es 1 día **anterior** a la OC |
| Factura de importación (17 líneas) | 17 | 137.910 | 262001686 / 262005712 (6), 262001802 / 262005717 (10), 262002387 / 262005713 (1) | `DocCur='USD'`, `tipo_compra='IMP'`, destino `ALM-IMP`, `NumAtCard` con referencia de embarque (`WHAA1260108ZY`, `184189`, `6556`) |
| Entrada de inventario sin GRPO (2 líneas) | 2 | 6.000 | 262000492 / 262001093 (líneas 0 y 1) | Movimiento OINM `trans_type='18'` (A/P Invoice) +3000 c/u en `LAB-M1` el 2026-02-12 |
| Sin evidencia documental (2 líneas) | 2 | 115 | 262002290 / 262004306, 262002366 / 262004458 | Moneda `BS`, comentarios sin anticipo ni referencia de embarque |

Detalle de las 4 facturas anticipo (única evidencia que implica pago antes de entrega):

| OC | Línea | Ítem | Cant. base | Proveedor | Fecha OC | Fecha factura | Δ OC→factura | N° proveedor | Comentario |
| --- | ---: | --- | ---: | --- | --- | --- | ---: | --- | --- |
| 262002089 | 0 | L00002 | 20.216 | PL000089 DISALI | 2026-06-26 | 2026-06-25 | −1 | 1457 | `SOLICITUD DE FACTURA ANTICIPADA DE FECHA 25/06/26` |
| 262002090 | 0 | L00002 | 10.000 | PL000089 DISALI | 2026-06-26 | 2026-06-25 | −1 | 1456 | `SOLICITU DE FACTURA ANTICIPADA DISALI - 25/06/26` |
| 262002091 | 0 | L00002 | 4.784 | PL000238 Guzman Jorge L. | 2026-06-26 | 2026-06-25 | −1 | S/F | `SOLICITUD DE FACTURA ANTICIPADA 25/06/26` |
| 262002813 | 0 | L00219 | 504.000 | PL000068 INDUSTRIAS RAVI | 2026-08-19 | 2026-08-19 | 0 | 0000007986 | `FACTURA ANTICIPADA COMPRA DE ENV.1/08 - IND. RAVI 13/08/26` |

## 6. Recepciones: linaje evaluado y candidatos rechazados

No existe ninguna recepción para el universo, pero sí existen movimientos parecidos que podrían confundirse; se documentan para que el no-vínculo sea auditable.

- **Recepciones vinculadas a las 25 líneas: 0** por los tres caminos (`BaseType=22`→OC, `18`→factura, `20`→recepción previa) y también 0 recibiendo como recepción directa.
- **Recepciones fuera de ventana: 0**. El gate contrasta con la ventana de OINM 2026-01-01 → 2026-09-24 y el dataset de recepciones cubre 2026-01-05 → 2026-09-23 (3.471 documentos): las 25 OC quedan dentro (`receipt_window_covers_po=True` en todas).
- **30 movimientos candidatos rechazados** sobre 10 líneas objetivo: se emparejaron por cantidad exacta, por proveedor, y por proveedor + almacén, y luego se resolvió su linaje hasta la OC.

| OC / línea | Ítem | Cant. comprada | Candidato rechazado | A qué OC pertenece de verdad |
| --- | --- | ---: | --- | --- |
| 262002089/0 | L00002 | 20.216 | TT20 2026-07-07 SAA-M1 +20.536 (PL000089) y +10.000 | OC 25608/0 y OC 25616/0 |
| 262002090/0 | L00002 | 10.000 | mismos + receipts 262001601/1895/2108/2221/2465/2797/3203 (PL000179) | OC 25602/0, 26245/0, 26851/0 |
| 262002091/0 | L00002 | 4.784 | TT20 2026-07-07 SAA-M1 +4.464 (PL000238) | OC 25609/0 |
| 262002366/0 | M03729 | 70 | TT20 2026-06-09 SAA-T1 +75 (PL000200) | OC 25742/0 |
| 262002813/0 | L00219 | 504.000 | TT20 2026-07-17 / 08-04 / 08-31 LAB-M1 +32.950 / +90.000 / +91.440 (PL000068) | OC 25618/0 (recibió por su propia factura) |
| 262001686/3, /5 y 262001802/7, /9, /11 | L03335, L01785, L03167, L03357, L03166 | 8.600 | TT20 2026-04-30 / 08-21 / 08-31 ALM-IMP (PE000001, PE000002) y transfers TT67 | OC 23522/0-10, 24997/0-4, 25934/0, 24943/0-9 |

El caso de la línea `L00002` de 10.000 es el más ilustrativo: una recepción de 10.000 unidades del mismo ítem, mismo proveedor y fecha cercana existe, pero ampara a la OC 25616/0, no a la 262002090. **Ningún candidato se atribuye por coincidencia de cantidad.**

## 7. Movimientos de inventario (OINM)

Solo dos líneas tienen entrada atribuible a su factura; las otras 23 no tienen movimiento con `base_ref` de su factura y línea ni salida del ítem en la fecha de la OC o de la factura (cobertura: ítem desde 2026-01-01, `base_ref` sin fecha límite).

- **OC 262000492 líneas 0 y 1 (`L03687`, `L03688`, FLEXO PRINT, 3.000 c/u, LAB-M1)**: el 2026-02-12 la factura 262001093 registró dos entradas de +3000 cada una (`trans_type='18'`, `base_ref=262001093`, `doc_line_num` 0 y 1) y el mismo día la OC se emitió con dos salidas de −3000 (`trans_type='60'`, documento 261501801, `BaseType=-1`, ítems alineados 0 y 1) con comentario **`CRUCE DE CODIGOS, PARA INGRESAR EL MISMO STOCK CON CODIGO E. CORREO PAOLA MATTOS 16.03.26`**. Ese mismo día y almacén ingresaron además 3.000 `E00013` y 3.000 `E00014` (etiquetas de colágeno LIV4), coherente con el cruce a "código E" del comentario.
- **2026 es el único año con `trans_type='18'`**: 64 movimientos, `in_qty` total 6.000, y **los dos de Flexo son los únicos con cantidad distinta de cero**. La facturación en almacén de este par es por lo tanto excepcional, no un modo operativo habitual.
- Las otras 23 líneas tienen `linked_inbound_base=0` y `linked_outbound_base=0`: ningún movimiento de inventario referencia su factura y línea. Como contexto no atribuible, las 3 líneas de DISALI y la línea de INDUSTRIAS RAVI mueven el mismo `ItemCode` en su almacén planificado el día de la factura mediante transfers internos TT67 (docs 260109523 y 260112476) que mueven stock preexistente; ningún movimiento corresponde a la factura ni a la OC.

## 8. Controles anti-falso positivo

Diez controles verifican que ninguna categoría se apoye en coincidencias ni en datos parciales.

| # | Control | Resultado |
| ---: | --- | --- |
| 1 | Universo y suma base | 25 líneas / 683.025 = esperado (heredado y reverificado) |
| 2 | Clave única y `ItemCode` no nulo | 0 duplicados, 0 nulos, 25 preservados |
| 3 | Válido en OC y factura | 0 líneas de OC inválidas, 0 facturas inválidas, `BaseType` preservado `22` en 25/25 |
| 4 | La factura apunta a su OC exacta (`BaseEntry`/`BaseLine`) | 0 líneas apuntando a otra OC (`invoice base not matching PO = 0`) |
| 5 | Recepción vinculada por linaje (no por fecha/proveedor/cantidad) | 0 recepciones; 30 candidatos resueltos hasta su OC real y rechazados |
| 6 | Movimiento atribuible: ítem, línea y proveedor coherentes | 2 movimientos con `ItemCode` y `doc_line_num` obligatorios en el enlace, 0 colisión de clave, 0 proveedor incoherente |
| 7 | Reversas y anulaciones | 0 reversas, 0 encabezados anulados, 0 líneas anuladas |
| 8 | Una categoría exacta por línea | partición válida, 0 `NOT_DETERMINABLE`, 0 sin clasificar |
| 9 | Cobertura temporal | `receipt_window_covers_po=True` en 25/25; 0 recepciones fuera de la ventana usada; dataset de recepciones 2026-01-05 → 2026-09-23 |
| 10 | Política SAP | `SAP_ACCESSED=NO`, `SAP_QUERY_COUNT=0`, `SAP_WRITE_COUNT=0` |

## 9. Resultado del gate

El gate verifica controles duros (25, 683.025, cero duplicados, cero sin clasificar, cero colisiones, partición exacta) y se ejecuta con `uv run python .../run_gate.py`.

- `GATE=TELCHI_AP_INVOICED_WITHOUT_WAREHOUSE_RECEIPT_V1_PASS`
- Evidencia: `evidence/summary_20261001T014033.json` y `evidence/ap_invoice_no_grpo_lines_20261001T014033.jsonl` (una línea por OC/línea objetivo con toda la evidencia).
- Tests del módulo: 17/17 en verde (`uv run pytest .../ap_invoiced_without_warehouse_receipt_v1/`).

## 10. Hallazgos no esperados

Cuatro hallazgos cambiaron cómo se interpreta el universo y conviene reutilizarlos en investigaciones siguientes.

- `OINM.base_ref` **no es un identificador único**: coincide con `DocNum` de OC, de recepción y de factura a la vez (3.337 `DocNum` de OC existen también como `DocNum` de recepción en la serie 2620xxxxx). Sólo se resuelve con `trans_type` + `doc_line_num` + `ItemCode` + `card_code`. Ignorar esto produce linaje falso.
- `LineStatus` de la factura no discrimina nada en este universo: con recepción hay 1.610 líneas `O` y 305 `C`; sin recepción hay 278 `O` y 274 `C`. La señal está en `OpenQty` de la OC y en el linaje, no en el estado.
- La OC se cierra (`C`, `OpenQty=0`) por facturación mientras la línea de factura queda `O` con `OpenQty` completo: para estas 25 líneas el cierre documental de la compra ocurrió sin ningún ingreso a almacén.
- La única entrada de stock vía factura de compra en 2026 pertenece a dos líneas con comentario explícito de cruce de códigos, no a un proceso de importación o anticipo.

## 11. Qué NO podemos afirmar (limitaciones del Data Lake)

Los límites siguientes son inherentes al Data Lake y no se cubren con supuestos ni con SAP.

- **No hay causales humanas**: el Data Lake no materializa historial de cambios de línea, notas de recepción borradas ni aprobaciones. La ausencia de recepción es un hecho documental; su motivo (recepción no registrada, drop shipment, cierre indebido, entrega posterior) queda `NOT_DETERMINABLE` sin SAP.
- **No se prueba la existencia física de la mercancía**: para 23 líneas afirmamos "sin recepción documental y sin movimiento de inventario atribuible a la línea en la ventana", no "la mercancía nunca llegó". El `ItemCode` sí puede tener movimientos propios de stock preexistente.
- **No se verifican cantidades físicas de almacén**: no hay conteo cíclico ni existencias por lote en las fuentes usadas; la única salvedad es la ventana de OINM, amplia pero acotada a 2022-03-31 → 2026-09-24.
- **El cruce de códigos de Flexo se infiere del comentario del documento** (evidencia primaria de la transacción) y de movimientos coincidentes de fecha, almacén y cantidad; no hay enlace `BaseEntry/BaseLine` entre la salida 261501801 y los ingresos de `E00013`/`E00014`.
- **No se evaluó el pago**: las líneas de factura están `O` con `OpenQty` completo en el extracto, lo que sólo indica que no hay pago/reconciliación de línea materializado, no un estado de tesorería real.

## 12. Reproducibilidad

La investigación vive en un módulo aislado sin dependencias de runtime y con lógica clasificadora pura, testeable sin Data Lake.

```bash
cd SrvRestAstroLS_v1/backend
uv run pytest modules/telchi/investigation/validation/ap_invoiced_without_warehouse_receipt_v1/ -q
uv run python modules/telchi/investigation/validation/ap_invoiced_without_warehouse_receipt_v1/run_gate.py
```

Archivos: `ap_invoice_no_grpo.py` (carga, evidencia, `classify()`), `run_gate.py` (controles y escritura de evidencia), `test_ap_invoice_no_grpo.py` (17 tests de la lógica pura), `evidence/` (resumen + una línea JSONL por OC/línea).

## 13. Recomendaciones de continuación

Acciones ordenadas por urgencia para cerrar las excepciones y reducir el riesgo residual.

1. Requerir a compras/almacén la recepción faltante o la anulación de las 2 líneas reales (115 unidades, 68 y 80 días sin resolver).
2. Verificar en SAP el despacho aduanero de las 17 líneas de importación (ALM-IMP, 26–30 días desde la factura) y el cumplimiento de entrega de las 4 facturas anticipo (539.000 unidades).
3. Corregir el maestro o el proceso de "cruce de códigos" de Flexo: la compra `L03687`/`L03688` sólo es rastreable por comentario, no por enlace documental.
4. Extender Foundation si se necesita causal humana: historial de cambios de línea de OC y notas de recepción eliminadas.

## 14. Distribución de las 10 categorías obligatorias

Reparto exacto de las 25 líneas y 683.025 unidades base; las categorías no usadas quedan en cero declarado, no omitidas.

| # | Categoría | Líneas | Unidades base | % base | Lectura |
| ---: | --- | ---: | ---: | ---: | --- |
| 1 | `DIRECT_AP_INVOICE_NO_GRPO` | 21 | 676.910 | 99,11 % | Factura directa de la OC sin recepción, con explicación documental: 4 líneas anticipo (539.000) y 17 de importación en USD (137.910) |
| 2 | `RECEIPT_FOUND_ALTERNATE_LINEAGE` | 0 | 0 | 0,00 % | Ninguna recepción resuelve a estas OC/facturas por ningún camino |
| 3 | `INVENTORY_ENTRY_WITHOUT_GRPO` | 2 | 6.000 | 0,88 % | Flexo `L03687`/`L03688`: stock ingresado por la propia factura (TT18) y emitido el mismo día con comentario de cruce de códigos |
| 4 | `RECEIPT_OUTSIDE_WINDOW` | 0 | 0 | 0,00 % | 0 recepciones fuera de la ventana usada (2026-01-01 → 2026-09-24) |
| 5 | `HISTORICAL_LINEAGE_GAP` | 0 | 0 | 0,00 % | La ventana de recepciones cubre las 25 OC (25/25) |
| 6 | `CANCELLED_OR_REVERSED` | 0 | 0 | 0,00 % | 0 encabezados anulados, 0 reversas de compra |
| 7 | `NON_INVENTORY_EXCEPTION` | 0 | 0 | 0,00 % | Los 23 ítems son inventariables |
| 8 | `QUANTITY_UOM_ISSUE` | 0 | 0 | 0,00 % | Sin recepciones no hay incompatibilidad de UoM que resolver; factura y OC coinciden en base 25/25 |
| 9 | `TRUE_INVOICED_WITHOUT_RECEIPT` | 2 | 115 | 0,02 % | Excepciones reales sin documento ni movimiento (sección 15) |
| 10 | `NOT_DETERMINABLE` | 0 | 0 | 0,00 % | Todo el universo es determinable con las fuentes permitidas |
| | **Total** | **25** | **683.025** | **100,00 %** | partición exacta, 1 categoría por línea |

## 15. Excepciones reales: `TRUE_INVOICED_WITHOUT_RECEIPT`

Dos líneas, 115 unidades base, sin recepción y sin entrada ni salida de inventario atribuible, más sin explicación documental: son las únicas que requieren gestión activa.

| OC / línea | Ítem | Cant. base | Proveedor | Almacén | Fecha OC | Factura | Fecha factura | Antigüedad | Comentario relevante |
| --- | --- | ---: | --- | --- | --- | --- | --- | ---: | --- |
| 262002290/0 | L01491 `BENTONITA x Kg.` (INSUMO) | 45 | PL000973 EQUIPETROL SA | 2A-MAG Almacén Magistral | 2026-07-15 | 262004306 (`BaseEntry=27086`) | 2026-07-06 (−9 días) | 80 días | Sin anticipo ni referencia de embarque; sin candidatos de recepción siquiera |
| 262002366/0 | M03729 `PALLET DE MADERA p/traslado` (VARIOS) | 70 | PL000200 PROVEEDORES VARIOS | SAA-M1 Procesadora Saavedra | 2026-07-21 | 262004458 (`BaseEntry=27225`) | 2026-07-18 (−3 días) | 68 días | Único candidato: recepción de 75 u. en SAA-T1 del 2026-06-09 que ampara a la OC 25742/0 |

Por qué son "reales": ambas facturas son `DocCur='BS'`, sin comentario de anticipo y sin NumAtCard con embarque; no existe recepción por linaje, ni candidato que las cubra, ni movimiento cuyo `base_ref` sea su factura. Verificado además sobre toda la tabla OINM (2022-03-31 → 2026-09-24), `L01491` no tiene ninguna entrada: sólo una salida de 5 u. el 2026-01-22. `M03729` sólo tiene entradas de arranque (2022) y, en 2026, la recepción de 75 u. que pertenece a la OC 25742/0, transferida el 2026-09-04 de `SAA-T1` a `SAA-M1` (75 u., no 70): ese stock es de otra compra. Magnitud baja (0,02 % del universo) pero antigüedad alta (68–80 días).

## 16. Respuesta ejecutiva

Resultado del gate sobre las 25 líneas y 683.025 unidades base, desglosado por explicación documental.

De las 25 líneas facturadas sin recepción (683.025 unidades base), **21 líneas y 676.910 unidades (99,11 %) están explicadas por documentación**: 17 líneas son facturas de importación en USD con referencia de embarque hacia `ALM-IMP` (137.910) y 4 son facturas anticipo con la solicitud escrita en el comentario de OC y factura (539.000). **2 líneas y 6.000 unidades (0,88 %) sí entraron a almacén sin documento GRPO**, por la propia factura de compra, y salieron el mismo día bajo un comentario de cruce de códigos. **Sólo 2 líneas y 115 unidades (0,02 %) son excepciones reales** sin recepción ni movimiento atribuible, con 68 y 80 días de antigüedad. No existe ninguna recepción para estas 25 líneas por ningún camino documental; los 30 movimientos parecidos se comprobó que amparan a otras OC.

## 17. Interpretación de negocio

Qué significa el reparto para compras, almacén y control interno, más allá del número de líneas.

El patrón dominante no es un fallo de control de almacén sino **una secuencia de compra distinta a la estándar**: se factura primero y la recepción se espera después (anticipos) o la mercancía se tramita en importación (nacionalización posterior a la factura).

- **Anticipos (539.000 unidades, 78,9 % del universo)**: hay pago antes de entrega explícito en el documento. El riesgo no es contable sino de cumplimiento de entrega; la OC 262002813 sola concentra 504.000 de esas unidades con INDUSTRIAS RAVI.
- **Importación (137.910 unidades en USD, 20,2 %)**: 26 a 30 días desde la factura sin ingreso a `ALM-IMP` es el régimen que el propio gate anterior identificó como lento (p90 >30 días para importación), por lo que este grupo está en la cola normal de despacho, no en una anomalía. Conviene confirmar nacionalización antes de aceptar el cierre de esas OC.
- **Entrada sin GRPO (6.000 unidades)**: el material comprado sí se usó, pero entró con un documento de factura y salió bajo un "cruce de códigos", es decir quedó registrado bajo otro `ItemCode`. Para trazabilidad de lote esto es un riesgo real de perder el vínculo compra → material → producto.
- **Excepciones reales (115 unidades)**: magnitud irrelevante para el balance, pero son compras cerradas y pagadas en apariencia sin respaldo de entrega; ambas conviene resolver con soporte del proveedor (EQUIPETROL y "proveedores varios").
- **Para el control interno**: la señal útil no es `LineStatus` (no discrimina), sino `OC cerrada + factura abierta + cero recepción + cero movimiento atribuible`. Ese cuatruple filtro deja sólo 2 líneas materiales para auditoría, frente a las 25 originales.
