# Status actual - docs/analisis-tecnico

Objetivo: `analisis-tecnico-no-runtime`

Ultima actualizacion: 2026-05-15

## Estado general

`docs/analisis-tecnico/` contiene analisis tecnico de producto, automatizacion o factibilidad que no pertenece directamente al runtime de desarrollo.

## Acciones realizadas

### 2026-05-15 - Analisis de modelos visuales economicos para SAP B1

- Se agrego `sap_b1_modelos_vision_costos_automatizacion.md`.
- El documento complementa la factibilidad SAP B1 existente con:
  - comparacion entre `gpt-5-nano` y `Gemini 2.5 Flash-Lite`;
  - criterio para usar Microsoft UI Automation como fuente primaria;
  - uso de OCR local y modelos visuales como fallback;
  - modelos relevantes disponibles en OpenRouter;
  - politica recomendada de ruteo y benchmark minimo.
- Decision preliminar registrada:
  - `gpt-5-nano` como opcion visual economica si se usa OpenAI directo;
  - `google/gemini-2.5-flash-lite` como opcion visual economica si se centraliza en OpenRouter;
  - DeepSeek V4 Flash como orquestador textual, no como lector de capturas.
- No se toco runtime, backend, Astro, `team360_orquestador`, AG-UI ni laboratorio browser.

### 2026-05-13 - Reubicacion de factibilidad SAP Business One

- Se movio `sap_b1_desktop_automation_factibilidad.md` desde `SrvRestAstroLS_v1/docs/` a este directorio.
- Motivo:
  - es un documento de factibilidad tecnica y comercial interna;
  - no es documentacion de runtime, backend, Astro, migraciones ni implementacion productiva;
  - corresponde a `docs/analisis-tecnico/` por la convencion documental vigente.
- El documento conserva la ampliacion local con secciones de licenciamiento, checklist, costos, monitoreo y rollback.
- Documentos actuales:
  - `analisis_tecnico_browser_automation_modelos_ai_2026-05-08.md`
  - `sap_b1_desktop_automation_factibilidad.md`
  - `sap_b1_modelos_vision_costos_automatizacion.md`

### 2026-05-13 - Separacion de analisis tecnico no operativo

- Se movio a este directorio el analisis tecnico de browser automation y modelos AI.
- Documentos actuales:
  - `analisis_tecnico_browser_automation_modelos_ai_2026-05-08.md`
- Se agrego `README.md` como indice local.
- Se agrego este `status_actual.md` para registrar el ultimo estado del directorio.

## Validacion

- Se agrego el nuevo documento al indice local `docs/analisis-tecnico/README.md`.
- Se verifico que `sap_b1_desktop_automation_factibilidad.md` existe en `docs/analisis-tecnico/`.
- Se mantuvo separado de `SrvRestAstroLS_v1/docs/`, que queda para desarrollo, backend, Astro, runtime y migraciones.

## Pendientes recomendados

- Usar este directorio para factibilidad tecnica no ligada todavia a implementacion concreta.
- Si un analisis pasa a decisiones de desarrollo, reflejarlo tambien en `SrvRestAstroLS_v1/docs/status_actual.md`.
