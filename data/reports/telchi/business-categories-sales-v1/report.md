# TelchiAI — categorías comerciales y ventas V1

Corrección interpretativa DEVELOPMENT y atribución monetaria INVESTIGATION READ ONLY. Rama `feature/console-backend-core`; sin promoción, cambios de permisos, reinicios ni WhatsApp automático.

## Interpretación aplicada

La regla genérica de productos de Luna absorbía categorías; el catálogo admitía búsqueda por producto antes de evaluar la entidad. El diagnóstico aportado por el owner y el prompt previo explican el recorrido erróneo.

- Reproducción de origen: WhatsApp del 20/10/2026, «cuanto vendimos de materia prima en septiembre», precedida por facturación de septiembre de 2026. La auditoría original fue aportada en el pedido, no extraída nuevamente aquí; no se inventa un Session ID.
- HEAD de partida: `09d2ec715a31bb88574d734eacb9f437f008624e`. Worktree preexistente preservado; sin commit/push.
- Vocabulario compacto de diez códigos/etiquetas de la taxonomía existente, sin catálogo, cantidades ni membresía. Fuente inmutable `v2_product_business_type_f9c1130d852ccb61`, taxonomy SHA-256 `47869a144029baf4862dbb0da0aa47d2dceda53cee810cd8acf7a145d95ecede`.
- Luna interpreta el significado; NO se implementa clasificador de productos por palabras. Sólo el crosswalk existente acredita membresía.
- Sin extender State Engine: el slot V2 `entity_mention={text:canonical_category_code,type:null}` conserva la categoría como intención NO ejecutable. Es una convención acotada del intérprete/catálogo, no un filtro Foundation. El texto original permanece en el turno y la propuesta en auditoría. No se inventan tipos comerciales.
- La barrera del catálogo precede a productos y globales, aun ante una propuesta EXECUTE con categoría y texto simultáneos. `execute_products` conserva su contrato; el entrypoint autorizado `execute` rechaza la categoría.
- Formatter determinístico: importe de categoría no disponible, período comprensible, sin tablas/códigos internos ni cifras de investigación. No se promete cantidad como sustituto monetario.
- Consumo productivo queda sin métrica de ventas, con categoría conservada y operación no disponible. No se agrega una métrica productiva al estado comercial; el formatter no deduce consumo sólo porque metric sea null. La pregunta original auditada conserva esa intención.
- Ambigüedad comercial real usa ASK metric; las consultas monetarias inequívocas y sus seguimientos conservan intención y período.

## Evidencia interpretativa y regresión

La sonda focal usa OpenAI Responses directo, modelo devuelto `gpt-5.6-luna`, esfuerzo devuelto `medium`, sin proxy, fallback ni herramientas. No consulta datos empresariales ni certifica RBAC vivo o transporte.

[Propuestas y checks reales](luna-r1.json): seis turnos PASS, incluido preflight mínimo real de credencial/provider/modelo. No se usaron LiteLLM/Milvus/SAP porque este flujo no los consume.

| Turno | Interpretación observada |
| --- | --- |
| Cuánto facturamos en septiembre de 2026 | sales.net_amount, septiembre completo solicitado |
| Cuánto vendimos de materia prima en septiembre | RAW_MATERIAL, sales.net_amount, mismo septiembre/año, DIRECT_UNAVAILABLE |
| ¿Y de productos terminados? | LAB_FINISHED_PRODUCT, mismo período/métrica, DIRECT_UNAVAILABLE |
| Buscame el producto L01128 | products.search, código literal, categoría ausente |
| Buscá productos que digan materia prima | products.search, texto literal, categoría ausente |
| ¿Cuánta materia prima consumimos en producción? | RAW_MATERIAL, sin métrica monetaria/documental de ventas, DIRECT_UNAVAILABLE |

Comandos desde backend:

```bash
uv run python -m modules.telchi.assistant.tests.live_business_categories --output <path-json-nuevo>
uv run pytest modules/telchi/assistant/tests/test_business_categories.py modules/telchi/assistant/tests/test_product_sales.py modules/telchi/assistant/tests/test_enterprise_context.py modules/telchi/assistant/tests/test_sales_monetary.py modules/telchi/assistant/tests/test_rejected_execution_guard.py modules/telchi/assistant/tests/test_sales_business_contract.py modules/telchi/assistant/tests/test_conversational_quality.py -q
```

La primera corrida offline señaló diez assertions incorrectas del test nuevo: EXECUTE con metric=null ya es rechazado por el State Engine. Se corrigió la expectativa, no el motor. La regresión comprueba ambas barreras. La corrida siguiente obtuvo 160 PASS / 1 skip PostgreSQL opt-in; después se añadieron dos tests de ambigüedad y continuidad. El cierre final registra la cifra actualizada en validations.json.

El archivo real r1 conserva hashes del código en esa corrida. Después sólo se generalizó el texto de indisponibilidad sin métrica para no inferir consumo desde null y se añadieron tests; no cambió el prompt, adaptador, taxonomía, State Engine ni selección del catálogo respecto de esa sonda.

## Foundation y linaje monetario

[Esquemas](foundation-schema.json) y [consultas/conciliación final](reconciliation-r2.json) conservan SQL exacto, parámetros, conteos, Decimal y linaje. r1 se preserva; r2 añade distribución del residuo y desglose de vínculos NC por categoría.

- Foundation `foundation_afd08d9eca6a725be53cdc3f9d5709c9`, snapshot de lectura 1408, base manifest 1322.
- Reference publicada `v2_reference_closure_2088d5885204313a`; crosswalk SHA-256 `7fcfef912cc8ef46868e03b56f90b61da13c08e951c453abc0483690edc36e10`. Conserva RAW_MATERIAL/PBT-006: 306 productos VALIDATED, COMBINED, sin clasificación por nombre.
- Período investigado `[2026-09-01,2026-10-01)`, por DocDate. Última factura observada 24/09; última NC 23/09. Foundation data_as_of 28/09 NO implica documentos capturados hasta el 28 ni cierre de septiembre.
- Venta y NC tienen capturas/componentes distintos; igualdad de publicación no elimina ese desfase. source_as_of/extraction_id coinciden entre cada cabecera y sus propias líneas observadas.
- Conexión DuckLake comprobada READ_ONLY, una conexión, un thread, 256 MB, sin spill. SQL sólo SELECT/DESCRIBE y ajustes de sesión propios. No SAP, DDL/DML ni cambios de CURRENT/clasificación.

## Conciliación documental

Los importes siguientes son observaciones investigativas en BS, no resultados de una capability monetaria por categoría. No se publican al formatter ni se consideran facturación neta de categoría.

| Universo activo N | Cabeceras | Líneas | DocTotal | Suma line_total | Diferencia cabeceras − líneas |
| --- | ---: | ---: | ---: | ---: | ---: |
| Facturas OINV/INV1 | 30.301 | 65.163 | 8.891.439,79 | 8.048.691,58 | 842.748,21 |
| NC ORIN/RIN1 | 224 | 1.071 | 328.670,24 | 302.320,17 | 26.350,07 |

- Join exacto dentro de cada tipo: `source_system='SAP_B1_HANA'`, `source_table` OINV↔INV1 u ORIN↔RIN1 y `doc_entry`. Grano de línea `(source_system,source_table,doc_entry,line_num)`; sin duplicación en las líneas del período, sin cabeceras activas sin líneas.
- Clasificación: namespace transaccional SAP_B1_HANA → ItemCode del crosswalk SAP_HANA; códigos únicos, 42.147 filas/42.147 códigos. No unir fuentes de otro namespace ni cruzar DocEntry entre tipos documentales.
- Cero discrepancias observadas de extracción, source_as_of o moneda entre cabecera/línea; todos los importes de este alcance son BS y parsean a DECIMAL(38,6). Esto no acredita otras monedas ni una regla cambiaria general.
- Facturas: sólo 872 concilian dentro de 0,01; 29.429 no. Residuos positivos en 28.999 y negativos en 430; máximo absoluto BS 15.926,73. No son sólo errores de redondeo.
- NC: sólo 22 concilian dentro de 0,01; 202 no. Residuos positivos en 200 y negativos en 2; máximo absoluto BS 4.528,77.
- 8.282 facturas y 121 NC contienen más de una categoría: no atribuir su DocTotal entero a cada categoría. No repartirlo proporcionalmente sin decisión empresarial y prueba contable.
- Las facturas canceladas Y y documentos de cancelación C (uno de cada, BS 87,50) quedan fuera por active N; sin convertir estados de línea en criterio de anulación documental.

## Notas de crédito, clasificación y cobertura

La resta por fecha documental puede definirse para importes registrados de líneas, pero no equivale a reconstruir venta original, devolución física ni neto financiero por categoría.

- 1.006 líneas NC con BaseType=13 enlazan exactamente a líneas INV1, mismo producto y factura activa; fechas base observadas 01–23/09. 64 líneas BaseType=-1 no tienen factura base directa; una BaseType=16 referencia devolución, cuya cadena no se acredita aquí.
- No se observaron importes negativos en estas NC. No se agrega doble resta por devolución: RIN1 y devolución no son dos ventas negativas independientes.
- RAW_MATERIAL: 526 líneas de factura, 34 productos, 495 documentos; importe registrado de líneas BS 839.582,63. Ocho líneas NC, seis productos, siete NC; BS 16.317,71. Siete líneas enlazan a factura y una es standalone BaseType=-1.
- Su diferencia aritmética BS 823.264,92 es sólo contraste investigativo de importes registrados de líneas por DocDate. NO se acredita como venta neta ni facturación; no es una respuesta comercial autorizada.
- Cobertura de join clasificador: 100% de las 65.163 líneas de facturas y 1.071 de NC observadas. No hay UNKNOWN en estas líneas; sí 23.628 UNKNOWN en el crosswalk completo. No confundir match con calidad: existen líneas PACKAGING PROVISIONAL/NAME_BASED (1.535 factura, 35 NC), que una capacidad futura debe separar de categorías acreditadas.
- Crosswalk: cero filas con valid_from/valid_to informadas. RAW_MATERIAL es clasificación actual aplicada retrospectivamente, no historia certificada. No atribuye consumo a ventas, aunque el producto también se use en producción.
- Cobertura temporal parcial: ausencia de documentos fuera de lo capturado no significa ventas cero; NC de otros períodos y reclasificaciones posteriores pueden cambiar la interpretación de una reconstrucción por factura original.
- En el SQL de evidencia, `product_mismatches` usa IS DISTINCT FROM y cuenta NULL de bases no encontradas. Para BaseType distinto de 13 son vínculos NO RESUELTOS, no discrepancias de producto demostradas; para los 1.006 vínculos encontrados el conteo es cero.

## Semántica faltante y conclusión monetaria

Foundation publica doc_total, monedas y algunos totales sistema/extranjera; las líneas de factura publican line_total y price. No publica la descomposición suficiente para conciliar impuestos/descuentos/ajustes de estas cabeceras.

- Faltan impuestos por línea/cabecera, descuentos por línea/cabecera con su base/porcentaje, fletes/gastos, redondeos documentales y reglas de asignación por categoría respaldadas por fuente. No se atribuye el residuo a un componente específico sin esos campos.
- Falta verificar formalmente la definición SAP de cada campo capturado, moneda monetaria de LineTotal frente a moneda del precio en otras divisas, precisión y conversiones; coincidencia BS local no acredita casos FX.
- Faltan tratamiento empresarial de NC standalone y vía devolución, eventual cambio de categoría entre factura y NC, exclusiones comerciales de cuentas técnicas/internas y semántica temporal (fecha NC frente a restatement de factura original).
- Una fórmula respaldada como diagnóstico es `SUM(INV1.line_total de OINV N del período y categoría) − SUM(RIN1.line_total de ORIN N del período y categoría)`, separada por moneda y clasificación. Su nombre defendible provisional es **importe registrado de líneas comerciales menos NC por fecha documental, con clasificación actual**. No es automáticamente «venta neta», «facturación documental bruta» ni ingreso contable.
- Conciliación buscada: DocTotal = líneas + componentes fuente de impuestos/gastos/ajustes − descuentos, con redondeo documental. Es una identidad a especificar/verificar, no una fórmula acreditada aquí. No está permitido resolverla ajustando proporciones hasta que cuadre.

## Contrato futuro propuesto, no implementado

Sólo se propone una capacidad horizontal de categoría. La semántica y la conciliación requieren decisión del owner antes de construir o registrar una capability.

- Input: categoría canónica acreditada y dimensión product_business_type; `[date_from,date_to_exclusive)`; moneda explícita sin conversión implícita; `metric` explícita; `classification_version` y política de calidad mínima.
- Métrica candidata a decidir: `recorded_commercial_line_amount_after_credit_lines`, con componentes factura/NC separados y etiqueta de clasificación actual. `category_net_revenue` no se propone como equivalente ni como disponible.
- Resultado propuesto: importe de líneas factura, importe de líneas NC y diferencia, moneda/base monetaria validada; definición y versión; exclusión canceladas, política NC; productos/líneas/documentos; matched/unmatched/UNKNOWN/PROVISIONAL; cobertura temporal y por componente; fecha de actualización; publication_id, snapshot y hashes de crosswalk; residual documental NO atribuido y límites explícitos.
- Errores/ausencias: no convertir faltantes en cero, no truncar categorías ni descartar UNKNOWN silenciosamente, no elegir productos por coincidencia textual, no mezclar unidades físicas o monedas.
- Autorización propuesta: permiso comercial normal de lectura Telchi, registrado/habilitado en el catálogo scoped existente si se aprueba. FULL_ACCESS del piloto lo resolvería por su mecanismo vigente, sin otro grant individual ni cambio al resolver. Ningún permiso fue creado en esta tarea.
- Para facturación neta de categoría se necesita primero capturar/verificar los componentes faltantes y aprobar su asignación y regla temporal. Este reporte no autoriza modificar Foundation ni capturar nuevas fuentes.

## Garantías DEV y estado operacional

El fingerprint de código cambia. No se modifica el manifest ni se renuevan gates por sustituir un hash. Esta tarea no habilita tráfico.

- `assistant_foundation`: reacreditar preguntas de categoría con handler/persistencia real y cero consultas incompatibles, más un recorrido de producto/código/texto y monetario global que mantenga su contrato y linaje.
- `model_no_fallback`: sonda real de esta tarea aporta evidencia del prompt nuevo/modelo/esfuerzo, sin sustituir admisión de una instancia autorizada ni claim de RBAC vivo.
- `http_auth`, `identity_tenant_isolation`, `business_authorization`, `durable_idempotency`: código de sus fronteras no modificado. Su evidencia anterior sólo puede reutilizarse tras revisión change-based de condiciones y procedencia; no declarada renovada aquí. La barrera de categorías debe verificarse dentro de la autorización/persistencia real en la reconciliación focalizada.
- `SIX_GATES=STALE`, `READY_FOR_MANUAL_WHATSAPP=NO`. Sin reinicios ni envíos. El próximo paso operativo es reconciliación focalizada por el procedimiento vigente; el próximo paso monetario es decisión del owner sobre semántica y datos faltantes.

## Guard de recursos y límites

Host compartido observado antes de tests y scans. Carga inicial 6,83/8 cores, memoria disponible 2,7 GB; después carga 3,89 y 3,1 GB disponibles. Swap usada estable aproximadamente 308 MB, sin crecimiento en muestras consecutivas.

`HOST_PREFLIGHT=BUSY_BUT_SAFE`, `RESOURCE_GUARD=PASS`, `CONCURRENCY_USED=1` runner o conexión, DuckDB un thread/256 MB para investigación, sin browser ni suites generales. Procesos ajenos terminados: cero. Procesos propios persistentes: cero al retornar comandos síncronos; no se inició listener.

Incidencias de herramientas: un fetch inicial de timestamps Parquet requirió pytz ausente; no se instaló dependencia (se usaron esquemas/columnas sin timestamp nativo). El primer SQL investigativo usó alias reservado rows y fue corregido a row_count antes de obtener evidencia. Ninguna incidencia demuestra defecto de datos o justifica modificar Foundation.
