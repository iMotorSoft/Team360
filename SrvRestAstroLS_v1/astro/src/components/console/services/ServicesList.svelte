<script lang="ts">
  import { Card, EmptyState, SectionHeader, StatCard, StatusBadge } from "../../ui";
  import { formatDateTime } from "../../../lib/formatters";
  import { getOrganizationNameForWorkspace, getVisibleServices, getWorkspaceName } from "../../../lib/mock";
  import { buildServiceDetailRoute, deriveConsoleAudience } from "../../../lib/navigation/derive";
  import { consoleContext } from "../../../stores/consoleContext.svelte";

  const audience = $derived(deriveConsoleAudience(consoleContext.bootstrap));
  const visibleServices = $derived.by(() => {
    const services = getVisibleServices(consoleContext.bootstrap);
    return audience === "client" ? services.filter(({ workspaceId }) => workspaceId === consoleContext.activeWorkspace.id) : services;
  });
  const activeServices = $derived(visibleServices.filter(({ status }) => status === "active").length);
  const attentionServices = $derived(visibleServices.filter(({ health }) => ["warning", "critical", "pending"].includes(health)).length);
</script>

<section>
  <SectionHeader
    eyebrow="Prestaciones habilitadas"
    title={audience === "client" ? "Servicios contratados" : "Servicios"}
    description={audience === "owner"
      ? "Consulta prestaciones visibles en la red, su estado operativo y los próximos pasos sin perder el contexto de cada workspace."
      : audience === "partner"
        ? "Revisa servicios propios y de clientes autorizados, con foco en activaciones, resultados y tareas concretas."
        : "Consulta qué está funcionando, qué resultados entrega cada servicio y qué requiere atención de tu equipo."}
  />

  <div class="mt-7 grid gap-3 sm:grid-cols-3">
    <StatCard label="Servicios visibles" value={String(visibleServices.length)} description="Según perfil y alcance mock." />
    <StatCard label="Activos" value={String(activeServices)} description="Prestaciones en funcionamiento." />
    <StatCard label="Con seguimiento" value={String(attentionServices)} description="Requieren revisión o configuración." />
  </div>

  <div class="mt-6 grid gap-4 xl:grid-cols-2">
    {#each visibleServices as service}
      <Card variant="large">
        <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <p class="text-[0.68rem] font-bold uppercase tracking-[0.15em] text-[#168b88]">{service.packageName}</p>
            <h2 class="mt-2 text-lg font-bold tracking-[-0.035em] text-[#173b5b]">{service.name}</h2>
            <p class="mt-2 text-xs leading-5 text-[#78909f]">
              {audience === "client" ? service.clientSummary : service.description}
            </p>
          </div>
          <div class="flex shrink-0 flex-wrap gap-2">
            <StatusBadge status={service.status} />
            <StatusBadge status={service.health} />
          </div>
        </div>

        <div class="mt-5 grid gap-2 sm:grid-cols-3">
          {#each service.metrics.slice(0, 3) as metric}
            <div class="rounded-xl bg-[#f3f8f8] p-3">
              <p class="text-lg font-bold tracking-[-0.04em] text-[#214762]">{metric.value}</p>
              <p class="mt-1 text-[0.68rem] leading-4 text-[#78909f]">{metric.label}</p>
              {#if metric.trend}<p class="mt-1 text-[0.64rem] font-bold text-[#168b88]">{metric.trend}</p>{/if}
            </div>
          {/each}
        </div>

        <dl class="mt-5 grid gap-3 border-t border-[#edf1f2] pt-4 text-xs text-[#78909f] sm:grid-cols-2">
          <div><dt class="font-bold uppercase tracking-[0.1em] text-[#9aa9b1]">Categoría</dt><dd class="mt-1 font-semibold text-[#587184]">{service.category}</dd></div>
          <div><dt class="font-bold uppercase tracking-[0.1em] text-[#9aa9b1]">Última ejecución</dt><dd class="mt-1 font-semibold text-[#587184]">{formatDateTime(service.lastRunAt, consoleContext.locale)}</dd></div>
          {#if audience !== "client"}
            <div><dt class="font-bold uppercase tracking-[0.1em] text-[#9aa9b1]">Organización</dt><dd class="mt-1 font-semibold text-[#587184]">{getOrganizationNameForWorkspace(service.workspaceId)}</dd></div>
            <div><dt class="font-bold uppercase tracking-[0.1em] text-[#9aa9b1]">Workspace</dt><dd class="mt-1 font-semibold text-[#587184]">{getWorkspaceName(service.workspaceId)}</dd></div>
          {/if}
        </dl>

        <div class="mt-5 flex flex-col gap-3 rounded-2xl bg-[#f8fbfa] p-3.5 sm:flex-row sm:items-center sm:justify-between">
          <p class="text-xs font-semibold leading-5 text-[#668092]">Próximo paso: {service.nextStep}</p>
          <a
            class="inline-flex shrink-0 justify-center rounded-full bg-[#153b5b] px-4 py-2 text-xs font-bold text-white transition hover:bg-[#168b88]"
            href={buildServiceDetailRoute(service.workspaceId, service.id, consoleContext.activeProfile)}
          >
            Ver servicio
          </a>
        </div>
      </Card>
    {/each}
    {#if visibleServices.length === 0}
      <EmptyState
        title="Este workspace todavía no tiene servicios habilitados."
        description="Cuando se active una prestación podrás consultar su estado, resultados y próximos pasos desde esta pantalla."
        nextStep="Revisar la configuración del workspace o contactar soporte."
      />
    {/if}
  </div>
</section>
