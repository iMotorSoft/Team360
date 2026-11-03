# Foundation SQL Comparison

Se ejecutó cada operación candidata y un algoritmo SQL independiente sobre CURRENT verificado. Permisos del usuario se prueban aparte: esta comparación de auditoría no autoriza exposición por el handler.

Latest usa ROW_NUMBER frente a LIMIT; coverage usa fechas distintas ordenadas y suma de conteos por fecha frente a MIN/MAX/COUNT. No se copió el builder como oracle. Misma población explícita: facturas activas N, SAP_B1_HANA, fecha no nula.

Foundation `foundation_afd08d9eca6a725be53cdc3f9d5709c9`, snapshot 1408. Cobertura activa cuenta 330429, no 330443 de la sonda histórica con todos los estados: diferencia de población deliberada. Última fecha 2026-09-24; último mes con filas 2026-09; no se certifica agosto ni septiembre completos.

SQL fuente, parámetros, filas, latencias y binding completos en [foundation_comparison.json](foundation_comparison.json). No hay cantidades, unidades, importes, signos ni monedas en el nuevo contrato: comparación monetaria/física NOT_APPLICABLE, no PASS inventado.

## sales.latest_documents

Paridad exacta read-only de filas, fechas, IDs, estados, límites y orden. No equivale a BUSINESS_PASS HTTP autorizado.

Servicio (137.544 ms), parámetros `['SAP_B1_HANA', 'N', 10]`:

```sql
SELECT source_system,doc_entry,doc_num,doc_date,canceled
FROM (SELECT * FROM telchi.atomic."sales_document" AT (VERSION => 1408))
WHERE source_system=? AND canceled=? AND doc_date IS NOT NULL
ORDER BY doc_date DESC,CAST(doc_entry AS BIGINT) DESC,doc_entry DESC LIMIT ?
```

Referencia independiente (180.651 ms), parámetros `[10]`:

```sql
WITH ordered AS (
                SELECT source_system,doc_entry,doc_num,doc_date,canceled,
                       ROW_NUMBER() OVER (ORDER BY doc_date DESC, CAST(doc_entry AS BIGINT) DESC,doc_entry DESC) AS position
                FROM (SELECT * FROM telchi.atomic."sales_document" AT (VERSION => 1408)) WHERE canceled='N' AND source_system='SAP_B1_HANA' AND doc_date IS NOT NULL)
                SELECT source_system,doc_entry,doc_num,doc_date,canceled FROM ordered WHERE position<=? ORDER BY position
```

Resultado: `[{"source_system": "SAP_B1_HANA", "doc_entry": "11532517", "doc_num": "260192728", "doc_date": "2026-09-24T00:00:00", "canceled": "N"}, {"source_system": "SAP_B1_HANA", "doc_entry": "11532516", "doc_num": "260192727", "doc_date": "2026-09-24T00:00:00", "canceled": "N"}, {"source_system": "SAP_B1_HANA", "doc_entry": "11532515", "doc_num": "260192726", "doc_date": "2026-09-24T00:00:00", "canceled": "N"}, {"source_system": "SAP_B1_HANA", "doc_entry": "11532514", "doc_num": "260192725", "doc_date": "2026-09-24T00:00:00", "canceled": "N"}, {"source_system": "SAP_B1_HANA", "doc_entry": "11532513", "doc_num": "260739131", "doc_date": "2026-09-24T00:00:00", "canceled": "N"}, {"source_system": "SAP_B1_HANA", "doc_entry": "11532512", "doc_num": "260192724", "doc_date": "2026-09-24T00:00:00", "canceled": "N"}, {"source_system": "SAP_B1_HANA", "doc_entry": "11532511", "doc_num": "260192723", "doc_date": "2026-09-24T00:00:00", "canceled": "N"}, {"source_system": "SAP_B1_HANA", "doc_entry": "11532510", "doc_num": "260192722", "doc_date": "2026-09-24T00:00:00", "canceled": "N"}, {"source_system": "SAP_B1_HANA", "doc_entry": "11532509", "doc_num": "260192721", "doc_date": "2026-09-24T00:00:00", "canceled": "N"}, {"source_system": "SAP_B1_HANA", "doc_entry": "11532508", "doc_num": "260739130", "doc_date": "2026-09-24T00:00:00", "canceled": "N"}]`. Diferencias: ninguna.

## sales.coverage

Paridad exacta read-only de filas, fechas, IDs, estados, límites y orden. No equivale a BUSINESS_PASS HTTP autorizado.

Servicio (64.112 ms), parámetros `['SAP_B1_HANA', 'N']`:

```sql
SELECT MIN(doc_date) AS first_date,MAX(doc_date) AS last_date,COUNT(*) AS documents
FROM (SELECT * FROM telchi.atomic."sales_document" AT (VERSION => 1408)) WHERE source_system=? AND canceled=? AND doc_date IS NOT NULL
```

Referencia independiente (48.973 ms), parámetros `[]`:

```sql
SELECT doc_date,COUNT(*) AS n FROM (SELECT * FROM telchi.atomic."sales_document" AT (VERSION => 1408))
                WHERE canceled='N' AND source_system='SAP_B1_HANA' AND doc_date IS NOT NULL
                GROUP BY doc_date ORDER BY doc_date
```

Resultado: `[{"first_date": "2022-03-31T00:00:00", "last_date": "2026-09-24T00:00:00", "documents": 330429, "latest_month_with_rows": "2026-09", "complete_month_certified": false}]`. Diferencias: ninguna.
