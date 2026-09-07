# TELCHI SAP — HALLAZGOS CRÍTICOS: ANULACIONES

**Módulo:** Telchi SAP
**Capa:** DataScience — Temporalidad SAP
**Fecha:** 2026-08-23
**Estado:** INVESTIGACIÓN INICIAL COMPLETA

---

## HALLAZGO 1: 93.4% DE ANULACIONES OCURREN 31-90 DÍAS DESPUÉS

### Distribución de Timing de Anulación

| Bucket | Count | % | Monto |
|--------|-------|---|-------|
| 0 días (mismo día) | 40 | 3.6% | $37,855 |
| 1-7 días | 3 | 0.3% | $4,367 |
| 8-30 días | 29 | 2.6% | $31,511 |
| **31-90 días** | **1,040** | **93.4%** | **$526,214** |
| 91-365 días | 2 | 0.2% | $9,777 |
| **TOTAL** | **1,114** | **100%** | **$609,724** |

### Implicación

Si solo miramos `DocDate`, **perdemos el 93.4% de las anulaciones** que ocurren en el siguiente trimestre. Esto invalida cualquier análisis que no contemple la temporalidad de anulaciones.

---

## HALLAZGO 2: UpdateDate + UpdateTS = FECHA DE ANULACIÓN

### Precisión Disponible

- **UpdateDate**: Fecha de la última actualización del documento
- **UpdateTS**: Timestamp con precisión de segundos (formato HHMMSS)

### Cobertura

- **100% de facturas anuladas (Y)** tienen UpdateTS disponible
- **100% de facturas reversión (C)** tienen UpdateTS disponible

### Ejemplo Real

```
Factura Original (Y):
  DocEntry:    11291985
  DocNum:      260301114
  CardCode:    C001241
  DocDate:     2026-05-30
  UpdateDate:  2026-06-16  ← FECHA DE ANULACIÓN
  UpdateTS:    144311      ← HORA: 14:43:11
  DocTotal:    225.00

Documento Reversión (C):
  DocEntry:    11292216
  DocNum:      260101465
  DocDate:     2026-05-30  ← Fecha del documento reversión
  TransId:     15742906    ← Diferente al original (15773119)
```

### Regla Derivada

```
cancellation_date = Y.UpdateDate
cancellation_time = Y.UpdateTS (formato HHMMSS)
cancellation_timestamp = Y.UpdateDate + Y.UpdateTS
```

---

## HALLAZGO 3: PARES Y/C VINCULADOS

### Patrón de Vinculación

| Campo | Y (Original) | C (Reversión) | ¿Coincide? |
|-------|--------------|---------------|------------|
| CardCode | C001241 | C001241 | ✓ |
| DocTotal | 225.00 | 225.00 | ✓ |
| DocEntry | 11291985 | 11292216 | ✗ (diferente) |
| DocNum | 260301114 | 260101465 | ✗ (diferente) |
| TransId | 15773119 | 15742906 | ✗ (diferente) |
| DocDate | 2026-05-30 | 2026-05-30 | ✓ |
| UpdateDate | 2026-06-16 | 2026-05-30 | ✗ (diferente) |

### Regla de Vinculación

```sql
Y."CardCode" = C."CardCode"
AND Y."DocTotal" = C."DocTotal"
AND C."CANCELED" = 'C'
AND ABS(DAYS_BETWEEN(Y."UpdateDate", C."DocDate")) <= 7
```

---

## HALLAZGO 4: ANULACIONES TARDÍAS EXISTEN

### Casos >90 Días

| Factura | DocDate | UpdateDate | Días |
|---------|---------|------------|------|
| ??? | 2024-05-14 | 2024-10-04 | 143 |
| ??? | 2024-07-10 | 2024-10-04 | 86 |

**Impacto:** Estas anulaciones afectan ventas históricas de hace meses.

---

## HALLAZGO 5: PAGOS ANULADOS EXISTEN

### Volume

- **Pagos válidos (N):** 1,782,379 ($495M)
- **Pagos anulados (Y):** 10,689 ($14.5M)
- **Tasa de anulación:** 0.6%

### Implicación

Los pagos anulados deben excluirse del análisis de cobranza válida.

---

## HALLAZGO 6: RECONCILIACIONES ANULADAS EXISTEN

### Volume

- **Reconciliaciones válidas (N):** 2,038,861 ($7.1B)
- **Reconciliaciones anuladas (Y):** 14,849 ($470M)
- **Reconciliaciones reversión (C):** 14,849 ($470M)
- **Tasa de anulación:** 0.7%

### Implicación

Las reconciliaciones anuladas deben excluirse del cálculo de settlement.

---

## MODELO TEMPORAL PROPUESTO

### Tres Vistas

```
1. AS-REPORTED (Histórica)
   - Qué sabíamos en fecha X
   - Usa DocDate para filtrar
   - NO incluye anulaciones futuras

2. RESTATED (Verdad Económica Actual)
   - Qué es verdad HOY
   - Usa cancellation_date para excluir anuladas
   - SÍ incluye anulaciones conocidas

3. EVENTS (Movimientos)
   - Qué ocurrió en cada período
   - Incluye creaciones Y anulaciones
   - Permite reconstruir timeline
```

### Campos Derivados por Factura

```sql
-- Original fields
OINV."DocEntry",
OINV."DocDate",
OINV."DocTotal",
OINV."CANCELED",

-- Derived temporal fields
CASE WHEN OINV."CANCELED" = 'Y'
     THEN OINV."UpdateDate"
     ELSE NULL END AS "CancellationDate",

CASE WHEN OINV."CANCELED" = 'Y'
     THEN OINV."UpdateTS"
     ELSE NULL END AS "CancellationTime",

DAYS_BETWEEN(OINV."DocDate", OINV."UpdateDate") AS "DaysToCancellation",

-- Lifecycle
'CREATED' AS "Event",
OINV."DocDate" AS "EventDate"
```

---

## SQL DE DERIVACIÓN DE FECHA DE ANULACIÓN

```sql
-- Cancellation date derivation
SELECT
    OINV."DocEntry",
    OINV."DocNum",
    OINV."CardCode",
    OINV."DocDate",
    OINV."DocTotal",
    OINV."CANCELED",
    OINV."UpdateDate" AS "CancellationDate",
    OINV."UpdateTS" AS "CancellationTimestamp",
    CASE
        WHEN OINV."CANCELED" = 'Y'
        THEN DAYS_BETWEEN(OINV."DocDate", OINV."UpdateDate")
        ELSE 0
    END AS "DaysToCancellation"
FROM TELCHI."OINV"
WHERE OINV."CANCELED" IN ('Y', 'C')
```

---

## PRÓXIMOS PASOS

1. **Crear SQL de cancellation lifecycle** — Timeline completa por factura
2. **Crear SQL de payment lifecycle** — Timeline de pagos por factura
3. **Crear SQL de as-of AR reconstruction** — AR por fecha histórica
4. **Crear test de marzo → junio** — Validar que anulación tardía se detecta
5. **Crear SQL de cohort collections** — Curvas de cobranza
6. **Crear SQL de seller + collection** — Métricas cruzadas

---

## CRITERIO DE ÉXITO

Para considerar PASS el modelo temporal:

- [ ] Fecha de anulación derivada de SAP (UpdateDate)
- [ ] Anulación tardía (>30 días) detectable
- [ ] Vista AS-REPORTED reproducible
- [ ] Vista RESTATED excluye anuladas
- [ ] Timeline de eventos por documento
- [ ] Test marzo → junio PASS
