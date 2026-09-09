# TELCHI — GL / TransType / Account Behavior V1

**Gate:** `TELCHI_GL_TRANS_TYPE_ACCOUNT_BEHAVIOR_V1_PASS`
**Veredicto:** **PASS** — el GL queda explicado con degradaciones explícitas; no se interpreta la ausencia del mecanismo estándar como ausencia de retenciones.

## A. Veredicto ejecutivo

Telchi tiene **5792286 OJDT**, **18250121 JDT1** y **824 OACT**. El volumen está dominado por los tipos mostrados abajo; `TransType=30` se separa mediante una regla reproducible, pero `DataSource=O` es un proxy operativo y no prueba por sí solo intención humana.

La búsqueda de retenciones se reporta como: **el mecanismo estándar observado no mostró importes no nulos; el GL sí queda rastreado hacia cuentas/memos candidatos si aparecen**. No se declara que Telchi no registre retenciones.

## B. GL en números

| Objeto | Filas | Desde | Hasta |
|---|---:|---|---|
| OJDT | 5792286 | 2022-03-31T00:00:00 | 2026-09-08T00:00:00 |
| JDT1 | 18250121 | 2022-03-31T00:00:00 | 2026-09-08T00:00:00 |
| OACT | 824 | — | — |

## C. Mapa completo de TransType

| TransType | Objeto propuesto | Asientos | Líneas | % GL | Débito | Crédito | Estado lineage |
|---:|---|---:|---:|---:|---:|---:|---|
| 13 | A/R Invoice | 1837200 | 9339492 | 31.71805 | 575514888.91 | 575514888.91 | PROVEN (100.0%) |
| 24 | Incoming Payment | 1826011 | 3973527 | 31.52488 | 534465007.63 | 534465007.63 | PARTIAL (99.4006%) |
| 30 | Journal Entry | 1605339 | 3264740 | 27.71512 | 661677182.75 | 661677182.75 | PROVEN (100.0%) |
| 67 | Inventory Transfer | 190766 | 438035 | 3.29345 | 1436977436.7 | 1436977436.7 | PROVEN (100.0%) |
| 15 | Delivery | 93223 | 207519 | 1.60943 | 69351498.69 | 69351498.69 | PROVEN (100.0%) |
| 46 | Outgoing Payment | 42928 | 93635 | 0.74112 | 6405268425.84 | 6405268425.84 | PARTIAL (96.8948%) |
| 60 | Goods Issue | 33245 | 81261 | 0.57395 | 274483136.05 | 274483136.05 | PROVEN (100.0%) |
| 18 | A/P Invoice | 32518 | 105525 | 0.5614 | 1188029022.18 | 1188029022.18 | PROVEN (100.0%) |
| 59 | Goods Receipt | 27353 | 61527 | 0.47223 | 308745367.71 | 308745367.71 | PROVEN (100.0%) |
| 321 | Internal Reconciliation | 22283 | 48188 | 0.3847 | 148292425.39 | 148292425.39 | PROVEN (100.0%) |
| 202 | Production Order | 20187 | 48904 | 0.34852 | 8230177.62 | 8230177.62 | PROVEN (100.0%) |
| 20 | Goods Receipt PO | 17041 | 34175 | 0.2942 | 998618228.79 | 998618228.79 | PROVEN (100.0%) |
| 25 | Deposit | 14801 | 448612 | 0.25553 | 222320131.1 | 222320131.1 | PROVEN (100.0%) |
| 14 | A/R Credit Memo | 10715 | 59616 | 0.18499 | 15610700.42 | 15610700.42 | PROVEN (100.0%) |
| -3 | Closing Balance | 5257 | 10514 | 0.09076 | 1763612251.42 | 1763612251.42 | STRONG (None%) |
| -2 | Opening Balance | 4443 | 8886 | 0.07671 | 941232053.18 | 941232053.18 | STRONG (None%) |
| 19 | A/P Credit Memo | 4077 | 15864 | 0.07039 | 5899964.72 | 5899964.72 | PROVEN (100.0%) |
| 21 | Goods Return | 3920 | 7841 | 0.06768 | 1673017.22 | 1673017.22 | PROVEN (100.0%) |
| 16 | Return | 501 | 1002 | 0.00865 | 225192.27 | 225192.27 | PROVEN (100.0%) |
| 69 | Landed Costs | 382 | 1032 | 0.00659 | 14437346.77 | 14437346.77 | PROVEN (100.0%) |
| 162 | Inventory Revaluation | 96 | 226 | 0.00166 | 411170499.41 | 411170499.41 | PROVEN (100.0%) |

## D. Automáticos vs manuales

La clasificación no usa únicamente `TransType=30`: primero reconoce lineage documental; luego `AutoStorno`, `DataSource=I/O` y finalmente `UNCERTAIN`. La categoría manual se define como `TransType=30 AND DataSource=O AND AutoStorno<>Y`, declarada como proxy operativo.

| Categoría | Asientos / filas agregadas |
|---|---:|
| DOCUMENT_GENERATED | 4140163 |
| MANUAL_JOURNAL_ENTRY | 1588132 |
| SYSTEM_GENERATED | 46784 |
| INTEGRATION_GENERATED | 15786 |
| UNCERTAIN | 1421 |

Asientos manuales por regla: **1588132**, período 2022-04-01T00:00:00 → 2026-09-08T00:00:00, importe local agregado 91585204.67.

## E. Cuentas y comportamiento

La evidencia completa de las 824 cuentas, jerarquía, clasificación económica, rankings de movimiento/saldo/transacciones, contrapartidas, riesgos semánticos y muestras está en el JSON. La clasificación SAP conserva `GroupMask`, `FatherNum`, `Levels`, `Postable`, `ActCurr`, `ValidFor` y `FrozenFor`; la interpretación económica Team360 se mantiene separada.

| Cuenta | Nombre | Movimiento absoluto | Saldo neto | Líneas | Clasificación | Riesgo |
|---|---|---:|---:|---:|---|---|
| 1111006 | BANCO FIE Cta.Cte. 60-0-0000-628-1 MN | 6000611972.74 | 431706.24 | 17110 | ACTIVO.BANCO | NORMAL |
| 4210109 | Otros ingresos | 5634650536.9 | -92214.9 | 7056 | REVIEW.SEMANTIC_RISK | SEMANTIC_RISK |
| 3110502 | Resultados del periodo | 1911908192.92 | 0.0 | 6214 | PATRIMONIO | NORMAL |
| 1130402 | Almacen Transitorio de Importaciones | 1751675209.92 | 60798.0 | 1028 | REVIEW.SEMANTIC_RISK | SEMANTIC_RISK |
| 1130401 | Mercadería en tránsito | 1748721252.66 | 3425390.62 | 707 | ACTIVO | NORMAL |
| 1130102 | Almacén Prod. a Granel Procesadora Saavedra | 1153160803.71 | 14362041.31 | 12000 | ACTIVO | NORMAL |
| 2110201 | Cuentas por pagar ME | 1057962781.06 | -1776237.66 | 1708 | PASIVO.PROVEEDORES | NORMAL |
| 1120101 | Cuentas por cobrar clientes MN | 924115817.3 | 3856456.82 | 3479323 | ACTIVO.CUENTAS_A_COBRAR | NORMAL |
| 4110101 | Ventas producto terminado | 897395497.37 | -71405264.97 | 1849353 | INGRESOS | NORMAL |
| 9110102 | Arrastre de Saldos - Cierre de Gestion | 820764555.98 | 0.0 | 3500 | UNRESOLVED | NORMAL |
| 1130101 | Almacén Materia Prima | 737900592.92 | 7839047.34 | 22354 | ACTIVO | NORMAL |
| 2110101 | Cuentas por pagar MN | 614452597.52 | -6240282.36 | 60195 | PASIVO.PROVEEDORES | NORMAL |
| 6110405 | Ajuste Inv. Litel | 526655977.65 | -1867.43 | 496 | REVIEW.SEMANTIC_RISK | SEMANTIC_RISK |
| 5110101 | Costos de ventas | 517749209.71 | 37391913.13 | 1851854 | COSTO_DE_VENTAS | NORMAL |
| 1110101 | Caja General Tesoreria MN | 371494868.02 | 86779.2 | 64173 | ACTIVO.CAJA | NORMAL |

## F. Control accounts y contrapartidas

La relación `Business Partner → control account → JDT1 → GL` queda preservada en las cuentas control y en el JSON; no se usa el saldo OACT como sustituto de deuda abierta.

| Cuenta | Nombre | Moneda | Saldo local |
|---|---|---|---:|
| 1120101 | Cuentas por cobrar clientes MN | BS | 3856481.82 |
| 1120201 | Cuentas por cobrar clientes ME | USD | 0.0 |
| 2110101 | Cuentas por pagar MN | BS | -6240282.36 |
| 2110201 | Cuentas por pagar ME | ## | -1776237.66 |

## G. Monedas, períodos y posting timing

Configuración observada: moneda principal `BS`, moneda sistema `USD`, multimoneda `B`. Se inspeccionan `Debit/Credit`, `SYSDeb/SYSCred`, `FCDebit/FCCredit`, `FCCurrency`, `OFPR`, `FinncPriod`, `CreateDate`, `RefDate` y `TaxDate`; el JSON contiene distribución por moneda, período y buckets de backdating.

## H. Retenciones — nuevas pistas

La consulta cruzó cuentas OACT por nombre/código, configuración OWHT, `JDT1.WTaxCode/WTSum/WTApplied` y memos. En la corrida actual `JDT1` tiene `WTaxCode` no nulo = 0, `WTSum` = 0 y `WTApplied` = 0; eso solo prueba que **no aparecen usando ese mecanismo estándar**.

Los 6/6 códigos OWHT apuntan a cuentas OACT existentes y esas cuentas tienen saldo corriente cero en la corrida. El GL sí encontró señales que justifican priorizar el siguiente gate: cuentas fiscales/impositivas con movimientos manuales (por ejemplo `2140103 IUE por pagar` y `2140102 IT por pagar`). `1130205 Almacén Retención` tiene movimientos de inventario (`TransType=60/67`) y por `GroupMask=1` se interpreta como almacén, no como pasivo WHT; es un falso positivo nominal que queda documentado. Todo esto es una pista, no una conclusión de retención contabilizada.

## I. Casos reales y evidencia

Se conservaron muestras completas de **21/21 TransTypes**, con header OJDT, líneas JDT1 y OACT; también muestras de asientos manuales común/alto importe/cierre/palabra clave cuando existen.

## J. Balance e invariantes

Balance por `TransId`: 5792286 balanceados, 0 fuera de tolerancia 0.01, diferencia máxima 0.0.

| Invariante | Resultado |
|---|---|
| GL01 OJDT.TransId único | {'ROWS': 5792286, 'DISTINCT_TRANSIDS': 5792286} |
| GL02 JDT1 sin OJDT | {'ORPHAN_LINES': 0} |
| GL03 JDT1.Account en OACT | {'ORPHAN_ACCOUNT_LINES': 0} |
| GL05 TransTypes observados | {'OBSERVED_TYPES': 21} |
| GL09 padres OACT inválidos | 0 |
| GL10 SAP_WRITE_COUNT | 0 |

## K. Vacíos semánticos

- `DataSource=O` separa un universo operativo de asientos tipo 30, pero no demuestra quién digitó cada asiento ni excluye procesos externos.
- Los tipos -2/-3 no tienen header operacional; su semántica queda STRONG por el tipo observado y el patrón, no por un documento.
- La ruta de retenciones queda abierta si las cuentas/memos no explican saldo, período, documento y reversa completos.
- AP/AR, bancos, depósitos, cash flow y estados financieros no se profundizan en este gate.

## L. Próximo gate

La evidencia actual prioriza `TELCHI_WITHHOLDING_TAX_ACCOUNTING_TRACEABILITY_V1`: hay cuentas fiscales y movimientos tipo 30 compatibles, mientras que el mecanismo estándar WHT permanece vacío. AP y tesorería siguen después; no se construyen todavía aging, cash flow ni política de retenciones.

## Artefactos

- JSON técnico: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/gl_trans_type_account_behavior/gl_trans_type_account_behavior_v1.json`
- Script reproducible: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/gl_trans_type_account_behavior/gl_trans_type_account_behavior_v1.py`
- SAP/HANA: SELECT-only; `SAP_WRITE_COUNT=0`.
