# TELCHI SAP — ANÁLISIS: FACTURAS ANULADAS EN MES DIFERENTE

**Fecha:** 2026-08-23
**Estado:** ANÁLISIS COMPLETO

---

## HALLAZGO PRINCIPAL

**1,067 facturas fueron anuladas en un mes diferente al original.**

La mayoría **NO tienen factura de reemplazo**.

---

## 1. RESUMEN POR MES

| Mes Original | Mes Anulación | Facturas | Monto |
|--------------|---------------|----------|-------|
| 2024-05 | 2024-06 | 134 | $108,397.24 |
| 2024-05 | 2024-07 | **843** | **$376,265.93** |
| 2024-04 | 2024-06 | 69 | $53,340.86 |
| 2024-06 | 2024-07 | 13 | $4,877.96 |
| Otros | - | 8 | $9,295.76 |

**HALLAZGO CRÍTICO: 843 facturas de mayo 2024 fueron anuladas en julio 2024.**

---

## 2. ESTADO DE REEMPLAZO

| Estado | Facturas | Monto |
|--------|----------|-------|
| **SIN REEMPLAZO** | **1,064** | **$552,922.99** |
| CON REEMPLAZO | 3 | $5,792.76 |

**1,064 facturas (99.7%) NO tienen factura de reemplazo.**

---

## 3. IMPLICACIÓN CONTABLE

### Escenario: Factura de mayo anulada en julio sin reemplazo

```
MAYO:
- Factura emitida: $X
- Ventas registradas: $X
- Impuestos: $X

JULIO (anulación):
- Factura anulada: -$X
- Ventas reversadas: -$X
- Impuestos reversados: -$X
```

### Impacto en Reportes

| Período | Ventas Registradas | Ventas Netas (hoy) |
|---------|-------------------|-------------------|
| Mayo 2024 | Incluye facturas anuladas | Excluye facturas anuladas |
| Julio 2024 | Incluye reversión | Excluye reversión |

**Si se reporta solo por DocDate:**
- Mayo mostraría ventas infladas
- Julio mostraría la reversión

**Si se reporta por estado actual (restated):**
- Mayo mostraría las ventas válidas actuales
- No habría reversión en julio

---

## 4. PREGUNTA CRÍTICA

**¿Dónde está la mercadería de estas 1,064 facturas?**

Si las facturas no tienen reemplazo:
1. ¿Se devolvió la mercadería?
2. ¿Se entregó sin factura?
3. ¿Hay un problema de conciliación?

---

## 5. PRÓXIMOS PASOS

1. Investigar el lote de mayo 2024 (843 facturas)
2. Verificar si hay devoluciones (ODRN)
3. Verificar el estado de las entregas
4. Entender por qué no hay facturas de reemplazo

---

**Telchi SAP — Análisis de Facturas Anuladas en Mes Diferente — V1**
