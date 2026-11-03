# Business Runtime Results

Preguntas reales por curl al adaptador existente, misma cadena Srv05 DEV, identidad y permisos PostgreSQL. No hay WhatsApp outbound. Ninguna operación nueva obtuvo BUSINESS_PASS: permisos específicos ausentes.

## Escenarios focalizados

Resultado final con Luna GPT-5.6 Medium, sin fallback ni otro verificador. La auditoría conservada distingue intención, commit, disponibilidad y ejecución real.

| Test | Pregunta | Clasificación | Committed | Ejecución | Métrica |
| --- | --- | --- | --- | --- | --- |
| TQ01 | Dame las últimas 10 ventas registradas | DENIED | True | not_executed | sales.latest_documents |
| TQ02 | Ventas de mayo de 2026 | NEEDS_CLARIFICATION | True | not_executed | None |
| TQ03 | ¿Cuál es el último mes con ventas registradas? | DENIED | True | not_executed | sales.coverage |
| TQ04 | Dame las últimas ventas de Calenta | DIRECT_UNAVAILABLE | True | not_executed | sales.latest_documents |
| TQ05 | Quiero importes y cantidades | DIRECT_UNAVAILABLE | True | not_executed | sales.net_amount |
| TQ06 | Ventas de mayo de 2026 | NEEDS_CLARIFICATION | True | not_executed | None |
| TQ06 | ¿Y el mes anterior? | NEEDS_CLARIFICATION | True | not_executed | None |
| TQ07 | ¿Cuáles fueron los productos más vendidos? | DIRECT_UNAVAILABLE | True | not_executed | sales.source_top_items |
| TQ08 | Dame el importe neto por producto de mayo de 2026 | DIRECT_UNAVAILABLE | True | not_executed | sales.net_amount |
| TQ09 | Mostrá la cobertura de facturas activas por fecha documental | DENIED | True | not_executed | sales.coverage |
| TQ11 | Sumá en una sola cantidad física las ventas de todos los productos de mayo de 2026 | DIRECT_UNAVAILABLE | True | not_executed | sales.source_top_items |
| TQ12 | Dame las últimas ventas de Calenta Forte y Calenta como una sola marca | DIRECT_UNAVAILABLE | True | not_executed | sales.latest_documents |

TQ01/TQ03/TQ09: DENIED, committed=True, execution_status=not_executed, execution_result=null. Respuesta: «requiere un permiso comercial específico. No se consultó Foundation». No se declara consulta empresarial autorizada desde ese HTTP.

TQ02/TQ06: aclaración material importe/cantidad; mes completo conserva mayo y seguimiento abril. No se implementó importe genérico sin definición. TQ05 no sustituye importes por cantidades. TQ04/TQ12 no inventan Calenta ni ausencia de ventas. TQ11 no ejecuta agregación física; ese bloqueo mensual no acredita comprensión universal de unidades incompatibles.

TQ10 no se expone mediante campo HTTP falsificable: prueba de guard inyecta committed=False en el handler real de test y exige cero llamadas. El adapter no permite que un cliente controle committed, identidad ni grants.

TQ07 inicial ejecutó la capability V1 **existente** con cantidades reales; no satisface la exigencia de una consulta nueva. TQ07 final fue DIRECT_UNAVAILABLE: Luna propuso fin exclusivo 2026-09-17 sin un período solicitado, fuera de la ventana fija. Es una limitación conversacional observada, no ausencia de datos. El registry bloqueó sin ampliar la ventana. La corrida legacy final sí ejecutó dos consultas V1; sólo su compatibilidad fija se declara PASS.

## Regresión anterior

Se conservaron dos corridas completas del runner sin cambiar sus doce escenarios ni treinta y dos turnos. La segunda usa el prompt corregido y mantiene el guard estricto.

Primera corrida: 8 ERROR, todos propuestas rechazadas sin ejecución, causados por ASK metric manteniendo métrica elegida y por EXECUTE monetario sin período. Se corrigió Luna para que «las dos» signifique importes/cantidades y no límite 2; no se flexibilizó el State Engine. Evidencia inicial en legacy_runtime_http/runtime_http_results.json.

Final: 12 escenarios/32 turnos, 0 ERROR; 28 DIRECT_UNAVAILABLE, 2 DIRECT_AVAILABLE V1, 1 ANALYSIS_UNAVAILABLE, 1 NEEDS_CLARIFICATION. Rechazos y semánticas pendientes no se contabilizan como fallo funcional. Evidencia en [legacy final](legacy_runtime_http_r2/runtime_http_results.json).

Nuevos: [runtime final](runtime_http_r2/runtime_http_results.json), once escenarios HTTP/doce turnos más TQ10 unitario. Primeras corridas y logs preservados; los owners de auditoría se redactaron del export por minimización.
