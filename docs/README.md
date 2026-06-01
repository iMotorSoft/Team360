# Team360 Docs

Documentacion raiz del proyecto Team360 para material no tecnico de runtime.

## Estructura

- `negocio/`: contexto comercial, tesis de negocio, analisis de clientes o mercados.
- `estrategia/`: decisiones de producto/plataforma, continuidad, inventarios y estrategia tecnica-negocio.
- `analisis-tecnico/`: analisis tecnico no operativo, sin reemplazar la documentacion de desarrollo.
- `clients/`: insumos documentales provistos por clientes para analisis y relevamiento.
- `presentaciones/`: recursos visuales para presentaciones comerciales o de producto.
- `ux/`: decisiones compartidas de producto, experiencia y arquitectura de informacion.
- `frontend/`: documentacion tecnica de frontend, arquitectura UX y estrategias de migracion.
- `adr/`: registros breves de decisiones de arquitectura.
- `templates/`: plantillas documentales reutilizables.

## Decisiones base

- `ux/team360-domains-and-console-strategy.md`: separacion entre `team360.live` y `console.team360.live`, Team360 Console multi-organizacion y caso inicial de distribuidor regional.
- `adr/ADR-001-team360-domain-separation-and-console.md`: ADR resumido de la separacion de dominios y consola.
- `ux/team360-console-navigation-model.md`: modelo de navegacion contextual de Team360 Console.
- `adr/ADR-002-team360-console-navigation-by-role.md`: ADR resumido de navegacion por contexto y permisos.
- `ux/team360-console-app-shell-and-layout-system.md`: sistema base de App Shell y layouts reutilizables.
- `adr/ADR-003-team360-console-app-shell-and-layout-system.md`: ADR resumido del sistema de layouts.
- `frontend/team360-frontend-technical-base-from-vertice360.md`: analisis de Vertice360 como base frontend, deteccion de brechas, stack moderno (incluido DaisyUI 5 con Tailwind 4 CSS-first) y estrategia de migracion.
- `adr/ADR-004-team360-frontend-base-vertice360-modern-stack.md`: ADR resumido de la base frontend con stack moderno.
- `frontend/team360-package-manager-and-ui-policy.md`: politica obligatoria de pnpm, Tailwind CSS 4 + DaisyUI 5 CSS-first y wrappers UI Team360.
- `adr/ADR-005-team360-pnpm-tailwind4-daisyui5-ui-policy.md`: ADR resumido de package manager y capa UI frontend.

## Reportes y evidencias

Los reportes generados, muestras, snapshots y entregables de analisis viven en:

- `../data/reports/`

La documentacion tecnica de backend, Astro, runtime, migraciones y estado de desarrollo vive en:

- `../SrvRestAstroLS_v1/docs/`
