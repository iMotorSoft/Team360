# Foundation parity

[foundation_parity.json](foundation_parity.json) compara filas HTTP con los algoritmos SQL independientes ya acreditados. Ninguna llamada directa a capability sustituye la evidencia conversacional.

## Binding y referencia

CURRENT permaneció `foundation_afd08d9eca6a725be53cdc3f9d5709c9`, snapshot 1408. Sólo se consultó Foundation read-only; sin SAP, DDL/DML, Parquet ni cambios de publicación.

- Latest: ROW_NUMBER por DocDate/DocEntry descendentes, posiciones <=10; alternativa independiente a ORDER BY/LIMIT de la capability.
- Cobertura: fechas ordenadas y conteo por fecha; fecha extrema y suma derivadas, alternativa independiente a MIN/MAX/COUNT del servicio.
- Universo: SAP_B1_HANA, OINV cabeceras activas canceled=N y DocDate no nulo; excluye notas de crédito, no representa ventas netas.
- B01: diez identificadores, referencias, fechas, orden y cantidad coinciden exactamente. Primer DocEntry `11532517`, último `11532508`.
- B02/B03: primera fecha `2022-03-31T00:00:00`, última `2026-09-24T00:00:00`; `330429` documentos; mes `2026-09`; complete_month_certified=False.
- B04 primera lista también coincide; segunda pregunta no consulta ni simula una página.
- Permisos, capability, parámetros, estado, correlación, fuente y snapshot constan por B01–B04 en JSON. Cada ejecución nueva hizo una invocación de capability/una query empresarial Foundation; consultas internas de metadatos/conexión no se presentan como queries empresariales.

## Resultado

DATA_PASS y SEMANTIC_PASS se restringen al universo documental definido; BUSINESS_RUNTIME_PASS exige además respuesta HTTP real y AUTH_PASS efectivo, no importe neto ni completitud comercial inferidos.

B01/B02/B03: paridad exacta y respuestas empresariales verificadas. No se declararon métricas monetarias, marcas ni filtros comerciales adicionales.
