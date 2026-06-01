# Team360 Console - Revisión UX y consistencia visual

Fecha: 2026-05-31

## Objetivo

Auditar y pulir la maqueta operativa mock de `console.team360.live` antes de revisión por diseño. El alcance se limitó a claridad, consistencia visual, navegación contextual, responsive y accesibilidad básica.

## Rutas revisadas

- Públicas: `/`.
- Entrada mock: `/login`, `/select-workspace`.
- Console: `/w/[workspaceId]`, `/services`, `/services/[serviceId]`, `/reports`, `/alerts`, `/tasks`, `/team`, `/settings`, `/workers`, `/runs`, `/organizations`, `/partners`, `/clients`.
- Complementarias: `/workspaces`, `/client-services`, `/results`, `/support`.

## Perfiles revisados

- `team360_admin`.
- `team360_operator`.
- `partner_admin`.
- `client_admin`.

La visibilidad frontend sigue siendo demostrativa. Ocultar navegación o mostrar un mensaje de alcance limitado no reemplaza validación backend.

## Problemas encontrados y mejoras aplicadas

### Drawer y clases condicionales Svelte

Se detectó uso de `class:list` en componentes Svelte. Esa sintaxis corresponde a Astro y renderizaba `class="list"`, rompiendo clases condicionales en sidebar, navegación, banner y tabs.

Se reemplazó por expresiones `class` válidas en Svelte. El drawer vuelve a quedar cerrado inicialmente en tablet/mobile y conserva apertura manual.

### Rutas de entrada

`/login` y `/select-workspace` devolvían `404`.

Se agregaron pantallas explícitamente mock:

- acceso de diseño sin formulario ni credenciales;
- selector de experiencias para Admin Team360, Operador Team360, Partner Admin y Client Admin.

### Perfil Operador Team360

`team360_operator` se derivaba visualmente como cliente final.

Se agregó audiencia `operator`, derivada desde organización de membresía Team360 y permisos efectivos. El operador ve servicios asignados, workers y ejecuciones resumidas sin recibir red global.

### Responsive

- Reportes usa cards en mobile y tabla desde tablet.
- Clientes usa cards en mobile y tabla desde tablet.
- Sidebar funciona como drawer fuera de desktop.
- Se verificó ausencia de overflow horizontal evidente en `1440`, `1280`, `768` y `390`.

### Copy operativo

- Estados internos se presentan con labels comprensibles: `Activo`, `Saludable`, `En seguimiento`, `Revisión recomendada`, `Generando`.
- Fechas y duraciones usan `Intl.DateTimeFormat` e `Intl.NumberFormat`.
- Settings reemplaza “integraciones placeholder” por “integraciones previstas”.
- Acciones no implementadas se muestran deshabilitadas con copy explícito.
- Mensajes de visibilidad limitada explican el próximo paso.

### Wrappers y estados UX

Se agregó `EmptyState` con variantes `empty`, `error` y `permission`. Se usa en servicios, reportes, tareas, equipo, workers y runs.

Se pulieron:

- `Button`: foco visible.
- `LinkButton`: foco visible.
- `Loading`: copy con elipsis tipográfica y `aria-live`.
- `Tabs`: teclado con flechas, `Home`, `End`, foco visible y sincronización del tab en query param desde detalle de servicio.
- `StatusBadge`: labels operativos centralizados.

### Interacción global

- foco visible global;
- `touch-action: manipulation`;
- `overscroll-behavior: contain` para drawer;
- reducción de animaciones con `prefers-reduced-motion`;
- marca Team360 protegida con `translate="no"`.

## Consistencia con la home pública

La consola conserva azul profundo, teal, fondos claros, bordes suaves, cards redondeadas y aire visual. La densidad es mayor que en la home: prioriza estado, acción y resultado sin convertirse en landing.

## RTL e i18n

- `dir` cambia mediante locale.
- El drawer respeta apertura desde el lado lógico.
- Sidebar, topbar, breadcrumbs y cards se recomponen en RTL sin overflow.
- Persisten hardcodes en español dentro de pantallas mock. La extracción completa a mensajes i18n queda pendiente antes de producción.
- El preview hebreo actual valida estructura, no traducción completa ni QA lingüístico.

## Límites

- No se implementó auth real.
- No se implementaron permisos reales.
- No se conectó backend, API, DB ni migraciones.
- No se implementó AG-UI funcional.
- No se agregaron dependencias.
- No se generaron descargas reales.

## Validaciones ejecutadas

- `corepack pnpm check`: OK, `60` archivos, `0 errors`, `0 warnings`, `0 hints`.
- `corepack pnpm build`: OK, `111` páginas estáticas.
- `corepack pnpm dev --host 127.0.0.1 --port 4321`: OK.
- Smoke HTTP y DOM local con Chrome headless: OK sobre home, entrada mock, selector, dashboard, servicios, detalle, reportes, alertas, tareas, red, workers y runs.
- Capturas locales desktop, laptop, tablet, mobile y RTL: revisadas y eliminadas al cerrar.
- Medición CDP de `scrollWidth`: sin overflow horizontal en rutas críticas para `1440`, `1280`, `768` y `390`.
- Perfiles: cliente sin navegación workers/runs y con mensaje de visibilidad limitada por URL directa; operador Team360 con workers/runs resumidos; partner sin red global.
- `git diff --check -- SrvRestAstroLS_v1/astro SrvRestAstroLS_v1/docs docs/frontend`: OK.
- Auditoría acotada de lockfiles, transportes reales, secretos y referencias heredadas: OK.

## Pendientes para diseño

- Revisar jerarquía final de dashboard por perfil.
- Definir tratamiento visual final de alertas críticas y aprobaciones.
- Evaluar si “Servicios de clientes” debe mantenerse como ruta separada para partner.
- Diseñar autenticación productiva y recuperación de acceso como flujo independiente.
- Ejecutar QA lingüístico hebreo con contenido traducido.

## Pendientes técnicos

- Extraer copy mock relevante a `src/lib/i18n/`.
- Agregar pruebas visuales automatizadas cuando exista pipeline frontend.
- Reemplazar bootstrap mock por contrato autenticado cuando backend esté definido.
- Implementar autorización backend antes de considerar privadas las rutas de consola.
