# May 2026 Foundation reconciliation

CURRENT efectivo fue confirmado sin modificarlo: `foundation_afd08d9eca6a725be53cdc3f9d5709c9`, commit snapshot 1408. La extracción independiente cotejó cada documento y no reutilizó la agregación del servicio.

| Mes | Facturación BS | NC BS | Neto documental BS | Facturas / NC activas |
| --- | --- | --- | --- | --- |
| 2026-05 | 8761459.220000 | 209380.030000 | 8552079.190000 | 36242 / 245 |
| 2026-06 | 10033501.020000 | 270007.350000 | 9763493.670000 | 35360 / 261 |

[foundation_reconciliation.json](foundation_reconciliation.json) conserva SQL, parámetros, grupos por moneda/estado/source, documentos únicos, hashes de filas, latencias y diferencias cero. Mayo usa [2026-05-01, 2026-06-01); junio [2026-06-01, 2026-07-01).

Control 1: DocTotal, N, DocDate y NC siguen el contrato histórico. Control 2: grano único por fuente/documento y tipo; sin joins ni duplicación por líneas. Control 3: segundo SQL sin agregación recupera cabeceras, sumadas mediante Decimal en Python; comparado con SQL agregado y luego con el servicio/HTTP.

La factura anulada original Y y reversa C de mayo aparecen en dos grupos de dos documentos, 740,22 BS por grupo: quedan fuera del valor válido. Todos los demás grupos y NC están en el JSON; no se ocultan exclusiones ni se suman monedas diferentes.

Resultado PASS para reproducción del total documental seleccionado. CONDITIONAL respecto a cobertura empresarial completa y desglose fiscal, explícitamente fuera de esta certificación. No se extrapola la comparación a SAP actual ni se compara un MTD corporativo con el total compañía de otro snapshot.
