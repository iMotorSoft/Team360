# TelchiAI Direct Ask DEV

Piloto local para preguntar a Luna sobre Foundation. Reutiliza el investigador adaptativo; no es un servicio, autenticación Console ni autorización productiva.

## Inicio en Ubuntu

La credencial OpenAI DEV ya autorizada debe estar disponible en la shell. No copiar su valor a comandos, reportes ni código. No se necesita levantar backend, frontend, PostgreSQL, Milvus o WhatsApp.

```bash
cd /media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend
TEAM360_ENV=development uv run --no-sync python -m modules.telchi.exploratory_sql.ask --authorize-dev-io-exception
```

Escribir una pregunta y pulsar Enter. Los turnos siguientes conservan el contexto local, incluidas aclaraciones; cada investigación vuelve a acreditar sus cifras. `/salir`, Ctrl+D o Ctrl+C en el prompt cierran la sesión. Ctrl+C durante investigación pide cancelación.

El flag acepta explícitamente identidad local DE PRUEBA ligada al UID y la excepción DEV de espera de I/O existente. No representa RBAC empresarial; no sirve para exponer este runner a usuarios externos. Entorno ausente o productivo: rechazo antes de lectura/modelo.

## Modelo y fuentes

La configuración no admite proveedor/modelo alternativos ni fallback. Las fuentes son una proyección lógica, no un catálogo físico accesible al modelo.

- OpenAI Responses directo: `gpt-5.6-luna`, reasoning `medium`, `store=false`, 8192 tokens de salida, máximo 16 llamadas investigativas más preflight mínimo por turno.
- Publicación fijada: `foundation_afd08d9eca6a725be53cdc3f9d5709c9`; snapshot `1408`. Cualquier cambio de binding bloquea la lectura; nunca se sigue CURRENT silenciosamente.
- Fuentes: facturas activas OINV/INV1 publicadas, operación comercial a grano línea, metadatos documentales, productos y vendedores. No hay filtro fijo de SKU o período. Otros dominios/fuentes no expuestos no se inventan.
- `doc_date` es fecha documental ISO a grano día, normalizada desde timestamp; `source_as_of` conserva la procedencia cruda. No se certifica cobertura calendario completa.
- Descubrimiento textual con `contains(lower(item_name),'texto')`. Un nombre no acredita marca universal, composición química ni conversión física.

## Investigación y verificación

Luna propone SQL o una aclaración. El servidor mantiene catálogo, permisos, publicación, presupuesto, ejecución y evidencia. La pregunta nunca se interpreta como comando del sistema o ruta de filesystem.

El loop sigue siendo `adaptive_research.run`: observaciones sucesivas, validación positiva, executor read-only, evidencia emitida por servidor, revisión de afirmaciones con discrepancias y hasta tres reparaciones. La memoria es solo del proceso, acotada; el historial no aporta autoridad ni hechos revalidados.

El verificador recalcula sumas y conteos desde filas independientes sin agregar, comprueba claves únicas/no nulas, reconstruye cabeceras/líneas, contrasta moneda y procedencia, y rechaza multiplicaciones. Las claves de referencia se pasan como datos a tablas temporales privadas en memoria; nunca se escriben en Foundation.

| Construcción | Tratamiento |
| --- | --- |
| SUM directo de line_total BS | Decimal independiente y binding de resultado/columna/fila; VERIFIED_WITH_LIMITATIONS si coincide |
| Conteos de líneas y COUNT DISTINCT doc_entry | Reconstrucción independiente al grano correspondiente |
| Grupos simples, CASE/COALESCE soportados | Reevalúa pertenencia al grupo; una etiqueta calculada no se vuelve oficial |
| CTE y subconsulta FROM | Pueden ejecutarse si se validan; linaje no acreditado, nunca VERIFIED |
| Joins propuestos | Límites estructurales/presupuesto; sin acreditación del grano empresarial, nunca VERIFIED |
| Aritmética derivada o función independiente desconocida | Sin métrica/semántica acreditada; UNVERIFIED, reformulación posible |
| Cambios de grano desconocidos, fanout o procedencia incompatible | Rechazo de la afirmación; no se publica como cifra verificada |
| Porcentajes entre resultados | UNVERIFIED: no asumir que una referencia filtrada es el universo completo |
| Causalidad, marca universal, conversiones | No acreditadas mediante mera igualdad numérica |
| Referencia incompleta, truncada o fuera de presupuesto | Sin verificación, aunque SQL haya ejecutado exitosamente |

Solo los hechos estructurados acreditados se presentan como cifras. La prosa libre de Luna y sus conclusiones quedan en auditoría, no se convierten en respuesta certificada. La cobertura de la pregunta es declarada por el modelo y no es una garantía independiente de completitud empresarial.

## Límites y cancelación

Se conservan los controles del piloto supervisado y sus límites pendientes. Este runner no acredita un sandbox OS ni habilita producción.

- Una consulta simultánea y lock interproceso compartido con los otros pilotos; un thread DuckDB, memoria del motor 512 MiB y spill deshabilitado.
- Máximo 12 propuestas de consulta investigativa y 12 consultas de referencia por turno, 120 s por consulta, 900 s SQL por fase y 1200 s de pared investigativa.
- Resultado: 5000 filas / 2 MiB. Entrada al modelo: 32 KiB, agregados hasta 30 filas y muestras documentales hasta tres. Memoria conversacional 12 KiB antes del siguiente turno; al agotarla se solicita nueva sesión.
- Guardian de memoria/swap existente. No se elevan límites ante rechazos. Errores de binding o ejecución no exponen diagnósticos físicos.
- Cancelación por evento/interrupt durante SQL y petición investigativa al modelo. El preflight inicial puede tardar hasta 45 s; establecer la conexión Foundation no es OS-preemptible.
- Límite DuckDB no equivale a RSS, CPU o bytes escaneados del proceso. Estos controles OS siguen sin acreditación. No usar como servicio multiusuario.
- Se conservan hechos parciales acreditables si el turno se interrumpe. Se cierran conexiones, monitores, watcher y tarea HTTP propios; no se crean servidores ni se tocan procesos ajenos.

## Evidencia y evaluación ciega

Cada sesión genera JSON privado en `data/reports/telchi/direct-ask-v1/`: preguntas, conversación, propuestas, observaciones, manifests, controles independientes, revisiones, uso del modelo y latencias. No se estima coste monetario sin precios acreditados.

El reporte de cierre de esta tarea vive en [report.md](../../../../../data/reports/telchi/direct-ask-v1/report.md). Los intentos fallidos se preservan y se distinguen de la corrida final. HEAD sin commit no identifica por sí solo el código: el congelamiento debe registrar también digests y estado del árbol.

Para comparar: misma pregunta textual, período, universo, publicación/snapshot y acceso read-only; sesiones separadas, sin respuesta del otro sistema. Registrar modelo/herramientas de Pi por el operador, sin incorporarlo al runtime. Verificación independiente posterior; ningún cambio de código tras conocer la pregunta inédita.

## WhatsApp posterior

La futura integración debe invocar este mismo investigador desde la composición autorizada de TelchiHandler, no ejecutar el CLI ni duplicar su loop. No se implementa en esta etapa.

El handler deberá aportar identidad/RBAC reales revalidados, scope y binding fijados, presupuesto y cancelación; el investigador devuelve hechos/evidencia/limitaciones. Permanecen intactos Srv05, Evolution, Messaging, Dispatcher, phone bindings, conversaciones, estado determinístico, envío durable y auditoría. Antes de habilitarlo se requieren los gates propios del canal y reemplazar la identidad sintética; este documento no autoriza activación.
