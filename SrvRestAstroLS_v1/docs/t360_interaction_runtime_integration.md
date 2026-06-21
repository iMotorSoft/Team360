# Team360 - Integracion controlada de interaction_blocks en /t360

## Alcance

Esta nota documenta la primera integracion frontend-runtime de `interaction_blocks`
en la experiencia publica `/t360`.

No implementa iframe, Web Component, SDK ni `postMessage`.

No modifica backend, endpoints, prompts, migraciones, DB, Milvus ni LiteLLM.

## Contrato backend observado

Endpoint:

```text
POST /api/diagnosis/turn
```

Request observado:

```json
{
  "session_id": "conv_optional",
  "message": "texto del usuario",
  "locale": "es"
}
```

Response observado:

```json
{
  "session_id": "conv_...",
  "response_text": "texto del assistant",
  "turn_count": 1,
  "is_new": true,
  "language": {},
  "turn_decision": {},
  "diagnosis": null
}
```

El backend actual no emite `interaction_block`.

## Contrato frontend esperado

La capa visual queda preparada para aceptar:

```json
{
  "interaction_block": {
    "type": "next_step_choice",
    "actions": []
  }
}
```

El campo entra como `unknown`, pasa por `normalizeT360InteractionBlock()` y solo
se renderiza mediante `T360InteractionRenderer`.

Si el campo no existe, `/t360` mantiene el comportamiento actual.

Si el campo existe pero es invalido, se muestra el fallback seguro del renderer
y la conversacion no se rompe.

## Adapter frontend-runtime

Archivos:

```text
SrvRestAstroLS_v1/astro/src/lib/t360/diagnosis/types.ts
SrvRestAstroLS_v1/astro/src/lib/t360/diagnosis/normalizer.ts
SrvRestAstroLS_v1/astro/src/lib/t360/diagnosis/adapter.ts
```

Responsabilidades:

* normalizar la respuesta real del runtime;
* aceptar `interaction_block` como payload opcional;
* validar el bloque sin acoplar componentes genericos al backend;
* traducir eventos UI estructurados a mensajes compatibles con el endpoint
  actual;
* conservar fallback al flujo textual cuando no hay bloque.

## Traduccion de eventos

Los componentes siguen emitiendo eventos locales:

```text
t360action
t360choice
t360choices
```

El adapter los traduce a `message` para `POST /api/diagnosis/turn`.

Ejemplos:

```text
show_current_diagnosis -> "Dame el diagnostico actual..."
continue_conversation  -> "Quiero seguir conversando..."
single_choice          -> "Selecciono la opcion ..."
multi_choice           -> "Selecciono estas opciones..."
```

Esto mantiene el transporte fuera de los componentes genericos.

## Bloques conectados

Quedan conectados de forma controlada:

```text
next_step_choice
single_choice
diagnosis_action_card
```

Los demas bloques siguen renderizables por el renderer y probados en el lab,
pero no dependen de que el backend actual los emita.

## Fallbacks

* Loading: se mantiene `isLoading` y bloqueo de envio.
* Error HTTP/backend caido: se mantiene mensaje localizado y retry.
* Sin `interaction_block`: se mantiene flujo actual.
* `interaction_block` invalido: fallback seguro del renderer.
* Diagnostico existente: se conserva `DiagnosisResult` actual.

## Validaciones ejecutadas

* `curl /api/health` contra backend local.
* `curl POST /api/diagnosis/turn` contra backend local.
* `curl /t360`, `/t360-interaction-lab` y `/api/health` via Astro local.
* Playwright del lab.
* Playwright completo de `/t360`.
* Smoke real `/t360` contra backend vivo.
