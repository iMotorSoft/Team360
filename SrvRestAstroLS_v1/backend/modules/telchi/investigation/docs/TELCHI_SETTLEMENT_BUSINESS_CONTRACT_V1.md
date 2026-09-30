# TELCHI_SETTLEMENT_BUSINESS_CONTRACT_V1

## Estado y alcance

- Entidad: `TELCHI`.
- Dominio: `COBRANZAS` con trazabilidad documental.
- Etapa: `INVESTIGATION`.
- Fuente: SAP Business One sobre HANA, `READ ONLY`.
- Foundation objetivo futuro: `foundation_417c860c216805f18341bb741ee026e3`.
- Resultado de este contrato: diseño aditivo; **no implementa ni publica settlement**.
- Gate relacionado: `TELCHI_SETTLEMENT_BUSINESS_CONTRACT_AND_SOURCE_DISCOVERY_V1_PASS`.

## 1. Objetivo de negocio

Preservar los hechos transaccionales que permitan reconstruir cómo y cuándo una obligación de
cliente fue cancelada: documentos, cobranzas, aplicaciones directas, medios y reconciliaciones.
`CONTADO` no es un campo fuente ni forma parte de la capa base; será una clasificación posterior,
versionada y aprobada por TELCHI.

El contrato mantiene separados:

1. **condición comercial**: `OINV.GroupNum → OCTG.GroupNum`, fecha de documento y vencimiento;
2. **pago/cobranza**: `ORCT` y sus medios;
3. **settlement**: aplicaciones `RCT2` y ledger de reconciliación `OITR/ITR1`.

## 2. Entidades, granularidades y claves

| Entidad | Grano | Clave canónica | Fuente principal |
|---|---|---|---|
| `settlement_document` | un documento comercial | `source_system + object_type + doc_entry` | `OINV` (13), `ORIN` (14) |
| `settlement_document_installment` | una cuota de documento | clave de documento + `installment_id` | `INV6` |
| `settlement_payment` | una cobranza | `source_system + object_type(24) + payment_doc_entry` | `ORCT.DocEntry` |
| `settlement_allocation` | una relación agregada pago-destino-cuota | `source_system + payment_doc_entry + target_object_type + target_doc_entry + installment_id + document_line` | `RCT2`, agrupado |
| `settlement_reconciliation` | una reconciliación | `source_system + reconciliation_id` | `OITR.ReconNum` |
| `settlement_reconciliation_member` | un miembro de reconciliación | clave de reconciliación + `line_sequence` | `ITR1.ReconNum + LineSeq` |
| `settlement_payment_method` | un componente de medio | clave de pago + `method_source + source_line_id` | `ORCT`, `RCT1`, `RCT3` |
| `payment_term` | una condición comercial | `source_system + payment_term_id` | `OCTG.GroupNum` |

`source_system + object_type + doc_entry` fue validada como identidad documental: no hubo duplicados
de `DocEntry` en `OINV`, `ORIN` ni `ORCT`; `object_type` evita colisiones entre familias. No se usa
`DocNum` como identidad técnica. Para reconciliaciones se requiere `ReconNum`, que no es `DocEntry`.

`RCT2` no tiene un identificador de línea y se observaron 92 filas indistinguibles bajo
`payment + target type + target + installment + document line` (1.839.000 filas frente a 1.838.908
claves). Para no fabricar una identidad inestable, la entidad canónica agrupa esa combinación,
preserva `source_row_count` y suma los importes. La relación y el monto total permanecen exactos.

## 3. Relaciones demostradas

- Aplicación directa: `RCT2.DocNum = ORCT.DocEntry`; se validaron 1.839.000/1.839.000 filas.
- Destino factura: `RCT2.InvType=13 AND RCT2.DocEntry=OINV.DocEntry`; 1.837.109/1.837.109.
- `RCT2.InvoiceId` **no** identifica la factura en esta instancia; no produjo vínculos a `OINV`.
- Reconciliación: `ITR1.ReconNum = OITR.ReconNum`.
- Miembro: `ITR1.SrcObjTyp + ITR1.SrcObjAbs` enlaza con la familia del objeto (13 factura, 14 NC,
  24 cobranza; otros tipos se preservan sin recodificarlos silenciosamente).
- Condición: `OINV.GroupNum = OCTG.GroupNum`; esto no prueba pago.
- Detalle de cheque/tarjeta: `RCT1.DocNum` y `RCT3.DocNum` enlazan con `ORCT.DocEntry`.

Se demostraron 14.759 pagos aplicados a varias facturas, 7.303 facturas con varios pagos y 3.076
reconciliaciones activas N:N. Una reconciliación N:N prueba sus miembros y el monto reconciliado de
cada miembro, pero no una asignación pairwise arbitraria entre cada débito y cada crédito.

## 4. Campos fuente mínimos

### Documento

`source_system`, `object_type`, `DocEntry`, `DocNum`, `CardCode`, `DocDate`, `DocDueDate`, `DocCur`,
`DocTotal`, `DocTotalFC`, `DocTotalSy`, `PaidToDate`, `PaidFC`, `PaidSys`, `GroupNum`, `CANCELED`,
`CancelDate`, `DocStatus`, `TransId`, `UpdateDate`, `UpdateTS`.

`credit_applied` no es un campo de cabecera defendible: se deriva de reconciliaciones con miembros
`SrcObjTyp=14` cuando la atribución sea inequívoca; en componentes N:N se conserva como no atribuido.

### Pago

`ORCT.DocEntry`, `DocNum`, `DocDate`, `TaxDate`, `DocDueDate`, `DocCurr`, `DocTotal`, `DocTotalFC`,
`DocTotalSy`, `Canceled`, `CancelDate`, `Status`, `TransId`, `CashSum`, `TrsfrSum`, `CheckSum`,
`CreditSum`, equivalentes FC/system, `PayNoDoc`, `NoDocSum`, `OpenBal`, `UpdateDate`, `UpdateTS`.

### Aplicación

`RCT2.DocNum` (pago), `InvType`, `DocEntry` (destino), `InstId`, `DocLine`, `SumApplied`, `AppliedFC`,
`AppliedSys`, `DocRate`, `LinkDate`, descuentos, retenciones, diferencias y `source_row_count`.

### Medio

- efectivo: componente de cabecera `ORCT.CashSum`;
- transferencia: `ORCT.TrsfrSum`, fecha y referencia, sin exponer datos bancarios sensibles;
- cheque: una fila por `RCT1.LineID`, importe/moneda y fechas; referencias sensibles protegidas;
- tarjeta: una fila por `RCT3.LineID`, importe/moneda/tipo; nunca publicar PAN o datos de titular;
- `RCT4`: aplicación del pago a cuentas contables, no “otro medio de pago”. Se conserva como destino
  contable separado.

No se aplana un pago mixto a un único medio. Se observaron 12.623 pagos con más de un componente.

### Reconciliación

`OITR.ReconNum`, `ReconDate`, `Total`, `ReconCurr`, `Canceled`, `CancelAbs`, `IsSystem`, `ReconType`,
`InitObjTyp`, `InitObjAbs`, `CreateDate/Time`, `CreateTS`, `UpdateTS`; y por miembro:
`ITR1.LineSeq`, `SrcObjTyp`, `SrcObjAbs`, `TransId`, `TransRowId`, `InstID`, `IsCredit`, `ReconSum`,
`ReconSumFC`, `ReconSumSC`, `FrgnCurr`, `CashDisSum`, retenciones y gastos.

## 5. Reglas monetarias y moneda

1. Guardar sin conversión los tres importes SAP cuando existan: moneda local, extranjera y sistema.
2. Guardar los códigos `DocCur/DocCurr`, `ReconCurr` y `FrgnCurr`; nunca sumar monedas nominales
   distintas.
3. Para BS, comparar importes locales. Para documentos en moneda extranjera, comparar el eje FC del
   documento con `AppliedFC/ReconSumFC`; el eje system sirve como control, no como sustituto.
4. Tolerancia base: `0,01` unidad monetaria por documento y eje. Si la moneda define otra escala,
   usar `max(0,01, 10^-decimal_places)` y versionar la regla.
5. Los componentes de medio conciliaron con `ORCT.DocTotal` dentro de Bs 0,01 en 1.825.024 de
   1.825.031 pagos activos. Las siete diferencias deben conservar descuentos, retenciones,
   `UndOvDiff` y destinos contables; no se deben forzar.
6. La ecuación de control es por moneda y documento:

```text
obligation_amount
≈ effective_reconciled_amount + remaining_open_amount
```

`effective_reconciled_amount` es el total de los miembros del propio documento, no la suma de todos
los contrapartes del `ReconNum`. El desglose por efectivo/NC/asiento solo es exacto cuando la relación
es directa o inequívoca. Descuentos, retenciones, gastos, diferencias y anticipos se conservan como
componentes explícitos antes de exigir igualdad.

## 6. Cancelaciones y estados

- Los documentos y pagos cancelados se preservan con su flag y fecha, pero no aportan a settlement
  vigente.
- Estado vigente de reconciliación: solo `OITR.Canceled='N'`.
- SAP conserva pares: reconciliación original `Y` y reversa `C`, unidas por `CancelAbs`. Se observaron
  15.450 pares; 500 reversiones ocurrieron en fecha posterior, hasta 1.490 días después.
- Para histórico as-of a nivel fecha, una reconciliación original aplica desde `ReconDate` hasta antes
  de la `ReconDate` de su pareja reversa. En la fecha de reversión, el contrato usa cierre de día.
  No es posible reconstruir estados intradía cuando origen y reversa comparten fecha.
- Nunca borrar ni mutar el evento original durante ingesta; publicar estado efectivo derivado.

## 7. Notas de crédito, reconciliaciones y multiplicidad

Una nota de crédito (`ORIN`, objeto 14) no es un pago. Su efecto económico se prueba como miembro de
una reconciliación. El caso real `ReconNum=2654224` contiene NC 21527 e invoice 11533926 por Bs 1.915
cada una.

`RCT2` preserva aplicaciones directas de pagos. `OITR/ITR1` es el ledger autoritativo del settlement,
incluidos pagos a cuenta aplicados después, NC, asientos y reconciliaciones manuales. No sumar RCT2 e
ITR1 como dos cancelaciones: RCT2 aporta lineage payment→target y OITR/ITR1 aporta el efecto de
settlement. En N:N se publican miembros, no pares inventados.

## 8. Open balance y semántica as-of

### Saldo actual

`current_open_amount = document_amount - current_paid_to_date`, por eje monetario, controlado además
contra cuotas `INV6`. En esta instancia `OINV` tenía 1.854.288 facturas activas saldadas, 45 parciales,
1.968 impagas y 2.230 canceladas.

### Saldo histórico

```text
open_amount_as_of(D, t) = obligation_as_of(D, t)
                         - sum(effective_document_member_amount(D, recon_date <= t))
```

La función temporal debe aplicar reversas por `CancelAbs`, excluir documentos/pagos cancelados según
su fecha efectiva y conservar cuotas (`InstID`). Es reconstruible a cierre de día desde el inicio de
cobertura observado (2022-03-31). Antes de esa fecha, o intradía, es `NOT_DETERMINABLE`. `PaidToDate`
solo responde estado actual y no reemplaza el ledger histórico.

## 9. Hechos derivados

Para documento activo y una moneda/eje homogéneo:

- `total_allocated_amount`: suma de aplicaciones `RCT2` activas agrupadas; es lineage directo, no se
  suma nuevamente al reconciliado.
- `effective_reconciled_amount(t)`: suma de `ITR1.ReconSum` de los miembros del documento efectivos a
  `t`.
- `total_credit_applied`: suma atribuible a miembros tipo 14 solo en componentes 1:1 o con enlace
  directo demostrado; en N:N usar `NULL` + `UNATTRIBUTED_N_TO_N`, manteniendo total settlement exacto.
- `remaining_open_amount(t) = max(0, obligation - effective_reconciled_amount(t))` dentro de tolerancia.
- `first_payment_date`: mínima `ORCT.DocDate` de pagos directos o pagos contraparte inequívocos.
- `last_payment_date`: máxima fecha equivalente.
- `fully_settled_date`: primera fecha de evento en la que el saldo acumulado queda `<= tolerance` y no
  es deshecho por una reversa posterior antes del as-of consultado.
- `settlement_latency_days = fully_settled_date - document_date`.
- `paid_same_calendar_day`: existe pago activo con fecha igual a `document_date`, aun si queda saldo.
- `fully_settled_same_calendar_day`: `fully_settled_date = document_date`.
- `partially_paid`: settlement efectivo `> tolerance` y saldo `> tolerance`.
- `unpaid`: settlement efectivo `<= tolerance` y saldo `> tolerance`.
- `overpaid`: settlement efectivo excede obligación por más de tolerancia; separar crédito a cuenta
  antes de afirmarlo.
- `number_of_payments`: pagos distintos vinculados directamente o inequívocamente.
- `number_of_payment_methods`: componentes positivos distintos del pago; no atribuir un medio a cada
  factura cuando un pago mixto cancela varias.

Toda derivación incluye `as_of_date`, `calculation_version`, `monetary_axis`, `quality_status` y las
claves fuente usadas.

## 10. Definiciones observables de CONTADO

| Variante | Regla observable | Qué significa |
|---|---|---|
| `CASH_TERM` | término `OCTG` aprobado como contado | acuerdo comercial, no pago efectivo |
| `SAME_DAY_PAYMENT` | existe pago el día del documento | hubo cobro, aunque puede quedar saldo |
| `SAME_DAY_FULLY_SETTLED` | saldo llega a tolerancia el mismo día | obligación cancelada ese día |
| `IMMEDIATE_SETTLEMENT(N)` | cancelación total dentro de N días | ventana que TELCHI debe aprobar |
| `EVENTUALLY_PAID` | cancelación total al as-of | no implica contado |

**Decisión requerida de TELCHI:** elegir A) término configurado como contado; B) cancelación completa
el mismo día; C) cancelación completa dentro de `N` días e indicar `N`; o D) otra regla escrita. La
ingeniería no elegirá silenciosamente.

## 11. Provenance y relación con Foundation

El futuro componente es aditivo. Consumirá las identidades de `sales_document` y
`credit_memo_document` de CURRENT y publicará entidades settlement separadas. No modifica ni
reinterpreta `sales`, `credit_memo`, `reference`, `oinm`, `oitw` ni `material_supply`; tampoco depende
de UoM.

Cada fila debe incluir `source_system=SAP_HANA`, tabla, clave nativa serializada, fecha de extracción,
snapshot/run id, versión de transformación, versión semántica y calidad de lineage. PostgreSQL de
publicación y manifests decidirán qué versión es visible; SAP sigue siendo fuente READ ONLY.

## 12. Limitaciones conocidas

- No existe identidad física de línea en `RCT2`; se usa relación agregada con multiplicidad fuente.
- Una reconciliación N:N no prueba reparto pairwise entre todos sus miembros.
- Un pago mixto no distribuye sus medios por factura.
- El estado intradía y el histórico anterior a 2022-03-31 no son reconstruibles con estas fuentes.
- Los siete pagos con diferencia medio-total requieren conservar componentes de ajuste.
- Campos bancarios, tarjeta, nombres y datos fiscales requieren minimización y control de acceso.
- La Foundation aún no contiene este componente. PASS del gate significa “sabemos qué construir”, no
  “settlement está productivo”.
