# Configuracion inicial productiva - Vera para Team360.live

Fecha documental: 2026-06-05  
Inspeccion ejecutada: 2026-06-07  
Objetivo: definir configuracion/seeding productivo inicial para el primer paquete real de Team360, sin implementar codigo funcional, migraciones ni frontend.

## 1. Resumen ejecutivo

Este documento define la primera configuracion productiva real de Team360:

```text
Team360 Platform
  -> Team360.live como primer cliente real
  -> paquete vendible Asistente Inteligente Vera
  -> assistant instance team360_sales_diagnosis
  -> workers logicos del paquete
  -> knowledge scope propio
  -> home publica
  -> Console
```

La configuracion separa explicitamente la plataforma (`Team360 Platform`) del cliente real (`Team360.live`). El administrador global de plataforma es `mario.rojas@alquimiablue.com`; el administrador cliente de Team360.live es `mario.rojas.marconi@gmail.com`.

El paquete inicial es `Asistente Inteligente Vera`, con funcion de ventas y diagnostico de automatizacion. Debe salir como servicio vendible de Team360, no como demo, mock interno ni excepcion hardcodeada.

La experiencia deseada empieza por texto libre y conversacion abierta:

```text
Free Text -> Slot Extraction -> L0/L1 Context -> Dynamic Checklist -> L2 Retrieval if needed -> DiagnosisResult -> LeadCapture -> Console
```

El motor base debe seguir siendo `automation_diagnosis`. No se recomienda crear un motor paralelo. La salida correcta es convertir la configuracion actual de diagnosis en una instalacion productiva seedable y trazable.

## 2. Decision de naming: Vera como marca comercial, no identificador tecnico

Decision aprobada: se usa la Opcion B.

`Vera` es el nombre comercial visible del asistente. No debe usarse como identificador tecnico estable en backend, seeds, migrations, tests, assistant instances, workers, knowledge scopes, integraciones ni historiales.

Los identificadores tecnicos permanecen neutrales y estables:

| Concepto | Identificador tecnico estable |
| --- | --- |
| `assistant_instance_code` | `team360_sales_diagnosis` |
| `package_code` | `pkg_sales_diagnosis` |
| `knowledge_scope_code` | `ks_team360_sales_diagnosis` |
| `service_code` | `svc_sales_diagnosis` o equivalente tecnico estable si el mock actual exige otro patron |
| worker codes | Sin `vera`; deben describir capacidades tecnicas/logicas |

Vera vive en campos visibles/configurables:

- `display_name`.
- `commercial_name`.
- `service_name` visible.
- `package_name` visible.
- marketing copy.
- Console label.
- Home publica.
- CTA.

Nombres visibles permitidos:

- `Asistente Inteligente Vera`.
- `Vera - Diagnostico de Automatizacion`.
- `Vera para Ventas y Diagnostico`.

Razon: si manana se cambia el nombre comercial `Vera`, no debe romper backend, seeds, migrations, tests, assistant instances, workers, knowledge scopes, integraciones ni historiales de sesiones/leads. Un rebranding debe cambiar metadata/display fields, no identificadores tecnicos ni datos historicos.

## 3. Estado actual encontrado

### Platform/admin

- Backend: no existe tabla `platforms` ni entidad formal `Platform`.
- Backend: `core_workspaces` puede representar contextos operativos, pero no distingue por si solo `Team360 Platform` de un cliente real.
- Frontend mock: `org-team360` existe como organizacion `team360_owner`.
- Frontend mock: `ws-team360-control` existe como workspace de control global.
- Frontend mock: `team360_admin` existe como perfil de administracion global, pero el usuario mock asociado es `sofia.admin@example.test`, no `mario.rojas@alquimiablue.com`.
- No se detecto seed productivo de administrador plataforma.

### Organizations

- Backend: no existe tabla `organizations`; `lat.md/console-multi-organization.md` declara que esta es una brecha actual.
- Frontend mock: `organizations.ts` modela `org-team360`, `org-carmel-retail`, `org-mama-mia-360`, clientes de partner y un partner onboarding.
- No existe en backend ni mock una organizacion separada `Team360.live` como primer cliente real.

### Workspaces

- Backend: `core_workspaces` existe con `slug`, `display_name`, `timezone`, `status`, `metadata_jsonb`.
- Runtime diagnosis: `AutomationDiagnosisPostgresRepository._upsert_workspace()` puede crear/actualizar un workspace desde una configuracion de assistant instance.
- Runtime actual usa `team360_public_site` como workspace slug para la instalacion directa de Team360.
- Frontend mock: no existe `ws-team360-live` ni workspace mock equivalente a Team360.live cliente; existe `ws-team360-control` como control global.

### Users

- Backend: `core_users` existe con `workspace_id`, `email`, `display_name`, `role`, `status`, `metadata_jsonb`.
- Backend: no se detectaron seeds productivos para los emails `mario.rojas@alquimiablue.com` ni `mario.rojas.marconi@gmail.com`.
- Frontend mock: `users.ts` contiene usuarios ficticios `example.test`.
- Falta modelar dos identidades separadas: platform admin y client admin.

### Roles/perfiles

- Backend: migracion `002_team360_rbac_packages_workers_knowledge.sql` crea `core_permissions`, `core_roles`, `core_role_permissions`, `core_permission_profiles`, `core_profile_permissions`, `core_user_roles`, `core_user_profiles`.
- Backend: existen seeds de permisos atomicos generales: dashboard, task, package, worker, knowledge, credential, audit, user y role.
- No se detectaron seeds productivos explicitos para perfiles `platform_admin` y `client_admin` asociados a los dos usuarios reales.
- Frontend mock: perfiles `team360_admin`, `team360_operator`, `team360_support`, `partner_admin`, `client_admin` existen como simulacion.

### Packages

- Backend: `automation_packages` existe con `workspace_id`, `assistant_instance_id`, `package_code`, `package_name`, `plan_code`, `status`, features, limits y settings.
- Backend: `package_plans`, `package_features` y `package_plan_features` existen y tienen seeds iniciales.
- Runtime: `TEAM360_SALES_DIAGNOSIS_CONFIG` usa `automation_package_id = "pkg_sales_diagnosis"` y `automation_package_name = "Asistente de venta y diagnostico"`.
- No existe configuracion productiva con nombre comercial `Asistente Inteligente Vera`.

### Services

- Backend: no existe tabla separada `services` o `contracted_services`.
- Frontend mock: `services.ts` modela servicios visibles de Console.
- No existe servicio mock/real `Asistente Inteligente Vera` asociado a Team360.live.
- `lat.md/console-multi-organization.md` diferencia `package` como oferta comercial y `service` como resultado contratado visible al cliente.

### Assistant instances

- Backend: `assistant_instances` existe desde migracion 002.
- Backend: migracion 004 agrega `assistant_code` e indice unico por `(workspace_id, assistant_code)`.
- Runtime: existen dos configuraciones in-memory:
  - `team360_sales_diagnosis`.
  - `automation_diagnosis_default` como lab/compatibilidad legacy.
- Default runtime actual: `DEFAULT_ASSISTANT_INSTANCE_ID = "team360_sales_diagnosis"`.
- No existe `vera_team360_sales_diagnosis`, y la decision aprobada es no crearlo como identificador tecnico.

### Workers

- Backend: `worker_definitions`, `package_workers` y `package_worker_configs` existen.
- Migracion 002 siembra workers base: `diagnosis_ai_interpreter`, `workflow_classifier`, `approval_worker`, `sap_b1_desktop_worker`, `meli_browser_worker`, `document_ocr_worker`, `rag_retriever_worker`, `notification_worker`.
- Migracion 004 siembra workers del paquete sales diagnosis: `guided_intake_worker`, `lead_qualification_worker`, `knowledge_retrieval_worker`, `diagnosis_scoring_worker`, `package_recommendation_worker`, `proposal_outline_worker`, `crm_handoff_worker`, `calendar_handoff_worker`, `agui_render_worker`.
- Runtime actual vincula package workers `pw_team360_*` contra esos worker definitions.
- No existen los worker codes logicos pedidos para Vera: `free_text_interpreter`, `slot_extractor`, `dynamic_checklist_builder`, `diagnosis_classifier`, `lead_capture_worker`, `knowledge_retrieval_worker`, `result_presenter_worker`.

### Knowledge scopes

- Backend: existen `knowledge_scopes`, `knowledge_scope_bindings`, `knowledge_documents`, `knowledge_chunks`.
- Backend: migracion 003 agrega `knowledge_embedding_models`, `knowledge_chunk_embeddings` y vista `knowledge_ready_chunks` con pgvector.
- Runtime actual: `ks_team360_sales_diagnosis` existe como scope conceptual y se upsertea en postgres cuando se instala el paquete.
- Runtime actual: knowledge in-memory carga documentos Markdown desde fixtures.
- `lat.md/knowledge-scope-contract.md` define el contrato canonico `KnowledgeScope -> KnowledgeDocument -> KnowledgeChunk -> VectorEmbedding`.
- No existe ingesta productiva ArangoDB/Milvus para Vera.

### Diagnosis sessions/leads

- Backend: migracion 004 crea `automation_diagnosis_sessions`, `automation_diagnosis_answers`, `automation_diagnosis_leads`.
- Backend: `core_events` ya existe y se usa para eventos del diagnostico.
- Runtime postgres actual persiste snapshots de sesiones, respuestas, leads y eventos.
- Limitacion actual: modo postgres persiste snapshots, pero la continuidad/hidratacion de sesion desde DB aun depende del proceso in-memory.
- No existen tablas `automation_diagnosis_messages`, `automation_diagnosis_slots` ni `diagnosis_templates`.

## 4. Brecha entre estado actual y configuracion deseada

| Objetivo deseado | Estado actual | Brecha exacta |
| --- | --- | --- |
| Platform admin `mario.rojas@alquimiablue.com` | Solo usuarios mock y `core_users` generico | Falta seed real, rol/perfil y alcance global/plataforma. |
| Cliente `Team360.live` | `org-team360` como owner; no backend organizations | Falta modelar Team360.live como cliente real separado de Team360 Platform. |
| Client admin `mario.rojas.marconi@gmail.com` | No existe seed | Falta usuario real, perfil `client_admin` y acceso al workspace cliente. |
| Paquete Vera | Existe `pkg_sales_diagnosis` generico | Falta configurar nombre comercial visible `Asistente Inteligente Vera` sin cambiar el `package_code`. |
| Assistant instance `team360_sales_diagnosis` | Runtime usa ese identificador y los tests lo esperan | Falta configurar `Vera` en display/metadata, no crear `vera_team360_sales_diagnosis`. |
| Workers minimos Vera | Existen workers sales diagnosis parcialmente equivalentes | Falta mapear/cargar worker definitions Vera o alias logicos sobre workers existentes. |
| Knowledge scope Vera | Existe `ks_team360_sales_diagnosis` | Falta metadata L0/L1/L2 y visible offer `Asistente Inteligente Vera`, sin renombrar el scope tecnico. |
| Home publica enganchada a Vera | Home usa CTA `mailto` | Falta componente publico conversacional y payload con assistant instance/canal. |
| Console ve servicio y leads/sesiones | Console mock ve servicios genericos; `/diagnosis` es vista global | Falta servicio Vera visible, lista de sesiones/leads/resultados y permisos por platform/client admin. |
| L0/L1/L2 productivo | Documentado, no persistido | Falta template versionado o seed de settings para L0/L1; L2 futuro sin ingesta aun. |

## 5. Modelo de configuracion productiva inicial

### Platform

Entidad conceptual de control global. Hoy deberia representarse de forma transitoria con:

- `core_workspaces.slug = "team360_platform"`, o mantener `ws-team360-control` en mock.
- `metadata_jsonb.platform_code = "team360_platform"`.
- En migracion futura, conviene crear `core_organizations`/`core_platforms` o equivalente antes de depender de `metadata_jsonb` como contrato permanente.

### PlatformAdmin

Usuario con administracion global/plataforma:

- Email: `mario.rojas@alquimiablue.com`.
- Perfil: `platform_admin`.
- Alcance: plataforma completa, clientes, workspaces, servicios, paquetes, workers, knowledge, auditoria, usuarios.
- No debe confundirse con el administrador cliente de Team360.live.

### Organization

Cliente/organizacion contractual. Para esta salida:

- `Team360.live` debe ser primera organizacion cliente real.
- Aunque Team360 sea self-customer, debe modelarse como cliente con el mismo camino que futuros clientes.
- Hasta que exista tabla backend de organizaciones, la relacion puede vivir en `core_workspaces.metadata_jsonb` y en mocks frontend.

### Workspace

Contexto operativo del cliente y del canal publico:

- Un workspace cliente para Team360.live.
- Debe contener servicio Vera, assistant instance, sesiones, leads, knowledge scope y configuracion de canal.

### User

Identidad autenticable/autorizable:

- Platform admin: `mario.rojas@alquimiablue.com`.
- Client admin: `mario.rojas.marconi@gmail.com`.
- Los usuarios no deben guardar contrasenas ni secretos en seeds.

### Role/Profile

Capas de autorizacion inicial:

- `platform_admin`: control global.
- `client_admin`: administra Team360.live y servicio Vera.
- `operator/support`: reservado para seguimiento futuro.
- `visitor/public`: usuario anonimo de home publica; no entra a Console.

### Service/Package

- `Package`: oferta vendible `Asistente Inteligente Vera`.
- `Service`: instancia visible contratada/activa dentro de Console para Team360.live.
- El cliente ve el servicio; no ve workers internos como producto.

### AssistantInstance

Configuracion tecnico-comercial del asistente para un workspace/canal:

- `assistant_instance_code = "team360_sales_diagnosis"`.
- `assistant_display_name = "Vera"` o `Asistente Inteligente Vera`, segun superficie visible.
- Vincula workspace, paquete, knowledge scope, public channel, locale policy, lead owner y package workers.

### WorkerDefinition

Catalogo reusable de capacidades logicas/tecnicas.

### WorkerBinding

`package_workers` vincula una instalacion de paquete con worker definitions, modo operativo, knowledge scope y configuracion.

### KnowledgeScope

Corpus y frontera de retrieval:

- Debe quedar asociado a Team360.live, Vera, paquete y workspace.
- Es el equivalente Team360 del `Catalog` en el patron JudaismoEnVivo.

### PublicChannel

Canal de entrada publico:

- Home publica `team360.live` / `team360.com`.
- Debe enviar `assistant_instance_code`, `site_channel`, `locale`, `source_url`, visitor/session y attribution metadata.

### LeadOwner

Responsable comercial del lead:

- Para Vera en Team360.live: `Team360.live` como cliente operativo y `Team360 Platform` como autoridad/auditoria.
- Recomendacion practica inicial: `lead_owner_code = "team360_live"` y `lead_owner_display = "Team360.live"`.

## 6. Configuracion propuesta concreta

| Campo | Valor propuesto |
| --- | --- |
| `platform_code` | `team360_platform` |
| `platform_name` | `Team360 Platform` |
| `platform_admin_email` | `mario.rojas@alquimiablue.com` |
| `organization_code` | `team360_live` |
| `organization_name` | `Team360.live` |
| `organization_type` | `direct_client` o `self_customer` si se formaliza ese subtipo |
| `workspace_code` / slug backend | `team360_live_public_site` |
| `workspace_display_name` | `Team360.live Public Site` |
| `client_admin_email` | `mario.rojas.marconi@gmail.com` |
| `package_code` | `pkg_sales_diagnosis` |
| `package_display_name` | `Asistente Inteligente Vera` |
| `package_commercial_name` | `Vera para Ventas y Diagnostico` |
| `package_function` | `Ventas y Diagnostico de Automatizacion` |
| `service_code` | `svc_sales_diagnosis` |
| `service_display_name` | `Asistente Inteligente Vera` |
| `assistant_instance_code` | `team360_sales_diagnosis` |
| `assistant_display_name` | `Vera` |
| `assistant_type` | `sales_diagnosis` |
| `knowledge_scope_code` | `ks_team360_sales_diagnosis` |
| `public_channel_code` | `team360_live_home` |
| `site_channel` | `team360.live` |
| `alternate_site_channel` | `team360.com` si el dominio se usa como entrada publica |
| `default_locale` | `es` |
| `supported_locales` | `es`, `en` iniciales; `he` solo si se decide soporte publico para este canal |
| `lead_owner_code` | `team360_live` |
| `lead_owner_display` | `Team360.live` |
| `market` | `direct` |
| `status` inicial | `active` para plataforma/cliente/servicio si sale productivo; `testing` solo si queda pre-release |
| `cost_center` | `team360_live_sales_diagnosis` |

### Nota de naming

El estado actual usa:

```text
assistant_instance_id = team360_sales_diagnosis
automation_package_id = pkg_sales_diagnosis
knowledge_scope_id = ks_team360_sales_diagnosis
```

La decision aprobada descarta estos identificadores tecnicos:

```text
assistant_instance_code = vera_team360_sales_diagnosis
package_code = pkg_vera_sales_diagnosis
knowledge_scope_code = ks_vera_team360_sales_diagnosis
```

No se debe crear `vera_team360_sales_diagnosis`, `pkg_vera_sales_diagnosis` ni `ks_vera_team360_sales_diagnosis` como nuevos identificadores core. Se mantiene `team360_sales_diagnosis` como identificador tecnico estable del assistant instance, `pkg_sales_diagnosis` como package code y `ks_team360_sales_diagnosis` como knowledge scope code.

Vera se configura en metadata/display fields: `display_name`, `commercial_name`, `package_name` visible, `service_name` visible, Console label, home publica, marketing copy y CTA. Un futuro cambio de marca no debe requerir migracion de datos ni romper historiales de sesiones/leads.

## 7. Relacion Vera con L0/L1/L2

### L0 inicial para Vera

L0 debe ser un abstract interno, corto y versionado:

```json
{
  "template_code": "team360_sales_automation_diagnosis",
  "version": "2026-06-05",
  "summary": "Diagnostico conversacional de automatizacion comercial para leads, CRM, WhatsApp, email, seguimiento y procesos operativos relacionados.",
  "default_outcome": "Lead calificado con diagnostico, paquete sugerido, riesgos y proximo paso comercial.",
  "visible_offer": "Asistente Inteligente Vera"
}
```

### L1 inicial para Vera

L1 debe ser el mapa interno del diagnostico:

- slots minimos;
- dolores comerciales/operativos;
- sistemas frecuentes;
- reglas de scoring;
- riesgos de seguridad;
- condiciones HITL;
- paquetes permitidos;
- checklist dinamico;
- CTAs comerciales.

Slots iniciales:

- `process_to_automate`.
- `business_pain`.
- `systems_involved`.
- `frequency_volume`.
- `rules_clarity`.
- `human_dependency`.
- `access_security`.
- `data_sensitivity`.
- `expected_result`.
- `economic_impact`.

Estos slots ya existen como pasos en `guided_flow.py`; la evolucion de Vera debe permitir inferirlos desde texto libre y preguntar solo faltantes.

### Vinculo con slots/checklist/scoring

- `free_text_interpreter` resume e identifica intencion.
- `slot_extractor` llena slots con confianza.
- `dynamic_checklist_builder` pregunta faltantes y confirmaciones.
- `diagnosis_classifier` reutiliza scoring/clasificacion deterministica actual.
- La LLM propone señales; Team360 decide clasificacion final.

### Vinculo con L2/RAG futuro

L2 debe conectarse al `KnowledgeScope` de Vera:

```text
ks_team360_sales_diagnosis
  -> KnowledgeDocument
  -> KnowledgeChunk
  -> ArangoDB source text/graph
  -> Milvus derived vector index
```

El patron a respetar viene de JudaismoEnVivo:

```text
Catalog -> MD -> Chunk -> Milvus
KnowledgeScope -> KnowledgeDocument -> KnowledgeChunk -> VectorEmbedding
```

### Que no debe cargarse todavia

- No cargar secretos, API keys ni credenciales.
- No implementar ingesta ArangoDB/Milvus todavia.
- No cargar knowledge cross-customer.
- No convertir pgvector en RAG primario.
- No crear colecciones fisicas por cliente como default.
- No meter L0/L1 como prompt hardcodeado disperso en frontend.

## 8. Workers propuestos

| Code | Proposito | Input conceptual | Output conceptual | LLM/regla | Knowledge scope | Prioridad |
| --- | --- | --- | --- | --- | --- | --- |
| `free_text_interpreter` | Interpretar texto libre inicial y entregar valor inmediato. | Mensaje publico, locale, canal, contexto L0. | Resumen, hipotesis, intencion, primeras oportunidades. | LLM via LiteLLM + reglas de seguridad. | Si, L0/L1; L2 solo si hace falta. | P1 |
| `slot_extractor` | Extraer slots canonicos desde texto libre y respuestas. | Mensajes, slots existentes, L1. | Slots inferidos con confianza y fuente. | LLM estructurada + normalizacion deterministica. | Si, L1. | P1 |
| `dynamic_checklist_builder` | Construir checklist solo con faltantes/confirmaciones. | Slots, confianza, reglas L1. | Lista priorizada de preguntas, maximo 3-6 visibles. | Regla deterministica; LLM opcional para copy. | Si, L1. | P1 |
| `diagnosis_classifier` | Clasificar resultado y scoring. | Slots confirmados, interpretacion, riesgos. | `DiagnosisResult`, classification, score, automation mode. | Deterministico como autoridad; LLM solo enriquece senales. | Si, L1/L2 si requiere contexto. | P1 |
| `lead_capture_worker` | Convertir sesion en lead trazable. | DiagnosisResult, contacto, consentimiento, canal. | Lead, estado, owner, next step, evento. | Regla deterministica. | No requiere retrieval; usa metadata del scope. | P1 |
| `knowledge_retrieval_worker` | Recuperar contexto L2 cuando L0/L1 no alcanza. | Query, slots, knowledge_scope_code, filters. | Chunks/documentos/fuentes acotadas. | Regla de retrieval + vector/graph. | Si, obligatorio. | P2 |
| `result_presenter_worker` | Preparar salida visible y card interna. | DiagnosisResult, riesgos, CTAs. | Respuesta usuario, internal card, bloques AG-UI futuros. | LLM para redaccion controlada + templates. | Opcional; puede usar L1/L2. | P2 |

### Mapeo con workers existentes

Los workers actuales pueden cubrir parte del objetivo:

| Worker pedido | Worker existente aproximado |
| --- | --- |
| `free_text_interpreter` | `guided_intake_worker` + `diagnosis_ai_interpreter` |
| `slot_extractor` | No existe como worker definition separado |
| `dynamic_checklist_builder` | No existe como worker definition separado |
| `diagnosis_classifier` | `diagnosis_scoring_worker` + `workflow_classifier` |
| `lead_capture_worker` | `lead_qualification_worker` + `crm_handoff_worker` |
| `knowledge_retrieval_worker` | `knowledge_retrieval_worker` / `rag_retriever_worker` |
| `result_presenter_worker` | `proposal_outline_worker` + `agui_render_worker` |

Recomendacion: para Vera, crear worker definitions con codes logicos neutrales o documentar alias explicitos. Los worker codes no deben incluir `vera`; el nombre comercial pertenece a display/metadata.

## 9. Knowledge Scope

### Scope inicial

```text
knowledge_scope_code: ks_team360_sales_diagnosis
name: Team360 Sales Diagnosis Knowledge
retrieval_mode: rag
graph_enabled: false inicialmente; true cuando ArangoDB GraphRAG este operativo
status: active o testing segun salida
```

### Que representa

Representa el corpus autorizado para Vera en Team360.live:

- criterios de viabilidad de automatizacion;
- seguridad, MFA, HITL y acciones bloqueadas;
- paquetes comerciales Team360;
- ejemplos de clasificacion;
- procesos comerciales, leads, CRM, WhatsApp, email;
- criterios para proponer consultoria vs paquete estandar.

### Asociacion con Vera

Debe tener bindings a:

- workspace `team360_live_public_site`;
- assistant instance `team360_sales_diagnosis`;
- package `pkg_sales_diagnosis`;
- package workers que requieran retrieval.

### Relacion con Team360.live

Team360.live es el cliente real propietario operativo del scope. Team360 Platform mantiene autoridad de auditoria/control, pero no debe mezclarse el scope de plataforma global con el scope de cliente.

### Metadata minima

```json
{
  "organization_code": "team360_live",
  "workspace_code": "team360_live_public_site",
  "assistant_instance_code": "team360_sales_diagnosis",
  "assistant_display_name": "Vera",
  "package_code": "pkg_sales_diagnosis",
  "package_display_name": "Asistente Inteligente Vera",
  "site_channel": "team360.live",
  "visible_offer": "Asistente Inteligente Vera",
  "locale_policy": {
    "default_locale": "es",
    "supported_locales": ["es", "en"]
  },
  "l0_template_code": "team360_sales_automation_diagnosis",
  "l1_map_version": "2026-06-05",
  "runtime_targets": {
    "arangodb": "future_source_text_graph",
    "milvus": "future_vector_index",
    "pgvector": "available_fallback_not_primary"
  },
  "status": "active"
}
```

## 10. Home publica

### Enganche esperado

La home publica debe iniciar Vera con:

```json
{
  "assistant_instance_code": "team360_sales_diagnosis",
  "assistant_display_name": "Vera",
  "source_channel": "home_public",
  "site_channel": "team360.live",
  "source_url": "https://team360.live/",
  "locale": "es",
  "visitor": {
    "anonymous_id": "...",
    "utm": {},
    "referrer": "..."
  }
}
```

### Experiencia

- Primer input: texto libre.
- No usar menus tipo "presione 1".
- No arrancar con formulario largo.
- Vera devuelve resumen y valor inmediato.
- Luego muestra checklist dinamico con faltantes.
- Al final presenta `DiagnosisResult` y captura lead.

### Lead attribution

Cada sesion debe persistir:

- `assistant_instance_code`.
- `site_channel`.
- `source_url`.
- `locale`.
- `visitor_jsonb`.
- `lead_owner`.
- `correlation_id`.
- `cost_attribution_jsonb`.

### Fallback si backend no responde

- Mostrar estado de indisponibilidad controlado.
- Mantener CTA alternativo por email/WhatsApp.
- Registrar evento frontend si existe telemetria.
- No perder el texto escrito si el usuario quiere reintentar.
- No prometer que se creo lead si backend fallo.

## 11. Console

Vera debe verse en Console como servicio activo del cliente Team360.live.

### Vistas minimas

- Servicio activo: `Asistente Inteligente Vera`.
- Sesiones: lista por fecha, canal, estado, locale, score y classification.
- Leads: estado comercial, owner, contacto, next step, consentimiento.
- Resultados: `DiagnosisResult`, score breakdown, riesgos, paquete recomendado.
- Configuracion: assistant instance, canal, locales, knowledge scope, workers vinculados.
- Tecnico: eventos, correlation id, model metadata, costos/latencia cuando exista.

### Permisos

- Platform admin ve todos los clientes, Vera, sesiones, leads, configuracion tecnica, eventos y auditoria.
- Client admin de Team360.live ve su servicio, sesiones/leads/resultados y configuracion funcional permitida.
- Operator/support futuro ve solo lo asignado.
- Visitor/public no entra a Console.

### Estado actual a corregir

- `/w/[workspaceId]/diagnosis` existe como vista de Console.
- `ServiceDetail` ya tiene tabs para servicio, pero no hay servicio Vera.
- `services.ts` no contiene un servicio estable como `svc_sales_diagnosis` con display visible Vera.
- El backend no expone endpoints de Console para listar sesiones/leads de diagnosis.

## 12. Roles y permisos iniciales

| Rol/perfil | Puede ver | Puede hacer | No debe hacer |
| --- | --- | --- | --- |
| `platform_admin` | Toda plataforma, clientes, servicios, sessions, leads, workers, knowledge, auditoria | Configurar plataforma, clientes, paquetes, assistant instances, workers, scopes, usuarios | Guardar secretos en metadata; saltar reglas de cliente/scope |
| `client_admin` | Team360.live, Vera, sesiones/leads/resultados propios, configuracion funcional | Revisar leads, estado del servicio, reportes y settings permitidos | Ver otros clientes; modificar workers criticos sin permiso plataforma |
| `operator/support` futuro | Sesiones/leads asignados, resultados operativos, tareas | Contactar/revisar/actualizar estado segun workflow | Gestionar plataforma completa o knowledge global |
| `visitor/public` | UI publica y su propia sesion en curso | Escribir texto libre, responder checklist, dejar contacto con consentimiento | Acceder a Console, ver leads ajenos, ver configuracion interna |

Permisos atomicos candidatos:

- `platform.manage`.
- `organizations.read`.
- `organizations.manage`.
- `workspaces.read`.
- `services.read`.
- `services.manage`.
- `diagnosis.session.read`.
- `diagnosis.lead.read`.
- `diagnosis.lead.manage`.
- `assistant.configure`.
- `knowledge.view`.
- `knowledge.upload`.
- `audit.view`.

Algunos ya existen parcialmente en seeds; `diagnosis.*`, `assistant.configure` y `platform.manage` no se observaron como permisos atomicos actuales.

## 13. Persistencia y migraciones

### Que alcanza con tablas existentes

Para una primera seed controlada, las tablas existentes alcanzan para:

- workspace cliente/canal via `core_workspaces`;
- usuarios via `core_users`;
- roles/perfiles via RBAC 002;
- assistant instance via `assistant_instances`;
- paquete via `automation_packages`;
- workers via `worker_definitions`, `package_workers`, `package_worker_configs`;
- knowledge scope via `knowledge_scopes`, `knowledge_scope_bindings`;
- sesiones/respuestas/leads via `automation_diagnosis_sessions`, `automation_diagnosis_answers`, `automation_diagnosis_leads`;
- eventos via `core_events`.

### Que probablemente requiere nueva migracion

Para salir sin deuda estructural fuerte, conviene una migracion futura explicita para:

- `core_organizations` o equivalente;
- relacion organization/workspace;
- servicios contratados visibles (`services` o `workspace_services`);
- perfiles/permisos productivos `platform_admin`, `client_admin`, `diagnosis.*`;
- mensajes conversacionales (`automation_diagnosis_messages`);
- slots extraidos (`automation_diagnosis_slots`);
- templates versionados L0/L1 (`diagnosis_templates`) si no se dejan en settings JSON inicialmente.

### Primero seed/mocks o migracion

Orden recomendado:

1. Definir documento y decision de naming.
2. Agregar seed/mocks productivos sin romper defaults existentes.
3. Solo despues agregar migracion si se decide formalizar organizations/services/messages/slots.

### Tablas que deberian recibir seeds

- `core_workspaces`.
- `core_users`.
- `core_roles`.
- `core_permission_profiles`.
- `core_user_roles`.
- `core_user_profiles`.
- `assistant_instances`.
- `automation_packages`.
- `worker_definitions`.
- `package_workers`.
- `package_worker_configs`.
- `knowledge_scopes`.
- `knowledge_scope_bindings`.
- Opcional: `knowledge_documents` y `knowledge_chunks` solo cuando se cargue L2 inicial.

### Que no conviene tocar todavia

- Migraciones 001-004 ya aplicadas: no reescribir ni corregir silenciosamente.
- ArangoDB/Milvus runtime.
- pgvector como RAG principal.
- Credenciales/provider secrets.
- `team360_orquestador`, salvo objetivo posterior explicito.
- Frontend home/Console hasta cerrar naming y seed backend.

## 14. Seeds / mocks recomendados

Archivos candidatos para cambios posteriores:

### Backend seed/migration

- `SrvRestAstroLS_v1/backend/db/migrations/005_team360_platform_vera_initial_seed.sql`: seed idempotente de plataforma, Team360.live y marca visible Vera. El filename puede mencionar Vera por contexto documental; los identificadores internos deben seguir siendo `team360_sales_diagnosis`, `pkg_sales_diagnosis`, `ks_team360_sales_diagnosis` y worker codes sin `vera`.
- `SrvRestAstroLS_v1/backend/modules/automation_diagnosis/assistant_instances.py`: agregar metadata/display fields para Vera sobre `team360_sales_diagnosis` o mover configuracion a seed/DB.
- `SrvRestAstroLS_v1/backend/modules/automation_diagnosis/schemas.py`: mantener defaults tecnicos actuales salvo que una decision posterior no relacionada con marca lo cambie.
- `SrvRestAstroLS_v1/backend/modules/automation_diagnosis/postgres_repository.py`: ajustar upsert para metadata organization/client/service si se formaliza.
- `SrvRestAstroLS_v1/backend/routes/automation_diagnosis.py`: mantener compatibilidad; no cambiar hasta nuevo contrato.
- `SrvRestAstroLS_v1/backend/routes/diagnosis.py`: futuro contrato publico conversacional.

### Frontend mocks

- `SrvRestAstroLS_v1/astro/src/lib/mock/organizations.ts`: agregar `org-team360-live` como cliente real.
- `SrvRestAstroLS_v1/astro/src/lib/mock/workspaces.ts`: agregar `ws-team360-live-public-site`.
- `SrvRestAstroLS_v1/astro/src/lib/mock/users.ts`: agregar usuarios reales sin secretos.
- `SrvRestAstroLS_v1/astro/src/lib/mock/bootstrap.ts`: perfiles `platform_admin`/`client_admin` o mapearlos a perfiles actuales.
- `SrvRestAstroLS_v1/astro/src/lib/mock/services.ts`: agregar `svc_sales_diagnosis` o equivalente estable con display visible Vera.
- `SrvRestAstroLS_v1/astro/src/lib/mock/workers.ts`: reflejar workers Vera en Console si se muestran a admins.

### Assistant instances/services/workspaces

- Backend: `assistant_instances.py` y futura migracion seed.
- Frontend: `services.ts`, `workspaces.ts`, `organizations.ts`.

### Home publica

- `SrvRestAstroLS_v1/astro/src/pages/index.astro`: insertar Vera cuando exista componente.
- `SrvRestAstroLS_v1/astro/src/lib/api/diagnosis.ts`: migrar o extender contrato.
- Futuro: `SrvRestAstroLS_v1/astro/src/components/diagnosis/PublicDiagnosisAssistant.svelte`.

Nota: el documento y un archivo seed pueden llevar `vera` en el nombre si su objetivo es describir/configurar la marca comercial. Dentro de codigo, seeds, migrations y referencias core, no introducir identificadores tecnicos `vera_*`; usar Vera solo en campos display/commercial/marketing.

## 15. Riesgos

- Mezclar `Team360 Platform` con `Team360.live` cliente y perder trazabilidad de permisos/costos.
- Hardcodear emails o dominios en logica de negocio en vez de seeds/config.
- Confundir demo interna con primer cliente real.
- Crear otro motor paralelo en vez de evolucionar `automation_diagnosis`.
- No preparar `KnowledgeScope` propio y terminar usando knowledge global o legacy.
- Enganchar home publica sin persistir `assistant_instance_code`, `site_channel`, `lead_owner` y `correlation_id`.
- Usar nombres comerciales como identificadores tecnicos provoca deuda y migraciones innecesarias ante rebranding.
- Renombrar `team360_sales_diagnosis` a `vera_team360_sales_diagnosis` romperia compatibilidad con tests/runtime/docs actuales y no corresponde a la decision aprobada.
- Exponer workers internos como producto visible para cliente.
- Iniciar con formulario/checklist rigido y romper la regla de texto libre primero.
- Activar L2/RAG sin filtros multi-tenant obligatorios.

## 16. Plan de implementacion posterior

### Paso 1 - Documento y decision de configuracion

- Aprobar este documento.
- Decision cerrada: Vera es marca comercial; el naming tecnico estable se mantiene.
- No crear `vera_team360_sales_diagnosis`.
- Usar display metadata para Vera sobre `team360_sales_diagnosis`, `pkg_sales_diagnosis` y `ks_team360_sales_diagnosis`.
- Confirmar si `Team360.live` debe ser `direct_client` o subtipo `self_customer`.

### Paso 2 - Seeds/mocks productivos

- Agregar seeds idempotentes de plataforma, cliente, admins, roles, paquete, service, assistant instance, workers y knowledge scope.
- Agregar mocks frontend equivalentes para Console.

### Paso 3 - Assistant instance Vera en backend

- Mantener configuracion tecnica `team360_sales_diagnosis`.
- Agregar display/commercial metadata para Vera sin cambiar identificadores core.
- Asegurar que el repository instala Vera con package workers y scope propio.

### Paso 4 - Servicio Vera visible en Console

- Agregar servicio activo.
- Mostrar sesiones, leads, resultados y configuracion segun permisos.
- Separar vista platform admin y client admin.

### Paso 5 - Home publica usando Vera

- Insertar entrada conversacional.
- Usar texto libre inicial.
- Enviar `assistant_instance_code`, channel, locale, visitor y attribution.
- Mantener fallback si backend falla.

### Paso 6 - Knowledge scope e ingesta L2 futura

- Cargar L0/L1 como configuracion versionada.
- Preparar L2 con documentos/chunks Markdown.
- Integrar ArangoDB/Milvus cuando el scope y filtros esten cerrados.

## 17. Lista exacta de archivos candidatos a modificar despues

| Path | Proposito posterior |
| --- | --- |
| `SrvRestAstroLS_v1/backend/db/migrations/005_team360_platform_vera_initial_seed.sql` | Seed idempotente productivo de plataforma, cliente y marca visible Vera. El filename puede mencionar Vera por ser documental/seed de marca; los identificadores internos deben seguir sin `vera_*`. |
| `SrvRestAstroLS_v1/backend/db/migrations/006_team360_organizations_services.sql` | Posible migracion futura para organizaciones y servicios visibles. |
| `SrvRestAstroLS_v1/backend/modules/automation_diagnosis/assistant_instances.py` | Agregar display/commercial metadata Vera sobre `team360_sales_diagnosis`. |
| `SrvRestAstroLS_v1/backend/modules/automation_diagnosis/schemas.py` | Revisar defaults y constants. |
| `SrvRestAstroLS_v1/backend/modules/automation_diagnosis/postgres_repository.py` | Ajustar upserts si se agregan organizations/services formales. |
| `SrvRestAstroLS_v1/backend/modules/automation_diagnosis/service.py` | Evolucionar flujo a free text/slots/checklist sin crear motor paralelo. |
| `SrvRestAstroLS_v1/backend/modules/automation_diagnosis/guided_flow.py` | Convertir pasos fijos en slots/checklist dinamico. |
| `SrvRestAstroLS_v1/backend/modules/automation_diagnosis/ai_interpreter.py` | Agregar slot extraction estructurada via LiteLLM. |
| `SrvRestAstroLS_v1/backend/routes/diagnosis.py` | Futuro contrato publico `/api/diagnosis/*`. |
| `SrvRestAstroLS_v1/backend/routes/diagnosis_schemas.py` | Schemas HTTP para start/message/checklist/lead/session. |
| `SrvRestAstroLS_v1/backend/app.py` | Registrar rutas nuevas cuando existan. |
| `SrvRestAstroLS_v1/astro/src/lib/mock/organizations.ts` | Agregar Team360.live como cliente real mock. |
| `SrvRestAstroLS_v1/astro/src/lib/mock/workspaces.ts` | Agregar workspace publico Team360.live. |
| `SrvRestAstroLS_v1/astro/src/lib/mock/users.ts` | Agregar admins reales sin secretos. |
| `SrvRestAstroLS_v1/astro/src/lib/mock/bootstrap.ts` | Ajustar perfiles/permisos visibles. |
| `SrvRestAstroLS_v1/astro/src/lib/mock/services.ts` | Agregar servicio tecnico estable con label visible Vera. |
| `SrvRestAstroLS_v1/astro/src/lib/mock/workers.ts` | Mostrar workers internos solo para admins si aplica. |
| `SrvRestAstroLS_v1/astro/src/lib/navigation/registry.ts` | Revisar modulo diagnosis/leads/configuracion cuando Console lo requiera. |
| `SrvRestAstroLS_v1/astro/src/lib/api/diagnosis.ts` | Crear cliente conversacional o mantener compatibilidad. |
| `SrvRestAstroLS_v1/astro/src/pages/index.astro` | Insertar Vera en home publica. |
| `SrvRestAstroLS_v1/astro/src/components/console/diagnosis/ConsoleDiagnosis.svelte` | Reusar conversacion y mostrar sesiones/resultados. |
| `SrvRestAstroLS_v1/astro/src/components/console/services/ServiceDetail.svelte` | Mostrar Vera como servicio activo con tabs. |
| `SrvRestAstroLS_v1/docs/status_actual.md` | Registrar avance tecnico/documental. |

## 18. Recomendacion final

El orden correcto para avanzar sin rehacer es:

1. Mantener cerrada la decision de naming: `Team360 Platform` distinto de `Team360.live`; Vera como marca visible; `team360_sales_diagnosis` como assistant instance tecnico estable.
2. Crear seeds idempotentes productivos en backend y mocks equivalentes en frontend, sin tocar el motor.
3. Registrar Vera en display/commercial metadata del assistant instance, paquete, service y knowledge scope tecnico existente.
4. Hacer visible Vera en Console con permisos diferenciados para platform admin y client admin.
5. Reemplazar el CTA `mailto` de la home por la experiencia conversacional de Vera.
6. Evolucionar `automation_diagnosis` hacia texto libre, slot extraction y checklist dinamico.
7. Recien despues activar L2 real con ArangoDB/Milvus, manteniendo PostgreSQL como verdad operacional.

No conviene empezar por frontend ni por una migracion amplia sin cerrar el modelo de configuracion. La pieza critica es resolver primero la identidad productiva: plataforma, cliente real, paquete Vera, assistant instance, workers, knowledge scope y trazabilidad de leads.
