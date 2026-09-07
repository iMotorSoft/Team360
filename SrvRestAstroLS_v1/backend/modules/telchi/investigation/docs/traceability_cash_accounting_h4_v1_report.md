# TELCHI — CASH ACCOUNTING TRACEABILITY H4 V1 — REPORT

**Fecha:** 2026-08-25
**Workspace:** `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi`
**Gate:** `TELCHI_ATOMIC_CASH_ACCOUNTING_TRACEABILITY_H4_V1`
**Resultado global:** `PASS` con `PHYSICAL_CASHBOX_SEMANTICS=DEGRADED` y `BRANCH=HEURISTIC` (documentados)

---

## A. Resultado

`TELCHI_ATOMIC_CASH_ACCOUNTING_TRACEABILITY_H4_V1_PASS`

La pregunta del dueño queda respondida transaccionalmente para toda la ventana 2023-02:

```
¿Esta factura figura cobrada? ¿Dónde entró realmente el dinero?
→ ORCT.TransId → OJDT → JDT1[Account=CashAcct] → débito EXACTO = CashSum
→ cuenta "Cajas <sucursal>" / "Caja Distribuidor Placa <móvil>"
```

## B. Cadena H4

| Tramo | Estado | Evidencia |
|---|---|---|
| ORCT→OJDT | ✅ PASS | TransId join 29.319/29.319 (100%), TransId único en OJDT → 1:1 |
| OJDT→JDT1 | ✅ PASS | relación 1:N preservada (todas las líneas del asiento) |
| JDT1→OACT | ✅ PASS | Account = ORCT.CashAcct (identidad, no posición); ContraAct = cliente |
| OACT→CashBox | 🟡 DEGRADED | flag `CashBox='N'` en TODAS las cuentas reales de caja → no marca caja física; la familia 11102xx/11103xx + naming sí |
| CashBox/Branch | 🟡 HEURISTIC | BPLId ausente en líneas y cuentas; branch vía naming (`Cajas Casa Matriz`, `Distribuidor Placa 4702-GIP`) |

## C. Cobertura (2023-02, primaria transaccional)

| Métrica | Valor |
|---|---|
| Pagos totales | 29.319 |
| Cancelados (trazados con reversa) | 135 |
| No-cash (N/A físico) | 5.097 |
| **Pagos con componente efectivo** | **24.087** |
| Journal matched | 24.087 (100%) |
| Journal missing | 0 |
| Account resolved / mismatch | 24.087 / 0 |
| **Amount EXACT** (delta=0) | **24.087 (100%)** |
| Amount tolerado / mismatch | 0 / 0 |
| Branch resuelto (heurístico) | 21.744 de 24.087 (90,3%); resto cuentas especiales (tesorería, divisas) |

## D. Taxonomía

```
CASH_ACCOUNTING_CONFIRMED      24.087
NOT_APPLICABLE_TO_PHYSICAL_CASH 5.097   (transfer/check/card only)
CASH_CANCELED                    135    (reversa vía StornoToTr)
CASH_JOURNAL_MISSING               0
CASH_ACCOUNT_MISMATCH              0
CASH_AMOUNT_MISMATCH               0
UNRESOLVED                         0
```

## E. Montos

| Métrica | Valor |
|---|---|
| Efectivo esperado (ORCT.CashSum) | $5.466.433,67 |
| Efectivo confirmado contablemente | $5.466.433,67 |
| Diferencia no confirmada | $0,00 |

## F. Casos reales (IDs SAP verificables)

**A. cash-only:** ORCT **382713**, TransId **3664190**, cuenta **1110201** (Cajas Casa Matriz MN), CashSum 2.765,00 → débito contable 2.765,00, delta 0 → CONFIRMED.
**B. mixed:** ORCT **444175**, TransId **4153980**, cuenta 1110202, efectivo descompuesto dentro del asiento mixto → CONFIRMED + MIXED_PAYMENT_DECOMPOSED.
**C. partial/small:** ORCT **401615**, TransId **3788786**, cuenta 1110201, cash 5,00 → delta 0 → CONFIRMED.
**Ejemplo estructural (auditoría manual):** ORCT 409496 / TransId 4110874: débito 104.400 en 1110205 + crédito al cliente C003457 (ContraAct). ORCT 402671 / 3792195: efectivo 2,64 (1110202) + transferencia 4.620 (1120301 puente "por Confirmar") − cliente 4.622,64.

## G. Anomalías y cancelaciones

**Anomalía real encontrada (branch mismatch, HEURISTIC):**
- Doc **1542943**: cobrado en "Caja Distribuidor Placa **5260 IHY**" pero la mercadería salió de "Almacen Movil **4702 GIP**". Único caso no coincidente de su tipo.

**Consistencia placa↔almacén (HEURISTIC):** 78.090/78.091 pares pago-cuenta-almacén coinciden (**100,0%**) extrayendo el código de placa del nombre de cuenta vs nombre de almacén.

**Cancelaciones (§33):** 112 cobros cancelados con efectivo tienen asiento original + reversa vía `OJDT.StornoToTr`; con semántica de signo correcta (la reversa ACREDITA la caja), **112/112 netean exactamente $0** → NET effect cero CONFIRMADO. Los 23 restantes cancelados sin componente cash.

## H. Tests

| Capa | Conteo | Resultado |
|---|---|---|
| UNIT previos (contracts/cash/traceability) | 33 | PASS |
| UNIT H4 nuevos (§27: joins, signos, monedas, mixed, canceled, branch, lineage) | 16 | PASS |
| LEGACY parquet | 3 | PASS |
| CONTRACT/SOURCE/SEMANTIC HANA | 12 | PASS |
| E2E SALES×CASH×STOCK (regresión baseline) | 6 | PASS |
| E2E H4 real (nuevo) | 6 | PASS |
| **TOTAL** | **76** | **76 PASS / 0 FAIL / exit 0** |

## I. Regresión

`TELCHI_ATOMIC_SALES_CASH_STOCK_TRACEABILITY_V1_PASS`: **PRESERVADO YES** (misma suite; 28.899 casos, CONSISTENT 23.023, REVIEW 0, UNEXPLAINED 0 intactos).

## J. Runtime

HANA ✅ read-only (writes=0) · VPN ✅ · Podman SIN TOQUE · sin tablas temporales en HANA (todo cálculo local).

## K. Git

Workspace telchi sin historial Git activo para este flujo (política del módulo: sin commits); archivos nuevos agregados sin tocar concurrentes.

## L. Documentación

STATUS_ACTUAL ✅ · LAT DEC-037..041 ✅ · este reporte ✅.

## M. Limitaciones reales

1. `OACT.CashBox='N'` universal → la semántica "caja física" se sostiene en familia/naming de cuenta, no en el flag (DEGRADED documentado).
2. BPLId ausente → branch es HEURISTIC (naming); nunca se presenta como hecho.
3. La medición placa↔almacén usa parsing de nombres (doble lado) → HEURISTIC.
4. Ventanas FC: solo 55 pagos cash con moneda distinta en la ventana; paridad validada en moneda local BS (los FC quedan con currency preservada en el trace).

## N. Próximo gate

`PRODUCTION_BOM_MAX_PRODUCIBLE_V1` — producto terminado → BOM → componentes → stock → MAX_PRODUCIBLE → bottleneck → cobertura.

## Decisión de signos (§36) — registrada

La reversa de un cobro cancelado ACREDITA la cuenta de caja: NET = Σ(Debit−Credit) sobre ambas patas SIN negación adicional. Un bug propio SIGN_ERROR (negar la segunda pata) fue detectado y corregido midiendo contra datos reales (112/112 net-zero).
