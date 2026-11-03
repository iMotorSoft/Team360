# Gates — Informe comercial C010264

Resultado inicial PARTIAL / BLOCKED_MEMBERSHIP_EVIDENCE. Datos de cliente y compras acreditados; oportunidades propias Telchi/Litel no calculables sin pertenencia aprobada.

| Garantía | Resultado |
| --- | --- |
| CURRENT exacto / snapshot 1408 / READ_ONLY | Verificado en ejecución |
| Identidad C010264 | Verificada: L&S S.R.L. |
| Unicidad, orfandad y compras por SQL independiente | Verificadas |
| Perfil, importes BS, NC y evolución | Verificados; scope cliente completo |
| Universo Telchi/Litel acreditado | BLOCKED_MEMBERSHIP_EVIDENCE |
| Top 20 y diferencias A/B/C | NOT_EXECUTED; no cero oportunidades |
| Importe neto por producto / UoM física de línea | UNRESOLVED; no usados |
| Candidata Business Semantics | Documentada, no persistida ni activada |
| LAT / diff / tests focalizados | Verificados; detalle de comandos abajo |
| Reconciliación final de artefactos | 52 facturas, 3 NC, 98 ItemCodes, 822 líneas únicas; meses/importes/frecuencias/últimas compras concordantes |

## Recursos y límites

Preflight BUSY_BUT_SAFE: 8 cores, load 5.57/5.00/3.14, 8440 MiB disponibles, swap 0; vmstat sin swap-in/out. Ejecución secuencial, 2 threads DuckDB, 512 MiB y sin spill. Cero procesos ajenos terminados; no servidores/browser creados.

Scope de escritura: este directorio de evidencia. Sin aplicación, migraciones, permisos, Foundation, memoria, commit, push ni deploy. Los cambios concurrentes fueron preservados.

## Validaciones de cierre

Las garantías de datos no convierten el resultado comercial pendiente en PASS. Rama feature/console-backend-core; impacto transversal nulo en runtime y catálogos.

- `uv run --no-sync pytest modules/telchi/datalake/tests/test_messaging_sales_query.py -q` desde backend: 2 passed, 0.47 s. No se cambió código; no se ejecutó una suite global.
- `lat check md`, `lat check index`, `lat check sections`, `lat check code-refs`, `lat check`: checks aprobados. LAT escanea su alcance configurado; no equivale a revisión semántica de este informe. Warnings: init/version y clave LLM ausentes; no se cambió configuración.
- `git diff --check`: sin errores. Archivos nuevos untracked: revisión directa de resumen, SQL/resultados, CSV y reconciliación Python3 de los artefactos; no se añaden al index.
- SQL independiente de compras coincide por ItemCode/frecuencia; reconciliación de importes mensuales y neto, 822 líneas únicas, fechas de ventana y última compra por artículo verificada.
- Dos errores de sintaxis SQL en el runner temporal se corrigieron antes de emitir resultados (aliases rows/month); sin defecto de aplicación. Una comprobación local usó python no instalado; reejecutada con python3 con éxito. ENVIRONMENTAL_ABORTS=0.
- RESOURCE_GUARD=PASS en las ejecuciones; CONCURRENCY_USED=2 threads DuckDB, pytest secuencial. UNRELATED_PROCESSES_TERMINATED=0; OWN_PROCESSES_LEFT_RUNNING=0: procesos síncronos finalizados, sin servidores ni workers persistentes.

Próximo paso: acreditar pertenencia ItemCode Telchi/Litel y entonces ejecutar Top 20/A/B/C. No se necesita ampliar capacidad ni promover memoria para resolver este caso.
