# Diagnosis Assistant: diseño de capa contextual L0/L1/L2

Fecha: 2026-06-05  
Alcance: documento base de diseño. No implementa codigo, componentes, endpoints ni migraciones.  
Insumo principal: `SrvRestAstroLS_v1/docs/diagnosis_assistant_platform_inventory_20260605.md`.

## 1. Resumen ejecutivo

Team360 Diagnosis Assistant debe evolucionar desde el flujo guiado actual hacia un diagnostico conversacional estructurado.

No es un chatbot abierto sin limites y tampoco es un formulario inicial. La experiencia visible empieza con texto libre y conversacion natural; la estructura aparece por detras mediante extraccion de slots, contexto L0/L1, checklist dinamico, retrieval L2 cuando haga falta, scoring deterministico y captura de lead.

La tesis operativa es:

```text
Free Text -> Slot Extraction -> L0/L1 Context -> Dynamic Checklist -> L2 Retrieval if needed -> DiagnosisResult -> LeadCapture -> Console
```

El modulo existente `automation_diagnosis` debe ser la base. No conviene crear un motor paralelo. El inventario tecnico confirma que ya hay frontend real conectado a API Litestar, LiteLLM por adapter, modo PostgreSQL activable, retrieval simple, scoring deterministico y smokes reales. Ver `SrvRestAstroLS_v1/docs/status_actual.md`, seccion "Estado general", y `SrvRestAstroLS_v1/docs/diagnosis_assistant_platform_inventory_20260605.md`, secciones 7 y 8.

## 2. Principio UX central

La regla de producto es: texto libre primero.

El usuario debe poder escribir algo como:

```text
Quiero automatizar el seguimiento de leads que llegan por WhatsApp y email.
Hoy los vendedores se olvidan de responder y no sabemos que oportunidades se pierden.
```

El asistente debe interpretar ese texto, devolver valor inmediato y solo despues pedir lo faltante.

Reglas UX obligatorias:

- No iniciar con formulario largo.
- No usar experiencia tipo "presione 1 para ventas, presione 2 para soporte".
- No forzar categorias antes de escuchar el problema.
- El checklist aparece solo despues de interpretar el texto libre.
- Nunca preguntar algo que ya se pudo inferir con confianza razonable.
- Si algo fue inferido pero es critico, pedir confirmacion breve, no repetir una pregunta completa.
- Mostrar maximo 3 a 6 preguntas visibles por vez.
- Cada respuesta del asistente debe entregar valor: resumen, hipotesis, riesgo, oportunidad o proximo paso.

Esto no contradice `lat.md/automation-diagnosis.md`, que define que `automation_diagnosis` no es un chatbot abierto. La interpretacion correcta es: conversacion libre en superficie, estructura y decisiones controladas por Team360 por debajo.

## 3. Arquitectura conceptual

Flujo conceptual:

```text
Free Text
  -> Slot Extraction
  -> L0/L1 Context
  -> Dynamic Checklist
  -> L2 Retrieval if needed
  -> DiagnosisResult
  -> LeadCapture
  -> Console
```

Responsabilidades:

- `Free Text`: entrada natural del usuario en home publica, landing partner o Console.
- `Slot Extraction`: extrae proceso, dolor, sistemas, volumen, reglas, seguridad, sensibilidad de datos, resultado esperado e impacto.
- `L0/L1 Context`: selecciona el tipo de diagnostico y el mapa interno de slots, scoring, riesgos y automatizaciones posibles.
- `Dynamic Checklist`: pregunta solo faltantes o confirmaciones necesarias.
- `L2 Retrieval if needed`: recupera documentos/chunks cuando el caso requiere conocimiento de paquetes, verticales, seguridad, SAP B1, browser automation, HITL o casos similares.
- `DiagnosisResult`: genera salida tecnico-comercial estructurada.
- `LeadCapture`: captura CTA, consentimiento y datos comerciales.
- `Console`: deja trazabilidad operativa para Team360 o partner/distribuidor.

La salida del modelo no debe ser HTML. Segun `lat.md/ai-diagnosis-rag-runtime.md`, se debe renderizar UI desde estructuras semanticas validadas, eventualmente con AG-UI/SSE.

## 4. Relacion con JudaismoEnVivo

El patron probado de JudaismoEnVivo se resume como:

```text
Catalog -> MD -> Chunk -> Milvus -> analytics.py
```

Segun `docs/analisis-tecnico/team360_knowledge_scope_contract_judaismo_pattern.md`, el aprendizaje central es que `catalog_key` limita el corpus antes de recuperar contexto, `md_key` y `chunk_key` dan trazabilidad, y Milvus no es fuente de verdad.

Traduccion a Team360:

```text
Organization / Workspace / Service / AssistantInstance
  -> ResourceDocument
  -> ResourceChunk
  -> Semantic Index
  -> automation_diagnosis
```

Equivalencia operativa:

| JudaismoEnVivo | Team360 Diagnosis |
| --- | --- |
| `Catalog` | `KnowledgeScope` o `DiagnosisTemplate` asociado a Organization/Workspace/AssistantInstance |
| `catalog_key` | `knowledge_scope_id` + organization/workspace/assistant filters |
| `MD` | `ResourceDocument` / `KnowledgeDocument` |
| `md_key` | `document_id` |
| `Chunk` | `ResourceChunk` / `KnowledgeChunk` |
| `chunk_key` | `chunk_id` |
| Milvus vector | `Semantic Index` derivado |
| `analytics.py` | `automation_diagnosis` + scoring + result generation |

El documento `lat.md/ai-diagnosis-rag-runtime.md` fija que el runtime objetivo para la primera salida de diagnostico es ArangoDB + Milvus + LiteLLM, manteniendo PostgreSQL como verdad operacional.

## 5. L0/L1/L2

### L0

L0 es un abstract interno, corto y versionado, del tipo de diagnostico o servicio.

Ejemplo conceptual:

```json
{
  "template_code": "sales_automation_diagnosis",
  "summary": "Diagnostico de automatizacion comercial para leads, CRM, WhatsApp, email y seguimiento.",
  "default_outcome": "Lead calificado con paquete sugerido y proximo paso comercial."
}
```

Uso:

- Elegir tono, promesa visible y alcance inicial.
- Reducir tokens antes de cargar knowledge completo.
- Definir si el caso parece ventas, operaciones, reporting, ERP, marketplace o consultoria.

### L1

L1 es el mapa navegable interno del diagnostico.

Contiene:

- dolores comunes;
- fuentes posibles;
- slots minimos;
- preguntas minimas;
- reglas de scoring;
- automatizaciones candidatas;
- riesgos;
- condiciones HITL;
- bloqueos;
- CTAs posibles;
- paquetes permitidos.

L1 no se muestra como documentacion tecnica. Se usa para decidir que preguntar, que omitir y que confirmar.

### L2

L2 es el contenido completo:

- Markdown;
- documentos;
- playbooks;
- criterios de seguridad;
- catalogo de paquetes;
- knowledge scope;
- chunks semanticos;
- ArangoDB/Milvus cuando aplique.

Uso:

- Se invoca cuando L0/L1 y los slots no alcanzan.
- Sirve para casos con dominio especifico: SAP B1, marketplace, seguridad, MFA, browser automation, desktop automation, datos sensibles, verticales o casos similares.
- No debe bloquear la primera salida si L2 completo no esta disponible. Puede empezar con Markdown fixtures y evolucionar al patron ArangoDB/Milvus.

Por que L0/L1/L2 no rompen la conversacion:

- El usuario solo ve una conversacion natural.
- L0/L1/L2 son capas internas de contexto y decision.
- L0 evita cargar contexto irrelevante.
- L1 evita preguntar de mas.
- L2 se usa solo cuando agrega precision.
- El resultado se expresa en lenguaje comercial/operativo, no como estructura documental.

## 6. Flujo de usuario ideal

1. El usuario entra por la home de Team360, landing de partner o Console.
2. Ve un prompt libre, no un formulario.
3. Escribe que proceso quiere mejorar, que problema tiene o que quiere automatizar.
4. El backend crea o actualiza una `DiagnosisSession`.
5. El asistente extrae slots y selecciona contexto L0/L1.
6. Responde con valor inmediato:
   - resumen de lo entendido;
   - oportunidad preliminar;
   - posible impacto;
   - riesgo o condicion importante;
   - aviso de que faltan pocos datos.
7. El asistente muestra un checklist dinamico con faltantes.
8. El usuario completa o confirma los puntos necesarios.
9. Si el caso lo requiere, el backend recupera L2.
10. Team360 genera `DiagnosisResult` con scoring deterministico y salida estructurada.
11. La UI muestra:
    - factibilidad;
    - impacto;
    - complejidad;
    - fuentes necesarias;
    - automatizaciones sugeridas;
    - riesgos;
    - proximos pasos.
12. El usuario elige CTA:
    - solicitar revision;
    - WhatsApp;
    - agendar demo;
    - enviar diagnostico;
    - continuar en Console si corresponde.
13. La sesion se convierte en `LeadCapture` y queda visible en Console segun permisos.

## 7. Modelo de entidades

### DiagnosisTemplate

Define el tipo de diagnostico y su version.

Campos minimos:

- `template_code`
- `version`
- `l0`
- `l1`
- `supported_locales`
- `default_locale`
- `allowed_package_ids`
- `required_slots`
- `scoring_rules`
- `cta_policy`
- `status`

### DiagnosisSession

Representa una sesion de diagnostico.

Debe llevar siempre:

- `session_id`
- `organization_id`
- `workspace_id`
- `service_id` opcional inicialmente
- `assistant_instance_id`
- `automation_package_id`
- `knowledge_scope_id`
- `site_channel`
- `lead_owner`
- `partner_id` cuando aplique
- `market_country` cuando aplique
- `locale`
- `correlation_id`
- `status`

Esto sigue el contexto requerido en `lat.md/customer-packaged-assistant-instance.md`.

### DiagnosisMessage

Historial conversacional auditable.

Campos minimos:

- `message_id`
- `session_id`
- `role`
- `content`
- `locale`
- `message_type`
- `extracted_slots`
- `created_at_utc`

### DiagnosisSlot

Dato estructurado inferido, confirmado o faltante.

Campos minimos:

- `slot_key`
- `value`
- `confidence`
- `source`
- `status`
- `asked_at_utc`
- `confirmed_at_utc`

Estados sugeridos:

- `missing`
- `inferred`
- `needs_confirmation`
- `confirmed`
- `rejected`

### DiagnosisChecklist

View model temporal para UI.

Debe contener:

- slots faltantes;
- slots inferidos que requieren confirmacion;
- labels localizados;
- orden de prioridad;
- maximo visible recomendado;
- razon interna de cada pregunta.

### DiagnosisResult

Resultado final tecnico-comercial.

Debe incluir:

- `classification`
- `score_total`
- `score_breakdown`
- `feasibility`
- `impact`
- `complexity`
- `required_sources`
- `suggested_automations`
- `risk_flags`
- `blocked_actions`
- `automation_mode`
- `recommended_package_type`
- `next_steps`
- `visible_summary`
- `internal_card`

### LeadCapture

Conversion comercial de una sesion.

Debe incluir:

- `session_id`
- `lead_owner`
- `partner_id` cuando aplique
- `cta_type`
- `contact`
- `consent`
- `diagnosis_summary`
- `status`
- `created_at_utc`

### PartnerConfig / DistributorConfig

Configuracion por partner/canal.

Campos minimos:

- `partner_slug`
- `organization_id`
- `workspace_id`
- `display_name`
- `market_country`
- `supported_locales`
- `default_locale`
- `branding`
- `contact_channels`
- `assistant_instance_id`
- `lead_owner`
- `cost_center`
- `status`

## 8. Dos assistant instances iniciales

### `team360_sales_diagnosis`

Uso:

- Canal: home publica Team360 y Console.
- Site channel: `team360.live`.
- Lead owner: Team360.
- Mercado: directo.
- Idioma inicial: español, con soporte extensible a ingles.
- Branding: Team360.
- Knowledge scope: `ks_team360_sales_diagnosis`.

Debe tratarse como primera instalacion cliente real del paquete, no demo interna. Esta regla esta documentada en `lat.md/customer-packaged-assistant-instance.md`.

### `mamamia360_sales_diagnosis`

Uso:

- Canal: landing publica de partner, por ejemplo `/p/[partnerSlug]`.
- Partner/distribuidor: Mama Mia 360.
- Mercado: Israel.
- Idiomas: español, ingles, hebreo.
- Lead owner: Mama Mia 360.
- Branding: configurable por partner.
- Knowledge scope: `ks_mamamia360_sales_diagnosis`.

No debe existir logica tipo `if partner == "Mama Mia 360"`. Segun `lat.md/console-multi-organization.md`, Mama Mia 360 es una instancia configurable de partner regional, no una excepcion de producto.

## 9. Frontend propuesto

Stack respetado: Astro, Svelte 5, Tailwind 4, DaisyUI 5, pnpm.

Componentes sugeridos:

- `PublicDiagnosisAssistant.svelte`: isla publica que resuelve config de assistant instance y abre el flujo desde texto libre.
- `DiagnosisConversation.svelte`: conversacion reutilizable para home, landing partner y Console.
- `DynamicChecklist.svelte`: render de faltantes y confirmaciones, maximo 3 a 6 visibles.
- `DiagnosisResultCard.svelte`: muestra factibilidad, impacto, complejidad, fuentes, automatizaciones, riesgos y proximos pasos.
- `LeadCaptureCta.svelte`: CTA final y captura de contacto.

Paginas y ubicaciones:

- Home publica Team360: modificar `SrvRestAstroLS_v1/astro/src/pages/index.astro` para insertar `PublicDiagnosisAssistant.svelte`.
- Landing partner: crear en una fase posterior `SrvRestAstroLS_v1/astro/src/pages/p/[partnerSlug].astro`.
- Console: evolucionar `SrvRestAstroLS_v1/astro/src/components/console/diagnosis/ConsoleDiagnosis.svelte` para reutilizar `DiagnosisConversation.svelte`.
- Service view: mostrar el diagnostico como servicio activo en `ServiceDetail.svelte` o como vista relacionada.

El inventario actual detecta que el unico flujo real vive en Console y que la home aun usa `mailto`; ver `diagnosis_assistant_platform_inventory_20260605.md`, secciones 3, 4 y 9.

## 10. Backend propuesto

Stack respetado: Litestar, LiteLLM, PostgreSQL con `psycopg 3 async`, ArangoDB/Milvus para RAG.

Modulos sugeridos:

- `backend/routes/diagnosis.py`: contrato publico nuevo `/api/diagnosis/*`.
- `backend/modules/automation_diagnosis/templates.py`: definicion de `DiagnosisTemplate`, L0 y L1.
- `backend/modules/automation_diagnosis/slots.py`: extraccion, normalizacion, merge y confianza de slots.
- `backend/modules/automation_diagnosis/checklist.py`: generacion de checklist dinamico.
- `backend/modules/automation_diagnosis/conversation.py`: mensajes, respuesta inmediata y estado conversacional.
- `backend/modules/automation_diagnosis/partner_configs.py`: Team360 y partner/distributor configs.
- `backend/modules/automation_diagnosis/service.py`: evolucionar sin reemplazar; debe orquestar start/message/checklist/result/lead.

Integracion LiteLLM:

- Reutilizar el adapter existente.
- Agregar fase de slot extraction estructurada.
- Enviar metadata de organization/workspace/assistant/session/correlation como ya define `lat.md/ai-diagnosis-rag-runtime.md`.
- La LLM propone señales y resumen; Team360 decide scoring y clasificacion.

Persistencia PostgreSQL:

- Usar las tablas actuales `automation_diagnosis_sessions`, `automation_diagnosis_answers`, `automation_diagnosis_leads` y `core_events` en la primera iteracion.
- Agregar tablas de mensajes/slots/templates solo cuando el contrato conversacional lo requiera.
- Resolver la deuda de hidratacion desde DB en modo postgres antes de depender de sesiones largas o multi-proceso.

Futura conexion ArangoDB/Milvus para L2:

- ArangoDB debe ser fuente textual/grafo.
- Milvus debe ser indice derivado.
- Retrieval siempre filtrado por organization/workspace/assistant/knowledge scope.
- No bloquear la salida conversacional inicial por L2 completo.

## 11. Contrato API inicial

Los endpoints actuales `/api/automation-diagnosis/*` pueden mantenerse temporalmente. El nuevo contrato publico deberia ser `/api/diagnosis/*`.

### `POST /api/diagnosis/start`

Objetivo: crear sesion.

Request conceptual:

```json
{
  "assistant_instance_id": "team360_sales_diagnosis",
  "source_url": "https://team360.live",
  "locale": "es",
  "visitor": {},
  "initial_text": "Quiero automatizar el seguimiento de leads por WhatsApp."
}
```

Response conceptual:

```json
{
  "session_id": "diag_...",
  "status": "active",
  "assistant_instance_id": "team360_sales_diagnosis",
  "locale": "es",
  "message": {
    "role": "assistant",
    "content": "Entiendo que queres mejorar seguimiento comercial..."
  },
  "slots": {},
  "checklist": []
}
```

### `POST /api/diagnosis/message`

Objetivo: guardar texto libre, extraer slots, responder con valor inmediato y devolver faltantes.

Request conceptual:

```json
{
  "session_id": "diag_...",
  "message": "Los leads llegan por WhatsApp y email, unas 40 consultas por dia.",
  "locale": "es"
}
```

Response conceptual:

```json
{
  "session_id": "diag_...",
  "assistant_response": {
    "summary": "El caso parece una automatizacion comercial con impacto operativo.",
    "immediate_value": [
      "Se puede ordenar origen, prioridad y seguimiento.",
      "Probablemente requiera aprobacion humana para oportunidades de alto valor."
    ]
  },
  "inferred_slots": [
    {"slot_key": "systems_involved", "value": ["whatsapp", "email"], "confidence": 0.92}
  ],
  "checklist": {
    "items": [
      {"slot_key": "rules_clarity", "label": "Que tan claras son las reglas de prioridad?"},
      {"slot_key": "expected_result", "label": "Que resultado concreto esperas?"}
    ]
  }
}
```

### `POST /api/diagnosis/submit-checklist`

Objetivo: guardar faltantes/confirmaciones y generar diagnostico si ya alcanza.

Request conceptual:

```json
{
  "session_id": "diag_...",
  "answers": [
    {"slot_key": "rules_clarity", "value": "partially_clear"},
    {"slot_key": "expected_result", "value": "Lead clasificado y alerta de seguimiento"}
  ]
}
```

Response conceptual:

```json
{
  "session_id": "diag_...",
  "status": "diagnosed",
  "result": {
    "classification": "operational_automation",
    "feasibility": "high",
    "impact": "high",
    "complexity": "medium",
    "recommended_package_type": "team360_ops_starter"
  }
}
```

### `GET /api/diagnosis/session/{id}`

Objetivo: hidratar sesion para UI publica o Console.

Response conceptual:

```json
{
  "session_id": "diag_...",
  "status": "diagnosed",
  "messages": [],
  "slots": [],
  "checklist": {},
  "result": {},
  "lead": {}
}
```

### `POST /api/diagnosis/lead`

Objetivo: capturar CTA/contacto y convertir la sesion en lead calificado.

Request conceptual:

```json
{
  "session_id": "diag_...",
  "cta_type": "schedule_demo",
  "contact": {
    "name": "Nombre",
    "email": "cliente@example.com",
    "phone": "+972..."
  },
  "consent": true
}
```

Response conceptual:

```json
{
  "session_id": "diag_...",
  "lead_id": "lead_...",
  "lead_owner": "Team360",
  "status": "qualified"
}
```

## 12. Reglas de producto

- Nunca iniciar con formulario largo.
- Nunca iniciar con menu tipo "presione 1".
- Maximo 3 a 6 preguntas visibles por vez.
- No repetir preguntas inferidas.
- Confirmar solo inferencias criticas o de baja confianza.
- LLM propone; Team360 decide.
- Scoring deterministico al final.
- La respuesta siempre entrega valor inmediato.
- La salida debe ser estructurada para UI.
- Todo diagnostico debe asociarse a Organization, Workspace, Service y AssistantInstance.
- Todo resultado debe tener lead owner y trazabilidad de canal.
- Para partner, conservar atribucion de partner, locale, mercado y canal.
- No prometer bypass de MFA, hardware keys, biometria, anti-bot o acciones financieras irreversibles.
- No exponer workers al cliente como producto contratado; el cliente ve el servicio.

## 13. Riesgos y decisiones

Decisiones:

- No crear un motor paralelo.
- Evolucionar `automation_diagnosis` existente.
- No adoptar OpenViking como dependencia core.
- Copiar metodologia L0/L1/L2, no acoplar Team360 a una implementacion externa innecesaria.
- No bloquear salida por RAG completo.
- L2 puede venir despues usando el patron JudaismoEnVivo.
- Mantener PostgreSQL como verdad operacional.
- Mantener ArangoDB/Milvus como runtime RAG objetivo, no como fuente comercial.

Riesgos:

- El flujo actual esta implementado como cuestionario de 10 pasos; hay que migrarlo a conversacion sin romper scoring.
- `GUIDED_STEPS` existe duplicado entre frontend y backend; conviene mover la verdad del checklist al backend.
- `mamamia360_sales_diagnosis` esta documentado pero no configurado en runtime.
- La home publica aun no tiene asistente embebido.
- La persistencia PostgreSQL actual guarda snapshots, pero falta hidratacion robusta desde DB.
- Multi idioma existe en navegacion, no todavia en todo el contenido del diagnostico.
- L2 ArangoDB/Milvus esta documentado, pero no implementado en runtime.

## 14. Roadmap minimo real

No es un MVP descartable. Es una primera version real minima que valida el producto y evita rehacer la arquitectura.

### Paso 1: diseño y contrato

- Cerrar este diseño L0/L1/L2.
- Definir contrato `/api/diagnosis/*`.
- Definir slots canonicos y checklist dinamico.
- Definir configs iniciales Team360 y Mama Mia 360.

### Paso 2: frontend conversacional reutilizable

- Crear componentes Svelte reutilizables.
- Insertar en home publica Team360.
- Preparar landing `/p/[partnerSlug]`.
- Adaptar Console diagnosis view.

### Paso 3: backend conversacional con slots/checklist

- Agregar `conversation.py`, `slots.py`, `checklist.py`, `templates.py`.
- Mantener scoring actual.
- Mantener endpoints actuales hasta migrar E2E.

### Paso 4: Team360 + Mama Mia 360

- Configurar `team360_sales_diagnosis`.
- Agregar `mamamia360_sales_diagnosis`.
- Resolver branding, locale, lead owner y market.
- Validar español, ingles y hebreo.

### Paso 5: persistencia y Console tracking

- Persistir mensajes, slots, resultados y leads.
- Hidratar sesiones desde PostgreSQL.
- Mostrar sesiones/leads en Console por permisos.
- Agregar eventos de conversion y abandono.

### Paso 6: L2 RAG con ArangoDB/Milvus

- Implementar source ArangoDB para documentos/chunks.
- Implementar Milvus como indice derivado.
- Filtrar por organization/workspace/assistant/knowledge scope.
- Medir fallback Arango-only.
- Mantener pgvector como laboratorio/fallback, no runtime principal inicial.

## 15. Recomendacion final

La recomendacion tecnica es evolucionar `automation_diagnosis` hacia un orquestador conversacional de diagnostico, no crear un producto nuevo al costado.

Primero hay que cambiar la experiencia de entrada: texto libre en home Team360 y en landing de partner. Segundo, conservar el motor actual de scoring y persistencia. Tercero, introducir L0/L1 para reducir preguntas y tokens. Cuarto, diferir L2 ArangoDB/Milvus hasta que el flujo conversacional y la captura de lead funcionen con Team360 y Mama Mia 360.

El minimo real para salir es:

- texto libre inicial;
- respuesta inmediata;
- checklist dinamico;
- diagnostico estructurado;
- CTA/lead capture;
- trazabilidad por Organization/Workspace/Service/AssistantInstance;
- dos assistant instances configuradas: `team360_sales_diagnosis` y `mamamia360_sales_diagnosis`.

## Referencias revisadas

- `AGENTS.md`: reglas de ubicacion documental, ramas y separacion tecnica/comercial.
- `.agents/skills/team360-project/SKILL.md`: reglas de trabajo Team360, driver PostgreSQL, repositories y limites de `team360_orquestador`.
- `SrvRestAstroLS_v1/docs/status_actual.md`: estado actual de Fase 1, LiteLLM, PostgreSQL y smokes.
- `SrvRestAstroLS_v1/docs/diagnosis_assistant_platform_inventory_20260605.md`: inventario de rutas, frontend, backend, mocks, riesgos y propuesta inicial.
- `lat.md/automation-diagnosis.md`: assistant instances, outputs, intake fields, clasificacion y regla LLM/scoring.
- `lat.md/ai-diagnosis-rag-runtime.md`: ArangoDB + Milvus + LiteLLM, PostgreSQL como verdad, AG-UI/SSE.
- `lat.md/customer-packaged-assistant-instance.md`: Team360 direct como primera instalacion cliente real.
- `lat.md/console-multi-organization.md`: public site vs Console, partner configurable y autorizacion.
- `lat.md/status_actual.md`: estado de arquitectura viva y contrato JudaismoEnVivo.
- `docs/analisis-tecnico/team360_knowledge_scope_contract_judaismo_pattern.md`: equivalencia Catalog/MD/Chunk hacia KnowledgeScope/Document/Chunk.
- `docs/analisis-tecnico/team360_ai_diagnostico_stack_arango_milvus_litellm.md`: factibilidad del stack ArangoDB + Milvus + LiteLLM.
