# Inventario técnico — Diagnóstico conversacional Team360

Fecha: 2026-07-16  
Estado: `INVENTORY_COMPLETE_WITH_GAPS`  
Alcance: lectura técnica de Diagnóstico en `astro/` y `backend/`; no se tomó
ninguna decisión de reutilización para otro producto.

## Contexto verificado

- Repositorio: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360`
- Rama: `feature/console-backend-core`
- HEAD al iniciar: `c3c764b2800d4666ca69d939476aaa1312b7eea9`
- No se modificó código de producto durante el inventario.

## Superficies reales

| Superficie | Ruta | Naturaleza |
| --- | --- | --- |
| Vera pública | `/t360#vera` | Conversación multi-turno |
| Landing equivalente | `/#vera` | Incluye la misma entrada Vera |
| Diagnóstico Console | `/w/[workspaceId]/diagnosis` | Cuestionario guiado secuencial |
| Laboratorio | `/t360-diagnosticador-lab` | Entorno de prueba del componente |
| Embed | `/t360-embed-demo` y variantes | Diagnóstico embebible |

La experiencia conversacional relevante es **Vera pública**. El diagnóstico de
Console es una experiencia distinta: formulario guiado y clasificación final.

## Árbol frontend de Vera

```text
t360.astro
└─ PublicVeraEntry.svelte (client:load)
   └─ DiagnosticadorCore.svelte
      ├─ markdown.ts
      ├─ DiagnosisResult.svelte
      └─ T360InteractionRenderer.svelte
         ├─ T360ActionCard.svelte
         ├─ T360SingleChoice.svelte
         ├─ T360MultiChoice.svelte
         ├─ T360MissingRequirements.svelte
         └─ T360ProductFitCard.svelte
```

| Área | Archivo | Responsabilidad |
| --- | --- | --- |
| Entrada pública | `astro/src/components/diagnosis/PublicVeraEntry.svelte` | Ejemplos, identidad Vera, bindings del core |
| Shell de diálogo | `astro/src/lib/t360/diagnosticador/DiagnosticadorCore.svelte` | Turnos, composer, envío, loading, error y reset |
| Resultado | `astro/src/components/diagnosis/DiagnosisResult.svelte` | Diagnóstico tipado, detalle, riesgos y acciones |
| Cliente HTTP | `astro/src/lib/api/publicDiagnosis.ts` | `POST /api/diagnosis/turn` y embed auth |
| Normalización | `astro/src/lib/t360/diagnosis/normalizer.ts` | Convierte la respuesta HTTP al modelo de UI |
| Renderer de bloques | `astro/src/lib/t360/interaction/T360InteractionRenderer.svelte` | Selecciona el componente según el tipo |
| Guardas | `astro/src/lib/t360/interaction/guards.ts` | Allowlist y límites de bloques remotos |
| Sesión cliente | `astro/src/lib/t360/diagnosticador/state/session.ts` | `sessionStorage` de sesión e idioma |

## Estado Svelte 5 y persistencia

Vera usa `$state`, `$derived`, `$props` y `$bindable`; no usa stores globales
para el diálogo.

- Estado local: mensajes visibles, `sessionId`, texto de entrada, carga, error,
  idioma y bloques consumidos.
- Cliente: persiste sólo `session_id` e información de idioma en
  `sessionStorage`.
- Los mensajes visibles no sobreviven una recarga. Además, al cargar se
  invalida la sesión activa en cliente de forma deliberada.
- Backend: conserva `history_summary` y memoria semántica. Con
  `AUTOMATION_DIAGNOSIS_REPOSITORY=postgres`, el estado es PostgreSQL.

## Flujo y contratos

```text
usuario escribe
→ DiagnosticadorCore agrega el turno visual
→ POST /api/diagnosis/turn
→ backend carga o crea ConversationState
→ actualiza memoria, contexto e idioma
→ retrieval Milvus cuando aplica
→ generación LiteLLM o respuesta determinista
→ guardrails
→ texto + diagnosis + interaction_block opcionales
→ normalización y validación frontend
→ render conversacional y estructurado
```

Request de `POST /api/diagnosis/turn`:

```json
{
  "session_id": "opcional",
  "message": "texto del usuario",
  "locale": "es",
  "interaction_response": "opcional",
  "assistant_instance_code": "opcional",
  "organization_code": "opcional",
  "workspace_code": "opcional",
  "package_code": "opcional",
  "knowledge_scope_code": "opcional"
}
```

Response relevante:

```json
{
  "session_id": "conv_...",
  "response_text": "respuesta conversacional",
  "assistant_display_name": "Vera",
  "turn_count": 1,
  "is_new": true,
  "language": {},
  "turn_decision": {},
  "diagnosis": {},
  "interaction_block": {}
}
```

El backend principal está en:

- `backend/routes/diagnosis.py`: ruta pública, allowlist de contexto y auth de embed.
- `backend/modules/sales_diagnosis_runtime/runtime.py`: memoria, intención,
  decisión, retrieval, guardrails y respuesta.
- `backend/modules/sales_diagnosis_runtime/contracts.py`: contratos de turno,
  estado y diagnóstico.
- `backend/modules/sales_diagnosis_runtime/structured_diagnosis.py`: salida
  estructurada determinista.

## Texto enriquecido

El texto libre usa un renderer Markdown propio (`markdown.ts`), no una
librería de Markdown instalada explícitamente.

Soporta: párrafos, listas no ordenadas, negrita, cursiva, código inline y
enlaces `https`, `mailto` o relativos. Los encabezados Markdown se convierten
en párrafos.

No soporta realmente: tablas, blockquotes, listas ordenadas, imágenes, bloques
de código ni componentes dinámicos desde Markdown.

La riqueza principal no llega desde Markdown: llega como JSON tipado en
`diagnosis` e `interaction_block`. Los bloques válidos son:

- `next_step_choice`
- `single_choice`
- `multi_choice`
- `missing_requirements`
- `product_fit_card`
- `diagnosis_action_card`

## Seguridad

- El texto Markdown se escapa antes de generar HTML.
- Hay allowlist local de etiquetas: `strong`, `em`, `code`, `a`, `ul`, `ol`,
  `li`, `p` y `br`.
- Los enlaces se restringen a protocolos permitidos.
- Los bloques estructurados se validan por tipo, longitud y cantidad antes de
  renderizarse.
- Embed incluye HMAC, cliente activo, origen permitido y rate limit.

Riesgo registrado: el saneamiento HTML es propio y basado en expresiones
regulares; no se usa un sanitizador especializado. No se hallaron tests
unitarios directos del renderer/sanitizador.

## Modelo visual, responsive y accesibilidad

- Usuario: burbuja verde a la derecha.
- Asistente: bloque blanco con borde a la izquierda.
- Diagnóstico: panel estructurado, no burbuja.
- Loading: “Vera está escribiendo…”.
- Error: tarjeta roja simple.
- Historial: scroll interno con altura máxima; composer no fijo.
- Móvil: prueba E2E específica a `393×852` para bloques secuenciales y sin
  overflow horizontal.

Implementado: foco visible global, botones etiquetados, `aria-expanded` para
detalle, algunos `aria-live`, reducción de movimiento y `dir="rtl"`/`lang`
en el resultado estructurado para hebreo.

Gaps: loading del chat sin anuncio explícito, sin gestión programática de foco
al responder o fallar, y sin soporte específico de Enter/Shift+Enter,
auto-resize o límite de caracteres en el composer.

## Diagnóstico Console

`astro/src/components/console/diagnosis/ConsoleDiagnosis.svelte` implementa:

```text
iniciar sesión
→ responder pasos controlados
→ guardar cada respuesta
→ clasificar
→ mostrar score, riesgos, paquete y recomendación
```

Consume `/api/automation-diagnosis/session/*`. No ofrece historial
conversacional ni renderer de respuestas enriquecidas; no debe confundirse con
Vera.

## Runtime real comprobado

Se levantó el backend en `127.0.0.1:7050` con la configuración proporcionada
para PostgreSQL, LiteLLM y Milvus.

| Verificación | Resultado |
| --- | --- |
| Backend `:7050` | Activo |
| `GET /health` | HTTP 200 |
| `GET /schema` | HTTP 200 |
| LiteLLM `:4000` | Puerto activo |
| Milvus `:19530` | Puerto activo |
| Estado conversacional | PostgreSQL configurado |
| Retrieval | Milvus configurado |
| Generación | LiteLLM configurado |

No se envió un turno productivo contra los servicios reales durante este
inventario, para no crear una conversación de diagnóstico de prueba en el
estado persistente.

## Tests

Tests focalizados ejecutados:

```text
uv run pytest tests/test_diagnosis_public_router.py \
  tests/test_sales_diagnosis_runtime_contracts.py -q

153 passed, 1 warning
```

El warning corresponde al modo por defecto en memoria de esos tests aislados,
que no cargaron la configuración runtime documentada arriba.

E2E relevantes identificados:

- `astro/e2e/public-vera.spec.ts`
- `astro/e2e/public-vera-mobile-sequential-blocks.spec.ts`
- `astro/e2e/public-vera-new-conversation.spec.ts`
- pruebas de embed y loader bajo `astro/e2e/diagnosticador-*.spec.ts`

No se ejecutó una regresión E2E visual completa ni un turno real con LiteLLM y
Milvus; ésa es la razón del estado `WITH_GAPS`.

## Riesgos priorizados

| Riesgo | Nivel |
| --- | --- |
| Sanitizador regex propio para `{@html}` | Alto |
| Acoplamiento a diagnóstico comercial y catálogo Team360 | Alto |
| Historial visual no persistente al recargar | Medio |
| Composer limitado para teclado y móvil | Medio |
| Accesibilidad parcial de loading/errores | Medio |
| RTL probado principalmente en resultado estructurado | Medio |

## Cierre

Este informe describe qué está construido para Diagnóstico en Team360 y qué
evidencia se obtuvo. No contiene una decisión ni una propuesta de reutilización
para Breslov Research; esa evaluación debe hacerse en una fase posterior.
