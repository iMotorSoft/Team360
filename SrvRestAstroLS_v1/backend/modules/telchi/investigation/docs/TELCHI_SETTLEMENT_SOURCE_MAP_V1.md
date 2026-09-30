# TELCHI_SETTLEMENT_SOURCE_MAP_V1

## Convenciones

`CONFIRMED` significa columna, unión y datos observados en SAP/HANA. `CONDITIONAL` significa que el
hecho es exacto solo bajo la condición indicada. Todas las fuentes SAP se consultaron `READ ONLY`.

| Business fact | Source table | Source field(s) | Join/key | Confidence | Notes |
|---|---|---|---|---|---|
| Identidad factura | `OINV` | `ObjType`, `DocEntry` | `13 + DocEntry` | CONFIRMED | `DocEntry` único en 1.858.531 filas |
| Número visible factura | `OINV` | `DocNum` | clave documento | CONFIRMED | No usar como PK |
| Cliente técnico | `OINV` | `CardCode` | clave documento | CONFIRMED | Minimizar; no publicar nombre salvo necesidad |
| Fecha/vencimiento factura | `OINV` | `DocDate`, `DocDueDate` | clave documento | CONFIRMED | Vencimiento no prueba cobro |
| Condición asignada | `OINV` | `GroupNum` | `OINV.GroupNum=OCTG.GroupNum` | CONFIRMED | Condición comercial |
| Moneda e importe factura | `OINV` | `DocCur`, `DocTotal`, `DocTotalFC`, `DocTotalSy`, `DocRate` | clave documento | CONFIRMED | Preservar tres ejes |
| Saldo actual factura | `OINV` | `DocTotal-PaidToDate`, equivalentes FC/system | clave documento | CONFIRMED | Snapshot actual, no histórico |
| Estado/cancelación factura | `OINV` | `DocStatus`, `CANCELED`, `CancelDate` | clave documento | CONFIRMED | Excluir efecto vigente, preservar fila |
| Cuota/vencimiento | `INV6` | `DocEntry`, `InstlmntID`, `DueDate`, `InsTotal`, `PaidToDate`, `Status` | `DocEntry+InstlmntID`; `ObjType=13` | CONFIRMED | 1.858.531 filas/1.858.531 claves observadas |
| Identidad nota de crédito | `ORIN` | `ObjType`, `DocEntry` | `14 + DocEntry` | CONFIRMED | `DocEntry` único en 10.884 filas |
| Importe/estado NC | `ORIN` | fechas, moneda, totales, `CANCELED`, `DocStatus`, `TransId` | clave NC | CONFIRMED | NC no es pago |
| Identidad cobranza | `ORCT` | `ObjType`, `DocEntry` | `24 + DocEntry` | CONFIRMED | `DocEntry` único en 1.836.181 filas |
| Fecha cobranza | `ORCT` | `DocDate`, `TaxDate`, `DocDueDate` | clave pago | CONFIRMED | Usar `DocDate`; conservar las demás |
| Total/moneda cobranza | `ORCT` | `DocCurr`, `DocTotal`, `DocTotalFC`, `DocTotalSy`, rates | clave pago | CONFIRMED | BS y USD observados |
| Estado/cancelación cobranza | `ORCT` | `Canceled`, `CancelDate`, `Status` | clave pago | CONFIRMED | 11.150 cancelados observados |
| Pago a cuenta | `ORCT` | `PayNoDoc`, `NoDocSum*`, `OpenBal*` | clave pago | CONFIRMED | No inventar factura destino |
| Pago→destino | `RCT2` | `DocNum`, `InvType`, `DocEntry`, `InstId`, `DocLine` | `DocNum=ORCT.DocEntry`; tipo+`DocEntry`=destino | CONFIRMED | No usar `RCT2.InvoiceId` como DocEntry |
| Importe aplicado | `RCT2` | `SumApplied`, `AppliedFC`, `AppliedSys`, descuentos/ajustes | clave agregada de allocation | CONFIRMED | Agrupar duplicados exactos y guardar conteo |
| Fecha de enlace directo | `RCT2` | `LinkDate` | allocation | CONFIRMED | Settlement efectivo se controla con OITR/ITR1 |
| Efectivo | `ORCT` | `CashSum`, `CashSumFC`, `CashSumSy`, `CashAcct` | clave pago | CONFIRMED | Componente de medio, no clasificación de venta |
| Transferencia | `ORCT` | `TrsfrSum*`, `TrsfrDate`, `TrsfrRef` | clave pago | CONFIRMED | Referencia protegida |
| Cheque resumen | `ORCT` | `CheckSum*` | clave pago | CONFIRMED | Cabecera |
| Cheque detalle | `RCT1` | `DocNum`, `LineID`, `CheckSum`, `Currency`, fechas | `DocNum=ORCT.DocEntry` | CONFIRMED | 2.471 líneas, clave única; datos sensibles protegidos |
| Tarjeta resumen | `ORCT` | `CreditSum`, `CredSumFC`, `CredSumSy` | clave pago | CONFIRMED | Cabecera |
| Tarjeta detalle | `RCT3` | `DocNum`, `LineID`, `CreditSum`, `CreditCur`, cuotas/tipo | `DocNum=ORCT.DocEntry` | CONFIRMED | 204.227 líneas, clave única; no publicar PAN/titular |
| Destino a cuenta GL | `RCT4` | `DocNum`, `LineId`, `AcctCode`, `SumApplied*` | `DocNum=ORCT.DocEntry` | CONFIRMED | No es “otro medio”; es aplicación contable |
| Pago mixto | `ORCT` + `RCT1/RCT3` | componentes positivos | clave pago | CONFIRMED | 12.623 observados; no distribuir medio por factura |
| Identidad reconciliación | `OITR` | `ReconNum` | `source_system+ReconNum` | CONFIRMED | Único en 2.119.291 filas |
| Fecha/moneda reconciliación | `OITR` | `ReconDate`, `ReconCurr`, `Total` | clave reconciliación | CONFIRMED | BS y USD observados |
| Tipo/origen reconciliación | `OITR` | `IsSystem`, `ReconType`, `InitObjTyp`, `InitObjAbs` | clave reconciliación | CONFIRMED | Manual `IsSystem=N` observado |
| Cancelación reconciliación | `OITR` | `Canceled`, `CancelAbs`, `ReconDate` | `CancelAbs↔ReconNum` | CONFIRMED | Pares Y/C; cierre de día para as-of |
| Miembro reconciliación | `ITR1` | `ReconNum`, `LineSeq`, `SrcObjTyp`, `SrcObjAbs`, `InstID` | `ReconNum+LineSeq` | CONFIRMED | Clave única en 4.531.894 filas |
| Importe reconciliado del miembro | `ITR1` | `ReconSum`, `ReconSumFC`, `ReconSumSC`, `IsCredit` | miembro | CONFIRMED | Autoridad de efecto sobre el documento |
| Factura↔pago por reconciliación | `OITR/ITR1` | miembros tipo 13 y 24 | mismo `ReconNum` | CONDITIONAL | Exacto como componente; pairwise exacto solo si no es N:N |
| Factura↔NC | `OITR/ITR1` | miembros tipo 13 y 14 | mismo `ReconNum` | CONDITIONAL | Caso 1:1 probado; N:N queda sin reparto inventado |
| Reconciliación manual | `OITR/ITR1` | `IsSystem=N`, miembros | `ReconNum` | CONFIRMED | 30.102 reconciliaciones activas manuales observadas |
| Saldo histórico as-of | `OITR/ITR1` + documentos | `ReconDate`, `Canceled`, `CancelAbs`, monto miembro | documento+fecha | CONFIRMED_DATE_GRAIN | Desde 2022-03-31; no intradía |
| Primera/última fecha pago | `ORCT/RCT2`, o miembro tipo 24 inequívoco | `ORCT.DocDate` | documento↔pago | CONDITIONAL | No derivar pairwise en N:N |
| Fecha fully settled | eventos efectivos `OITR/ITR1` | `ReconDate`, acumulado de miembro | documento+fecha | CONFIRMED_DATE_GRAIN | Primera fecha con saldo dentro de tolerancia |
| Término maestro | `OCTG` | `GroupNum`, `PymntGroup`, `ExtraMonth`, `ExtraDays`, cuotas | `GroupNum` | CONFIRMED | 37 términos SAP; 18 con cero meses/días |
| `payment_terms` Foundation | Parquet reference | schema V2, 0 filas | referencia CURRENT | CONFIRMED | Dataset existe vacío; no contiene OCTG |
| Provenance | todas | tabla, clave nativa, timestamps de extracción, run/snapshot/versiones | por entidad | REQUIRED | Sin `derived somehow` |

## Tablas candidatas descartadas o acotadas

| Tabla | Decisión | Motivo observado |
|---|---|---|
| `OINV` | útil | cabecera, condición, importes y saldo actual |
| `INV6` | útil | cuota y saldo por vencimiento |
| `ORIN` | útil | notas de crédito como documentos, no pagos |
| `ORCT` | útil | cobranza y resumen de medios |
| `RCT1` | útil | detalle de cheques |
| `RCT2` | útil con clave corregida | aplicación directa; `DocNum` es pago y `DocEntry` destino |
| `RCT3` | útil | detalle de tarjetas |
| `RCT4` | útil, no como medio | aplicación a cuenta contable |
| `OITR/ITR1` | imprescindible | ledger de settlement y reconciliación |
| `OCTG` | útil solo comercial | términos; no prueba settlement |

## Corrección necesaria frente a SQL investigativo previo

Los archivos históricos `payment_application_v1.sql`/validación FINANCIAL-003 documentaban
`RCT2.DocEntry = ORCT.DocEntry` y trataban `InvoiceId` como identificador de factura. Los datos reales
demostraron lo contrario: `RCT2.DocNum = ORCT.DocEntry` en 100% de las filas y, para tipo 13,
`RCT2.DocEntry = OINV.DocEntry` en 100%. Este source map es la autoridad para el próximo gate; los
artefactos históricos no fueron modificados en esta investigación.
