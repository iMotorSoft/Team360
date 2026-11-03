# Integración Luna y State Engine

Se usa el handler Telchi/Srv05 y dispatcher existentes. No se añadió otro motor conversacional, una segunda llamada LLM ni SQL producido por Luna.

## Punto de integración

El resolver corre después de los dos controles de BusinessAuthorization, dentro de la transacción del turno y antes de `LunaInterpreter.interpret`.

Archivos modificados: [composition.py](../../../../SrvRestAstroLS_v1/backend/modules/telchi/assistant/composition.py), [handler.py](../../../../SrvRestAstroLS_v1/backend/modules/telchi/assistant/handler.py), [luna.py](../../../../SrvRestAstroLS_v1/backend/modules/telchi/assistant/luna.py), [state_engine.py](../../../../SrvRestAstroLS_v1/backend/modules/telchi/assistant/state_engine.py).

Luna recibe código, ID/versión, significado, tipo/dimensión, aliases limitados, ambigüedad, madurez, links a capabilities y evidencia estructurada acotada. No recibe catálogo completo. Candidatos de vector sólo se entregan con política explícita de score/margen; siguen sin confirmación automática.

El intérprete preexistente usa OpenAI Responses directo `gpt-5.6-luna`/medium. Se conserva ese contrato, timeout, clave privada y comprobación de modelo/esfuerzo; LiteLLM se utiliza en embeddings. No se sustituyó Luna.

## Estado y guard

Los IDs y versiones relevantes se guardan en `semantic_references` del estado existente; el modelo no puede editar ese path. No se copia la definición permanente al estado.

- Sólo después de `committed is True` se adjuntan refs y se prepara respuesta.
- ASK mantiene hash pending coherente al adjuntar referencias. Definición pendiente nunca desbloquea un total global como sustituto.
- REFINE/ANSWER conserva concepto publicado del contexto y bloquea su operación pendiente.
- NEW_QUERY explícito libera refs previas y conserva las operaciones existentes de nueva consulta.
- Referencia retirada/no publicada, o resolver desactivado, bloquea refinamiento sobre plan semántico previo.
- Capability Registry + autorización viva permanecen antes de cualquier ejecución. Una definición/link/entidad no concede permisos.

Auditoría existente incluye candidatos autorizados, método, score, calibración, degradación, tiempos y refs confirmadas. Messaging y su mecanismo de persistencia/ownership no cambian.

## Corrección focalizada acreditada

La prueba HTTP encontró limit 1 en una pregunta por última fecha. El contrato documental existente aceptaba sólo limit 10 y dejaba pasar una lista de facturas.

Síntoma/causa: [http_final caso R04](http_final/http_results.json), propuesta NEW_QUERY/EXECUTE/sales.latest_documents/limit=1. Cambio mínimo: esa misma pregunta literal admite limit 1 o 10 en la corrección a cobertura; 50, propuestas inválidas/conflictivas o REFINE siguen intactas/rechazadas. No se corrige un rechazo del motor.

Regresión pytest específica y [HTTP posterior](http_coverage_fix/http_results.json) verifican `sales.coverage`, permiso propio, fuente CURRENT y cero listados sustitutos. El resultado anterior se conserva como evidencia del fallo, no se oculta.
