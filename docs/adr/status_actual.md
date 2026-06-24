# Status actual - docs/adr

Objetivo: `decisiones-arquitectura`

Ultima actualizacion: 2026-06-24

## Estado general

`docs/adr/` contiene versiones breves y trazables de decisiones de arquitectura de Team360.

## Acciones realizadas

### 2026-06-24 - ADR-006 plantilla base para nuevos proyectos

- Se creo `ADR-006-new-project-bootstrap-template.md`.
- Se registro la decision de reutilizar la estructura operativa/documental de
  Team360 como plantilla base para nuevos proyectos.
- Se enlazo la plantilla ejecutable `docs/templates/project-structure-template.md`.
- Se agrego el criterio de adopcion parcial de herramientas externas: tomar
  conceptos de gstack `/diagram` y `/investigate` sin adoptar gstack como
  dependencia.
- Se distinguio `docs/adr/` como decision historica y `lat.md/` como
  invariante vivo.
- Se actualizo `docs/adr/README.md`.

### 2026-05-31 - ADR-005 pnpm, Tailwind CSS 4, DaisyUI 5 y wrappers UI

- Se creo `ADR-005-team360-pnpm-tailwind4-daisyui5-ui-policy.md`.
- Se registro pnpm como package manager obligatorio.
- Se registro Tailwind CSS 4 + DaisyUI 5 CSS-first como stack UI inicial obligatorio.
- Se fijo el encapsulamiento DaisyUI detras de wrappers Team360.

### 2026-05-31 - Correccion ADR-004 DaisyUI 5 + Tailwind 4

- Se corrigio la consecuencia incorrecta que exigia eliminar o postergar DaisyUI.
- Se documento Tailwind CSS 4 + DaisyUI 5 como combinacion valida con integracion CSS-first.
- Se mantuvo la prohibicion de reutilizar tema y configuracion legacy de Vertice360.

### 2026-05-31 - ADR-004 Base frontend desde Vertice360 con stack moderno

- Se creo `ADR-004-team360-frontend-base-vertice360-modern-stack.md`.
- Se registro la decision de tomar Vertice360 como base tecnica/UX inicial y modernizar a pnpm, Astro 6, Svelte 5 con Runes, Tailwind 4 y AG-UI.

### 2026-05-31 - ADR-003 App Shell y layouts de Team360 Console

- Se creo `ADR-003-team360-console-app-shell-and-layout-system.md`.
- Se registro un unico shell adaptable con layouts reutilizables y estados de UI seguros.

### 2026-05-31 - ADR-002 navegacion contextual de Team360 Console

- Se creo `ADR-002-team360-console-navigation-by-role.md`.
- Se registro la decision de usar un App Shell adaptable y navegacion derivada desde contexto y permisos efectivos.

### 2026-05-31 - ADR-001 separacion de dominios y Team360 Console

- Se creo `ADR-001-team360-domain-separation-and-console.md`.
- Se registro la decision base para separar sitio publico y consola privada multi-organizacion.

## Validacion

- Para `ADR-006-new-project-bootstrap-template.md` se ejecuto
  `git diff --check` sin errores de whitespace.
- El ADR enlaza la guia extensa de producto y UX y la arquitectura viva correspondiente.

## Pendientes recomendados

- Mantener ADRs breves; colocar narrativa extensa en el directorio documental apropiado.
