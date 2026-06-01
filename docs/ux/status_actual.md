# Status actual - docs/ux

Objetivo: `producto-ux`

Ultima actualizacion: 2026-05-31

## Estado general

`docs/ux/` contiene decisiones compartidas de producto y experiencia que deben alinear diseno, frontend, backend y direccion comercial.

## Acciones realizadas

### 2026-05-31 - App Shell y sistema de layouts base

- Se agrego `team360-console-app-shell-and-layout-system.md`.
- Se definieron anatomia del App Shell, sidebar, topbar, switchers, breadcrumbs, area principal, panel lateral, notificaciones y boundary global.
- Se documentaron patrones de layout, estados de UI, responsive e implicancias para Astro y Svelte 5 con Runes.
- No se implementaron pantallas, componentes, rutas, build ni cambios de DB.

### 2026-05-31 - Modelo de navegacion contextual de Team360 Console

- Se agrego `team360-console-navigation-model.md`.
- Se definio navegacion derivada de tipo de organizacion, rol, permisos efectivos, workspace activo, servicios contratados y modulos habilitados.
- Se documento App Shell, contexto activo obligatorio, navegacion global, tabs de servicio y wireframes textuales.
- Se registraron implicancias para Astro, Svelte 5 con Runes y contrato backend de bootstrap.
- No se implementaron pantallas, componentes, rutas ni cambios de DB.

### 2026-05-31 - Separacion de dominios y estrategia Team360 Console

- Se agrego `team360-domains-and-console-strategy.md`.
- Se documento la separacion entre `team360.live` y `console.team360.live`.
- Se definio Team360 Console como plataforma operativa multi-organizacion.
- Se modelo a `Mamá Mía 360` como primera instancia de Partner / Distribuidor Regional, sin reglas hardcodeadas.
- Se registraron implicancias UX, frontend Astro + Svelte 5 con Runes y backend multi-tenant.

## Validacion

- El documento distingue estrategia aprobada de trabajo tecnico futuro.
- No se implementaron pantallas, componentes, rutas ni cambios de DB.

## Pendientes recomendados

- Crear wireframes visuales de baja fidelidad a partir del sistema de layouts.
- Disenar la evolucion del schema multi-organizacion antes de implementar permisos de consola.
