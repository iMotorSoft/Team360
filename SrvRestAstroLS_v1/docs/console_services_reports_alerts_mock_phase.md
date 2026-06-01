# Team360 Console - Servicios y pantallas mock concretas

Fecha: 2026-05-31

## Objetivo

Materializar vistas operativas concretas para diseño funcional de `console.team360.live`, usando fixtures sintéticos y sin conectar backend, auth, DB ni AG-UI funcional.

## Rutas

- `/w/[workspaceId]/services`
- `/w/[workspaceId]/services/[serviceId]`
- `/w/[workspaceId]/reports`
- `/w/[workspaceId]/alerts`
- `/w/[workspaceId]/tasks`
- `/w/[workspaceId]/team`
- `/w/[workspaceId]/settings`
- `/w/[workspaceId]/workers`
- `/w/[workspaceId]/runs`

Las rutas técnicas de workers y ejecuciones se mantienen para Team360 mock. Además de ocultarse en navegación para otros perfiles, sus componentes aplican una guarda visual si se accede por URL directa.

## Componentes creados

- `astro/src/components/console/services/ServicesList.svelte`
- `astro/src/components/console/services/ServiceDetail.svelte`
- `astro/src/components/console/reports/ReportsList.svelte`
- `astro/src/components/console/alerts/AlertsList.svelte`
- `astro/src/components/console/tasks/TasksList.svelte`
- `astro/src/components/console/team/TeamList.svelte`
- `astro/src/components/console/settings/WorkspaceSettings.svelte`
- `astro/src/components/console/workers/WorkersList.svelte`
- `astro/src/components/console/runs/RunsList.svelte`

Se agregaron wrappers reutilizables en `astro/src/components/ui/`: `SectionHeader`, `StatCard`, `StatusBadge` y `Tabs`.

## Servicios mock

Se ampliaron fixtures tipados con cinco casos genéricos:

- Automatización de Leads y CRM.
- Reporte Ejecutivo Semanal.
- Control de Stock y Publicaciones.
- Conciliación Bancaria Asistida.
- Agente de Atención Inicial.

También se agregaron datos sintéticos relacionados para reportes, alertas, tareas, runs, workers e integraciones placeholder. No se usan clientes reales, credenciales ni llamadas a APIs.

## Diferencias por perfil

- Team360 Admin puede ver alcance multi-workspace, paquetes, workers, runs y tab técnica.
- Partner Admin recibe profundidad intermedia sobre sus workspaces autorizados, sin logs profundos.
- Cliente Final ve servicios contratados con lenguaje simple, resultados, reportes, alertas, tareas e historial orientado a soporte.

El detalle de servicio deriva tabs por audiencia. La tab técnica existe solo para Team360 mock.

## UX

- Servicios presenta métricas resumidas, health, última ejecución, próximo paso y CTA al detalle.
- Reportes ofrece acciones mock de ver y descargar; no genera PDFs.
- Alertas separa negocio, aprobación y técnica, con acción sugerida.
- Tareas muestra responsable, vencimiento, prioridad y servicio relacionado.
- Settings presenta datos de contexto e integraciones placeholder en modo solo lectura.
- Workers y runs muestran resúmenes seguros; no incluyen logs sensibles.

## Límites

- No existe persistencia.
- No existen permisos productivos; las guardas son demostrativas.
- No existe edición real de settings ni creación de usuarios.
- No se conectan transportes HTTP, SSE o WebSocket.
- No se generan descargas reales.

## Validación

- `corepack pnpm check`: OK, `56` archivos, `0 errors`, `0 warnings`, `0 hints`.
- `corepack pnpm build`: OK, `109` páginas estáticas.
- Smoke HTTP local: OK sobre servicios, detalle, alertas, tareas, workers, runs y detalle cliente.
- Smoke DOM local con Chrome headless: OK sobre lista y detalle de servicios, alertas, tareas, worker Team360 y guarda visual de worker ante acceso directo con perfil cliente.
- `git diff --check` acotado: OK.
- Auditoría de archivos nuevos: sin whitespace final, lockfiles incompatibles, perfiles Chrome residuales, transportes reales, patrones de secretos, términos heredados ni referencias del partner fixture fuera de mock data.
