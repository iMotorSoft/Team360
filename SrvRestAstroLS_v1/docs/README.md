# Project Docs

Documentación transversal de Team360. Comenzar por [AGENTS](../../AGENTS.md) y el [único estado técnico GLOBAL](status_actual.md); este índice organiza detalle e historia, no otro tablero vigente.

## Navegación vigente

El tablero GLOBAL enlaza las autoridades locales. LAT conserva arquitectura y reglas; fases y reportes guardan evidencia fechada sin sustituir el estado actual.

- [Estado GLOBAL](status_actual.md) → [LAT](../../lat.md/lat.md), [ownership](../../lat.md/team360-global-orchestration.md) y [política documental](../../lat.md/lat-documentation-policy.md).
- Flow: [README / runbook](../backend/modules/flow/README.md).
- Diagnosis: [estado local](../backend/modules/sales_diagnosis_runtime/status_actual.md).
- Messaging/Evolution: [README canónico](../backend/modules/messaging/README.md).
- Telchi: [estado local](../backend/modules/telchi/status_actual.md) y [CONTEXT arquitectónico](../backend/modules/telchi/CONTEXT.md).
- Console/Auth: [estado local](../backend/modules/console/status_actual.md), [enrollment/login CLI DEV](team360_console_dev_password_login_v1.md).
- Srv05: [aislamiento Evolution y source runtime](team360_srv05_evolution_isolation.md), [Fase 1](team360_srv05_phase1.md), [Fase 2](team360_srv05_phase2.md), [runtime Fase 3](../backend/modules/srv05_runtime.py) y [tests](../backend/tests/test_srv05_runtime.py). Perfil `full` no equivale a Full Team360 Gate.
- [Full Gate y follow-up](team360_full_gate_v1.md#followup-operacional-seguro) → [evidencia final](../../data/reports/team360-full-gate/operational-followup-final/report.json): Structural PASS / Operational DEGRADED, sin promoción.
- [Messaging↔Telchi: profiling y condición operativa del 08/10](../../data/reports/messaging/telchi-datalake-pre-sql-profile-v1/report.md); autoridades locales conservan el estado y los límites.
- [Histórico hasta 2026-06-28](status_historico_hasta_2026-06-28.md) y [bitácora congelada al normalizar](status_historico_hasta_normalizacion_2026-10-06.md), incluidos cambios preexistentes. No son estados alternativos.

## Documentos tecnicos

Los documentos siguientes conservan contratos y fases de implementación; interpretar sus límites según fecha y consultar el tablero vigente antes de operar.

- `automation_diagnosis_fase1.md`: modulo de diagnostico de automatizacion con LiteLLM, RAG simple, scoring deterministico y contratos preparados para multi-paquete / multi-worker.
- `postgresql_live_team360_setup.md`: inicializacion de la DB viva `team360`, aplicacion de migraciones 001-004 y auditorias post-migracion.
- `telchi_vpn_operations.md`: runbook headless de VPN Telchi con alternativas FortiClient y strongSwan, operación de servicios, seguridad y gate TCP de SAP HANA.
- `postgresql_004_automation_diagnosis_runtime.md`: persistencia runtime del asistente de venta/diagnostico, sesiones, respuestas, leads, eventos y package installation `team360_sales_diagnosis`.
- `frontend_phase1_astro_svelte_tailwind_daisyui.md`: scaffold tecnico inicial con pnpm, Astro, Svelte 5, Tailwind CSS 4, DaisyUI 5, wrappers UI y reserva AG-UI.
- `frontend_home_team360_live_phase.md`: primera home comercial publica de `team360.live`, layout publico, copy, componentes marketing y validacion responsive.
- `console_mock_context_i18n_phase.md`: base funcional de diseño para Team360 Console con configuración global, mock data multi-organización, bootstrap por perfil, store Svelte 5 con Runes e i18n inicial `es`/`en`/`he`.
- `console_app_shell_mock_phase.md`: primera versión navegable de Team360 Console con App Shell Svelte, navegación contextual, rutas mock, dashboards adaptativos y smoke local.
- `console_services_reports_alerts_mock_phase.md`: pantallas mock concretas de servicios, detalle, reportes, alertas, tareas, equipo, settings, workers y runs para diseño funcional.
- `console_design_review_inventory.md`: inventario de pantallas, rutas, perfiles y prioridades para revisión visual por diseño.
- `console_ux_visual_review_phase.md`: auditoría UX y pulido visual de la consola mock, incluyendo responsive, accesibilidad básica y validación de perfiles.
- `ux_console_backend_alignment.md`: analisis tecnico para alinear Team360 Console con el modelo PostgreSQL aplicado, definir mapeos UX-DB, rutas, visibilidad y fases de integracion.

## Decisiones transversales relacionadas

Estas fuentes preservan decisiones de producto y UX; LAT mantiene las invariantes arquitectónicas correspondientes.

- `../../docs/ux/team360-domains-and-console-strategy.md`: separacion de dominios, Team360 Console y modelo conceptual multi-organizacion.
- `../../docs/ux/team360-console-navigation-model.md`: modelo de navegacion contextual, App Shell y contratos esperados para frontend y backend.
- `../../docs/ux/team360-console-app-shell-and-layout-system.md`: sistema base de shell, layouts, estados de UI y reparto Astro/Svelte.
- `../../docs/adr/ADR-001-team360-domain-separation-and-console.md`: ADR resumido.
- `../../docs/adr/ADR-002-team360-console-navigation-by-role.md`: ADR resumido de navegacion contextual.
- `../../docs/adr/ADR-003-team360-console-app-shell-and-layout-system.md`: ADR resumido de App Shell y layouts.
- `../../lat.md/console-multi-organization.md`: invariantes estables para frontend y backend.
