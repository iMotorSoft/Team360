# Contexto empresarial TelchiAI V1

La pregunta original pasa en una única llamada real Luna Medium. Este cierre no acredita permisos actuales mediante DB, ejecución Foundation ni WhatsApp E2E.

## Causa y corrección

Luna carecía de empresa propia estructurada y recibía reglas que trataban empresas mencionadas como filtros. El catálogo rechazaba correctamente el filtro; el State Engine conservaba la propuesta correctamente.

- Rama: `feature/console-backend-core`; worktree preexistente preservado, sin commit/push.
- `handler.py`: entrega contexto desde identidad/canal resueltos, sólo después de autorización efectiva existente. La etiqueta Telchi pertenece al módulo y sólo se usa cuando tenant y workspace coinciden con la política aprobada y la identidad. No hay aliases inferidos del texto ni cambios RBAC.
- `luna.py`: recibe `enterprise_context` estructurado; distingue titular propio de cliente/proveedor/marca/producto/empresa externa. Una mención explícita como cliente o proveedor sigue siendo filtro, incluso si se llama Telchi. No elimina entidades después del modelo.
- Formatter `unavailable_response`: conserva entidad e intención, explica indisponibilidad comercial sin categorías internas ni «tipo pendiente de resolución». Conserva la aclaración de que una fecha distinta no desbloquea el filtro.
- `tests/test_enterprise_context.py`: contratos offline y aislamiento; `tests/live_enterprise_context.py`: sonda de una única llamada, sin escritura DB ni ejecución de capabilities.
- State Engine, catálogo, capacidades, Foundation, SQL, permisos, Messaging, infraestructura, lifecycle y `source_digest()` no modificados.

## Evidencia y validación

El [JSON real](luna-single.json) conserva propuesta raw, estado confirmado, modelo verificado y checks. No se aplicaron reparaciones de propuesta para obtener este resultado.

- Real: `gpt-5.6-luna`, `medium`, OpenAI Responses directo, sin fallback, herramientas ni retries; 6.813 segundos, una llamada. La misma llamada comprueba auth/provider/modelo/contenido; no se hizo preflight generativo adicional.
- Pregunta: «Mostrame las últimas 5 facturas de venta de Telchi.»
- Resultado raw: `NEW_QUERY`, `EXECUTE`, `sales.latest_documents`, límite 5, `entity_mention=null`, período null, sin sucursal/canal/comparación/producto ni referencia temporal.
- Se proporcionó un período anterior deliberadamente: no se heredó.
- State Engine: `committed=true`, `contract_error=null`. Catálogo: `allowed=true`; permiso requerido `telchi.sales.latest_documents.read.v1`.
- Contexto: workspace piloto de la [evidencia de permisos efectivos existente](../sales_rbac_business_runtime_v1/EFFECTIVE_PERMISSIONS.md), no tenant extraído de la pregunta. La sonda reutiliza la identidad/grants registrados; NO es autenticación fresca ni revalidación efectiva actual. El handler mantiene su revalidación PG antes del intérprete y de la ejecución.
- Offline final: `uv run pytest modules/telchi/assistant/tests tests/test_telchi_assistant_srv05.py -q`: **311 passed**, un warning previo de repositorio Diagnosis in-memory.
- Una corrida intermedia detectó pérdida de la aclaración sobre fecha en el formatter; se restauró esa información y se repitió la suite con éxito.
- Comando real desde backend: `uv run python -m modules.telchi.assistant.tests.live_enterprise_context --output ../../data/reports/telchi/enterprise_context_v1/luna-single.json`.
- Gates documentales: `lat check md`, `lat check index`, `lat check sections`, `lat check code-refs`, `lat check`: todos correctos. Warnings de configuración LAT (init/clave semántica ausentes), sin fallos. `git diff --check`: correcto; archivos untracked propios comprobados adicionalmente.
- Foundation calls: 0. WhatsApp enviados: 0. LlmFit completo: no ejecutado.

## Negativos y límites de aislamiento

Los negativos usan propuestas controladas para verificar barreras y conservación; no prueban comprensión semántica real de Luna para esas frases. Sólo se autorizó una llamada real, reservada a la pregunta original.

- «Mostrame las últimas cinco facturas de la empresa XYZ», «Mostrame las ventas al cliente XYZ», «Mostrame las compras al proveedor XYZ»: la entidad se conserva y el catálogo bloquea tanto DIRECT_UNAVAILABLE como una propuesta EXECUTE incompatible, sin consultar datos ni sustituir por total global.
- Cliente/proveedor llamados Telchi también permanecen como filtros en las pruebas de contrato.
- Tenant/workspace discordantes: cero llamadas al modelo/capabilities. Sin grant documental: DENIED. Consulta sin mención de Telchi: contrato disponible sin regresión offline.
- Riesgo residual: el State Engine valida estructura, no semántica; si el modelo omite una entidad externa en su propuesta, las barreras actuales no pueden reconstruirla. No se declara probado el comportamiento real de esos negativos ni garantía semántica universal. No se agregó una excepción lexical ni otro clasificador.
- Compras sigue sin capability: la prueba negativa acredita que una propuesta documental con esa entidad no se ejecuta; no incorpora métricas de compras ni amplía el catálogo.

## Gates y siguiente paso

El código cambió; manifiestos ligados a fuentes pueden quedar obsoletos aunque la prueba focalizada pase. Ningún hash, aprobación ni manifiesto vigente fue actualizado para aparentar validez.

- Revalidación proporcional preparada: contrato/contexto y suite local completados; evidencia real del intérprete completada. Antes de WhatsApp, renovar por el procedimiento existente los gates afectados de interpretación/assistant, autorización e aislamiento y compatibilidad HTTP, con manifiesto nuevo sólo cuando la evidencia corresponda a las fuentes actuales. No repetir LlmFit ni consultas Foundation sin necesidad/autorización.
- La inspección read-only no detectó TelchiAI/Srv05 activo; no se detuvieron ni iniciaron servicios. Si al retomar está activo, pedir cierre manual antes de actualizar runtime.
- Siguiente paso mínimo: owner revisa evidencia, confirma permisos efectivos del piloto y vigencia de gates/aprobación mediante flujo existente; inicia runtime DEV manualmente con estas fuentes y repite una vez la pregunta por WhatsApp en una etapa autorizada.
- Impacto transversal: sólo entrada al intérprete y formatter Telchi; no cambios de contratos de Messaging ni infraestructura.

## Recursos y cierre

Host con ocho cores, load aproximado 2–3, unos 7 GB disponibles y swap usada cero. Se ejecutaron tests secuenciales, sin workers paralelos ni servidores propios.

`HOST_PREFLIGHT=SAFE`; `RESOURCE_GUARD=PASS`; `CONCURRENCY_USED=1` runner; `UNRELATED_PROCESSES_TERMINATED=0`; `ENVIRONMENTAL_ABORTS=0`; `OWN_PROCESSES_LEFT_RUNNING=0`.
