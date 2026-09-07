# TELCHI SAP — INVESTIGACIÓN: LOTE MAYO 2024

**Fecha:** 2026-08-23
**Estado:** INVESTIGACIÓN COMPLETA

---

## HALLAZGO PRINCIPAL

**843 facturas de mayo 2024 fueron anuladas en julio 2024 en un evento de masiva.**

---

## 1. CARACTERÍSTICAS DEL LOTE

| Característica | Valor |
|----------------|-------|
| Facturas originales | 843 |
| Mes original | Mayo 2024 |
| Mes anulación | Julio 2024 |
| Monto total | $376,265.93 |
| **Con entrega** | **0 (0%)** |
| **Sin entrega** | **843 (100%)** |
| PaidToDate = DocTotal | Sí (todas) |

---

## 2. HALLAZGOS CLAVE

### 2.1 SIN ENTREGA

**Ninguna de las 843 facturas tiene entrega asociada.**

Esto significa:
- La mercadería **NUNCA SALIÓ** del inventario
- No hay impacto de stock
- No hay devolución necesaria

### 2.2 COBRO COMPLETO

**Todas las facturas tienen PaidToDate = DocTotal.**

Esto significa:
- El dinero **FUE RECIBIDO**
- Las facturas estaban completamente pagadas
- No hay deuda pendiente de estas facturas

### 2.3 NOTAS DE CRÉDITO EXISTENTES

Los clientes de este lote tienen notas de crédito:

| Mes | Cantidad | Monto |
|-----|----------|-------|
| Mayo 2024 | 35 | $25,782.78 |
| Junio 2024 | 8 | $22,234.53 |
| Julio 2024 | 23 | $103,943.63 |
| **Total** | **66** | **$151,960.94** |

---

## 3. PATRÓN IDENTIFICADO

### 3.1 Facturas de Venta sin Entrega

Las 843 facturas son **facturas de venta directa sin entrega de mercadería**. Esto puede significar:

1. **Ventas de servicios** (no requieren entrega física)
2. **Ventas de contado** (pago inmediato sin entrega)
3. **Errores de facturación** (facturas creadas por error)

### 3.2 Anulación Masiva

El hecho de que **843 facturas fueran anuladas el mismo día (16 de julio 2024)** sugiere:

1. **Proceso de reconciliación** - Se revisaron facturas de mayo
2. **Corrección de errores** - Se encontraron facturas incorrectas
3. **Cierre de período** - Se ajustaron las cuentas de mayo

### 3.3 Cobro Completo

Que todas las facturas tengan cobro completo significa que:

1. El dinero **fue recibido** por estas facturas
2. Las notas de crédito pueden haber sido usadas para **devolver el dinero**
3. O las facturas eran **válidas pero incorrectas** y se corrigieron

---

## 4. IMPLICACIÓN CONTABLE

### 4.1 Para Mayo 2024

| Concepto | Impacto |
|----------|---------|
| Ventas brutas | Incluye las 843 facturas |
| Ventas netas (hoy) | Excluye las 843 facturas |
| Diferencia | $376,265.93 |

### 4.2 Para Julio 2024

| Concepto | Impacto |
|----------|---------|
| Reversión | -$376,265.93 |
| Notas de crédito | +$103,943.63 |
| Neto julio | -$272,322.30 |

### 4.3 Para el Análisis Actual

Si se reporta por **DocDate** (histórico):
- Mayo mostraría ventas infladas
- Julio mostraría la reversión

Si se reporta por **estado actual** (restated):
- Mayo mostraría las ventas válidas actuales
- No habría reversión en julio

---

## 5. PREGUNTAS ABIERTAS

1. **¿Por qué se anularon 843 facturas simultáneamente?**
   - ¿Fue un proceso de reconciliación?
   - ¿Se encontraron errores sistemáticos?
   - ¿Fue un ajuste de cierre de período?

2. **¿Qué pasó con el dinero cobrado?**
   - ¿Se devolvió a los clientes?
   - ¿Se aplicó a otras facturas?
   - ¿Se quedó como crédito a favor?

3. **¿Las notas de crédito están relacionadas?**
   - ¿Son devoluciones de este lote?
   - ¿Son de otros conceptos?

---

## 6. RECOMENDACIONES

1. **Investigar la causa de la anulación masiva**
2. **Verificar si el dinero fue devuelto**
3. **Confirmar que las notas de crédito están relacionadas**
4. **Documentar este evento como caso especial**

---

## 7. IMPACTO EN EL ANÁLISIS DE VENTAS

Este hallazgo es **CRÍTICO** para el análisis de ventas:

- **1,064 facturas** (99.7%) de las anuladas en mes diferente **NO tienen reemplazo**
- **843 facturas** son de un **evento de anulación masiva** en julio 2024
- Estas facturas **no tienen entrega** (no afectan stock)
- Estas facturas **tienen cobro completo** (el dinero fue recibido)

**Conclusión:** Las anulaciones en mes diferente representan principalmente un **evento de reconciliación/corrección**, no problemas operativos individuales.

---

**Telchi SAP — Investigación del Lote Mayo 2024 — V1**
