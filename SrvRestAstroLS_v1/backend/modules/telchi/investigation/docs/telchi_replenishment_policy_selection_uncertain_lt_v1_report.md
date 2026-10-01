# TELCHI — Gate 6: policy selection under lead-time uncertainty V1

**Continuación:** `TELCHI_PHYSICAL_LEAD_TIME_V1_NOT_OBSERVABLE`\
**Contexto:** `ENTITY=TELCHI` · `DOMAIN=REPOSICIÓN / STOCK_E_INVENTARIOS` · `STAGE=INVESTIGATION`\
**Universo:** `ItemCode LIKE 'L%'` · branch `2A` · 100 productos · 365 días\
**Control:** SAP/HANA read-only · `SAP_WRITE_COUNT=0` · `MAX_WORKERS=1` · `RESOURCE_GUARD=ENABLED`

## 1. Resumen ultraejecutivo

- **100 productos L**: 53 `SERVICE_PROBLEM`, 14 `EXCESS_INVENTORY_PROBLEM`, 2 `BOTH`, 31 `NEITHER`.
- **23 permiten acción analítica controlada**: 6 `READY_FOR_POLICY` y 17 `READY_WITH_CONSERVATIVE_POLICY`.
- **32 `LEAD_TIME_DEPENDENT`**: todos los candidatos B3 `ROBUST_LOW`; 14 `NEEDS_OPERATIONAL_DATA`; 31 `KEEP_CURRENT`.
- **Robustez B3 preservada**: HIGH 24, MEDIUM 3, LOW 32, NOT_ROBUST 0. El worst-case/regret valida 23 candidatos HIGH/MEDIUM; 1 HIGH y 3 MEDIUM quedan para datos adicionales.
- **Impacto descriptivo READY, por producto y UoM nativa**: disponibilidad media worst-case 0,980 frente a 0,490 CURRENT; stockout 7,4 frente a 186,2 días. El grupo conservador usa más inventario para proteger servicio.
- **Mínimo faltante**: `dispatch_timestamp` + `receipt_timestamp`, enlazados a transferencia, origen y sucursal destino.
- `INVENTORY_VALUE=NOT_READY`; dimensiones físicas no están cargadas de forma utilizable.

**Veredicto:** `TELCHI_REPLENISHMENT_POLICY_SELECTION_UNCERTAIN_LT_V1_PASS`. No se ejecuta ninguna recomendación. Siguiente paso: `GATE 7 — PILOT REPLENISHMENT POLICY DESIGN` para los 23 READY, con captura física en paralelo.

## 2. Product segmentation

| Clase | Productos | Criterio operativo |
|---|---:|---|
| `READY_FOR_POLICY` | 6 | HIGH/MEDIUM + mejora material worst-case sin costo material de inventario |
| `READY_WITH_CONSERVATIVE_POLICY` | 17 | HIGH/MEDIUM + mejora robusta con costo de inventario |
| `LEAD_TIME_DEPENDENT` | 32 | LOW; la magnitud depende del lead time |
| `KEEP_CURRENT` | 31 | CURRENT sigue competitivo |
| `NEEDS_OPERATIONAL_DATA` | 14 | sin base suficiente para seleccionar responsablemente |

Materialidad: disponibilidad `≥ +2 pp`; stockout `≥ 3 días`; inventario `≥ 10%`; movimientos `≥ 10%` con servicio no inferior (`−1 pp` / `+3 días`). Diferencias microscópicas no cuentan.

## 3. Policy portfolio

| Política | Productos | Complejidad |
|---|---:|---|
| `MIN_MAX` | 5 | LOW |
| `REORDER_POINT` | 0 | MEDIUM |
| `DAYS_OF_SUPPLY` | 49 | LOW |
| `PERIODIC_REVIEW` | 0 | LOW |
| `DYNAMIC_TARGET` | 5 | HIGH |
| `HYBRID` | 0 | HIGH |
| `KEEP_CURRENT` | 41 | LOW |

Portfolio observado: `DAYS_OF_SUPPLY` 49, `MIN_MAX` 5, `DYNAMIC_TARGET` 5 y CURRENT 41. No se fuerza variedad. `DYNAMIC_TARGET` es HIGH; DOS/MIN_MAX son LOW.

## 4. Robustness, worst-case y regret

Se procesaron 1.900 configuraciones × 6 escenarios desde los artefactos Gate 5B, sin repetir trazas SAP. `worst_case.jsonl` conserva `WORST_CASE_AVAILABILITY`, `WORST_CASE_STOCKOUT_DAYS`, `WORST_CASE_AVG_INVENTORY` y `WORST_CASE_REPLENISHMENTS`. `regret.jsonl` conserva `MAX_REGRET`, `AVG_REGRET` y sus cuatro componentes.

| Robustez B3 | Productos | MAX_REGRET medio | AVG_REGRET medio | READY |
|---|---:|---:|---:|---:|
| `ROBUST_HIGH` | 24 | 0.484 | 0.411 | 23/24 |
| `ROBUST_MEDIUM` | 3 | 3.111 | 2.697 | 0/3 |
| `ROBUST_LOW` | 32 | 1.777 | 1.486 | 0/32 |

Regret compuesto = media equiponderada de distancia relativa al mejor valor disponible en el mismo LT para disponibilidad, stockout, inventario y reposiciones. No es un score de negocio; los componentes quedan trazables.

### 4.1 Los 24 ROBUST_HIGH

| Item | Problema | Candidato | CURRENT A/SO/I/R | Candidato best A/SO/I/R | Worst A/SO/I/R | LT 0/1/2/3/5/7: A/SO/I/R |
|---|---|---|---|---|---|---|
| L02205 | SERVICE_PROBLEM | DAYS_OF_SUPPLY {'target_dos': 14, 'trigger_dos': 7} | 87.12%/47/29.4/8 | 99.73%/1/20.4/23 | 92.05%/29/20.6/23 | 0:99.73%/1/20.4/23.0 · 1:98.63%/5/20.0/21.0 · 2:96.44%/13/20.1/20.0 · 3:95.62%/16/20.2/16.0 · 5:94.79%/19/20.6/14.0 · 7:92.05%/29/20.0/11.0 |
| L00136 | SERVICE_PROBLEM | DAYS_OF_SUPPLY {'target_dos': 14, 'trigger_dos': 7} | 44.11%/204/2.2/2 | 100.00%/0/4.0/0 | 100.00%/0/4.0/0 | 0:100.00%/0/4.0/0.0 · 1:100.00%/0/4.0/0.0 · 2:100.00%/0/4.0/0.0 · 3:100.00%/0/4.0/0.0 · 5:100.00%/0/4.0/0.0 · 7:100.00%/0/4.0/0.0 |
| L00163 | SERVICE_PROBLEM | DAYS_OF_SUPPLY {'target_dos': 14, 'trigger_dos': 7} | 94.25%/21/15.4/9 | 100.00%/0/26.0/0 | 100.00%/0/26.0/0 | 0:100.00%/0/26.0/0.0 · 1:100.00%/0/26.0/0.0 · 2:100.00%/0/26.0/0.0 · 3:100.00%/0/26.0/0.0 · 5:100.00%/0/26.0/0.0 · 7:100.00%/0/26.0/0.0 |
| L02290 | BOTH | MIN_MAX {'min_days': 7, 'max_days': 30} | 78.36%/79/14.1/14 | 99.18%/3/12.1/13 | 89.04%/40/12.1/13 | 0:99.18%/3/12.1/13.0 · 1:98.36%/6/11.6/13.0 · 2:96.71%/12/11.4/12.0 · 3:95.34%/17/11.3/12.0 · 5:92.88%/26/11.7/11.0 · 7:89.04%/40/11.0/10.0 |
| L00253 | SERVICE_PROBLEM | DAYS_OF_SUPPLY {'target_dos': 14, 'trigger_dos': 7} | 98.08%/7/18.0/7 | 100.00%/0/22.6/0 | 100.00%/0/22.6/0 | 0:100.00%/0/22.6/0.0 · 1:100.00%/0/22.6/0.0 · 2:100.00%/0/22.6/0.0 · 3:100.00%/0/22.6/0.0 · 5:100.00%/0/22.6/0.0 · 7:100.00%/0/22.6/0.0 |
| L00254 | SERVICE_PROBLEM | DAYS_OF_SUPPLY {'target_dos': 14, 'trigger_dos': 7} | 97.53%/9/19.8/13 | 100.00%/0/16.8/0 | 100.00%/0/16.8/0 | 0:100.00%/0/16.8/0.0 · 1:100.00%/0/16.8/0.0 · 2:100.00%/0/16.8/0.0 · 3:100.00%/0/16.8/0.0 · 5:100.00%/0/16.8/0.0 · 7:100.00%/0/16.8/0.0 |
| L00255 | SERVICE_PROBLEM | DAYS_OF_SUPPLY {'target_dos': 14, 'trigger_dos': 7} | 75.89%/88/15.5/8 | 100.00%/0/16.2/0 | 100.00%/0/16.2/0 | 0:100.00%/0/16.2/0.0 · 1:100.00%/0/16.2/0.0 · 2:100.00%/0/16.2/0.0 · 3:100.00%/0/16.2/0.0 · 5:100.00%/0/16.2/0.0 · 7:100.00%/0/16.2/0.0 |
| L00344 | SERVICE_PROBLEM | DAYS_OF_SUPPLY {'target_dos': 14, 'trigger_dos': 7} | 98.08%/7/9.9/1 | 100.00%/0/8.0/0 | 100.00%/0/8.0/0 | 0:100.00%/0/8.0/0.0 · 1:100.00%/0/8.0/0.0 · 2:100.00%/0/8.0/0.0 · 3:100.00%/0/8.0/0.0 · 5:100.00%/0/8.0/0.0 · 7:100.00%/0/8.0/0.0 |
| L01079 | SERVICE_PROBLEM | MIN_MAX {'min_days': 7, 'max_days': 30} | 0.00%/365/0.0/18 | 89.32%/39/283.3/10 | 72.33%/101/291.0/10 | 0:89.32%/39/283.3/10.0 · 1:86.58%/49/272.9/10.0 · 2:83.84%/59/262.5/10.0 · 3:82.19%/65/291.0/9.0 · 5:77.26%/83/270.1/9.0 · 7:72.33%/101/249.3/9.0 |
| L00406 | SERVICE_PROBLEM | DAYS_OF_SUPPLY {'target_dos': 14, 'trigger_dos': 7} | 10.68%/326/4.9/1 | 100.00%/0/46.0/0 | 100.00%/0/46.0/0 | 0:100.00%/0/46.0/0.0 · 1:100.00%/0/46.0/0.0 · 2:100.00%/0/46.0/0.0 · 3:100.00%/0/46.0/0.0 · 5:100.00%/0/46.0/0.0 · 7:100.00%/0/46.0/0.0 |
| L00528 | SERVICE_PROBLEM | DAYS_OF_SUPPLY {'target_dos': 14, 'trigger_dos': 7} | 10.68%/326/0.4/1 | 100.00%/0/4.0/0 | 100.00%/0/4.0/0 | 0:100.00%/0/4.0/0.0 · 1:100.00%/0/4.0/0.0 · 2:100.00%/0/4.0/0.0 · 3:100.00%/0/4.0/0.0 · 5:100.00%/0/4.0/0.0 · 7:100.00%/0/4.0/0.0 |
| L00408 | SERVICE_PROBLEM | DAYS_OF_SUPPLY {'target_dos': 14, 'trigger_dos': 7} | 10.68%/326/5.1/1 | 100.00%/0/48.0/0 | 100.00%/0/48.0/0 | 0:100.00%/0/48.0/0.0 · 1:100.00%/0/48.0/0.0 · 2:100.00%/0/48.0/0.0 · 3:100.00%/0/48.0/0.0 · 5:100.00%/0/48.0/0.0 · 7:100.00%/0/48.0/0.0 |
| L00409 | SERVICE_PROBLEM | DAYS_OF_SUPPLY {'target_dos': 14, 'trigger_dos': 7} | 10.68%/326/2.8/1 | 100.00%/0/26.0/0 | 100.00%/0/26.0/0 | 0:100.00%/0/26.0/0.0 · 1:100.00%/0/26.0/0.0 · 2:100.00%/0/26.0/0.0 · 3:100.00%/0/26.0/0.0 · 5:100.00%/0/26.0/0.0 · 7:100.00%/0/26.0/0.0 |
| L00530 | SERVICE_PROBLEM | DAYS_OF_SUPPLY {'target_dos': 14, 'trigger_dos': 7} | 10.68%/326/6.3/0 | 100.00%/0/59.0/0 | 100.00%/0/59.0/0 | 0:100.00%/0/59.0/0.0 · 1:100.00%/0/59.0/0.0 · 2:100.00%/0/59.0/0.0 · 3:100.00%/0/59.0/0.0 · 5:100.00%/0/59.0/0.0 · 7:100.00%/0/59.0/0.0 |
| L00412 | SERVICE_PROBLEM | DAYS_OF_SUPPLY {'target_dos': 14, 'trigger_dos': 7} | 10.68%/326/0.9/1 | 100.00%/0/8.0/0 | 100.00%/0/8.0/0 | 0:100.00%/0/8.0/0.0 · 1:100.00%/0/8.0/0.0 · 2:100.00%/0/8.0/0.0 · 3:100.00%/0/8.0/0.0 · 5:100.00%/0/8.0/0.0 · 7:100.00%/0/8.0/0.0 |
| L00889 | SERVICE_PROBLEM | DAYS_OF_SUPPLY {'target_dos': 14, 'trigger_dos': 7} | 94.25%/21/11.8/1 | 100.00%/0/9.1/0 | 100.00%/0/9.1/0 | 0:100.00%/0/9.1/0.0 · 1:100.00%/0/9.1/0.0 · 2:100.00%/0/9.1/0.0 · 3:100.00%/0/9.1/0.0 · 5:100.00%/0/9.1/0.0 · 7:100.00%/0/9.1/0.0 |
| L00953 | SERVICE_PROBLEM | DAYS_OF_SUPPLY {'target_dos': 14, 'trigger_dos': 7} | 21.92%/285/2.0/0 | 100.00%/0/9.0/0 | 100.00%/0/9.0/0 | 0:100.00%/0/9.0/0.0 · 1:100.00%/0/9.0/0.0 · 2:100.00%/0/9.0/0.0 · 3:100.00%/0/9.0/0.0 · 5:100.00%/0/9.0/0.0 · 7:100.00%/0/9.0/0.0 |
| L00909 | SERVICE_PROBLEM | DAYS_OF_SUPPLY {'target_dos': 14, 'trigger_dos': 7} | 10.68%/326/4.5/1 | 100.00%/0/42.0/0 | 100.00%/0/42.0/0 | 0:100.00%/0/42.0/0.0 · 1:100.00%/0/42.0/0.0 · 2:100.00%/0/42.0/0.0 · 3:100.00%/0/42.0/0.0 · 5:100.00%/0/42.0/0.0 · 7:100.00%/0/42.0/0.0 |
| L01203 | SERVICE_PROBLEM | DAYS_OF_SUPPLY {'target_dos': 14, 'trigger_dos': 7} | 93.15%/25/11.4/1 | 100.00%/0/16.0/0 | 100.00%/0/16.0/0 | 0:100.00%/0/16.0/0.0 · 1:100.00%/0/16.0/0.0 · 2:100.00%/0/16.0/0.0 · 3:100.00%/0/16.0/0.0 · 5:100.00%/0/16.0/0.0 · 7:100.00%/0/16.0/0.0 |
| L02177 | SERVICE_PROBLEM | DAYS_OF_SUPPLY {'target_dos': 14, 'trigger_dos': 7} | 5.75%/344/0.1/0 | 100.00%/0/1.0/0 | 100.00%/0/1.0/0 | 0:100.00%/0/1.0/0.0 · 1:100.00%/0/1.0/0.0 · 2:100.00%/0/1.0/0.0 · 3:100.00%/0/1.0/0.0 · 5:100.00%/0/1.0/0.0 · 7:100.00%/0/1.0/0.0 |
| L02179 | SERVICE_PROBLEM | DAYS_OF_SUPPLY {'target_dos': 14, 'trigger_dos': 7} | 74.25%/94/0.7/0 | 100.00%/0/1.0/0 | 100.00%/0/1.0/0 | 0:100.00%/0/1.0/0.0 · 1:100.00%/0/1.0/0.0 · 2:100.00%/0/1.0/0.0 · 3:100.00%/0/1.0/0.0 · 5:100.00%/0/1.0/0.0 · 7:100.00%/0/1.0/0.0 |
| L02197 | EXCESS_INVENTORY_PROBLEM | DAYS_OF_SUPPLY {'target_dos': 14, 'trigger_dos': 7} | 100.00%/0/4.1/1 | 100.00%/0/4.0/0 | 100.00%/0/4.0/0 | 0:100.00%/0/4.0/0.0 · 1:100.00%/0/4.0/0.0 · 2:100.00%/0/4.0/0.0 · 3:100.00%/0/4.0/0.0 · 5:100.00%/0/4.0/0.0 · 7:100.00%/0/4.0/0.0 |
| L02234 | SERVICE_PROBLEM | DAYS_OF_SUPPLY {'target_dos': 14, 'trigger_dos': 7} | 83.29%/61/0.8/1 | 100.00%/0/1.0/0 | 100.00%/0/1.0/0 | 0:100.00%/0/1.0/0.0 · 1:100.00%/0/1.0/0.0 · 2:100.00%/0/1.0/0.0 · 3:100.00%/0/1.0/0.0 · 5:100.00%/0/1.0/0.0 · 7:100.00%/0/1.0/0.0 |
| L02308 | SERVICE_PROBLEM | DAYS_OF_SUPPLY {'target_dos': 14, 'trigger_dos': 7} | 5.75%/344/0.1/0 | 100.00%/0/1.0/0 | 100.00%/0/1.0/0 | 0:100.00%/0/1.0/0.0 · 1:100.00%/0/1.0/0.0 · 2:100.00%/0/1.0/0.0 · 3:100.00%/0/1.0/0.0 · 5:100.00%/0/1.0/0.0 · 7:100.00%/0/1.0/0.0 |

Los 24 conservan `ROBUST_LT_COUNT` HIGH de Gate 5B. Bajo magnitud, 23 HIGH/MEDIUM pasan como READY; no se convierte automáticamente el resto en política. Todas las cantidades son por producto/UoM.

## 5. Service, inventory y BOTH

En los 55 `SERVICE_PROBLEM`/`BOTH`, la reducción material de stockout aparece en todos los escenarios para 41 productos, en mayoría para 2 y en ninguno para 12. No hay un caso “solo algunos” en la mejor política material.

Los 14 `EXCESS_INVENTORY_PROBLEM` tienen candidatos de ahorro en 12 con 3–6 escenarios, pero no robustos suficientes para despliegue; 2 necesitan datos. No se ahorra inventario si el servicio empeora materialmente.

| Item | Decisión | Robustez | Candidato | Worst A delta | Worst SO delta | Worst I delta |
|---|---|---|---|---:|---:|---:|
| L00038 | LEAD_TIME_DEPENDENT | ROBUST_LOW | DAYS_OF_SUPPLY(30,15) | -1,64 pp | +6 d | -23,5% |
| L03600 | LEAD_TIME_DEPENDENT | ROBUST_LOW | DAYS_OF_SUPPLY(45,22) | -1,92 pp | +7 d | -36,0% |
| L03576 | LEAD_TIME_DEPENDENT | ROBUST_LOW | DAYS_OF_SUPPLY(21,10) | -3,56 pp | +13 d | -77,5% |
| L00056 | LEAD_TIME_DEPENDENT | ROBUST_LOW | DAYS_OF_SUPPLY(14,7) | -12,33 pp | +45 d | -53,0% |
| L03255 | LEAD_TIME_DEPENDENT | ROBUST_LOW | DYNAMIC_TARGET(30) | -1,64 pp | +6 d | -2,4% |
| L00057 | LEAD_TIME_DEPENDENT | ROBUST_LOW | MIN_MAX(14,45) | -2,47 pp | +9 d | -27,5% |
| L01755 | LEAD_TIME_DEPENDENT | ROBUST_LOW | DYNAMIC_TARGET(30) | -1,92 pp | +7 d | -11,1% |
| L03256 | LEAD_TIME_DEPENDENT | ROBUST_LOW | DYNAMIC_TARGET(30) | -1,37 pp | +5 d | +8,3% |
| L00059 | LEAD_TIME_DEPENDENT | ROBUST_LOW | DAYS_OF_SUPPLY(60,30) | -2,47 pp | +9 d | +2,8% |
| L00060 | LEAD_TIME_DEPENDENT | ROBUST_LOW | MIN_MAX(7,30) | -6,85 pp | +25 d | -49,1% |
| L02197 | NEEDS_OPERATIONAL_DATA | ROBUST_HIGH | DAYS_OF_SUPPLY(14,7) | 0,00 pp | 0 d | -2,5% |
| L00061 | LEAD_TIME_DEPENDENT | ROBUST_LOW | DAYS_OF_SUPPLY(30,15) | -3,01 pp | +11 d | -14,0% |
| L03054 | LEAD_TIME_DEPENDENT | ROBUST_LOW | DYNAMIC_TARGET(21) | -3,29 pp | +12 d | -53,5% |
| L02165 | LEAD_TIME_DEPENDENT | ROBUST_LOW | DAYS_OF_SUPPLY(45,22) | -0,27 pp | +1 d | -11,1% |

`BOTH` prioritarios: `L02290` → `MIN_MAX(7,30)`, HIGH, READY: worst availability +10,68 pp, stockout −39 días, inventario −14,6%. `L02203` → `DYNAMIC_TARGET(30,0.98)`, MEDIUM, NEEDS_OPERATIONAL_DATA: worst availability −1,37 pp, stockout +5 días, inventario +38,0%.

## 6. Los 32 ROBUST_LOW

Hipótesis de sensibilidad, no causalidad: `HIGH_DEMAND_VARIABILITY` 17, `POLICY_PARAMETER_SENSITIVITY` 7, `LT_SENSITIVE_TRIGGER` 7, `HIGH_REPLENISHMENT_DEPENDENCE` 1.

Ver detalle por producto y evidencia observable en `product_selection.jsonl`; las hipótesis son `LT_SENSITIVE_TRIGGER`, `HIGH_DEMAND_VARIABILITY`, `INTERMITTENT_DEMAND`, `LOW_INITIAL_STOCK`, `HIGH_REPLENISHMENT_DEPENDENCE`, `POLICY_PARAMETER_SENSITIVITY` u `OTHER`.

## 7. Casos ejecutivos

Se generaron 10 HIGH, 5 MEDIUM/LOW y 5 KEEP_CURRENT en `executive_cases.jsonl`.

| Grupo | Item | Problema | Decisión | Política |
|---|---|---|---|---|
| HIGH | L01079 | SERVICE_PROBLEM | READY_WITH_CONSERVATIVE_POLICY | MIN_MAX {'min_days': 7, 'max_days': 30} |
| HIGH | L02177 | SERVICE_PROBLEM | READY_WITH_CONSERVATIVE_POLICY | DAYS_OF_SUPPLY {'target_dos': 14, 'trigger_dos': 7} |
| HIGH | L02308 | SERVICE_PROBLEM | READY_WITH_CONSERVATIVE_POLICY | DAYS_OF_SUPPLY {'target_dos': 14, 'trigger_dos': 7} |
| HIGH | L00406 | SERVICE_PROBLEM | READY_WITH_CONSERVATIVE_POLICY | DAYS_OF_SUPPLY {'target_dos': 14, 'trigger_dos': 7} |
| HIGH | L00408 | SERVICE_PROBLEM | READY_WITH_CONSERVATIVE_POLICY | DAYS_OF_SUPPLY {'target_dos': 14, 'trigger_dos': 7} |
| HIGH | L00409 | SERVICE_PROBLEM | READY_WITH_CONSERVATIVE_POLICY | DAYS_OF_SUPPLY {'target_dos': 14, 'trigger_dos': 7} |
| HIGH | L00412 | SERVICE_PROBLEM | READY_WITH_CONSERVATIVE_POLICY | DAYS_OF_SUPPLY {'target_dos': 14, 'trigger_dos': 7} |
| HIGH | L00528 | SERVICE_PROBLEM | READY_WITH_CONSERVATIVE_POLICY | DAYS_OF_SUPPLY {'target_dos': 14, 'trigger_dos': 7} |
| HIGH | L00530 | SERVICE_PROBLEM | READY_WITH_CONSERVATIVE_POLICY | DAYS_OF_SUPPLY {'target_dos': 14, 'trigger_dos': 7} |
| HIGH | L00909 | SERVICE_PROBLEM | READY_WITH_CONSERVATIVE_POLICY | DAYS_OF_SUPPLY {'target_dos': 14, 'trigger_dos': 7} |
| MEDIUM_LOW | L00006 | SERVICE_PROBLEM | LEAD_TIME_DEPENDENT | DAYS_OF_SUPPLY {'target_dos': 7, 'trigger_dos': 3} |
| MEDIUM_LOW | L00054 | SERVICE_PROBLEM | LEAD_TIME_DEPENDENT | DAYS_OF_SUPPLY {'target_dos': 7, 'trigger_dos': 3} |
| MEDIUM_LOW | L00175 | SERVICE_PROBLEM | LEAD_TIME_DEPENDENT | DAYS_OF_SUPPLY {'target_dos': 7, 'trigger_dos': 3} |
| MEDIUM_LOW | L00217 | SERVICE_PROBLEM | LEAD_TIME_DEPENDENT | DAYS_OF_SUPPLY {'target_dos': 7, 'trigger_dos': 3} |
| MEDIUM_LOW | L01667 | SERVICE_PROBLEM | LEAD_TIME_DEPENDENT | DAYS_OF_SUPPLY {'target_dos': 7, 'trigger_dos': 3} |
| KEEP_CURRENT | L00002 | NEITHER | KEEP_CURRENT | — |
| KEEP_CURRENT | L00058 | NEITHER | KEEP_CURRENT | — |
| KEEP_CURRENT | L00063 | NEITHER | KEEP_CURRENT | — |
| KEEP_CURRENT | L00234 | NEITHER | KEEP_CURRENT | — |
| KEEP_CURRENT | L00503 | NEITHER | KEEP_CURRENT | — |

La trazabilidad de cada caso apunta a `product_summary.jsonl` + `policy_metrics.jsonl`; no se generó una nueva traza HANA.

## 8. Product families

Se resolvieron familias para 100/100 usando `U_LINEA` o `ItmsGrpCod`; hay 15 grupos con al menos 2 productos. En 2 grupos la política común no empeora >5% el regret medio; en 13 la comparación no es completa porque algún producto conserva CURRENT sin regret comparable. No se agrupa si degrada el desempeño individual.

## 9. Product physical master data

| Campo | Cobertura |
|---|---:|
| largo | 0/100 (0.0%) |
| ancho | 0/100 (0.0%) |
| alto | 0/100 (0.0%) |
| volumen o dimensiones completas | 0/100 (0.0%) |
| peso | 1/100 (1.0%) |
| packaging físico | 1/100 (1.0%) |
| UoM packaging | 0/100 (0.0%) |
| packaging utilizable | 1/100 (1.0%) |
| UoM inventario/compra/venta | 100/100 (100.0%) |
| unidades por caja >1 | 0/100 (0.0%) |

`MISSING_PHYSICAL_MASTER_DATA`: 100/100 no tienen dimensión/volumen utilizable; 99/100 no tienen peso positivo; 99/100 no tienen packaging físico utilizable. UoM base existe 100/100, pero no representa capacidad.

**PRODUCT_PHYSICAL_DATA** = datos por producto. **WAREHOUSE_CAPACITY_DATA** = faltan m³ útiles, posiciones, racks, capacidad por zona, peso máximo y restricciones en `OWHS`; no se hizo optimización volumétrica.

## 10. Inventory value

`INVENTORY_VALUE=NOT_READY`, `AVG_INVENTORY_VALUE=NOT_READY`, `MAX_INVENTORY_VALUE=NOT_READY`, `CAPITAL_DELTA=NOT_READY`. `OITM.AvgPrice` positivo: 0/100; `OITW` tiene observaciones actuales, pero no una serie histórica validada para valorizar inventario simulado. No se inventa valorización.

## 11. Lead-time data capture

Diseño mínimo futuro, no implementado:

```text
dispatch_timestamp
receipt_timestamp
DocEntry / transfer_id
source_warehouse
destination_branch
```

Opcional `shipment_id/load_id` solo si una carga contiene múltiples OWTR. Reglas: `receipt_timestamp >= dispatch_timestamp`; cargas cerradas sin timestamps son inválidas; timezone obligatorio; cambios post-cierre solo con auditoría. Después: `OBSERVED_LT` por ruta con median/p75/p90 y backtest sustituyendo `ASSUMED_LT`.

## 12. Gate closure

- SAP/HANA: `SAP_WRITE_COUNT=0`; no transferencias ni parámetros productivos.
- Resource safety: PASS, `MAX_WORKERS=1`, 0 abortos.
- La demanda es `OBSERVED_DEMAND_ONLY`; stockout no equivale a venta perdida confirmada.
- Artefactos externos: `branch_replenishment_policy_selection/v1/` según `gate_result.json`.

## Veredicto

`TELCHI_REPLENISHMENT_POLICY_SELECTION_UNCERTAIN_LT_V1_PASS`

Next gate: `GATE 7 — PILOT REPLENISHMENT POLICY DESIGN`, sin escribir SAP; captura física en paralelo.
