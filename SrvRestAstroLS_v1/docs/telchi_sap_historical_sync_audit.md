# Auditoría del sync histórico SAP Business One de Telchi

Este informe registra la compatibilidad estructural y semántica del sync histórico con SAP HANA 2 actual. Es evidencia de auditoría read-only, no diseño implementado ni autorización para escribir SAP o Parquet.

## Resultado ejecutivo

La infraestructura y los 15 probes HANA están verdes. El gate queda `PARTIAL`: las incompatibilidades están diagnosticadas, pero objetivos comerciales no tiene líneas actuales ni lector legacy que permita confirmar su significado.

- Resultado técnico HANA: `15/15 PASS`.
- Paridad semántica: `9 PASS`, `8 CHANGE_REQUIRED`, `1 DEPRECATED`, `1 BLOCKED`.
- Extractores o rutinas inventariados: `19`.
- Estados `UNKNOWN`: `0`.
- Escrituras SAP, SQL DML y Parquet productivo: `0`.
- Fuente reproducible: `backend/scripts/audit_telchi_sap_historical_sync.py`.

## Baseline validado

El baseline fue comprobado nuevamente antes de ejecutar consultas históricas y después de crear los probes.

| Gate | Evidencia |
| --- | --- |
| VPN strongSwan | PASS |
| TCP | `192.168.20.20:30015` PASS |
| HANA | `2.00.056.00.1624618329` |
| Schema | `TELCHI` PASS |
| Usuario | `insiding_hana` PASS |
| Acceso | READ ONLY PASS |
| HANA smoke | `TEAM360_TELCHI_SAP_HANA_SMOKE_PASS` |
| Probe window | `2026-08-01` a `2026-08-13 23:59:59` |

El password se cargó desde el archivo privado externo ya establecido. No se imprimió ni se incorporó al repositorio.

## Fuentes históricas reales

El checkout del repositorio Telchi estaba vacío, pero su `HEAD` conserva las fuentes y 534 Parquet como blobs Git. La auditoría leyó esos blobs en un directorio temporal privado.

- Repositorio legacy: `/media/issajar/DEVELOP/Projects/telchi`.
- Extractor SAP operativo: `Insiding/DataScience/SrvRest/srvSyncTelchiSB101.py`.
- Herramientas SAP: `Insiding/DataScience/sapb1Tools01.py`.
- ERP anterior: `Insiding/DataScience/SrvRest/srvSyncTelchi02.py`.
- Costos anteriores: `Insiding/DataScience/SrvRest/syncCosto01.py`.
- Data Lake: `Insiding/DataScience/DS/` dentro del mismo `HEAD`.

Solo los dos primeros archivos consultaban HANA. Los extractores de compras, gastos, costos, caja, tracking y transformaciones usaban SQL Server/Arango del ERP anterior; no son SQL SAP que pueda ejecutarse sin rediseño.

## Inventario completo

El inventario cuenta outputs o rutinas con intención independiente. Los wrappers mensuales y las funciones `*Range` no se duplican como extractores.

| ID | Rutina legacy | Dominio | Clase | Output histórico | Frecuencia o intención |
| --- | --- | --- | --- | --- | --- |
| PRODUCTS | `makeProduct` | Productos | ACTIVE_LEGACY | `productSB1.parq` | snapshot por job |
| PRODUCT_PROPERTIES | `makeProductPropiety` | Propiedades de producto | UTILITY | merge en `productSB1` | snapshot, 64 queries |
| CUSTOMERS | `makeClient` | Clientes/socios | DORMANT_LEGACY | `clientSB1.parq` | snapshot manual; output no hallado |
| CUSTOMER_PROPERTIES | `makeClientPropiety` | Propiedades de socio | UTILITY | merge en `clientSB1` | snapshot, 64 queries |
| WAREHOUSE_MASTER | `makeOWHS` | Maestro de almacenes | DORMANT_LEGACY | `owhsSB1.parq` | snapshot manual |
| ITEM_WAREHOUSE | `makeWhareHouse` | Stock por almacén | ACTIVE_LEGACY | `wareHouseSB1.parq` | snapshot por job |
| WAREHOUSE_OFFICE_MAPPING | `makeSapWhsOfficeName` | Mapeo organizacional | UTILITY | `sapWhsOfficeName.parq` | conversión de Excel |
| SALES | `syncDSSale` / `makeSaleDFRange` | Ventas | ACTIVE_LEGACY | `saleSB1Product-YYYY-MM-DD.parq` | mes corriente |
| CREDIT_NOTES | `syncDSNC` / `makeNCDFRange` | Notas de crédito | ACTIVE_LEGACY | `ncB1Product-YYYY-MM-DD.parq` | mes corriente |
| INVENTORY_MOVEMENTS | `syncDSMoveProduct` / `makeMoveProductRange` | Movimientos | ACTIVE_LEGACY | `movProductSB1-YYYY-MM-DD.parq` | mes corriente |
| RECONCILIATIONS | `makeReconRange` | Reconciliaciones | DORMANT_LEGACY | `reconB1-YYYY-MM-DD.parq` | backfill manual; output no hallado |
| INCOMING_PAYMENTS | `makePaymentRange` | Cobros | DORMANT_LEGACY | `paymentB1-YYYY-MM-DD.parq` | backfill manual; output no hallado |
| ITEM_GROUPS | `makeOITB` | Grupos de artículos | DORMANT_LEGACY | `oitbSB1.parq` | snapshot manual |
| CHART_OF_ACCOUNTS | `makeOACT` | Plan contable | DORMANT_LEGACY | `oactSB1.parq` | snapshot manual |
| BOM_MIGRATION | `makeRecetasSap` | BOM/recetas | MIGRATION_ONLY | CSV para importar a SAP | migración puntual |
| PURCHASES | `makePurchaseDFRange` | Compras | ACTIVE_LEGACY | `purchase-YYYY-MM-DD.parq` | mensual, ERP anterior |
| PURCHASE_EXPENSES | `makePurchaseExpenseDFRange` | Gastos de compra | ACTIVE_LEGACY | `purchaseExpense-YYYY-MM-DD.parq` | mensual, ERP anterior |
| COSTS | `makeCostDay` / `costUTree` | Costos | ACTIVE_LEGACY | `ProductSaleCostDay-YYYY-MM-DD.parq` | cálculo diario derivado |
| SALES_TARGETS | No encontrado | Objetivos comerciales | UNKNOWN_LEGACY | No encontrado | objeto UDT observado |

Totales por clase: `ACTIVE_LEGACY=8`, `DORMANT_LEGACY=6`, `UTILITY=3`, `MIGRATION_ONLY=1`, `UNKNOWN_LEGACY=1`, `BACKFILL` separado `=0`.

## Matriz de compatibilidad

La columna “legacy” indica si el SQL original acotado ejecutó en HANA. `N/A` significa que la rutina no leía HANA o que no existía extractor, no que la infraestructura haya fallado.

| ID | Dominio | Objetos HANA | Legacy | Equivalente actual | Paridad semántica | Estado | Diagnóstico |
| --- | --- | --- | --- | --- | --- | --- | --- |
| PRODUCTS | Productos | OITM, OITB, OMRC, OITG | PASS | joins explícitos + fechas de actualización | Sí | PASS | 15 columnas legacy aún existen; 64 propiedades también existen |
| PRODUCT_PROPERTIES | Productos | OITM, OITG | PASS | extracción set-based de `QryGroup1..64` | Sí | PASS | 64 round trips son deuda, no cambio de negocio |
| CUSTOMERS | Clientes | OCRD | PASS | `CardType='C'` | Parcial | CHANGE_REQUIRED | legacy llamaba cliente también a proveedores |
| CUSTOMER_PROPERTIES | Clientes | OCRD, OCQG | PASS | propiedades limitadas a clientes | Parcial | CHANGE_REQUIRED | debe heredar el filtro de socio cliente |
| WAREHOUSE_MASTER | Almacenes | OWHS | PASS | proyección legacy | Sí | PASS | 82 almacenes, todos no bloqueados |
| ITEM_WAREHOUSE | Stock | OITW | PASS | snapshot por `ItemCode,WhsCode` | Sí | PASS | 1,356,566 claves completas y únicas |
| WAREHOUSE_OFFICE_MAPPING | Organización | Excel externo | N/A | conservar mapping versionado por negocio | Sí | PASS | utilidad externa, no extractor HANA |
| SALES | Ventas | OINV, INV1, OSLP, OUSR | PASS | filtro `CANCELED='N'`, claves de línea y moneda | Parcial | CHANGE_REQUIRED | legacy incluía pares `Y/C` cancelados |
| CREDIT_NOTES | Notas de crédito | ORIN, RIN1, OSLP | PASS | signo negativo + `CANCELED='N'` | Parcial | CHANGE_REQUIRED | el signo es válido; cancelaciones no |
| INVENTORY_MOVEMENTS | Movimientos | OINM VIEW | PASS | ledger base sin `Price/0.87` | Parcial | CHANGE_REQUIRED | vista cambió y el factor fijo no es semántica universal |
| RECONCILIATIONS | Reconciliación | OITR, ITR1, OUSR | PASS | conservar flag `Canceled` | Sí | PASS | join y columnas vigentes |
| INCOMING_PAYMENTS | Cobros | ORCT | PASS | moneda `DocCurr`, claves y update fields | Sí | PASS | query vigente; consumidores deciden tratamiento de cancelados |
| ITEM_GROUPS | Productos | OITB | PASS | proyección legacy | Sí | PASS | columnas y casing vigentes |
| CHART_OF_ACCOUNTS | Contabilidad | OACT | PASS | proyección legacy + update date | Sí | PASS | objeto y columnas vigentes |
| BOM_MIGRATION | BOM | OITT, ITT1 | N/A | lector read-only de BOM actual | No | DEPRECATED | la rutina vieja escribía CSV de migración, no extraía HANA |
| PURCHASES | Compras | OPOR, POR1, OCRD, OITM, OWHS | N/A | órdenes SAP no canceladas | Parcial | CHANGE_REQUIRED | reemplaza `cohor/codor`; campos locales requieren mapping |
| PURCHASE_EXPENSES | Costos de compra | OIPF, IPF1, IPF2 | N/A | landed costs SAP | Parcial | CHANGE_REQUIRED | categorías libres del ERP anterior no tienen mapping directo |
| COSTS | Costos | OINM, OITM, OITT, ITT1, OPCH/PCH1 | N/A | especificación por valoración SAP, no fórmula legacy | No | CHANGE_REQUIRED | dependía de Arango, Parquet viejos y árbol recursivo mutable |
| SALES_TARGETS | Objetivos | `@OBJ_VENTAS_C`, `@OBJ_VENTAS_L` | N/A | join cabecera/línea probado | No demostrable | BLOCKED | 8 cabeceras, 0 líneas y ningún lector legacy |

Los totales finales son `PASS=9`, `CHANGE_REQUIRED=8`, `DEPRECATED=1`, `BLOCKED=1`, `UNKNOWN=0`.

## Evidencia temporal HANA

Las métricas actuales demuestran que el backfill no puede basarse en la fecha final de un único dataset histórico.

| Dominio/objeto | Filas actuales | Mínimo | Máximo |
| --- | ---: | --- | --- |
| Facturas OINV | 1,804,006 | 2022-03-31 | 2026-08-13 |
| Notas ORIN | 10,466 | 2022-04-01 | 2026-08-13 |
| Movimientos OINM | 8,239,535 | 2022-03-31 | 2026-08-13 |
| Reconciliaciones OITR | 2,056,498 | 2022-03-31 | 2026-08-13 |
| Cobros ORCT | 1,782,055 | 2022-03-31 | 2026-08-13 |
| Órdenes de compra OPOR | 18,399 | 2022-01-01 | 2026-08-13 |
| Facturas de proveedor OPCH | 31,712 | 2022-03-31 | 2026-08-13 |
| Productos OITM | 16,715 | snapshot | snapshot |
| Socios OCRD | 13,963 | snapshot | snapshot |
| BOM OITT / ITT1 | 1,040 / 7,730 | 2022-03-18 | update 2026-08-13 |

Los socios se dividen en `12,906` clientes y `1,057` proveedores. Esto confirma que el filtro ausente en `makeClient` cambia el significado del output.

## Paridad con Parquet histórico

Se leyeron los Parquet versionados sin escribirlos. Los seis cortes SAP comparables cubren 2022-04-01 a 2022-09-30; no hay cortes SAP posteriores a septiembre de 2022 en el `HEAD` auditado.

| Dataset | Parquet histórico | HANA actual misma ventana | Diferencia observada |
| --- | --- | --- | --- |
| Ventas, filas | 380,688 | 381,033 | +345 |
| Ventas, cantidad | 6,033,683.43 | 6,039,181.43 | +5,498.00 |
| Ventas, importe reconstruido/header | 37,856,289.20 | 37,875,448.58 | +19,159.38 |
| NC, filas | 3,899 | 3,919 | +20 |
| NC, cantidad firmada | -103,453.00 | -105,102.00 | -1,649.00 |
| NC, importe reconstruido/header | -865,596.35 | -872,204.46 | -6,608.11 |
| Movimientos, filas | 844,361 | 812,712 | -31,649 |
| Movimientos, entrada | 30,582,429.7372 | 30,633,490.5557 | +51,060.8185 |
| Movimientos, salida | 32,974,802.9056 | 30,835,335.2981 | -2,139,467.6075 |
| Movimientos, valor | -4,883,979.03 | 569,208.61 | +5,453,187.64 |

Las diferencias no se “corrigieron” para forzar igualdad. Ventas y NC muestran revisiones históricas pequeñas; OINM muestra una revisión material de la vista o de su contenido y exige backfill completo con la query actual.

Los snapshots también crecieron: productos `10,046 → 16,715`, OITW `592,320 → 1,356,566`, OITB `38 → 40`, OACT `523 → 823` y OWHS `59 → 82`.

## Semántica y transformaciones

Las transformaciones Python fueron auditadas junto con el SQL, porque varias decisiones de negocio no estaban expresadas en HANA.

- Ventas distribuía la diferencia entre `SUM(GTotal)` y `DocTotal` por coeficiente de línea y llamaba `ItemSale` al resultado.
- NC negaba cantidades e importes y repetía la distribución; el signo se conserva, el tratamiento de cancelados cambia.
- Ambos generaban `YMD`, `YM`, `Y`, rellenaban referencias y añadían `OfficeName` desde un Excel externo.
- Movimientos enriquecía OINM con factura, entrega, cliente, usuario y vendedores mediante varios merges.
- Movimientos calculaba `ItemSaleU = Price / 0.87`; esa constante no puede sobrevivir como regla universal.
- Productos y clientes concatenaban hasta 64 propiedades con `|`; la semántica se conserva, la ejecución debe ser set-based.
- Los `fillna` legacy sin asignación en movimientos no modificaban el DataFrame y son bugs silenciosos.
- La variante nueva de `makeSaleDFRange` en `sapb1Tools01.py` proyectaba más columnas pero conservaba un rename incompatible; podía retornar `None` por excepción silenciosa.

## Readiness incremental

Los cursores se proponen solo como contrato para el gate siguiente. Deben usar solapamiento temporal e idempotencia porque SAP permite actualizar documentos históricos.

| Extractor futuro | Backfill | Cursor candidato | Clasificación | Riesgo principal |
| --- | --- | --- | --- | --- |
| PRODUCTS | completo | `UpdateDate,UpdateTS,ItemCode` | SAFE_INCREMENTAL_CURSOR | altas y congelados |
| CUSTOMERS | completo | `UpdateDate,UpdateTS,CardCode` | SAFE_INCREMENTAL_CURSOR | separar C/S |
| WAREHOUSE_MASTER | completo | ninguno confiable | FULL_REFRESH | snapshot pequeño |
| ITEM_WAREHOUSE | completo | ninguno en objeto | FULL_REFRESH | snapshot grande |
| SALES | desde 2022-03-31 | `UpdateDate,UpdateTS,DocEntry,LineNum` | COMPOSITE_CURSOR_REQUIRED | cambios tardíos/cancelaciones |
| CREDIT_NOTES | desde 2022-04-01 | `UpdateDate,UpdateTS,DocEntry,LineNum` | COMPOSITE_CURSOR_REQUIRED | signos/cancelaciones |
| INVENTORY_MOVEMENTS | completo | `TransNum,TransSeq` | SAFE_INCREMENTAL_CURSOR | OINM es vista y puede reexpresarse |
| RECONCILIATIONS | completo | `ReconNum,LineSeq` | COMPOSITE_CURSOR_REQUIRED | cancelaciones posteriores |
| INCOMING_PAYMENTS | completo | `UpdateDate,UpdateTS,DocEntry` | COMPOSITE_CURSOR_REQUIRED | anulaciones |
| ITEM_GROUPS | completo | ninguno necesario | FULL_REFRESH | snapshot pequeño |
| CHART_OF_ACCOUNTS | completo | `UpdateDate,AcctCode` | SAFE_INCREMENTAL_CURSOR | jerarquía padre |
| BOM | completo | `UpdateDate,UpdateTS,Code,ChildNum` | COMPOSITE_CURSOR_REQUIRED | componentes eliminados |
| PURCHASES | desde 2022-01-01 | `UpdateDate,UpdateTS,DocEntry,LineNum` | COMPOSITE_CURSOR_REQUIRED | campos locales sin mapping |
| PURCHASE_EXPENSES | completo | `UpdateDate,DocEntry,LineNum` | COMPOSITE_CURSOR_REQUIRED | asignación IPF2 |
| COSTS | completo | no definido | NEEDS_RESEARCH | método de valoración requerido |
| SALES_TARGETS | no autorizado | no definido | NEEDS_RESEARCH | línea UDT vacía |

## Contrato para los extractores futuros

Esta especificación define fuentes y outputs mínimos; no crea módulos productivos ni writers.

| Extractor | Fuente SAP validada | Clave primaria candidata | Columnas/transformaciones requeridas | Estado |
| --- | --- | --- | --- | --- |
| Products | OITM + OITB + OMRC + OITG | ItemCode | maestro, grupo, fabricante, UDF, flags de propiedad | PASS |
| Customers | OCRD + OCQG | CardCode | solo CardType C, grupo y propiedades | CHANGE_REQUIRED |
| Warehouses | OWHS | WhsCode | nombre, bloqueo, cuentas; mapping oficina externo | PASS |
| Item warehouse | OITW | ItemCode + WhsCode | on hand, committed, on order, precios/cuentas | PASS |
| Sales | OINV + INV1 + OSLP | DocEntry + LineNum | no cancelados, moneda, líneas, vendedor; definir neto/impuesto | CHANGE_REQUIRED |
| Credit notes | ORIN + RIN1 + OSLP | DocEntry + LineNum | no canceladas y magnitudes firmadas negativas | CHANGE_REQUIRED |
| Inventory movements | OINM | TransNum + TransSeq | ledger, cantidad, valor y costo; sin factor 0.87 | CHANGE_REQUIRED |
| Reconciliations | OITR + ITR1 | ReconNum + LineSeq | flags y referencias origen | PASS |
| Incoming payments | ORCT | DocEntry | medios de pago, moneda, estado y BP | PASS |
| Item groups | OITB | ItmsGrpCod | grupo y cuentas | PASS |
| Chart of accounts | OACT | AcctCode | jerarquía, posting y saldos | PASS |
| BOM | OITT + ITT1 | Code + ChildNum | cabecera, componente, cantidad y almacén | DEPRECATED legacy / source current PASS |
| Purchases | OPOR + POR1 | DocEntry + LineNum | proveedor, fechas, moneda, producto, almacén, importes | CHANGE_REQUIRED |
| Purchase expenses | OIPF + IPF1 + IPF2 | DocEntry + LineNum + AlcCode | landed cost y asignación por línea | CHANGE_REQUIRED |
| Costs | OINM/OITM/BOM/AP invoices | por definir | política de valoración y costo efectivo | CHANGE_REQUIRED |
| Sales targets | UDT cabecera/línea | Code + LineId | supervisor, vendedor y meses | BLOCKED |

No se define todavía schema Parquet físico, particionado, scheduler, checkpoint store ni servicio Team360. Esas decisiones pertenecen al gate `NEW TEAM360 SAP EXTRACTORS`.

## Deuda de implementación legacy

Esta deuda no invalida por sí sola la lógica de negocio, pero impide copiar el software viejo como arquitectura nueva.

- Credenciales y endpoint histórico embebidos en blobs legacy.
- Paths absolutos, conexiones globales y múltiples sistemas acoplados.
- SQL interpolado con fechas y 64 consultas por propiedades.
- `except:` que devuelve `None` o continúa como si el sync hubiera terminado.
- Writes Parquet no atómicos, sin checkpoints, manifest ni control de idempotencia.
- Merges propensos a duplicación y `fillna` sin asignación.
- Scheduler local y Dask/Arango sin contrato de consistencia.
- BOM legacy generaba CSV de importación; no era read-only.

## Cambios de lógica de negocio

Estos puntos son independientes de la calidad de implementación y deben resolverse en el diseño siguiente.

- Excluir o representar explícitamente documentos cancelados en ventas y NC.
- Distinguir clientes de proveedores en OCRD.
- Eliminar el factor fijo de impuesto/precio en OINM.
- Definir si compras futuras usan órdenes, recepciones o facturas como verdad financiera.
- Mapear gastos legacy a landed costs SAP y decidir su asignación.
- Elegir política de valoración para costos y tratamiento de BOM.
- Confirmar si objetivos UDT sigue vigente y cómo se pueblan sus líneas.

## Reproducción

Los comandos siguientes ejecutan solo preflight, SELECT acotado, tests locales y validaciones del repositorio.

```bash
cd SrvRestAstroLS_v1/backend
uv run python scripts/smoke_telchi_sap_hana.py
uv run python scripts/audit_telchi_sap_historical_sync.py
uv run pytest -q tests/test_telchi_sap_historical_sync_audit.py
uv run python -m py_compile scripts/audit_telchi_sap_historical_sync.py
cd ../..
git diff --check
```

El auditor termina con `TEAM360_TELCHI_SAP_HISTORICAL_SYNC_PROBES_PASS`. El gate global permanece parcial únicamente por semántica de objetivos y cambios de negocio ya clasificados.

## Gate y próximo paso

La evidencia responde qué extraía el legacy, qué objetos siguen vigentes, qué cambió y qué fuentes actuales son candidatas. No autoriza todavía el nuevo pipeline.

```text
TEAM360_TELCHI_SAP_HISTORICAL_SYNC_AUDIT_PARTIAL
```

El siguiente gate puede diseñar `NEW TEAM360 SAP EXTRACTORS` usando esta matriz, resolver `SALES_TARGETS` con Telchi y fijar las políticas de compras/costos antes de escribir Parquet.
