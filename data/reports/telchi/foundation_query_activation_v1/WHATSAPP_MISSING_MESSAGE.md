# WhatsApp Missing Message

Estado EVIDENCE_INSUFFICIENT para «Ventas de mayo 2026», 12/10/2026. No se atribuye el silencio a semántica o al handler sin un inbound correlacionable.

## Trazabilidad focalizada

Consultas read-only acotadas en PostgreSQL y Evolution. No hubo envío, replay, cambio de webhook ni edición de Messaging.

| Etapa | Evidencia | Conclusión |
| --- | --- | --- |
| Evolution inbound | Últimos 100 de 135 mensajes; sin match exacto en la página consultada | Parcial; no demuestra no recibido |
| Webhook/Srv05 | GET actual: enabled=false, events=[]; URL configurada | Configuración actual, no prueba de configuración a la hora del mensaje |
| Dispatcher/identidad | No inbound exacto en canal Telchi DEV el 12/10 UTC para la frase | No reconstruible por ID; no afirmar rechazo |
| Estado/handler | Sin evento correlacionable | No afirmar procesado ni sin respuesta |
| Outbound intent/publicación | Sin inbound correlacionable | No acreditar envío, fallo ni entrega |
| Entrega observable | Conversación compartida sin respuesta visible | Evidencia de interfaz, no confirmación de recepción técnica |

[preflight_and_trace.json](preflight_and_trace.json) y [evolution_trace.json](evolution_trace.json) conservan estados minimizados. Búsqueda PG estricta por fecha UTC y redacción exacta tiene límite de zona horaria/variantes; no se considera búsqueda exhaustiva del canal. Historia Evolution excede el bound y no se ocultó esa condición.

Próximo paso: aportar provider message ID o timestamp/zona exactos para correlacionar inbound → dispatcher → intent → provider status. El webhook actual deshabilitado es un riesgo operacional verificable, no un defecto de código demostrado ni autorización para activarlo.
