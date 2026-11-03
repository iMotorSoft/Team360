# Business HTTP results

Foundation `foundation_afd08d9eca6a725be53cdc3f9d5709c9`, snapshot **1408**, CURRENT efectivo confirmado; solo DEV y lectura. Sin SAP, modificaciones canónicas, reingestión, deploy ni cambio de modelo.

Luna GPT-5.6 Medium directa, modelo/effort verificados, sin fallback. Batería existente por loopback/auth, handler real y PostgreSQL: 16 escenarios, 25 turnos, cero errores funcionales en la corrida final; HTTP 200 por sí solo no determina éxito.

| Caso | Turnos | Resultado final |
| --- | --- | --- |
| B01 | 1 | DIRECT_AVAILABLE |
| B02 | 1 | DIRECT_UNAVAILABLE |
| B06 | 2 | DIRECT_AVAILABLE, DIRECT_AVAILABLE |
| P01 | 1 | DIRECT_AVAILABLE |
| P02 | 2 | DIRECT_AVAILABLE, DIRECT_AVAILABLE |
| P04 | 3 | DIRECT_AVAILABLE, NEEDS_CLARIFICATION, DIRECT_AVAILABLE |
| P05 | 1 | DIRECT_AVAILABLE |
| P06 | 3 | DIRECT_AVAILABLE, DIRECT_AVAILABLE, DIRECT_AVAILABLE |
| P07 | 1 | DIRECT_AVAILABLE |
| P08 | 1 | DIRECT_AVAILABLE |
| P09 | 1 | DIRECT_AVAILABLE |
| P10 | 1 | DIRECT_AVAILABLE |
| P11 | 3 | DIRECT_AVAILABLE, DIRECT_AVAILABLE, DIRECT_AVAILABLE |
| P12 | 1 | DIRECT_AVAILABLE |
| P16 | 2 | DIRECT_AVAILABLE, DIRECT_UNAVAILABLE |
| P17 | 1 | DIRECT_AVAILABLE |

P03 está en el segundo turno P02; P04 pregunta solo cuando la selección es ambigua y luego consulta L03658 verificado. P05/P06 responden parcialmente con líneas/cantidades y la limitación monetaria, no total global. P09 conserva opciones y pide precisión. P16 rechaza agregación física incompatible. P17 vacío correcto.

P13/P14/P15/P18 están en [HTTP security/restart](security_http_final/security_restart_results.json); P18 prueba persistencia real PG y reinicio, con intérprete fixture explícito. [Respuestas completas finales](business_http_final/runtime_http_results.json).

El último guard impide sustituir productos contextualizados por totales globales. Su regresión es focalizada; la evidencia HTTP se reutiliza porque todos sus estados siguen autorizados por el registry actual y el formatter reproduce las mismas respuestas, ver current_contract_replay.json. No se iniciaron nuevos servidores bajo la presión posterior del host.

La primera corrida se conserva: tuvo rechazos por /pending emitido por el modelo y refinamiento de texto con IDs verificados. Se corrigió la continuidad de selección en State Engine y se aclaró la gramática del intérprete; ningún rechazo se reparó para ejecutar, ni se cambió SQL/semántica para ocultarlo. Corridas corregida y final sin esos fallos.
