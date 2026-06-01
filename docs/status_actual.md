# Status actual - docs

Objetivo: `documentacion-no-tecnica`

Ultima actualizacion: 2026-05-31

## Estado general

`docs/` contiene documentacion no tecnica de runtime: negocio, estrategia, analisis tecnico no operativo, insumos de clientes, presentaciones, decisiones UX, ADRs y plantillas.

## Acciones realizadas

### 2026-05-31 - Politica frontend pnpm y capa UI Team360

- Se agrego `docs/frontend/team360-package-manager-and-ui-policy.md`.
- Se agrego `docs/adr/ADR-005-team360-pnpm-tailwind4-daisyui5-ui-policy.md`.
- Se fijo pnpm como package manager frontend obligatorio.
- Se fijo Tailwind CSS 4 + DaisyUI 5 CSS-first como stack UI inicial obligatorio, encapsulado en wrappers Team360.
- No se implemento codigo, componentes, rutas, paquetes ni cambios de DB.

### 2026-05-31 - Correccion documental DaisyUI 5 + Tailwind 4

- Se corrigio la premisa incorrecta de incompatibilidad entre DaisyUI 5 y Tailwind 4 en la base tecnica frontend y ADR-004.
- Se documento integracion moderna CSS-first y encapsulamiento detras de wrappers Team360.
- No se implemento codigo, componentes, rutas, paquetes ni cambios de DB.

### 2026-05-31 - Base frontend Team360 desde Vertice360

- Se creo `docs/frontend/` con README.md y status_actual.md.
- Se creo `docs/frontend/team360-frontend-technical-base-from-vertice360.md` con analisis completo de Vertice360, deteccion de brechas, stack moderno, estrategias de migracion y bootstrap contract.
- Se creo `docs/adr/ADR-004-team360-frontend-base-vertice360-modern-stack.md`.
- Se actualizaron `docs/README.md`, `docs/adr/README.md`, `lat.md/lat.md` y `lat.md/status_actual.md`.
- No se implemento codigo, componentes, rutas ni migraciones.

### 2026-05-31 - App Shell y layouts base de Team360 Console

- Se agrego `docs/ux/team360-console-app-shell-and-layout-system.md`.
- Se agrego `docs/adr/ADR-003-team360-console-app-shell-and-layout-system.md`.
- Se documentaron patrones de shell, layouts, estados de UI, responsive e implicancias Astro/Svelte.
- No se implementaron pantallas, componentes, rutas, build ni cambios de DB.

### 2026-05-31 - Modelo de navegacion contextual de Team360 Console

- Se agrego `docs/ux/team360-console-navigation-model.md`.
- Se agrego `docs/adr/ADR-002-team360-console-navigation-by-role.md`.
- Se documento el App Shell adaptable, contexto activo, navegacion por usuario, tabs de servicio y wireframes textuales.
- Se mantuvo la regla de no implementar pantallas, rutas, componentes ni cambios de DB en esta etapa.

### 2026-05-31 - Alta de UX y ADR para Team360 Console

- Se agrego `docs/ux/` para decisiones compartidas de producto, experiencia y arquitectura de informacion.
- Se agrego `docs/adr/` para registros breves de decisiones de arquitectura.
- Se documento la separacion entre `team360.live` y `console.team360.live`.
- Se modelo a `Mamá Mía 360` como primera instancia configurable de Partner / Distribuidor Regional para Israel.
- Se actualizaron el indice raiz y los status locales de ambos directorios.

### 2026-05-28 - Alta de clients y presentaciones

- Se agrego `docs/clients/` para insumos documentales provistos por clientes.
- Se agrego `docs/clients/mario_castro/` con el workbook base de KPIs CEO.
- Se agrego `docs/presentaciones/` con recursos visuales de servicios.
- Se crearon status locales en los nuevos directorios documentales activos.
- Se actualizo `docs/README.md`.
- No se agregaron credenciales ni archivos `.env`.

### 2026-05-15 - Nuevo analisis SAP B1 sobre modelos de vision y costos

- Se agrego en `docs/analisis-tecnico/` el documento `sap_b1_modelos_vision_costos_automatizacion.md`.
- Se mantuvo dentro de analisis tecnico no operativo porque registra criterios de seleccion, costos, arquitectura y benchmark preliminar, sin documentar runtime implementado.
- Se actualizo el indice y status local de `docs/analisis-tecnico/`.
- No se modifico documentacion tecnica de runtime en `SrvRestAstroLS_v1/docs/`.

### 2026-05-13 - Reubicacion de factibilidad SAP Business One

- Se movio `sap_b1_desktop_automation_factibilidad.md` a `docs/analisis-tecnico/`.
- La decision corrige la ubicacion previa en `SrvRestAstroLS_v1/docs/`, porque el documento es de factibilidad tecnico-comercial y no de runtime.
- Se actualizo el status local de `docs/analisis-tecnico/`.

### 2026-05-13 - Status locales por directorio documental

- Se agrego esta bitacora local para registrar el ultimo estado relevante de `docs/`.
- Se mantuvo la separacion:
  - `negocio/` para contexto comercial y analisis de negocio.
  - `estrategia/` para decisiones de producto/plataforma e inventarios.
  - `analisis-tecnico/` para factibilidad tecnica no ligada al runtime.
  - `templates/` para plantillas documentales.
- Se definio que cada subdirectorio activo tenga su propio `status_actual.md`.

### 2026-05-13 - Orden documental no tecnico

- Se reorganizo el material no tecnico en subdirectorios.
- Se actualizo `README.md` como indice raiz.

## Validacion

- Se verifico que `docs/ux/` y `docs/adr/` tienen `README.md` y `status_actual.md`.
- Se verifico que `docs/clients/` y `docs/presentaciones/` tienen `status_actual.md`.
- Se verifico que el nuevo documento queda bajo `docs/analisis-tecnico/`.
- Se verifico la estructura de `docs/` y subdirectorios activos.
- No se movio documentacion tecnica de desarrollo desde `SrvRestAstroLS_v1/docs/`.

## Pendientes recomendados

- Mantener este archivo actualizado cuando cambie la estructura raiz de `docs/`.
- Actualizar tambien el status local de cada subdirectorio afectado.
