# Project Docs

Documentacion transversal del proyecto Team360.

## Documentos tecnicos

- `automation_diagnosis_fase1.md`: modulo de diagnostico de automatizacion con LiteLLM, RAG simple, scoring deterministico y contratos preparados para multi-paquete / multi-worker.
- `postgresql_live_team360_setup.md`: inicializacion de la DB viva `team360`, aplicacion de la migracion 001 y audit post-migracion.
- `frontend_phase1_astro_svelte_tailwind_daisyui.md`: scaffold tecnico inicial con pnpm, Astro, Svelte 5, Tailwind CSS 4, DaisyUI 5, wrappers UI y reserva AG-UI.
- `frontend_home_team360_live_phase.md`: primera home comercial publica de `team360.live`, layout publico, copy, componentes marketing y validacion responsive.
- `console_mock_context_i18n_phase.md`: base funcional de diseño para Team360 Console con configuración global, mock data multi-organización, bootstrap por perfil, store Svelte 5 con Runes e i18n inicial `es`/`en`/`he`.
- `console_app_shell_mock_phase.md`: primera versión navegable de Team360 Console con App Shell Svelte, navegación contextual, rutas mock, dashboards adaptativos y smoke local.
- `console_services_reports_alerts_mock_phase.md`: pantallas mock concretas de servicios, detalle, reportes, alertas, tareas, equipo, settings, workers y runs para diseño funcional.
- `console_design_review_inventory.md`: inventario de pantallas, rutas, perfiles y prioridades para revisión visual por diseño.
- `console_ux_visual_review_phase.md`: auditoría UX y pulido visual de la consola mock, incluyendo responsive, accesibilidad básica y validación de perfiles.
- `ux_console_backend_alignment.md`: analisis tecnico para alinear Team360 Console con el modelo PostgreSQL aplicado, definir mapeos UX-DB, rutas, visibilidad y fases de integracion.

## Decisiones transversales relacionadas

- `../../docs/ux/team360-domains-and-console-strategy.md`: separacion de dominios, Team360 Console y modelo conceptual multi-organizacion.
- `../../docs/ux/team360-console-navigation-model.md`: modelo de navegacion contextual, App Shell y contratos esperados para frontend y backend.
- `../../docs/ux/team360-console-app-shell-and-layout-system.md`: sistema base de shell, layouts, estados de UI y reparto Astro/Svelte.
- `../../docs/adr/ADR-001-team360-domain-separation-and-console.md`: ADR resumido.
- `../../docs/adr/ADR-002-team360-console-navigation-by-role.md`: ADR resumido de navegacion contextual.
- `../../docs/adr/ADR-003-team360-console-app-shell-and-layout-system.md`: ADR resumido de App Shell y layouts.
- `../../lat.md/console-multi-organization.md`: invariantes estables para frontend y backend.
