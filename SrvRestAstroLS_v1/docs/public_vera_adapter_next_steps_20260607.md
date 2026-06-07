# Public Vera Adapter: estado actual y próximos pasos

Fecha: 2026-06-07  
Alcance: análisis de archivos existentes, sin modificar código funcional, backend ni home.

---

## 1. Qué hace hoy PublicVeraEntry.svelte

Componente Svelte 5 (Runes) renderizado como isla `client:load` al final de la home pública (`index.astro:273`). Presenta:

- Título "Hablá con Vera" + subtítulo copy.
- 3 botones de ejemplo precargados (leads WhatsApp, Facebook Ads, Excel manual).
- Textarea de texto libre + botón "Analizar oportunidad".
- Envío single-shot a `startPublicDiagnosis()`.
- Estados: `idle` → `submitting` → `response` (éxito) o `error` (fallback).
- Fallback por `mailto:contacto@team360.live` siempre visible.
- En éxito, muestra mensaje sintético local (no backend) y texto: *"Todavía no capturamos datos de contacto ni generamos un resultado final."*
- En error, muestra mensaje genérico y conserva el texto en textarea.

No hay loop conversacional, ni checklist, ni resultado, ni lead capture.

---

## 2. Qué hace hoy publicDiagnosis.ts

Adaptador frontend mínimo en `src/lib/api/publicDiagnosis.ts` (69 líneas). Exporta:

- `PUBLIC_DIAGNOSIS_CONTEXT`: constantes con identificadores técnicos estables.
- `PublicDiagnosisRequest` / `PublicDiagnosisResponse` (interfaces).
- `startPublicDiagnosis(request)`: función asíncrona que:
  1. Valida texto no vacío.
  2. Llama a `startSession()` (desde `diagnosis.ts`) → `POST /api/automation-diagnosis/session/start`.
  3. Llama a `saveAnswer()` (desde `diagnosis.ts`) → `POST /api/automation-diagnosis/session/{id}/answer` con `step_id="process_to_automate"` y `{ free_text: text }`.
  4. Retorna objeto con `session` y `message` generado localmente por `buildPreliminaryMessage()`.
- `buildPreliminaryMessage(text)`: función pura que trunca texto a 160 caracteres y genera 3 frases fijas concatenadas. **No hay mensaje del backend. No hay IA.**

---

## 3. Qué endpoint backend reutiliza

Reusa dos endpoints existentes de `/api/automation-diagnosis/*`:

| Endpoint | Uso | Response |
|---|---|---|
| `POST /api/automation-diagnosis/session/start` | Crear sesión de diagnóstico | `DiagnosisSession` (id, org, workspace, status, etc.) |
| `POST /api/automation-diagnosis/session/{id}/answer` | Guardar respuesta `process_to_automate` | `SaveAnswerResponse` |

**NO** llama a `POST /api/automation-diagnosis/session/{id}/classify` en ningún momento.

El backend resuelve `assistant_instance_id="team360_sales_diagnosis"` contra `TEAM360_SALES_DIAGNOSIS_CONFIG` en `assistant_instances.py` y aplica scoping, locale, workers y cost attribution.

---

## 4. Qué metadata envía actualmente

En `startSession()` (vía `diagnosis.ts`):

| Campo | Valor |
|---|---|
| `source_url` | `window.location.href` |
| `locale` | `"es"` |
| `assistant_instance_id` | `"team360_sales_diagnosis"` |
| `visitor.anonymous_id` | UUID de localStorage (clave `team360_public_visitor_id`) |
| `visitor.source_channel` | `"home_public"` |
| `visitor.site_channel` | `"team360.live"` |
| `visitor.assistant_display_name` | `"Vera"` |
| `visitor.lead_owner` | `"team360_live"` |
| `visitor.service_code` | `"svc_sales_diagnosis"` |
| `visitor.package_code` | `"pkg_sales_diagnosis"` |
| `visitor.knowledge_scope_code` | `"ks_team360_sales_diagnosis"` |
| `visitor.template_code` | `"team360_sales_automation_diagnosis"` |
| `visitor.initial_text_length` | `text.length` |

En `saveAnswer()`:

| Campo | Valor |
|---|---|
| `step_id` | `"process_to_automate"` |
| `answer.free_text` | texto sin trim |

---

## 5. Qué respuesta recibe y cómo la transforma

**Respuesta real del backend:**

- `startSession()` devuelve objeto `DiagnosisSession` completo (veintitantos campos: id, organization_id, workspace_id, status, etc.).
- `saveAnswer()` devuelve `SaveAnswerResponse` con session_id y answer persistida.

**Transformación frontend:**

- El mensaje visible al usuario **no viene del backend**. Se genera localmente con `buildPreliminaryMessage()`: 3 frases fijas concatenadas que reconocen el texto y anuncian que sigue revisión de sistemas.
- El session.id se retiene en el objeto response pero **no se usa para nada después**.
- No se parsea, clasifica ni transforma nada más; la UI solo muestra `responseMessage`.

---

## 6. Limitaciones para conversación real

| Limitación | Detalle |
|---|---|
| Single-shot | Un envío → respuesta estática → fin. No hay `message` endpoint. |
| Mensaje sintético | `buildPreliminaryMessage()` es cadenas fijas locales, no IA ni backend. |
| Sin slot extraction | El texto libre se manda a `process_to_automate` pero no se analiza. |
| Sin checklist dinámico | `GUIDED_STEPS` (10 pasos de Console) existe en `diagnosis.ts` pero no se usa aquí. |
| Sin classify | No se llama a `/classify`. La sesión queda en estado `active`. |
| Sin lead capture | No hay formulario de contacto, consentimiento ni CTA más allá de mailto. |
| Sin hidratación | Si el usuario recarga, no hay `GET /session/{id}` para recuperar estado. |
| Sin historial | No hay `DiagnosisMessage`, no hay conversación multiplexada. |
| Sin L2 retrieval | No hay RAG, no hay ArangoDB/Milvus, no hay knowledge scope consultado. |
| Sin fallback IA real | Si el backend falla, solo mailto. No hay modo offline parcial. |

---

## 7. Qué falta para `start → message → checklist → result → lead`

Flujo objetivo según `diagnosis_context_layer_l0_l1_l2_design_20260605.md`:

```
start → message → checklist → result → lead
```

Brechas actuales:

| Paso | Estado hoy | Lo que falta |
|---|---|---|
| **start** | ✅ `POST /api/automation-diagnosis/session/start` | Migrar a `POST /api/diagnosis/start` con contrato nuevo |
| **message** | ❌ No existe | Endpoint `POST /api/diagnosis/message` + slot extraction + respuesta real del backend |
| **checklist** | ❌ No existe | Endpoint `POST /api/diagnosis/submit-checklist` + lógica dinámica |
| **result** | ❌ No se llama a classify | Endpoint `GET /api/diagnosis/session/{id}` + resultado estructurado |
| **lead** | ❌ Solo mailto | Endpoint `POST /api/diagnosis/lead` + UI de captura + CTA |

Además:
- No hay componente de conversación multi-turn (solo `PublicVeraEntry`).
- No hay slot extraction engine en backend.
- No hay tabla de mensajes persistida.
- No hay checklist dinámico generado desde L0/L1.

El diseño completo de estos contratos ya está documentado en `diagnosis_context_layer_l0_l1_l2_design_20260605.md` (secciones 5, 6, 7, 11).

---

## 8. Contrato API futuro recomendado

Adoptar el contrato definido en `diagnosis_context_layer_l0_l1_l2_design_20260605.md:453-601`:

| Endpoint | Método | Propósito |
|---|---|---|
| `/api/diagnosis/start` | POST | Crear sesión con texto libre inicial |
| `/api/diagnosis/message` | POST | Mensaje, slot extraction, respuesta real |
| `/api/diagnosis/submit-checklist` | POST | Guardar faltantes/confirmaciones, trigger classify |
| `/api/diagnosis/lead` | POST | Capturar CTA + contacto + consentimiento |
| `/api/diagnosis/session/{id}` | GET | Hidratar sesión para UI |

Los endpoints actuales `/api/automation-diagnosis/*` se mantienen para el flujo guiado de Console (compatibilidad).

---

## 9. Cambios mínimos necesarios después

Orden sugerido:

1. **Backend**: crear `routes/diagnosis.py` con `POST /api/diagnosis/start` y `POST /api/diagnosis/message`. Reutilizar `AutomationDiagnosisService`, no crear motor paralelo.
2. **Backend**: agregar slot extraction (puede empezar con LLM + parsing simple).
3. **Backend**: agregar `POST /api/diagnosis/submit-checklist` con lógica de checklist dinámico basado en slots faltantes.
4. **Backend**: agregar `POST /api/diagnosis/lead` para captura de contacto y CTA.
5. **Frontend**: reemplazar `PublicVeraEntry.svelte` por `PublicDiagnosisAssistant.svelte` (o evolución) con componente de conversación multi-turn.
6. **Frontend**: agregar `DynamicChecklist.svelte` y `LeadCaptureCta.svelte`.
7. **E2E**: ampliar `public-vera.spec.ts` para cubrir `message` y `checklist`.
8. **Backend**: agregar `GET /api/diagnosis/session/{id}` para hidratación.

---

## 10. Qué NO conviene tocar todavía

| Área | Motivo |
|---|---|
| `/api/automation-diagnosis/*` existente | Flujo guiado de Console sigue activo y testeado |
| `ConsoleDiagnosis.svelte` | Flujo de Console no debe romperse |
| Scoring/classifier (`classifier.py`) | Funciona y es determinístico; migrar después |
| ArangoDB / Milvus / L2 | No hay necesidad para la primera iteración conversacional |
| PGVector / embeddings | Laboratorio/fallback; no bloquea flujo conversacional |
| `diagnosis.ts` base | Console depende de este cliente; no modificar |
| `assistant_instances.py` | Config de `team360_sales_diagnosis` ya está lista |
| Migraciones DB | `004` ya da las tablas de sesiones/answers/leads |
| Identificadores `vera_*` | Prohibido por decisión de naming; Vera es solo display |
| `team360_orquestador` | No tocar salvo que el objetivo lo pida explícitamente |
| `mailto:contacto@team360.live` | Debe conservarse como fallback ante error de backend |

---

## Archivos analizados

- `SrvRestAstroLS_v1/astro/src/components/diagnosis/PublicVeraEntry.svelte`
- `SrvRestAstroLS_v1/astro/src/lib/api/publicDiagnosis.ts`
- `SrvRestAstroLS_v1/astro/src/lib/api/diagnosis.ts`
- `SrvRestAstroLS_v1/astro/src/pages/index.astro`
- `SrvRestAstroLS_v1/astro/e2e/public-vera.spec.ts`
- `SrvRestAstroLS_v1/backend/routes/automation_diagnosis.py`
- `SrvRestAstroLS_v1/backend/routes/diagnosis_schemas.py`
- `SrvRestAstroLS_v1/backend/modules/automation_diagnosis/assistant_instances.py`
- `SrvRestAstroLS_v1/docs/diagnosis_context_layer_l0_l1_l2_design_20260605.md`
- `SrvRestAstroLS_v1/docs/status_actual.md`
- `docs/status_actual.md`
