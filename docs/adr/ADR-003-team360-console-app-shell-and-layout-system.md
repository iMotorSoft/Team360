# ADR-003: App Shell y sistema de layouts de Team360 Console

Estado: `aceptado`

Fecha: `2026-05-31`

## Contexto

Team360 Console necesita una estructura UX/frontend consistente para Team360, partners y clientes finales. Crear layouts independientes por rol aumentaria duplicacion y haria mas dificil mantener contexto, permisos y estados de UI.

## Decision

Usar un unico App Shell adaptable con:

```text
sidebar contextual
topbar
organization / workspace switcher
breadcrumbs
main content area
right panel opcional
notification center
command/search opcional
user menu
global loading/error boundary
```

Definir layouts reutilizables para dashboard, listas, detalles, servicios, workers tecnicos, formularios, empty states, loading, errores y permission denied.

Astro estructura rutas y layouts base. Svelte 5 con Runes concentra interactividad y estado derivado. La UI se deriva del bootstrap backend y nunca reemplaza autorizacion.

## Consecuencias

- Team360, partners y clientes comparten estructura base.
- La profundidad tecnica varia por permisos y contexto.
- Los cambios de workspace deben invalidar estado obsoleto.
- Las rutas, componentes y estilos finales quedan pendientes de implementacion posterior.
- `Mamá Mía 360` permanece como ejemplo configurable de partner.

## Fuera de alcance

- Implementar codigo, rutas o componentes.
- Modificar DB o migraciones.
- Definir branding final.
- Cambiar configuracion de build.

## Referencias

- Guia extensa: `../ux/team360-console-app-shell-and-layout-system.md`
- Navegacion contextual: `../ux/team360-console-navigation-model.md`
- Arquitectura viva: `../../lat.md/console-multi-organization.md`
