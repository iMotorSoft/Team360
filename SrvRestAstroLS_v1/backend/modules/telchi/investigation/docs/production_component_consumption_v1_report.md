# TELCHI SAP — PRODUCTION COMPONENT CONSUMPTION V1

**Gate:** `TELCHI_PRODUCTION_COMPONENT_CONSUMPTION_V1_PASS`
**Date:** 2026-08-26
**HANA writes:** ZERO (READ ONLY)

---

## A. Resultado

**PASS** — El consumo real de componentes de producción fue reconstruido con
evidencia documental SAP: semántica gross/net, cancelaciones, timing, y
clasificación de varianza expected vs net.

---

## B. Cadena documental

```
OWOR (DocEntry)
  → WOR1 (LineNum: componente, factor BaseQtyNum/BaseQtyDen, IssueType, IssuedQty)
      → IGE1 (BaseType=202, BaseEntry=OWOR.DocEntry, BaseLine=WOR1.LineNum, ItemCode)
          → NET_ACTUAL_CONSUMPTION
```

Confirmación: `EXACT_DOCUMENT_LINK` (BaseEntry+BaseLine+ItemCode).

---

## C. Semántica Gross / Net — CERRADA

Evidencia (población completa):

| Dimensión | Resultado |
|-----------|-----------|
| OIGE.CANCELED | 100% = 'N' (49,162 activos, **cero cancelados**) |
| IGE1.Quantity signo | 100% positivo (135,351; **cero negativos**) |
| OINM TT60 InQty>0 (retorno) | 1 fila aislada de 2022 (BASE_REF='28' inválido = artefacto migración) |
| OINM TT60 negativo | 0 |

**Conclusión**: NO existe mecanismo documental de cancelación, devolución ni
reversa de componentes en la población de producción Telchi.

```text
GROSS_ISSUED_QTY = SUM(IGE1.Quantity) WHERE BaseType=202
CANCELED_QTY     = 0
RETURNED_QTY     = 0
REVERSED_QTY     = 0
NET_ACTUAL_CONSUMPTION = GROSS_ISSUED_QTY
```

---

## D. IssuedQty reconciliation

- `WOR1.IssuedQty == SUM(IGE1.Quantity)` en 134,291/134,292 líneas (99.999%)
- Confirmación del gate BOM: `ISSUEDQTY_SEMANTICS = ACTUAL_ACCUMULATED`
- Caso 17757 (única discrepancia): ver sección L.

---

## E. Manual vs Backflush

| Método | WOR1 líneas | % |
|--------|------------|---|
| M (Manual) | 95,579 | 67.5% |
| B (Backflush) | 46,058 | 32.5% |

Ambos generan IGE1 real. Timing en muestra (4,000 órdenes):
- issues antes del primer receipt: 116 líneas
- issues después del último receipt: 104 líneas

El timing de manual/backflush es mayormente pre-receipt, con una minoría
post-receipt (correcciones). `SAME_DAY_ORDERING` no siempre resoluble (sin hora).

---

## F. Múltiples issues

| Issues por línea WOR1 | Líneas |
|-----------------------|-------:|
| 0 | 6,072 |
| 1 | 133,540 |
| 2 | 724 |
| 3 | 36 |
| 4 | 1 |
| **Multi (≥2)** | **761 (0.54%)** |

El modelo soporta 1:N. Los 761 casos multi-issue preservan todos los documentos
(`issue_docs`).

---

## G. Cancelaciones / Returns / Reversals

```text
CANCELED:  NOT OBSERVED (0 OIGE cancelados)
RETURNS:   NOT OBSERVED (0 patrón de devolución)
REVERSALS: NOT OBSERVED (0 cantidades negativas)
```

La única excepción es 1 fila OINM TT60 de 2022 (artefacto de migración, BASE_REF
inválido) — excluida.

---

## H. Expected vs Net Actual (4,000 órdenes, 30,361 líneas)

| Clasificación | Líneas | % |
|---------------|-------:|---|
| EXACT | 25,236 | 83.1% |
| TRUE_OVER_CONSUMPTION_CANDIDATE | 3,488 | 11.5% |
| TRUE_UNDER_CONSUMPTION_CANDIDATE | 977 | 3.2% |
| EXPECTED_NOT_CONSUMED | 655 | 2.2% |
| PARTIAL_ZERO_OUTPUT_WITH_ISSUE | 5 | 0.02% |

Comparado con el baseline del gate BOM (EXACT 84.9%): consistente. La pequeña
diferencia se debe a la muestra mayor y al uso del expected exacto (num/den).

---

## I. Hallazgos reales — varianza por componente

### Sobre-consumo sistemático: componente `L00099`
Consumo real supera consistentemente el expected en montos redondos:

| Orden | Producto | Expected | Actual | Diff |
|-------|----------|---------:|-------:|-----:|
| 28638 | L02057 | 803 | 1,103 | +300 |
| 28349 | L00505 | 429 | 629 | +200 |
| 28490 | L01618 | 121 | 221 | +100 |
| 28228 | L01740 | 1,218 | 1,368 | +150 |

Patrón: +100/+150/+200/+300/+400/+500 en múltiples productos. Candidato a
receta desactualizada o emisión adicional real (empaque/insumo).

### Bajo-consumo: componente `L02475` en L03612
- 50,000 esperados → 49,700/49,800 emitidos (var -0.4% a -0.8%) — ajuste de
  emisión, no material.

---

## J. Clasificación residual

El residual del gate BOM (OVER 9.3%, UNDER 3.5%, NOT_CONSUMED 2.3%) fue
**re-clasificado** sin cancelaciones/returns:

- OVER → `TRUE_OVER_CONSUMPTION_CANDIDATE` (11.5%) — sin cancelaciones/returns
  que lo reduzcan; el consumo emitido ES el consumo neto.
- UNDER → `TRUE_UNDER_CONSUMPTION_CANDIDATE` (3.2%)
- NOT_CONSUMED (2.2%) → órdenes sin emisión (backflush pendiente, orden sin
  producción, o cierre administrativo)

`UNRESOLVED` no aplica: no hay cancelaciones/returns que no puedan vincularse.

---

## K. Edge cases

| Caso | Resultado |
|------|-----------|
| OINM TT60 InQty>0 (2022) | artefacto migración (BASE_REF='28' inválido), excluido |
| Múltiples issues (761 líneas) | preserva todos los documentos |
| ZERO_EXPECTED_WITH_ACTUAL | no observado en la muestra (manejo soportado) |
| PARTIAL_ZERO_OUTPUT_WITH_ISSUE | 5 casos |

---

## L. Caso 17757 (edge case, 1/~134K)

- OWOR 17757: produce **L01955** (Planned=200, Cmplt=0, Status=L, Whs=SAA-M1)
- WOR1 line 0: comp **L01942**, expected=57.142857
- **Dos IGE1** (doc 44000 y 44027, ambos 2025-04-17, qty=57.1429 cada uno)
  → gross=114.2858, pero `IssuedQty=57.1429` (refleja solo uno)
- Receipt IGN1 26914 registra **L01942** (el componente), no L01955 (producto)

**Interpretación**: orden de reacondicionamiento/rework donde el "producto
terminado" es el mismo componente. IssuedQty actualizado parcialmente (o issue
duplicada). Clasificación: `ACCUMULATED_PARTIALLY_UPDATED_OR_DUPLICATE_ISSUE`.

---

## M. Tests

| Suite | Resultado |
|-------|-----------|
| test_component_consumption_domain | 8 PASS |
| test_recipe_bom_domain | 12 PASS |
| Regresión users/attribution | 52 PASS |
| `git diff --check` | OK |
| READ ONLY | PASS (zero writes) |

---

## N. Artefactos

```
validation/production/component_consumption_domain.py
validation/production/component_consumption_v1.py
validation/production/test_component_consumption_domain.py
docs/production_component_consumption_v1_report.md
```

---

## O. Limitaciones

1. `SAME_DAY_ORDERING_UNRESOLVED`: sin hora en algunos campos, la secuencia
   intra-day no siempre es determinable.
2. El artefacto OINM TT60 de 2022 (migración) no se vincula a ninguna orden.
3. La interpretación del sobre-consumo de L00099 requiere validación de negocio
   (receta vs emisión real de empaque).
4. El caso 17757 es un edge case único, no generalizable.

---

## P. Próximo gate

`TELCHI_PRODUCTION_OUTPUT_TRACEABILITY_V1`
