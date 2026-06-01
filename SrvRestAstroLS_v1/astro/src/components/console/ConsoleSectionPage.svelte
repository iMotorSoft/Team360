<script lang="ts">
  import { BRAND } from "../global.js";
  import { Badge } from "../ui";
  import { formatDate, formatDateTime } from "../../lib/formatters";
  import { getMockWorkspaceContext, organizations, reports, runs, services, tasks, users, workspaces } from "../../lib/mock";
  import { deriveConsoleAudience } from "../../lib/navigation/derive";
  import type { ConsoleView } from "../../lib/navigation/registry";
  import { consoleContext } from "../../stores/consoleContext.svelte";

  let { view }: { view: ConsoleView } = $props();

  const audience = $derived(deriveConsoleAudience(consoleContext.bootstrap));
  const context = $derived(
    getMockWorkspaceContext(consoleContext.activeWorkspace.id, {
      includeTechnicalDetails: consoleContext.bootstrap.uiHints.technicalDepth !== "business",
    }),
  );
  const accessibleWorkspaceIds = $derived(new Set(consoleContext.bootstrap.accessibleWorkspaces.map(({ id }) => id)));
  const accessibleOrganizationIds = $derived(new Set(consoleContext.bootstrap.accessibleOrganizations.map(({ id }) => id)));
  const visibleServices = $derived(
    services.filter(
      ({ visibleToClient, workspaceId }) =>
        accessibleWorkspaceIds.has(workspaceId) && (consoleContext.bootstrap.uiHints.technicalDepth !== "business" || visibleToClient),
    ),
  );
  const visibleReports = $derived(reports.filter(({ workspaceId }) => accessibleWorkspaceIds.has(workspaceId)));
  const visibleTasks = $derived(tasks.filter(({ workspaceId }) => accessibleWorkspaceIds.has(workspaceId)));
  const visibleRuns = $derived(runs.filter(({ serviceId }) => visibleServices.some(({ id }) => id === serviceId)));
  const clients = $derived(
    consoleContext.bootstrap.accessibleOrganizations.filter(({ type }) => ["direct_client", "partner_client"].includes(type)),
  );
  const partners = $derived(consoleContext.bootstrap.accessibleOrganizations.filter(({ type }) => type === "partner"));
  const visibleUsers = $derived(
    users.filter(
      ({ organizationId, workspaceIds }) =>
        accessibleOrganizationIds.has(organizationId) || workspaceIds.some((workspaceId) => accessibleWorkspaceIds.has(workspaceId)),
    ),
  );
  const clientServices = $derived(
    visibleServices.filter(({ workspaceId }) => workspaceId !== consoleContext.activeWorkspace.id && workspaces.some(({ id }) => id === workspaceId)),
  );

  const copy = $derived.by(() => {
    const labels: Record<ConsoleView, [string, string, string]> = {
      home: ["Inicio", "", ""],
      organizations: ["Organizaciones", "Estructura autorizada de la red", "Consulta organizaciones, jerarquía, región y estado operativo."],
      partners: ["Partners", "Canales regionales configurables", "Seguimiento de distribuidores y activaciones dentro de la plataforma."],
      clients: [audience === "partner" ? "Mis clientes" : "Clientes", "Organizaciones cliente visibles", "Accede a cada contexto permitido sin mezclar datos entre organizaciones."],
      workspaces: ["Workspaces", "Contextos operativos", "Cada workspace delimita servicios, configuraciones y resultados visibles."],
      services: [audience === "client" ? "Servicios contratados" : "Servicios", "Prestaciones habilitadas", "Revisa estado, salud, paquete y próximo paso de cada servicio."],
      "client-services": ["Servicios de clientes", "Prestaciones dentro de tu red", "Consulta los servicios activos o en onboarding de clientes gestionados."],
      results: ["Resultados", "Indicadores comprensibles", "Métricas visibles del workspace activo para orientar decisiones y próximos pasos."],
      workers: ["Workers", "Capacidades técnicas autorizadas", "Vista interna de componentes operativos y ejecuciones relacionadas."],
      runs: ["Ejecuciones", "Actividad técnica reciente", "Seguimiento interno de runs, estados y resúmenes seguros."],
      reports: ["Reportes", "Salidas consultables", "Reportes generados y programados para el contexto operativo seleccionado."],
      alerts: ["Alertas", "Situaciones que requieren atención", "Prioriza eventos visibles, severidad y estado dentro del workspace."],
      tasks: ["Tareas", "Próximas acciones", "Trabajo manual, asistido o pendiente de aprobación humana."],
      team: [audience === "owner" ? "Usuarios" : "Equipo", "Personas y accesos visibles", "Usuarios autorizados dentro del alcance seleccionado."],
      support: ["Soporte", "Seguimiento contextualizado", "Centraliza consultas y escalamiento con el contexto operativo visible."],
      settings: ["Configuración", "Preferencias del contexto", "Parámetros visibles de experiencia, idioma y alcance mock."],
    };

    return labels[view];
  });

  function statusVariant(status: string): "success" | "warning" | "info" | "danger" | "neutral" {
    if (["active", "healthy", "completed", "ready"].includes(status)) return "success";
    if (["attention", "warning", "pending", "onboarding", "in_progress", "generating", "scheduled"].includes(status)) return "warning";
    if (["failed", "critical", "paused"].includes(status)) return "danger";
    return "neutral";
  }

  function organizationForWorkspace(workspaceId: string) {
    const workspace = workspaces.find(({ id }) => id === workspaceId);
    return organizations.find(({ id }) => id === workspace?.organizationId);
  }

  function serviceForId(serviceId: string) {
    return services.find(({ id }) => id === serviceId);
  }

  function statusLabel(status: string) {
    return (
      {
        active: "Activo",
        attention: "Requiere atención",
        completed: "Completado",
        critical: "Crítico",
        failed: "Falló",
        generating: "Generando",
        healthy: "Saludable",
        in_progress: "En curso",
        onboarding: "En activación",
        open: "Abierta",
        paused: "Pausado",
        pending: "Pendiente",
        ready: "Listo",
        resolved: "Resuelta",
        scheduled: "Programado",
        warning: "Revisión recomendada",
      }[status] ?? status
    );
  }
</script>

<section>
  <div>
    <p class="text-xs font-bold uppercase tracking-[0.2em] text-[#168b88]">{copy[1]}</p>
    <h1 class="mt-2 text-3xl font-bold tracking-[-0.055em] text-[#102d4f] sm:text-4xl">{copy[0]}</h1>
    <p class="mt-3 max-w-3xl text-sm leading-6 text-[#69808f]">{copy[2]}</p>
  </div>

  {#if view === "organizations"}
    <div class="mt-7 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
      {#each consoleContext.bootstrap.accessibleOrganizations as organization}
        <article class="rounded-2xl border border-[#e0e8ea] bg-white p-5">
          <div class="flex items-start justify-between gap-3">
            <div>
              <p class="text-sm font-bold text-[#284c67]">{organization.name}</p>
              <p class="mt-1 text-xs text-[#8396a2]">{organization.type}</p>
            </div>
            <Badge variant={statusVariant(organization.status)} class="h-auto px-2 py-1 text-[0.62rem]">{statusLabel(organization.status)}</Badge>
          </div>
          <div class="mt-5 flex items-center justify-between border-t border-[#edf1f2] pt-3 text-xs text-[#78909f]">
            <span>{organization.region}</span>
            <span>{workspaces.filter(({ organizationId }) => organizationId === organization.id).length} workspace(s)</span>
          </div>
        </article>
      {/each}
    </div>
  {:else if view === "partners"}
    <div class="mt-7 grid gap-4 lg:grid-cols-2">
      {#each partners as partner}
        <article class="rounded-3xl border border-[#e0e8ea] bg-white p-5 sm:p-6">
          <div class="flex items-center justify-between gap-3">
            <div>
              <p class="text-lg font-bold tracking-[-0.03em] text-[#173b5b]">{partner.name}</p>
              <p class="mt-1 text-xs text-[#8396a2]">Partner regional · {partner.region}</p>
            </div>
            <Badge variant={statusVariant(partner.status)} class="h-auto px-2 py-1 text-[0.62rem]">{statusLabel(partner.status)}</Badge>
          </div>
          <div class="mt-5 grid grid-cols-2 gap-3">
            <div class="rounded-2xl bg-[#f3f8f8] p-3">
              <p class="text-2xl font-bold tracking-[-0.05em] text-[#173b5b]">{organizations.filter(({ parentOrganizationId }) => parentOrganizationId === partner.id).length}</p>
              <p class="mt-1 text-xs text-[#78909f]">Clientes asociados</p>
            </div>
            <div class="rounded-2xl bg-[#f3f8f8] p-3">
              <p class="text-2xl font-bold tracking-[-0.05em] text-[#173b5b]">{workspaces.filter(({ organizationId }) => organizationId === partner.id).length}</p>
              <p class="mt-1 text-xs text-[#78909f]">Workspaces propios</p>
            </div>
          </div>
        </article>
      {/each}
    </div>
  {:else if view === "clients"}
    <div class="mt-7 grid gap-3 md:hidden">
      {#each clients as client}
        <article class="rounded-2xl border border-[#e0e8ea] bg-white p-4">
          <div class="flex items-start justify-between gap-3">
            <div>
              <h2 class="text-sm font-bold text-[#31536b]">{client.name}</h2>
              <p class="mt-1 text-xs text-[#8396a2]">{client.region}</p>
            </div>
            <Badge variant={statusVariant(client.status)} class="h-auto px-2 py-1 text-[0.62rem]">{statusLabel(client.status)}</Badge>
          </div>
          <p class="mt-4 border-t border-[#edf1f2] pt-3 text-xs text-[#78909f]">
            Workspace: {workspaces.find(({ organizationId }) => organizationId === client.id)?.name ?? "Activación pendiente"}
          </p>
        </article>
      {/each}
    </div>
    <div class="mt-7 hidden overflow-hidden rounded-3xl border border-[#e0e8ea] bg-white md:block">
      <div class="overflow-x-auto">
        <table class="w-full min-w-[42rem] text-start text-sm">
          <thead class="bg-[#f4f8f8] text-[0.65rem] uppercase tracking-[0.15em] text-[#78909f]">
            <tr><th class="px-5 py-3 text-start">Cliente</th><th class="px-5 py-3 text-start">Tipo</th><th class="px-5 py-3 text-start">Región</th><th class="px-5 py-3 text-start">Workspace</th><th class="px-5 py-3 text-start">Estado</th></tr>
          </thead>
          <tbody class="divide-y divide-[#edf1f2]">
            {#each clients as client}
              <tr class="text-[#567184]">
                <td class="px-5 py-4 font-bold text-[#31536b]">{client.name}</td>
                <td class="px-5 py-4">{client.type}</td>
                <td class="px-5 py-4">{client.region}</td>
                <td class="px-5 py-4">{workspaces.find(({ organizationId }) => organizationId === client.id)?.name ?? "Pendiente"}</td>
                <td class="px-5 py-4"><Badge variant={statusVariant(client.status)} class="h-auto px-2 py-1 text-[0.62rem]">{statusLabel(client.status)}</Badge></td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </div>
  {:else if view === "workspaces"}
    <div class="mt-7 grid gap-3 lg:grid-cols-2">
      {#each consoleContext.bootstrap.accessibleWorkspaces as workspace}
        <article class="rounded-2xl border border-[#e0e8ea] bg-white p-5">
          <div class="flex items-start justify-between gap-3">
            <div>
              <p class="text-sm font-bold text-[#284c67]">{workspace.name}</p>
              <p class="mt-1 text-xs text-[#8396a2]">{organizationForWorkspace(workspace.id)?.name}</p>
            </div>
            <Badge variant={statusVariant(workspace.status)} class="h-auto px-2 py-1 text-[0.62rem]">{statusLabel(workspace.status)}</Badge>
          </div>
          <p class="mt-4 text-xs text-[#78909f]">{workspace.type} · {workspace.locale.toUpperCase()} · {workspace.direction}</p>
        </article>
      {/each}
    </div>
  {:else if view === "services" || view === "client-services"}
    <div class="mt-7 grid gap-4 xl:grid-cols-2">
      {#each (view === "client-services" ? clientServices : context.services) as service}
        <article class="rounded-3xl border border-[#e0e8ea] bg-white p-5 sm:p-6">
          <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <p class="text-xs font-bold uppercase tracking-[0.14em] text-[#168b88]">{service.packageName}</p>
              <h2 class="mt-2 text-lg font-bold tracking-[-0.03em] text-[#173b5b]">{service.name}</h2>
              <p class="mt-2 text-xs leading-5 text-[#78909f]">{service.description}</p>
            </div>
            <Badge variant={statusVariant(service.health)} class="h-auto w-fit px-2 py-1 text-[0.62rem]">{service.health}</Badge>
          </div>
          <div class="mt-5 grid gap-2 sm:grid-cols-2">
            {#each service.metrics as metric}
              <div class="rounded-xl bg-[#f3f8f8] p-3">
                <p class="text-lg font-bold tracking-[-0.04em] text-[#214762]">{metric.value}</p>
                <p class="mt-1 text-[0.68rem] text-[#78909f]">{metric.label}{metric.trend ? ` · ${metric.trend}` : ""}</p>
              </div>
            {/each}
          </div>
          <p class="mt-4 border-t border-[#edf1f2] pt-3 text-xs font-semibold leading-5 text-[#668092]">Próximo paso: {service.nextStep}</p>
        </article>
      {:else}
        <p class="rounded-2xl border border-[#e0e8ea] bg-white p-5 text-sm text-[#718793]">No hay servicios visibles para este contexto.</p>
      {/each}
    </div>
  {:else if view === "results"}
    <div class="mt-7 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {#each context.services as service}
        {#each service.metrics as metric}
          <article class="rounded-2xl border border-[#e0e8ea] bg-white p-5">
            <p class="text-xs font-bold uppercase tracking-[0.14em] text-[#78909f]">{service.name}</p>
            <p class="mt-4 text-3xl font-bold tracking-[-0.06em] text-[#173b5b]">{metric.value}</p>
            <p class="mt-2 text-sm font-semibold text-[#587184]">{metric.label}</p>
            {#if metric.trend}<p class="mt-2 text-xs font-bold text-[#168b88]">{metric.trend}</p>{/if}
          </article>
        {/each}
      {/each}
    </div>
  {:else if view === "workers"}
    <div class="mt-7 grid gap-3 lg:grid-cols-2">
      {#each Array.from(new Set(visibleRuns.map(({ workerName }) => workerName))) as workerName}
        <article class="rounded-2xl border border-[#e0e8ea] bg-white p-5">
          <p class="text-sm font-bold text-[#284c67]">{workerName}</p>
          <p class="mt-2 text-xs leading-5 text-[#78909f]">Capacidad técnica interna · logs resumidos · sin secretos expuestos.</p>
          <div class="mt-4 flex items-center justify-between border-t border-[#edf1f2] pt-3 text-xs text-[#78909f]">
            <span>{visibleRuns.filter((run) => run.workerName === workerName).length} run(s)</span>
            <Badge variant="success" class="h-auto px-2 py-1 text-[0.62rem]">visible</Badge>
          </div>
        </article>
      {/each}
    </div>
  {:else if view === "runs"}
    <div class="mt-7 space-y-3">
      {#each visibleRuns as run}
        <article class="rounded-2xl border border-[#e0e8ea] bg-white p-5">
          <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <p class="text-sm font-bold text-[#284c67]">{run.workerName}</p>
              <p class="mt-1 text-xs text-[#8396a2]">{serviceForId(run.serviceId)?.name}</p>
            </div>
            <Badge variant={statusVariant(run.status)} class="h-auto w-fit px-2 py-1 text-[0.62rem]">{statusLabel(run.status)}</Badge>
          </div>
          <p class="mt-4 text-xs leading-5 text-[#668092]">{run.summary}</p>
          <p class="mt-3 text-[0.68rem] text-[#91a2ad]">{formatDateTime(run.startedAt, consoleContext.locale)} {run.finishedAt ? `→ ${formatDateTime(run.finishedAt, consoleContext.locale)}` : "· en curso"}</p>
        </article>
      {/each}
    </div>
  {:else if view === "reports"}
    <div class="mt-7 grid gap-3 lg:grid-cols-2">
      {#each context.reports as report}
        <article class="rounded-2xl border border-[#e0e8ea] bg-white p-5">
          <div class="flex items-start justify-between gap-3">
            <div>
              <p class="text-sm font-bold text-[#284c67]">{report.title}</p>
              <p class="mt-1 text-xs text-[#8396a2]">{report.period} · {report.type}</p>
            </div>
            <Badge variant={statusVariant(report.status)} class="h-auto px-2 py-1 text-[0.62rem]">{statusLabel(report.status)}</Badge>
          </div>
          <p class="mt-5 border-t border-[#edf1f2] pt-3 text-xs text-[#78909f]">{report.generatedAt ? `Generado: ${formatDateTime(report.generatedAt, consoleContext.locale)}` : "Generación en curso o programada."}</p>
        </article>
      {:else}
        <p class="rounded-2xl border border-[#e0e8ea] bg-white p-5 text-sm text-[#718793]">Todavía no hay reportes para este workspace.</p>
      {/each}
    </div>
  {:else if view === "alerts"}
    <div class="mt-7 space-y-3">
      {#each context.alerts as alert}
        <article class="rounded-2xl border border-[#e0e8ea] bg-white p-5">
          <div class="flex items-center justify-between gap-3">
            <Badge variant={statusVariant(alert.severity)} class="h-auto px-2 py-1 text-[0.62rem]">{alert.severity}</Badge>
            <span class="text-xs text-[#91a2ad]">{formatDateTime(alert.createdAt, consoleContext.locale)}</span>
          </div>
          <p class="mt-3 text-sm font-bold text-[#31536b]">{alert.title}</p>
          <p class="mt-2 text-xs text-[#78909f]">Estado: {statusLabel(alert.status)} · Servicio: {serviceForId(alert.serviceId)?.name}</p>
        </article>
      {:else}
        <p class="rounded-2xl border border-[#dce8e8] bg-white p-5 text-sm text-[#718793]">No hay alertas registradas para el contexto activo.</p>
      {/each}
    </div>
  {:else if view === "tasks"}
    <div class="mt-7 space-y-3">
      {#each context.tasks as task}
        <article class="flex flex-col gap-3 rounded-2xl border border-[#e0e8ea] bg-white p-5 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p class="text-sm font-bold text-[#31536b]">{task.title}</p>
            <p class="mt-1 text-xs text-[#8396a2]">{serviceForId(task.serviceId)?.name} · vence {formatDate(task.dueDate, consoleContext.locale)}</p>
          </div>
          <Badge variant={statusVariant(task.status)} class="h-auto w-fit px-2 py-1 text-[0.62rem]">{statusLabel(task.status)}</Badge>
        </article>
      {:else}
        <p class="rounded-2xl border border-[#dce8e8] bg-white p-5 text-sm text-[#718793]">No hay tareas pendientes para este workspace.</p>
      {/each}
    </div>
  {:else if view === "team"}
    <div class="mt-7 grid gap-3 lg:grid-cols-2">
      {#each visibleUsers as user}
        <article class="flex items-center gap-4 rounded-2xl border border-[#e0e8ea] bg-white p-4">
          <span class="grid size-11 shrink-0 place-items-center rounded-xl bg-[#153b5b] text-xs font-bold text-white">{user.avatarInitials}</span>
          <div class="min-w-0">
            <p class="truncate text-sm font-bold text-[#31536b]">{user.name}</p>
            <p class="mt-1 truncate text-xs text-[#8396a2]">{user.email}</p>
            <p class="mt-1 text-[0.68rem] font-bold uppercase tracking-[0.1em] text-[#168b88]">{user.role}</p>
          </div>
        </article>
      {/each}
    </div>
  {:else if view === "support"}
    <div class="mt-7 grid gap-5 lg:grid-cols-[1.15fr_0.85fr]">
      <section class="rounded-3xl border border-[#e0e8ea] bg-white p-5 sm:p-6">
        <p class="text-xs font-bold uppercase tracking-[0.16em] text-[#168b88]">Solicitudes recientes</p>
        <div class="mt-4 space-y-3">
          {#each context.tasks.slice(0, 4) as task}
            <article class="rounded-xl border border-[#edf1f2] px-3 py-3">
              <p class="text-xs font-bold text-[#36566f]">{task.title}</p>
              <p class="mt-1 text-[0.68rem] text-[#8a9ba6]">Seguimiento contextual · {task.status}</p>
            </article>
          {:else}
            <p class="rounded-xl bg-[#f4f8f8] p-4 text-xs text-[#718793]">No hay solicitudes abiertas.</p>
          {/each}
        </div>
      </section>
      <section class="rounded-3xl bg-[#123653] p-5 text-white sm:p-6">
        <p class="text-xs font-bold uppercase tracking-[0.16em] text-[#86ddd5]">Escalamiento</p>
        <h2 class="mt-3 text-xl font-bold tracking-[-0.035em]">Soporte Team360</h2>
        <p class="mt-3 text-sm leading-6 text-white/70">Comparte el contexto activo, el servicio afectado y la evidencia necesaria para acelerar el seguimiento.</p>
        <a class="mt-5 inline-flex rounded-full bg-[#72d9cf] px-4 py-2 text-xs font-bold text-[#123653] transition hover:bg-white" href={`mailto:${BRAND.supportEmail}`}>
          {BRAND.supportEmail}
        </a>
      </section>
    </div>
  {:else if view === "settings"}
    <div class="mt-7 grid gap-4 lg:grid-cols-2">
      <article class="rounded-3xl border border-[#e0e8ea] bg-white p-5 sm:p-6">
        <p class="text-xs font-bold uppercase tracking-[0.16em] text-[#168b88]">Experiencia</p>
        <dl class="mt-4 space-y-3 text-sm">
          <div class="flex justify-between gap-3 border-b border-[#edf1f2] pb-3"><dt class="text-[#78909f]">Idioma</dt><dd class="font-bold text-[#31536b]">{consoleContext.locale}</dd></div>
          <div class="flex justify-between gap-3 border-b border-[#edf1f2] pb-3"><dt class="text-[#78909f]">Dirección</dt><dd class="font-bold text-[#31536b]">{consoleContext.direction}</dd></div>
          <div class="flex justify-between gap-3"><dt class="text-[#78909f]">Perfil de diseño</dt><dd class="font-bold text-[#31536b]">{consoleContext.bootstrap.uiHints.profileLabel}</dd></div>
        </dl>
      </article>
      <article class="rounded-3xl border border-[#e0e8ea] bg-white p-5 sm:p-6">
        <p class="text-xs font-bold uppercase tracking-[0.16em] text-[#168b88]">Capacidades</p>
        <div class="mt-4 flex flex-wrap gap-2">
          {#each consoleContext.bootstrap.enabledModules as module}
            <Badge variant="neutral" class="h-auto px-2 py-1 text-[0.62rem]">{module}</Badge>
          {/each}
        </div>
        <p class="mt-5 text-xs leading-5 text-[#78909f]">Los módulos visibles son simulados para diseño. No representan autorización backend definitiva.</p>
      </article>
    </div>
  {/if}
</section>
