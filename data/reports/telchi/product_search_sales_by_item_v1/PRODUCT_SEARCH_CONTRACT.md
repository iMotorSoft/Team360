# Product search contract

Foundation `foundation_afd08d9eca6a725be53cdc3f9d5709c9`, snapshot **1408**, CURRENT efectivo confirmado; solo DEV y lectura. Sin SAP, modificaciones canónicas, reingestión, deploy ni cambio de modelo.

Operación `products.search`, permiso `telchi.products.search.read.v1`. Texto 1..120 caracteres normalizados, entrada cruda ≤240; rechaza controles. Límite 1..20. Mayúsculas, acentos, espacios redundantes y coincidencias parciales/código; nombres originales preservados.

SQL parametrizado con contains, no patrones SQL interpolados. Ranking estable: código exacto, palabra/frase completa, substring; desempate por ItemCode. Limit+1 detecta truncamiento. No elige arbitrariamente ante exceso o múltiples matches solo parciales.

Assistant consulta hasta veinte opciones y conserva contexto verificado. Selección automática de ventas: mejor rango, SellItem=Y (código exacto permite consultar un insumo explícito); los IDs seleccionados pertenecen exclusivamente al resultado real. Una búsqueda vacía informa catálogo/alcance sin inventar alternativas.

Tiempo máximo por worker 30 s; dos threads, 512 MB, temp sin spill, conexión read-only y binding exacto. Evidencia: product_sales_query.py, pruebas focalizadas, HTTP P01/P07/P08/P09.
