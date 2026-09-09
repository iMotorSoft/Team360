# TELCHI — INVESTIGACIÓN CONTABLE Y FINANCIERA PROFUNDA V1

**Estado:** `FOUNDATION_INITIAL_STRUCTURE_DISCOVERY` — investigación abierta
**Fecha de esta ejecución:** 2026-09-08 18:36 UTC
**Entidad / dominio / etapa:** `TELCHI / CONTABILIDAD / INVESTIGATION`
**Fuente:** SAP Business One sobre HANA, schema `TELCHI`, database `NDB`
**Evidencia:** `validation/financial_foundation/structure_discovery_v1.json`

> Este documento registra la primera ejecución solicitada. No cierra todavía
> `TELCHI_FINANCIAL_ACCOUNTING_FOUNDATION_V1_PASS` y no presenta una foto
> financiera final. Las cifras de distintas monedas no se suman sin conversión
> explícita.

## A. VEREDICTO EJECUTIVO

La estructura contable real ya es observable y trazable: `OJDT` contiene
5.789.775 asientos, `JDT1` 18.242.546 líneas y `OACT` 824 cuentas. El período
contable observado va de 2022-03-31 a 2026-09-08.

El primer mapa confirma, con datos Telchi, el enlace documental principal:

```text
OINV / ORIN / OPCH / ORCT / OVPM
        ↓ TransId
OJDT
        ↓ TransId
JDT1
        ↓ Account
OACT
```

La cobertura `header.TransId → OJDT.TransId` es 100% para facturas clientes,
notas de crédito, facturas proveedor, cobros, pagos efectuados, entregas,
devoluciones, transferencias y órdenes de producción con `TransId`. Es parcial
únicamente en documentos operativos que no generan asiento en todos los casos:
`OIGN` y `OIGE`.

**Aún no demostrado:** AP abierto por proveedor, aging AP, ciclo transaccional
de retenciones, cobro→depósito, conciliación bancaria, cancelación/reversa
completa de cada objeto y foto líquida multi-moneda.

## B. ARQUITECTURA CONTABLE REAL

### B.1 Libro Mayor

| Objeto | Filas | Fecha mínima | Fecha máxima | Evidencia |
|---|---:|---|---|---|
| `OJDT` | 5.789.751 | 2022-03-31 | 2026-09-08 | PROVEN |
| `JDT1` | 18.242.473 | 2022-03-31 | 2026-09-08 | PROVEN |
| `OACT` | 824 | — | — | PROVEN |

Se observaron 21 `TransType`. Los principales son: `13` factura cliente,
`24` cobro, `30` asiento/journal entry, `67` transferencia, `15` entrega,
`46` pago efectuado, `60` salida de inventario, `18` factura proveedor, `59`
entrada de inventario, `321` reconciliación interna, `202` producción, `20`
recepción de mercadería, `25` depósito, `14` nota de crédito cliente y `19`
nota de crédito proveedor. El catálogo final de tipos todavía requiere cerrar
los tipos `-2`, `-3`, `69`, `162` y `21` contra objetos reales.

### B.2 Mapa documental validado

| `TransType` | Tabla | Headers | Con `TransId` | Match OJDT | Estado |
|---:|---|---:|---:|---:|---|
| 13 | `OINV` | 1.836.473 | 1.836.473 | 1.836.473 | PASS |
| 14 | `ORIN` | 10.708 | 10.708 | 10.708 | PASS |
| 15 | `ODLN` | 93.530 | 93.173 | 93.173 | PASS |
| 16 | `ORDN` | 555 | 500 | 500 | PASS con headers sin asiento |
| 18 | `OPCH` | 32.491 | 32.491 | 32.491 | PASS |
| 19 | `ORPC` | 4.077 | 4.077 | 4.077 | PASS |
| 20 | `OPDN` | 19.857 | 17.031 | 17.031 | PASS con headers sin asiento |
| 21 | `ORPD` | 3.921 | 3.920 | 3.920 | PASS con header sin asiento |
| 24 | `ORCT` | 1.814.326 | 1.814.326 | 1.814.326 | PASS |
| 25 | `ODPS` | 14.789 | — | — | `TransAbs` probado, no `TransId` |
| 46 | `OVPM` | 41.563 | 41.563 | 41.563 | PASS |
| 59 | `OIGN` | 27.354 | 27.354 | 27.344 | PARTIAL |
| 60 | `OIGE` | 49.638 | 33.226 | 33.225 | PARTIAL |
| 67 | `OWTR` | 190.678 | 190.678 | 190.678 | PASS |
| 69 | `OIPF` | — | — | — | Sin `TransId`; relación pendiente |
| 162 | `OMRV` | 115 | 96 | 96 | PASS con headers sin asiento |
| 202 | `OWOR` | 20.951 | 20.178 | 20.178 | PASS con órdenes sin asiento |
| 321 | `OITR` | 2.094.359 | — | — | `ReconJEId` pendiente de probar |

La relación `DocEntry → TransId` no sustituye a la relación `TransId → JDT1`:
ambas deben conservarse. `JDT1` mantiene `Account`, `ShortName`, `ContraAct`,
`Debit`, `Credit`, `RefDate`, `DueDate`, `TaxDate`, `TransType`, `DocEntry`,
`DocNum`, `ProfitCode`, `OcrCode2..5`, `BPLId`, `WTaxCode` y campos de
conciliación.

### B.3 Caso real de trazabilidad

Caso seleccionado en febrero de 2023:

```text
ORCT DocEntry 404283 / DocNum 23027511 / Bs 205.500
  → ORCT.TransId 3819007
  → OITR.ReconNum 451463
  → ITR1: SrcObjTyp=24, SrcObjAbs=404283, ReconSum=205.500
  → 10 facturas cliente del mismo BP, entre ellas OINV DocEntry 2459307
  → OINV.TransId 3273073
  → JDT1: débito 1120101 Bs 402,97 / crédito 4110101 Bs 402,97
  → pago JDT1: débito 1111002 Bs 205.500 / crédito 1120101 Bs 205.500
  → OACT: 1120101 CxC clientes; 1111002 banco
```

El caso demuestra que un cobro puede aplicarse N:N a múltiples facturas. No se
debe atribuir el `DocTotal` completo del cobro a una sola factura.

## C. PLAN DE CUENTAS

`OACT` tiene 824 cuentas: 300 de activo (`GroupMask=1`), 77 de pasivo (`2`),
19 de patrimonio (`3`), 24 de ingresos (`4`), 15 de costo (`5`) y 380 de
gastos/resultado (`6`), además de grupos 7–10 sin saldo corriente relevante.
La clasificación por grupo es un mapa inicial; la clasificación económica
final se hará por comportamiento `JDT1`, no solo por nombre.

### C.1 Familias observadas

| Familia | Cuentas / comportamiento real | Estado |
|---|---|---|
| Caja tesorería, salones, laboratorio, distribuidores y caja chica | familias `11101xx`–`11107xx`; naming operativo por ubicación | STRONG |
| Bancos | `11110xx` y `1111201`; el master `ODSC` existe pero varios `DfltAcct` están vacíos | PARTIAL |
| CxC clientes | `1120101` MN y `1120201` ME; `1120101` muestra saldo corriente 3.874.854,23 | STRONG |
| Documentos por cobrar | `1120302` tarjetas, `1120303` cheques, `1120304` garantías | STRONG |
| Anticipos proveedores | `1121301/02`, `1121401/02` | STRONG |
| IVA crédito / otros créditos fiscales | `1121501` | STRONG |
| Inventarios y tránsito | familias `11301xx`–`11304xx` | STRONG |
| CxP proveedores | `2110101` MN, `2110201` ME, `211040x` otras CxP | STRONG |
| Anticipos clientes | `2110301` y padre `2110300` | STRONG |
| Impuestos por pagar | `2140101` débito IVA, `2140102` IT, `2140103` IUE | STRONG |
| Retenciones configuradas | `2140105`–`2140109` | PROVEN en configuración; saldo/lifecycle UNRESOLVED |
| Préstamos bancarios | `2210101` | STRONG |
| Ventas / costo / gastos | `4110101`, `5110101`, familias `60xxxx`/`63xxxx` | STRONG |
| Puentes y diferencias | `1120301` transferencias/QR por confirmar, `2110404` depósitos en tránsito, `6020302` sobrante/faltante | PARTIAL |

### C.2 Saldos relevantes observados

Los siguientes son `OACT.CurrTotal`, no una suma consolidada multi-moneda:

- bancos MN/mixtos en `FatherNum=1111000`: 4.620.795,78;
- banco ME `1111201`: 69.693,24 USD según `ActCurr`;
- caja general MN `1110100`: 175.122,10;
- cajas de salones MN `1110200`: 95.762,41;
- cajas de laboratorio/distribuidores MN `1110300`: 101.668,52;
- caja chica `1110700`: 41.446,86;
- documentos por cobrar `1120300`: 231.805,17;
- CxP MN `2110100`: -6.373.649,03;
- CxP ME `2110200`: -1.776.237,66;
- anticipos clientes: 180.333,25;
- IVA débito: -12.996.404,08;
- IVA crédito: 4.401.382,62;
- IT por pagar: -3.639.915,58;
- IUE por pagar: 636.985,00.

Estos importes son señales para el siguiente análisis, no una posición
financiera final. `OADM` confirma moneda principal `BS`, moneda del sistema
`USD` y multimoneda activa (`MultiCurr=B`).

## D. CUENTAS POR COBRAR

La semántica AR previa ya cerró para el baseline 2026-08-21:
`OINV.DocTotal - SUM(ITR1.ReconSum)` con reconciliaciones activas y control
`PaidToDate`, 1.861 facturas abiertas, Bs 3.847.327,43 outstanding, Bs
1.488.957,22 vencido y 344 clientes con deuda.

La primera ejecución contable agrega la prueba de que la cuenta control
`1120101` aparece en `JDT1` como débito de la factura y como crédito al aplicar
cobros. El AR sigue siendo **STOCK AS_OF_DATE**; no se reemplazará por el saldo
bruto de cobros.

**Estado:** PASS para el gate AR previo; integración AR→GL PASS estructural.

## E. CUENTAS POR PAGAR

La cadena documental de compras ya está validada hasta `OPCH`; esta ejecución
confirma `OPCH.TransId → OJDT → JDT1` en 100% de los headers con `TransId`.
También se confirma que `VPM2.DocNum = OVPM.DocEntry`, `VPM2.InvType='18'`
para aplicaciones a facturas proveedor: 24.923 filas, 15.106 pagos y 23.481
facturas relacionadas en el universo observado.

El cálculo **deuda AP abierta por proveedor y aging** aún no está cerrado. No
se debe usar `OACT.2110101 + 2110201` como sustituto: esas son cuentas de
control contable y pueden incluir movimientos, moneda, anticipos, ajustes y
otras CxP.

**Estado:** PARTIAL.

## F. RETENCIONES

La metadata confirmó el mecanismo estándar utilizado/configurado en esta
instalación:

- `OWHT`, `WHT1`, `WHT2`, `WHT3`, `AWHT` existen;
- hay 6 códigos activos (`01`–`06`);
- cuentas configuradas: `2140108` IT, `2140105` IUE bienes, `2140106` IUE
  servicios, `2140109` remesas, `2140107` RC-IVA servicios/dependientes;
- porcentajes configurados: 30, 50, 125, 125, 130 y 130, con base 10%.

Las tablas transaccionales estándar consultadas no muestran retención no nula
en la primera foto: `OPCH.WTSum=0`, `OVPM.WtSum=0`, `PCH5` no tiene filas no
nulas, `PCH6` no tiene WHT no nulo y `VPM6` no tiene filas. Las cuentas
`2140105`–`2140109` muestran saldo corriente cero.

Esto **no demuestra que nunca hubo retenciones** ni que no existan asientos
manuales/custom. Deben revisarse `JDT1.WTaxCode/WTSum`, UDF, `TAX1` y períodos
antes de responder acumulados o meses mezclados.

**Estado:** DEGRADED / UNRESOLVED para lifecycle; configuración PROVEN.

## G. CAJA

La semántica de caja contable está validada en el gate H4 previo:
`ORCT.CashAcct → JDT1.Account`, con el débito de caja igual a `ORCT.CashSum`
en la muestra 2023-02. `OACT.CashBox='N'` no identifica por sí solo una caja
física en Telchi; el grupo de cuenta y el nombre son la evidencia operativa.

El saldo contable no equivale automáticamente a efectivo físico, dinero aún no
depositado o arqueo. La separación requerida es:

```text
saldo OACT → cobro registrado → efectivo esperado → depósito → banco
                         ↘ diferencias / ajustes
```

**Estado:** PASS para asiento de cobro; arqueo físico y depósito pendiente aún
requieren estudio específico.

## H. BANCOS

`ODSC` existe con códigos de bancos y `OACT` contiene cuentas bancarias por
entidad/cuenta. Los pagos registran cuenta explícita en `CashAcct`,
`CheckAcct` y `TrsfrAcct`. Se observan cuentas BMSC, Banco Unión, FIE, BNB,
Ganadero, SAFI, Bank of America y Helm Bank, entre otras.

El banco destino del depósito aparece en `ODPS.DpsBank`, junto a
`DeposAcct`, `BanckAcct` y `TransAbs`. La configuración del master es
incompleta para una respuesta bancaria automática porque varios `ODSC.DfltAcct`
están vacíos y existen cuentas con `ActCurr='##'`.

**Estado:** PARTIAL; falta conciliación bancaria/extractos y cierre de moneda.

## I. DEPÓSITOS

`ODPS` existe con 14.789 filas y `DPS1` con 211.849 relaciones a cheques.
`ODPS.TransAbs → OJDT.TransId` tiene 100% de match en la foto.

La primera muestra real es `ODPS.DeposId=17786`, `DeposType=V`, fecha
2026-09-07, banco `BMSC`, cuenta bancaria `1111001`, importe documental
Bs 54.779,02, `TransAbs=16331692`; su asiento tiene movimientos entre
`1120302` (tarjetas) y `1111001` (banco). El texto del asiento referencia ventas
de 04/09–06/09, por lo que el depósito agrupa movimientos y no es una fila
simple cobro→depósito.

El tiempo cobro→depósito, depósitos tardíos, depósitos no relacionados y
tránsito por sucursal todavía no están medidos.

**Estado:** PASS para depósito→OJDT; DEGRADED para cobro→depósito.

## J. PAGOS

### Incoming payments (`ORCT`)

- activos: 1.803.469 documentos, `DocTotal` Bs 504.459.616,58;
- cancelados: 10.848 documentos, Bs 14.853.621,58;
- componentes activos: efectivo Bs 260.398.493,59; cheques Bs 15.437.570,92;
  transferencias Bs 201.954.008,45; tarjetas Bs 26.669.492,13;
- `RCT2` tiene 1.817.186 filas: la mayoría tiene `InvoiceId=0`; la aplicación
  financiera confiable es `OITR/ITR1`.

### Outgoing payments (`OVPM`)

- activos: 40.229 documentos, `DocTotal` Bs 716.365.637,53;
- cancelados: 1.333 documentos, Bs 32.761.561,53;
- aplicaciones a OPCH por `VPM2`: 24.923 filas en 15.106 pagos;
- muestra real: pago `OVPM.DocEntry=50029`, Bs 1.004.444,44 por transferencia,
  aplicado a tres facturas proveedor; el pago se refleja en `JDT1` como crédito
  banco `1111006` y débito CxP `2110101`.

Los agregados deben mantenerse separados por moneda y por documento válido.

## K. RECONCILIACIONES

`OITR` tiene 2.094.359 filas y `ITR1` 4.479.564. La clave física es
`OITR.ReconNum`; la clave de detalle es `ITR1.ReconNum + LineSeq`.

La muestra `ReconNum=451463` demuestra composición N:N: diez líneas de
facturas cliente (`SrcObjTyp=13`) y una línea de cobro (`SrcObjTyp=24`), todas
para `C003457`. El saldo se cancela por `ReconSum`, no por atribución del
importe total del pago a una sola factura.

La cancelación de reconciliaciones, reconciliación parcial/manual/automática y
su fecha as-of deben continuar con `CancelAbs`, `Canceled`, `ReconType`,
`IsSystem`, `UserSign` e `InitObjTyp`.

**Estado:** PASS en grano y composición previamente validada; lifecycle
completo de reversa aún en curso.

## L. CANCELACIONES Y REVERSAS

La evidencia estructural muestra `StornoToTr` en `OJDT` para 10.848 cobros,
1.333 pagos, 2.122 asientos tipo 30 y 644 reconciliaciones tipo 321, entre
otros. Los objetos y su reversa no deben excluirse sin conservar el evento.

El H4 previo probó reversa de cobro con crédito de la caja y `NET=0` en 112/112
casos. Para cerrar V1 falta completar la matriz por `OINV`, `ORIN`, `OPCH`,
`ORPC`, `ORCT`, `OVPM`, `ODPS`, `OITR` y asientos manuales, incluyendo fecha
original, fecha reversa y vínculo exacto.

**Estado:** PARTIAL; caja/cobro confirmado, matriz general pendiente.

## M. ASIENTOS MANUALES

`TransType=30` tiene 1.604.651 asientos y `CreatedBy=TransId` en 100% de esa
clase. Sin embargo, `UserSign`, memo vacío o `DataSource` no bastan para
calificar cada asiento como manual operativo, automático o regularización.

Se observan dos comportamientos: `DataSource='O'` con predominio de usuario
156 y muchos memos vacíos, y `DataSource='I'` repartido entre usuarios. El
usuario 156 concentra 1.388.029 asientos tipo 30. Esto es una señal P1 de
revisión semántica, no una conclusión de error.

Próximo análisis: agrupar por cuentas, `RefDate`, `TransCode`, `Memo`,
`CreatedBy`, `UserSign`, `AutoStorno`, `StornoToTr`, `BPLId`, proyecto y
contrapartida; separar cierres, arrastres, revaluaciones, importaciones y
ajustes.

**Estado:** PARTIAL.

## N. IMPUESTOS

La cartografía inicial confirma:

- IVA débito: `2140101`;
- IVA crédito: `1121501`;
- IT: `2140102`;
- IUE: `2140103`;
- retenciones: `2140105`–`2140109`;
- `TAX1` tiene 4.520.995 filas y conserva base, porcentaje, cuenta fiscal,
  documento base y valores de IVA;
- `OTAX` tiene 1.883.731 filas de relación tributaria.

La primera ejecución localiza cuentas y tablas, pero no cierra declaración,
pago, cierre fiscal ni período tributario.

**Estado:** PARTIAL.

## O. COMPRAS × FINANZAS

La cadena real demostrada hasta ahora es:

```text
OPOR → OPCH → OPDN
         ↓
       OJDT/JDT1
         ↓
       deuda AP
         ↓
       OVPM/VPM2
         ↓
       OJDT/JDT1 banco/caja
```

En Telchi el flujo documental observado es frecuentemente invoice-first
(`OPOR → OPCH → OPDN`), por lo que recepción, factura, reconocimiento de
inventario/gasto, IVA crédito, retención y salida de dinero no deben colapsarse
en una única fecha.

**Estado:** PASS estructural de documento→GL; deuda, retención y cash timing
PARTIAL.

## P. FOTO FINANCIERA ACTUAL

No se publica una foto consolidada en esta primera ejecución. La razón es
metodológica: `OACT.CurrTotal` contiene cuentas en BS, USD y `##`, y no se ha
cerrado aún la semántica de saldo corriente, moneda de cuenta, períodos,
retenciones, AP abierto y depósitos en tránsito.

Se conservan como insumos auditados:

- AR baseline 2026-08-21: Bs 3.847.327,43, previamente reconciliado;
- cuentas contables de caja/banco/CxC/CxP/impuestos identificadas;
- depósitos con enlace `ODPS.TransAbs → OJDT.TransId`;
- cuentas de retención configuradas y saldo corriente observado cero.

**Estado:** NOT READY.

## Q. ANOMALÍAS / RIESGOS

### Prioridad alta

1. `TransType=30` y usuario 156 concentran 1.388.029 asientos; requiere
   clasificación antes de interpretar como actividad manual.
2. Cuentas `ActCurr='##'` y moneda principal BS / sistema USD impiden sumar
   `CurrTotal` sin normalización.
3. Cuentas de CxP de control no equivalen todavía a deuda AP abierta por
   proveedor.
4. Retenciones configuradas, pero sin movimiento estándar no nulo en las
   tablas transaccionales consultadas; investigar custom/JDT1 antes de concluir
   que no existe pasivo histórico.

### Prioridad media

1. `OIGN`/`OIGE` presentan headers sin `TransId` o con match incompleto.
2. `ODSC` tiene configuración bancaria incompleta (`DfltAcct` vacío en varios
   códigos).
3. Depósitos agrupan múltiples medios/documentos; falta tiempo cobro→depósito.
4. `1120301` y `2110404` son cuentas puente candidatas, pero no se califican
   como anomalía hasta reconciliar su lifecycle.

### Prioridad baja

1. cuentas válidas/frozen y cuentas con saldo cero requieren separar catálogo
   histórico de uso operativo;
2. `OACT.CashBox='N'` no debe utilizarse como filtro de cajas físicas.

Clasificación actual: `REVIEW`, `SEMÁNTICA NO RESUELTA` y `CONTROL DÉBIL`
donde corresponde; no se infiere fraude.

## R. VACÍOS DE INFORMACIÓN

- AP open/aging por proveedor y fecha as-of;
- retención por documento, base, período, pago y asiento de cancelación;
- extracto bancario y conciliación externa;
- caja física, arqueo y diferencias por cierre;
- vínculo completo venta/cobro individual→depósito;
- cheques recibidos/emitidos, cartera, rechazo y disponibilidad real;
- pagos a cuenta y anticipos aplicados con semántica completa;
- períodos abiertos/cerrados y documentos fuera de período;
- diferencias de cambio realizadas/no realizadas;
- atribución confiable a sucursal/Business Place/BPL para cada familia;
- matriz general de cancelación/reversa por objeto;
- clasificación final de `TransType` no documentados y asientos tipo 30.

## S. FUTURO MODELO FINANCIERO TEAM360

La base permite construir posteriormente datasets separados por nivel:

- **Operativo:** documento, recepción, entrega, cobro, pago, depósito y
  movimiento físico;
- **Financiero:** AR/AP abierto, settlement, instrumentos, bancos, caja,
  anticipos, valores y tránsito;
- **Contable:** `OJDT`, `JDT1`, `OACT`, impuesto, cuenta, moneda, período y
  centro/proyecto.

El lineage mínimo futuro será:

```text
documento.DocEntry
 → documento.TransId
 → OJDT.TransId
 → JDT1.Line_ID / Account
 → OACT.AcctCode
 → reconciliación / pago / depósito
 → saldo as-of y moneda explícita
```

Antes de crear Data Lake definitivo deben cerrarse los contratos AP, WHT,
tesorería, depósitos, monedas, períodos, cancelaciones y dimensiones.

## T. PRÓXIMO GATE

El siguiente análisis concreto es:

**`TELCHI_GL_TRANS_TYPE_ACCOUNT_BEHAVIOR_V1`**

Alcance:

1. cerrar los 21 `TransType` contra objetos reales;
2. separar asiento automático, manual, cierre, arrastre, revaluación y ajuste;
3. reconstruir árbol `OACT` y comportamiento `JDT1` por cuenta;
4. validar `CurrTotal`, `SysTotal`, `EndTotal`, moneda y períodos;
5. seleccionar tres trazas completas adicionales: venta/cobro, compra/pago y
   depósito;
6. preservar `SAP_WRITE_COUNT=0`.

Después de ese gate, continuar en este orden: **AP abierto → retenciones →
transacciones de tesorería/depósitos → bancos/conciliación → foto financiera**.

### Estado del gate amplio solicitado

| Componente | Estado inicial |
|---|---|
| GL / Libro Mayor | PASS estructural |
| Plan de cuentas | PASS inicial / comportamiento pendiente |
| AR / Clientes | PASS previo + GL integrado |
| AP / Proveedores | PARTIAL |
| Incoming Payments | PASS estructural |
| Outgoing Payments | PASS estructural |
| Internal Reconciliation | PASS estructural |
| Cancelaciones/Reversas | PARTIAL |
| Caja | PASS contable / físico DEGRADED |
| Bancos | PARTIAL |
| Depósitos | PASS→OJDT / cobro→depósito DEGRADED |
| Retenciones | DEGRADED |
| Compras→Deuda→Pago | PARTIAL |
| Documento→OJDT→JDT1→OACT | PASS para objetos principales |
| `SAP_WRITE_COUNT` | **0** |

**Conclusión:** no declarar `TELCHI_FINANCIAL_ACCOUNTING_FOUNDATION_V1_PASS`.
La investigación queda correctamente abierta con el primer mapa contable real.
