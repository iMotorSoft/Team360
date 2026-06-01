# Team360 Console - Inventario de pantallas para revisión de diseño

Fecha: 2026-05-31

## Objetivo

Ordenar la revisión visual de la maqueta operativa de `console.team360.live`. Todas las rutas privadas usan datos mock y no representan auth ni autorización productiva.

## Pantallas

| Pantalla | Ruta | Perfiles | Objetivo | Componentes principales | Observaciones UX | Prioridad |
| --- | --- | --- | --- | --- | --- | --- |
| Home pública | `/` | Público | Comunicar propuesta comercial | `PublicMarketingLayout`, componentes marketing | Referencia de calidad visual, no de densidad operativa | Media |
| Acceso mock | `/login` | Diseño | Explicar entrada sin auth real | `MockAccessLayout`, `LinkButton` | Debe reemplazarse al diseñar autenticación productiva | Media |
| Selector de experiencia | `/select-workspace` | Diseño | Elegir perfil y workspace inicial | Cards de perfiles mock | Mantener rótulo visible de modo diseño | Media |
| Dashboard workspace | `/w/[workspaceId]` | Todos | Resumen operativo contextual | `AppShell`, `ConsoleDashboard`, `ContextBanner` | Revisar jerarquía de KPIs y prioridades por perfil | Alta |
| Servicios | `/w/[workspaceId]/services` | Todos | Consultar servicios contratados o autorizados | `ServicesList`, `StatCard`, `StatusBadge` | Pantalla central para cliente y partner | Alta |
| Detalle de servicio | `/w/[workspaceId]/services/[serviceId]` | Todos | Profundizar resultados y próximos pasos | `ServiceDetail`, `Tabs`, `EmptyState` | Validar tabs progresivas y densidad técnica Team360 | Alta |
| Resultados | `/w/[workspaceId]/results` | Partner, Cliente | Consultar indicadores visibles | `ConsoleSectionPage` | Revisar futura agrupación por período | Media |
| Reportes | `/w/[workspaceId]/reports` | Todos | Consultar entregables generados | `ReportsList`, cards mobile, tabla desktop | Descarga deshabilitada de forma explícita en mock | Alta |
| Alertas | `/w/[workspaceId]/alerts` | Todos | Priorizar situaciones visibles | `AlertsList`, `StatusBadge` | Separación por negocio, aprobación y técnica | Alta |
| Tareas | `/w/[workspaceId]/tasks` | Todos | Revisar acciones pendientes | `TasksList`, `EmptyState` | Confirmar orden futuro por prioridad y vencimiento | Alta |
| Equipo / usuarios | `/w/[workspaceId]/team` | Todos según permiso | Consultar personas y accesos resumidos | `TeamList`, `EmptyState` | No permite alta ni edición | Media |
| Configuración | `/w/[workspaceId]/settings` | Todos según módulo | Consultar contexto e integraciones previstas | `WorkspaceSettings` | Mantener solo lectura hasta definir permisos reales | Media |
| Workers | `/w/[workspaceId]/workers` | Team360 Admin, Operador Team360 | Observar capacidades internas resumidas | `WorkersList`, `EmptyState` | Cliente y partner reciben visibilidad limitada por URL directa | Media |
| Ejecuciones | `/w/[workspaceId]/runs` | Team360 Admin, Operador Team360 | Revisar actividad técnica segura | `RunsList`, `EmptyState` | Sin payloads, logs sensibles ni credenciales | Media |
| Organizaciones | `/w/[workspaceId]/organizations` | Team360 Admin | Consultar red visible | `ConsoleSectionPage` | Profundizar jerarquía visual en fase posterior | Media |
| Partners | `/w/[workspaceId]/partners` | Team360 Admin | Consultar distribuidores | `ConsoleSectionPage` | Mantener partners como configuración reusable | Media |
| Clientes | `/w/[workspaceId]/clients` | Team360 Admin, Partner | Consultar clientes autorizados | `ConsoleSectionPage`, cards mobile, tabla desktop | Partner no debe descubrir clientes laterales | Alta |
| Workspaces | `/w/[workspaceId]/workspaces` | Team360 Admin | Consultar contextos operativos | `ConsoleSectionPage` | Selector lateral sigue siendo acceso rápido principal | Baja |
| Servicios de clientes | `/w/[workspaceId]/client-services` | Partner | Consultar prestaciones de red delegada | `ConsoleSectionPage` | Evaluar si se integra luego dentro de Servicios | Media |
| Soporte | `/w/[workspaceId]/support` | Operador, Partner, Cliente | Consultar escalamiento contextual | `ConsoleSectionPage` | Reemplazar email mock al definir flujo real | Baja |

## Perfiles para capturas

| Perfil | Workspace inicial | Revisión recomendada |
| --- | --- | --- |
| `team360_admin` | `ws-team360-control` | Dashboard, organizaciones, partners, clientes, servicios, workers y runs |
| `team360_operator` | `ws-netzaj-marketplace` | Servicios asignados, workers, runs, alertas, tareas y soporte |
| `partner_admin` | `ws-mama-mia-israel` | Mis clientes, servicios de clientes, resultados, alertas y tareas |
| `client_admin` | `ws-netzaj-marketplace` | Servicios contratados, detalle, reportes, alertas, tareas y settings simples |

## Viewports

- Desktop: `1440px`.
- Laptop: `1280px`.
- Tablet: `768px`.
- Mobile lectura mínima: `390px`.
- Preview RTL estructural: `?locale=he`.
