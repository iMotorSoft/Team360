# TELCHI — WITHHOLDING TAX ACCOUNTING TRACEABILITY V1

**Gate:** `TELCHI_WITHHOLDING_TAX_ACCOUNTING_TRACEABILITY_V1_DEGRADED`
**Modo:** INVESTIGATION / READ ONLY / `SAP_WRITE_COUNT=0`
**Evidencia:** 2026-09-09T12:30:50.301717+00:00

## A. VEREDICTO EJECUTIVO

Telchi tiene configuración OWHT, pero el mecanismo transaccional estándar observado permanece sin importes. La cuenta real de retención de proveedor **no queda demostrada**: las cuentas configuradas no presentan movimiento y las cuentas `2140102`/`2140103` se comportan como IT/IUE, no como retenciones de proveedor.

Resultado del gate: **DEGRADED**. La investigación separa configuración, cálculo WHT estándar, pasivo fiscal general y pagos/regularizaciones. No se etiqueta como retención ningún diferencial de AP sin evidencia documental.

## B. CONFIGURACIÓN WHT SAP

| WtCode | Descripción | Rate | Base % | Cuenta | Inactivo |
|---|---|---:|---:|---|---|
| 01 | IT Retención | 30.0 | 10.0 | 2140108 | N |
| 02 | IUE Bienes | 50.0 | 10.0 | 2140105 | N |
| 03 | IUE Servicios | 125.0 | 10.0 | 2140106 | N |
| 04 | Remesas al Ext. | 125.0 | 10.0 | 2140109 | N |
| 05 | RC IVA Servicios | 130.0 | 10.0 | 2140107 | N |
| 06 | RC IVA Dependientes | 130.0 | 10.0 | 2140107 | N |

## C. USO REAL DEL WHT ESTÁNDAR

Conclusión cuantificada: `STANDARD_WHT_TRANSACTIONAL_PATH_UNUSED_OR_NON_MATERIAL`. `PCH5`, `PCH6`, `VPM6`, `VPM2`, cabeceras `OPCH`/`OVPM` y campos WHT de `JDT1` fueron medidos; el detalle completo está en el JSON.

## D. CUENTAS FISCALES

OACT contiene 824 cuentas; 63 entraron al universo fiscal por nombre, código, jerarquía o configuración OWHT.

| Cuenta | Nombre | Clasificación | Líneas | Débito | Crédito | Neto | Primera → última fecha |
|---|---|---|---:|---:|---:|---:|---|
| 1121500 | CUENTAS FISCALES | OTHER_FISCAL | 0 | 0 | 0 | 0 | None → None |
| 1121501 | Crédito Fiscal IVA | TAX_RECEIVABLE | 40126 | 40050767.18 | 35633741.73 | 4417025.45 | 2022-03-31T00:00:00 → 2026-09-08T00:00:00 |
| 1121502 | IUE por compensar | TAX_RECEIVABLE | 20 | 2535885.94 | 2200115.94 | 335770.0 | 2022-04-28T00:00:00 → 2026-01-01T00:00:00 |
| 1121602 | Credito Fiscal Transitorio | TAX_RECEIVABLE | 135 | 52455.22 | 52455.22 | 0.0 | 2025-04-30T00:00:00 → 2025-12-31T00:00:00 |
| 1130205 | Almacén Retención | OTHER_FISCAL | 2989 | 372818.74 | 265684.09 | 107134.65 | 2024-08-31T00:00:00 → 2026-09-09T00:00:00 |
| 1240200 | RETENCION JUDICIAL | OTHER_FISCAL | 0 | 0 | 0 | 0 | None → None |
| 1240201 | Retencion Judicial | OTHER_FISCAL | 53 | 975834.61 | 966150.61 | 9684.0 | 2022-08-16T00:00:00 → 2026-01-21T00:00:00 |
| 2140000 | OBLIGACIONES TRIBUTARIAS | TAX_LIABILITY | 0 | 0 | 0 | 0 | None → None |
| 2140100 | OBLIGACIONES TRIBUTARIAS | TAX_LIABILITY | 0 | 0 | 0 | 0 | None → None |
| 2140101 | Debito Fiscal IVA | TAX_LIABILITY | 1866338 | 49394401.99 | 62411103.27 | -13016701.28 | 2022-03-31T00:00:00 → 2026-09-09T00:00:00 |
| 2140102 | IT por pagar | TAX_LIABILITY | 1673604 | 9354657.23 | 12997931.99 | -3643274.76 | 2022-03-31T00:00:00 → 2026-09-09T00:00:00 |
| 2140103 | IUE por pagar | TAX_LIABILITY | 26 | 1983989.0 | 1347004.0 | 636985.0 | 2022-04-28T00:00:00 → 2026-04-29T00:00:00 |
| 2140104 | RC-IVA por Pagar | TAX_LIABILITY | 4 | 1204.67 | 1204.67 | 0.0 | 2026-06-30T00:00:00 → 2026-06-30T00:00:00 |
| 2140105 | Ret. IUE de bienes por pagar | WITHHOLDING_LIABILITY | 0 | 0 | 0 | 0 | None → None |
| 2140106 | Ret. IUE de servicios por pagar | WITHHOLDING_LIABILITY | 0 | 0 | 0 | 0 | None → None |
| 2140107 | Ret. RC-IVA por pagar | WITHHOLDING_LIABILITY | 0 | 0 | 0 | 0 | None → None |
| 2140108 | Ret. IT por pagar | WITHHOLDING_LIABILITY | 0 | 0 | 0 | 0 | None → None |
| 2140109 | Ret. remesas al exterior | WITHHOLDING_LIABILITY | 0 | 0 | 0 | 0 | None → None |
| 2140110 | Facilidad de Pagos SIN | TAX_LIABILITY | 407 | 18889874.2 | 10059941.12 | 8829933.08 | 2022-11-29T00:00:00 → 2026-08-27T00:00:00 |
| 6011300 | IMPUESTOS | TAX_EXPENSE | 0 | 0 | 0 | 0 | None → None |
| 6011301 | Impuesto Inmuebles | TAX_EXPENSE | 3 | 8066.0 | 0.0 | 8066.0 | 2026-01-28T00:00:00 → 2026-01-28T00:00:00 |
| 6011303 | Impuesto ITF | TAX_EXPENSE | 23 | 15424.88 | 0.0 | 15424.88 | 2026-01-14T00:00:00 → 2026-04-01T00:00:00 |
| 6011304 | Impuesto Promocionales (AJ) | TAX_EXPENSE | 0 | 0 | 0 | 0 | None → None |
| 6011305 | Impuesto vehiculo | TAX_EXPENSE | 0 | 0 | 0 | 0 | None → None |
| 6011600 | IMPUESTO A LAS TRANSACCIONES | TAX_EXPENSE | 0 | 0 | 0 | 0 | None → None |
| 6011601 | Impuesto a las transacciones | TAX_EXPENSE | 2 | 626.59 | 626.59 | 0.0 | 2026-03-03T00:00:00 → 2026-03-03T00:00:00 |
| 6310000 | IMPUESTOS | TAX_EXPENSE | 0 | 0 | 0 | 0 | None → None |
| 6310100 | IMPUESTOS | TAX_EXPENSE | 0 | 0 | 0 | 0 | None → None |
| 6310104 | Impuestos a los bienes inmuebles | TAX_EXPENSE | 31 | 318176.0 | 318176.0 | 0.0 | 2022-11-29T00:00:00 → 2025-12-31T00:00:00 |
| 6310105 | Impuesto vehículos | TAX_EXPENSE | 65 | 115290.0 | 115290.0 | 0.0 | 2022-07-14T00:00:00 → 2025-12-31T00:00:00 |
| 6310106 | Impuestos varios SIN | TAX_EXPENSE | 7 | 7221.93 | 7221.93 | 0.0 | 2024-04-22T00:00:00 → 2025-12-31T00:00:00 |
| 6310107 | Patentes, tasas e impuestos municipales | TAX_EXPENSE | 15 | 52624.0 | 52624.0 | 0.0 | 2023-02-14T00:00:00 → 2025-12-31T00:00:00 |
| 6310108 | Crédito fiscal perdido | OTHER_FISCAL | 3 | 210.6 | 210.6 | 0.0 | 2023-04-26T00:00:00 → 2023-04-27T00:00:00 |
| 6310110 | Multas y Sanciones Impuestos Nacionales | TAX_EXPENSE | 22 | 106839.92 | 106839.92 | 0.0 | 2022-09-28T00:00:00 → 2025-12-31T00:00:00 |

## E. CUENTAS DE RETENCIÓN IDENTIFICADAS

No se identifica una cuenta de retención contabilizada con evidencia suficiente. Las cuentas OWHT configuradas son cuentas existentes, pero sin actividad transaccional; `2140105`–`2140109` permanecen sin líneas. Resultado: **DEGRADED / cuenta real no probada**.

## F. GENERACIÓN DE LA RETENCIÓN

No se observa nacimiento documentado de retención en OPCH/OVPM/VPM2/VPM6 ni en una cuenta OWHT con movimiento. La evidencia de `2140102` corresponde a impuesto IT y la de `2140103` a IUE.

## G. ASIENTOS MANUALES

El subconjunto fiscal de `TransType=30 + DataSource='O'` fue cuantificado en HANA: {'JOURNALS': 1519936, 'LINES': 1519956, 'FIRST_DATE': '2022-04-01T00:00:00', 'LAST_DATE': '2026-09-09T00:00:00', 'DEBIT': 39750.51, 'CREDIT': 4517250.03}. `DataSource='O'` se conserva como proxy operativo, no como prueba de intención humana.

## H. ACUMULACIÓN MENSUAL

La serie mensual calcula `Opening + Credits - Debits = Closing` por cuenta. Es una reconstrucción a nivel de cuenta; no prueba que un saldo corresponda a sobres ni conserva FIFO por período.

| Cuenta | Meses | Meses con saldo | Máximo saldo abs. | Cierre reconstruido | OACT CurrTotal | Delta |
|---|---|---:|---:|---:|---:|---:|
| 1121501 | 2022-03 → 2026-09 | 52 | 7372806.45 | 4417025.45 | 4417025.45 | -0.0 |
| 1121502 | 2022-04 → 2026-01 | 6 | 580943.0 | 335770.0 | 335770.0 | 0.0 |
| 1121602 | 2025-04 → 2025-12 | 8 | 7653.01 | 0.0 | 0.0 | 0.0 |
| 1130205 | 2024-08 → 2026-09 | 24 | 107134.65 | 107134.65 | 107134.65 | 0.0 |
| 1240201 | 2022-08 → 2026-01 | 16 | 292871.64 | 9684.0 | 9684.0 | 0.0 |
| 2140101 | 2022-03 → 2026-09 | 51 | 13156113.24 | -13016701.28 | -13016701.28 | 0.0 |
| 2140102 | 2022-03 → 2026-09 | 51 | 3643274.76 | -3643274.76 | -3643274.76 | 0.0 |
| 2140103 | 2022-04 → 2026-04 | 11 | 636985.0 | 636985.0 | 636985.0 | 0.0 |
| 2140104 | 2026-06 → 2026-06 | 0 | 0.0 | 0.0 | 0.0 | 0.0 |
| 2140110 | 2022-11 → 2026-08 | 42 | 8829933.08 | 8829933.08 | 8829933.08 | -0.0 |
| 6011301 | 2026-01 → 2026-01 | 1 | 8066.0 | 8066.0 | 8066.0 | 0.0 |
| 6011303 | 2026-01 → 2026-04 | 4 | 15424.88 | 15424.88 | 15424.88 | 0.0 |
| 6011601 | 2026-03 → 2026-03 | 0 | 0.0 | 0.0 | 0.0 | 0.0 |
| 6310104 | 2022-11 → 2025-12 | 8 | 131556.0 | 0.0 | 0.0 | 0.0 |
| 6310105 | 2022-07 → 2025-12 | 4 | 26346.0 | 0.0 | 0.0 | 0.0 |
| 6310106 | 2024-04 → 2025-12 | 5 | 3985.93 | 0.0 | 0.0 | 0.0 |
| 6310107 | 2023-02 → 2025-12 | 5 | 22556.0 | 0.0 | 0.0 | 0.0 |
| 6310108 | 2023-04 → 2023-04 | 0 | 0.0 | 0.0 | 0.0 | 0.0 |
| 6310110 | 2022-09 → 2025-12 | 11 | 15894.0 | 0.0 | 0.0 | 0.0 |

## I. CANCELACIÓN

Se observan pagos/regularizaciones de obligaciones fiscales generales, especialmente IUE, pero no cancelación demostrable de una cuenta de retención WHT configurada. La detección de pares exactos con memo de anulación/reversión se ejecutó sobre cuentas fiscales (200 candidatos); no se interpreta como vínculo causal automático. La contraparte y los asientos completos de casos seleccionados están en `cases` del JSON.

## J. PAGO AL FISCO

Hay pagos bancarios con memos explícitos de IUE/IT para cuentas fiscales generales. No se demuestra un circuito `retención acumulada → pago al fisco` para una retención de proveedor.

## K. PROVEEDORES / DOCUMENTOS

Se reconstruyeron OPCH→VPM2→OVPM y sus diferencias económicas. `WTSum`/`WtAppld` permanecen en cero. Diferencias factura-pago se mantienen como `UNRESOLVED` o descuento/nota/anticipo potencial; no se convierten automáticamente en retención.

## L. PORCENTAJES

No se infieren porcentajes desde diferencias AP porque no existe un caso WHT transaccional con base y retención observables. La configuración OWHT conserva los porcentajes declarados por SAP, pero eso no demuestra uso real.

## M. CASOS REALES

Se conservaron casos de generación aparente, serie/acumulación, pago/regularización, ajuste/reversa y falso positivo. Cada caso contiene `TransId`, header, líneas JDT1, contraparte, memo, nivel de evidencia y clasificación en el JSON; los asientos están limitados a ejemplos concretos.

## N. ANOMALÍAS

- Las cuentas configuradas OWHT tienen saldo/actividad transaccional nula en el período observado.
- `1130205 Almacén Retención` es activo/inventario (`GroupMask=1`, movimientos 60/67), no pasivo WHT.
- `1240201 Retención Judicial` es una retención judicial bancaria distinta del WHT de proveedores.
- `2140102` y `2140103` tienen actividad fiscal real, pero sus memos/contrapartidas muestran IT/IUE general.

## O. LIMITACIONES

- SAP no conserva un objeto ‘sobre’ ni una identidad FIFO de pasivo en GL.
- Sin una cuenta WHT con movimientos no puede reconstruirse importe por proveedor/período.
- Los diferenciales OPCH/OVPM pueden incluir pago parcial, descuento, nota de crédito, anticipo o redondeo.
- Los niveles `EXACT_LINK`, `STRONG_MATCH`, `HEURISTIC_MATCH`, `NO_MATCH` se preservan por caso; no se mezclan.

## P. CONTROL OPERATIVO FUTURO

Controlar por separado: WHT calculado, cuenta pasiva acreditada, saldo pendiente, documentación externa y pago fiscal. Si el circuito continúa fuera de SAP, se requerirá una fuente operativa adicional antes de diseñar un arqueo.

## Q. PRÓXIMO GATE

`TELCHI_AP_PAYABLES_PAYMENT_RECONCILIATION_V1`: profundizar proveedores, pagos netos, descuentos/notas/anticipos y cualquier evidencia externa de sobres, manteniendo esta conclusión como baseline: configuración OWHT ≠ retención calculada ≠ pasivo contabilizado.

## Matriz de hipótesis

| Hipótesis | Evidencia | Estado |
|---|---|---|
| H1 WHT estándar SAP | Configuración presente; tablas/campos transaccionales sin importes | UNUSED_PROVEN |
| H2 Asientos manuales | Existen asientos manuales fiscales, pero no en cuentas WHT configuradas | PARTIAL / no probado para WHT |
| H3 Automático fuera de WHT | Cuentas IT/IUE automáticas/documentales; no son retención WHT | UNRESOLVED |
| H4 Agregado por períodos | Series de IT/IUE muestran acumulación fiscal general; sin cuenta WHT real | UNRESOLVED |
| H5 Retención en pago | AP/VPM medidos; campos WHT cero y sin cuenta WHT activa | REJECTED para ruta estándar |
| H6 Ajuste posterior | Ajustes/reversas fiscales y judiciales observados, no prueba WHT proveedor | PARTIAL |

## Invariantes

```json
{
  "WHT01_owht_accounts_exist_in_oact": {
    "configured": 6,
    "missing": [],
    "pass": true
  },
  "WHT02_fiscal_lines_have_ojdt": {
    "ORPHANS": 0,
    "pass": true
  },
  "WHT03_analyzed_journals_balance": {
    "JOURNALS": 5792399,
    "BALANCED": 5792399,
    "UNBALANCED": 0,
    "MAX_DIFF": 0.0,
    "pass": true
  },
  "WHT04_withholding_accounts_have_liability_evidence": {
    "configured_accounts": 6,
    "nonzero_candidate_rows": 0,
    "pass": false
  },
  "WHT05_standard_wht_quantified": "STANDARD_WHT_TRANSACTIONAL_PATH_UNUSED_OR_NON_MATERIAL",
  "WHT06_manual_fiscal_entries_quantified": true,
  "WHT07_origin_cancellation_evidence_labelled": true,
  "WHT08_sap_write_count": 0,
  "WHT09_monthly_rollforward_generated": true
}
```

## Artefactos

- JSON: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/withholding_tax_accounting_traceability/withholding_tax_accounting_traceability_v1.json`
- Runner: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/withholding_tax_accounting_traceability/withholding_tax_accounting_traceability_v1.py`
- SAP/HANA: SELECT-only; `SAP_WRITE_COUNT=0`.
