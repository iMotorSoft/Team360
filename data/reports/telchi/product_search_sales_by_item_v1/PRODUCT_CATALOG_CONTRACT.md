# Product catalog contract

Foundation `foundation_afd08d9eca6a725be53cdc3f9d5709c9`, snapshot **1408**, CURRENT efectivo confirmado; solo DEV y lectura. Sin SAP, modificaciones canónicas, reingestión, deploy ni cambio de modelo.

Catálogo: Reference products sellado por Foundation. Scope de esta operación: `SAP_HANA` (compañía SAP TELCHI); no mezcla Legacy ni resuelve todos los namespaces.

Clave natural: `item_code = source_native_id = _source_native_key`. `canonical_product_id` es derivado y no participa del JOIN comercial. Censo: 16.934 productos SAP únicos; cero duplicados. Fuente de nombre: sap_item_name, product_name, canonical_name, en ese orden.

Unidad disponible: sales_uom_id/inventory_uom_id de catálogo. No existe relación publicada aquí que permita presentar una etiqueta física desde esos IDs; no se deriva ni inventa. Estado: active/status/SellItem. Presentación: descripción original, sin alias ni conversión física.

Autoridad de procedencia: productores `modules/telchi/datalake/reference_update.py` (OITM_SQL y claves naturales), `create_initial.py` (_sales_candidate: ItemCode → item_code sin alteración) y `source_coverage.py` (TELCHI OINV/INV1). La equivalencia se limita a esta compañía SAP y publicación, no a fuentes homónimas.

Evidencia: [censo y schemas](foundation_reference.json).
