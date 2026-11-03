# ItemCode sales relation

Foundation `foundation_afd08d9eca6a725be53cdc3f9d5709c9`, snapshot **1408**, CURRENT efectivo confirmado; solo DEV y lectura. Sin SAP, modificaciones canónicas, reingestión, deploy ni cambio de modelo.

Reference SAP_HANA y Atomic SAP_B1_HANA son etiquetas de productores de la misma compañía TELCHI. OITM.ItemCode e INV1.ItemCode conservan la misma clave natural; no son canonical_product_id. Se filtra Reference al único namespace SAP de esa compañía y las líneas a su productor INV1, luego se une por ItemCode exacto. No se transforma ningún ID ni se crea crosswalk.

715.046 líneas: 715.045 con relación, una con ItemCode nulo (excluida); 6.581 ItemCodes no nulos distintos, todos presentes en catálogo. Cero productos no nulos de ventas ausentes del catálogo. El JOIN no multiplica filas porque el catálogo es único por clave dentro de SAP_HANA.

Grano línea: (source_system, DocEntry, LineNum); cabecera: (source_system, DocEntry). Censos iniciales sin duplicados; controles runtime por productos y cabeceras. Para las coincidencias de Calenta, sin líneas huérfanas ni multiplicación. El control rechaza vínculos huérfanos antes de publicar un vacío.

Evidencia: [referencia independiente](foundation_reference.json). No se acepta el JOIN solo porque encuentre algunas filas. La brecha de aliases/brand/canonical namespaces histórica permanece fuera de esta relación natural acreditada.
