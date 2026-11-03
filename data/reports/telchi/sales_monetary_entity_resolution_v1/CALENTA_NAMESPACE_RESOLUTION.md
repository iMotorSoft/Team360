# Calenta namespace resolution

Calenta tiene productos y operaciones documentadas. No se trata como palabra sin contexto, cliente demostrado ni marca única; la consulta empresarial permanece bloqueada por un crosswalk no acreditado.

La autoridad detallada recuperada es [CALENTA_RESOLUTION previa](../foundation_query_activation_v1/CALENTA_RESOLUTION.md). Conserva IDs canónicos, nombres, SellItem, aliases y cantidades/LineTotal por SKU; se reutiliza porque CURRENT sigue siendo el mismo snapshot 1408.

- Reference SAP_HANA: L02822, L02823, L02877, L03035, L03648, L03649, L03650 y L03658, con sus canonical_product_id originales. L02877 y L03648 son KG con SellItem=N.
- Atomic sales_line: SAP_B1_HANA y item_code fuente. El join literal de namespace queda vacío; no prueba ausencia de ventas.
- Cuatro SKUs tienen líneas de mayo documentadas: L02822, L02823, L03649, L03658. Cantidades y LineTotal nativos no son neto por producto ni conversión física.
- Aliases AMBIGUOUS y MAPPED de presentaciones no acreditan una única familia Calenta/Forte; LIKE también encuentra calentadores ajenos.

SQL de evidencia: `calenta_exact_skus_may` en [sondas históricas selladas](../historical_business_query_inventory_v1/foundation_business_cases.json), y registry `sales_by_item`, HQ-fbdda4165b64b30810 / HS-56822a0ce444d328eb. Conserva ItemCode exacto y unión (source_system, DocEntry) cabecera/línea; no filtra negocio por texto libre ni usa un candidato como CURRENT.

Brecha precisa: falta acreditar y versionar la correspondencia (SAP_B1_HANA, item_code) → (SAP_HANA, item_code, canonical_product_id), su unicidad y provenance. Además debe decidirse presentación o conjunto comercial Calenta vs Forte, sin incluir automáticamente KG internos.

No se creó mapping ni alias ficticio, no se ejecutó sales.latest_by_entity y no se provisionó un permiso sin operación defendible. M04/M11 conservaron la mención y ejecutaron cero consultas. ENTITY_RESOLUTION=PARTIAL; CALENTA_BUSINESS_QUERY=BLOCKED. Próximo paso focalizado: acreditar el crosswalk de estos ocho SKUs y pedir selección concreta de presentaciones, sin otro discovery universal.
