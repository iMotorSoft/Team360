# Business HTTP results

HTTP 200 no decide el gate: se cotejaron committed, permiso, capability, parámetros, binding, conteos, montos y SQL independiente. El runtime usó loopback, autenticación y la identidad piloto resuelta por PostgreSQL.

| Caso | Pregunta | Clasificación | Ejecución | ms |
| --- | --- | --- | --- | --- |
| B01 | Dame las últimas 10 facturas de venta registradas | ERROR | not_executed | 3853.79 |
| M01 | Ventas de mayo de 2026 | DIRECT_AVAILABLE | executed | 10457.05 |
| M02 | Ventas de junio de 2026 | DIRECT_AVAILABLE | executed | 6780.21 |
| M03 | ¿Cuál es el último mes con ventas? | DIRECT_AVAILABLE | executed | 6383.52 |
| M04 | Dame las últimas ventas de Calenta | DIRECT_UNAVAILABLE | not_executed | 3753.22 |
| M05 | Ventas de mayo de 2026 | DIRECT_AVAILABLE | executed | 7193.99 |
| M05 | Quiero importe y cantidades | DIRECT_AVAILABLE | executed | 8777.28 |
| M06 | Ventas de junio de 2026 | DIRECT_AVAILABLE | executed | 7754.53 |
| M06 | ¿Y el mes anterior? | DIRECT_AVAILABLE | executed | 7920.53 |
| M10 | Dame el importe neto por producto de mayo de 2026 | DIRECT_UNAVAILABLE | not_executed | 3774.49 |
| M11 | Dame las últimas ventas de Calenta y Calenta Forte como una sola marca | DIRECT_UNAVAILABLE | not_executed | 5040.95 |
| M07 | ¿Cuáles son los productos más vendidos? | DIRECT_AVAILABLE | executed | 13346.88 |
| M07 | Top 10 por cantidad documental del 1 de enero al 15 de septiembre de 2026, sin filtros | DIRECT_AVAILABLE | executed | 13107.6 |

Respuestas exactas y auditorías: [corrida actual](business_http_current/runtime_http_results.json). El ranking genérico tiene una [revalidación focalizada posterior](ranking_http_current/runtime_http_results.json), después del binding de ventana registrada.

M01 obtuvo neto Bs 8.552.079,19 y facturación válida Bs 8.761.459,22. M02 obtuvo neto Bs 9.763.493,67 y facturación válida Bs 10.033.501,02. M06 conservó estado y volvió de junio a mayo; M05 conservó importes y cantidades sin sumar unidades ni ofrecer el ranking fijo como cantidades mensuales.

M08/M09 recorren el mismo endpoint/handler con fixtures explícitas de permiso denegado e interpretación inválida: [security_http_results.json](security_http_results.json). M09 conserva el estado anterior, committed=False y cero capability_calls. No se creó otra API.

M10 responde la limitación concreta del neto por producto; M04/M11 siguen bloqueados por identidad/crosswalk, no por ausencia de datos. M12 son seis comparaciones monetarias independientes con diferencia cero en [http_reference_comparison.json](http_reference_comparison.json).

La corrida actual B01 fue rechazada por un `/pending` prohibido propuesto por Luna: committed=False y cero ejecución. Hubo B01 positivos en [corrida previa](business_http_final/runtime_http_results.json); no se borra ni se presenta el rechazo como PASS. La capability y permisos anteriores siguen válidos, pero la confiabilidad lingüística de últimas facturas queda PARTIAL por esa intermitencia. No ocurrió en las consultas monetarias cotejadas.

No se cambió el modelo, se debilitó el engine ni se ejecutaron capacidades al rechazar. Todos los servidores propios fueron detenidos por el harness; no se envió WhatsApp, no hubo deploy ni acceso SAP.
