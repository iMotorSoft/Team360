# Status actual - SrvRestAstroLS_v1/astro/docs

Objetivo: `documentacion-tecnica-frontend-local`

Ultima actualizacion: 2026-05-31

## Estado general

`SrvRestAstroLS_v1/astro/docs/` contiene notas locales del frontend Astro y recursos de apoyo visual.

## Acciones realizadas

### 2026-05-31 - Reubicacion de placeholder demo

- Se movio el README placeholder de `src/pages/demo/team360-orquestador/` a `docs/team360-orquestador-demo-placeholder.md`.
- Se evito que Astro genere una ruta accidental desde un archivo Markdown documental.
- No se implemento la pagina demo del orquestador.

## Validacion

- El build frontend debe exponer solo la ruta smoke `/` en esta fase.

## Pendientes recomendados

- Mantener fuera de `src/pages/` toda nota Markdown que no deba convertirse en ruta Astro.
