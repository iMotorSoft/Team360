# Validación SQL — C010264

Las consultas ejecutadas, parámetros y resultados íntegros están en SQL_EVIDENCE.json. FOUNDATION_BINDING.json contiene el binding y los cortes fuente.

## Fuente y seguridad

FoundationReader resolvió CURRENT antes y después de las consultas. ID foundation_afd08d9eca6a725be53cdc3f9d5709c9, snapshot 1408; tablas Atomic mediante AT VERSION 1408. Attachment READ_ONLY comprobado. Sin SAP, modificaciones Foundation ni latest fallback.

Reference y sus crosswalks se leyeron en la misma versión v2_reference_closure_2088d5885204313a, no desde alias latest. Todos los joins SAP usan source_system y claves naturales; SAP_HANA es el catálogo, SAP_B1_HANA las facturas.

## Garantías ejecutadas

La identidad fue resuelta por código y namespace con una fila. SQL comprobó unicidad de cabeceras, líneas, catálogo y clasificación empresarial; cero líneas huérfanas. La lista de compras y frecuencia se cotejó con una consulta independiente por IN/semijoin, sin joins de Reference.

El número de líneas detalladas concuerda con los agregados por producto. Los importes se calculan desde cabeceras, nunca desde un join a líneas; la moneda del cliente es BS y todos sus documentos tienen importe. Se conservan monedas y cancelaciones del universo global.

## Contratos y limitaciones

Se reutilizan sales_query.py (DocTotal OINV activas menos ORIN activas, BS) y product_sales_query.py (frecuencia/ocurrencias de facturas, sin atribución monetaria ni UoM física de línea). Cantidades se conservan por línea en CUSTOMER_INVOICE_LINES.csv, sin total físico; UoM del catálogo no sustituye UoM documental.

Corte fuente ventas: 2026-09-24T13:53:45.185438+00:00; NC: 2026-09-24T13:12:12.361426+00:00. El 24/09 no es un día completo. Los límites observados no certifican integridad histórica. Fecha global Foundation 28/09 no implica cobertura de ventas hasta ese día.

## Garantías pendientes del universo

Las consultas acreditan ausencia de relaciones de pertenencia y estado provisional del portfolio; no acreditan U. Top 20 global, Top 20 cliente, diferencias de conjuntos y ausencia de compras de U quedan NOT_EXECUTED / BLOCKED_MEMBERSHIP_EVIDENCE. No se declara PASS ni se confunde un CSV vacío con cero oportunidades.
