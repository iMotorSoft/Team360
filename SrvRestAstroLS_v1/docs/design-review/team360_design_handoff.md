# Team360 Design Handoff

## Objetivo

Esta rama es un snapshot para revisión visual y UX de la home pública y Team360 Console con datos mock. Sirve para diseñar navegación, jerarquía, responsive y estados visibles sin depender del backend.

## Rama

`ux/team360-console-design-handoff`

## Cómo correr la demo

```bash
cd SrvRestAstroLS_v1/astro
corepack pnpm install --frozen-lockfile
corepack pnpm dev --host 127.0.0.1 --port 4321
```

Para ejecutar el smoke local y regenerar capturas con Chromium:

```bash
corepack pnpm design:smoke
```

## Rutas principales

- Home pública: `/`
- Acceso mock: `/login`
- Selector de experiencias: `/select-workspace`
- Dashboard Team360: `/w/ws-team360-control`
- Servicios Team360: `/w/ws-team360-control/services`
- Reportes Team360: `/w/ws-team360-control/reports`
- Alertas Team360: `/w/ws-team360-control/alerts`
- Tareas Team360: `/w/ws-team360-control/tasks`
- Workers Team360: `/w/ws-team360-control/workers`
- Runs Team360: `/w/ws-team360-control/runs`
- Dashboard partner: `/w/ws-mama-mia-israel?profile=partner_admin`
- Dashboard cliente final: `/w/ws-netzaj-marketplace?profile=client_admin`
- Servicios cliente final: `/w/ws-netzaj-marketplace/services?profile=client_admin`
- Detalle mock real: `/w/ws-netzaj-marketplace/services/svc-netzaj-questions?profile=client_admin`

## Qué revisar en home

- Claridad de propuesta.
- Percepción premium sin intimidar.
- CTA local hacia consola.
- Composición mobile.
- Copy comercial.

## Qué revisar en consola

- Navegación contextual.
- Salida explícita `Cambiar workspace` hacia `/select-workspace` desde cualquier pantalla interna.
- Jerarquía visual y densidad.
- Dashboard.
- Servicios y detalle.
- Reportes, alertas y tareas.
- Drawer mobile.
- Estados vacíos.
- Diferencias visibles entre Team360, partner y cliente final.

## Perfiles mock

- `Team360 Admin`
- `Operador Team360`
- `Admin Distribuidor` para el perfil partner.
- `Admin Cliente`

## Limitaciones del mock

No son reales:

- Login.
- Auth.
- Permisos productivos.
- Backend.
- DB.
- AG-UI.
- Workers.
- Reportes descargables.

## Capturas

Las capturas regenerables se guardan en:

`SrvRestAstroLS_v1/docs/design-review/screenshots/`

Capturas focalizadas del cambio de workspace:

- `desktop-change-workspace-link.png`
- `mobile-change-workspace-link.png`

`Cambiar workspace` conserva `?profile=` para perfiles mock no default cuando vuelve al selector. Esta navegación forma parte de la experiencia de diseño y no representa auth, cierre de sesión ni permisos productivos.

## Pendientes para diseño

- [ ] Revisar paleta.
- [ ] Ajustar espaciados.
- [ ] Confirmar tipografía.
- [ ] Unificar criterio de íconos.
- [ ] Revisar estados vacíos, carga, advertencia y bloqueo visual.
- [ ] Validar tablas y cards mobile.
- [ ] Validar hebreo y RTL en una fase futura.
- [ ] Revisar accesibilidad visual: contraste, foco y tamaños táctiles.
