# Security regression

Foundation `foundation_afd08d9eca6a725be53cdc3f9d5709c9`, snapshot **1408**, CURRENT efectivo confirmado; solo DEV y lectura. Sin SAP, modificaciones canónicas, reingestión, deploy ni cambio de modelo.

Guard obligatorio committed is True: P14 propuesta inválida tras un resultado previo, cero ejecución y estado anterior preservado. P15 ItemCode inventado: rechazo, cero ejecución. product_context no es un path permitido al modelo; selección solo entre resultados reales y validados de la conversación actual.

P13 permiso específico faltante: denegación antes de Foundation; Console real distingue piloto autorizado y administrador sin grants. Permisos efectivos se comprueban en cada turno y por cada operación, no por teléfono. P18 preserva contexto después de reinicio; cambiar período consulta los mismos IDs sin repetir búsqueda.

Pruebas unitarias: texto/códigos/límites/períodos, SQL literal parametrizado, context injection, IDs no encontrados, guard comprometido y no comprometido, catálogo específico/RBAC narrow. La suite focalizada final incluye 200 PASS. Nunca se suman unidades desconocidas, DocTotal por producto ni NC silenciosas.

Host compartido: SAFE inicialmente, BUSY_BUT_SAFE al final; ejecución secuencial, dos threads DuckDB y 512 MB, un servidor temporal a la vez, sin browsers. Todos los servidores propios se reapearon; cero procesos ajenos terminados. Milvus/LiteLLM no son dependencias de esta ruta directa. Sin abortos ambientales; el fallo inicial del launcher fixture fue un defecto del harness corregido, no ambiental.
