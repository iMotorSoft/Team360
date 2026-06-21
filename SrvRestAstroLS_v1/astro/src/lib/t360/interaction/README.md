# T360 Interaction Blocks Lab

Laboratorio frontend aislado para validar `interaction_blocks` seguros de Team360.

## Alcance

- Renderiza bloques JSON tipados sin HTML dinamico.
- Usa fixtures locales, sin backend, DB, Milvus ni LiteLLM.
- Expone la ruta Astro `/t360-interaction-lab`.
- Emite eventos DOM internos para validar acciones y elecciones:
  - `t360action`
  - `t360choice`
  - `t360choices`

## Componentes principales

- `T360InteractionRenderer.svelte`: despacha cada bloque al componente visual correspondiente.
- `T360ActionCard.svelte`: renderiza `next_step_choice` y `diagnosis_action_card`.
- `T360SingleChoice.svelte`: renderiza seleccion simple.
- `T360MultiChoice.svelte`: renderiza seleccion multiple.
- `T360MissingRequirements.svelte`: renderiza faltantes del diagnostico.
- `T360ProductFitCard.svelte`: renderiza encaje de producto/pack.
- `T360DiagnosisSummary.svelte`: renderiza snapshot de diagnostico.
- `guards.ts`: normaliza y rechaza payloads invalidos.
- `events.ts`: centraliza el contrato de eventos DOM.
- `fixtures.ts`: contiene muestras locales auditables.

## Validacion

Desde `SrvRestAstroLS_v1/astro`:

```bash
corepack pnpm check
corepack pnpm build
corepack pnpm exec playwright test e2e/t360-interaction-lab.spec.ts --project=chromium
```

Si ya hay un servidor Astro levantado:

```bash
PLAYWRIGHT_SKIP_WEBSERVER=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:4321 \
  corepack pnpm exec playwright test e2e/t360-interaction-lab.spec.ts --project=chromium
```

## Regla de integracion

Este lab no define contrato backend productivo. Si un bloque se adopta en Vera o
Console, migrar primero el contrato a backend/tests y luego conectar la UI.
