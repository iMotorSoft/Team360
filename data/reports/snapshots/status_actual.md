# Status actual - data/reports/snapshots

Objetivo: `snapshots-historicos`

Ultima actualizacion: 2026-06-18

## Estado general

`data/reports/snapshots/` contiene snapshots historicos de estado del repo o de tareas puntuales.

## Acciones realizadas

### 2026-06-18 - Capturas hero preview `/t360`

- Se agrego `t360-hero-preview-20260618/` con capturas PNG de validacion
  visual del ajuste comercial del hero de `/t360`.
- Capturas generadas:
  - `desktop-hero.png`;
  - `desktop-preview-card.png`;
  - `desktop-vera-anchor.png`;
  - `mobile-hero.png`;
  - `mobile-preview-card.png`;
  - `mobile-vera-anchor.png`.
- Se verifico que el CTA `Probar diagnóstico en vivo` apunta a `#vera`, que
  el scroll llega a la experiencia real de Vera y que no hay overflow
  horizontal en desktop ni mobile.

### 2026-05-28 - Snapshot automation_diagnosis Fase 1

- Se agrego `team360_automation_diagnosis_fase1_20260528.md` como evidencia historica de la implementacion tecnica realizada.
- El snapshot referencia la documentacion viva en `SrvRestAstroLS_v1/docs/automation_diagnosis_fase1.md`.
- Se mantuvo la separacion documental: evidencia historica en `data/reports/snapshots/`, documentacion tecnica de runtime en `SrvRestAstroLS_v1/docs/`.

### 2026-05-13 - Separacion de snapshots historicos

- Se movio a este directorio el snapshot `team360_status_20260331T133223-0300.md`.
- Se agrego este `status_actual.md` para registrar el ultimo estado del directorio.

## Validacion

- Se mantuvo el contenido historico del snapshot sin reescribir rutas internas antiguas.

## Pendientes recomendados

- Agregar aca nuevos snapshots cuando sean evidencia historica, no documentacion viva.
