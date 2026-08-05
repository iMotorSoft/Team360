<script lang="ts">
  import { Card, EmptyState, SectionHeader, StatusBadge } from "../../ui";
  import { formatDateTime, formatDuration } from "../../../lib/formatters";
  import { getAccessibleWorkspaceIds, services, workers } from "../../../lib/mock";
  import { consoleContext } from "../../../stores/consoleContext.svelte";

  const visibleWorkers = $derived.by(() => {
    const workspaceIds = getAccessibleWorkspaceIds(consoleContext.bootstrap);
    const serviceIds = new Set(services.filter(({ workspaceId }) => workspaceIds.has(workspaceId)).map(({ id }) => id));
    return workers.filter(({ serviceId }) => serviceIds.has(serviceId));
  });

  function serviceName(serviceId: string) {
    return services.find(({ id }) => id === serviceId)?.name ?? "Servicio no disponible";
  }
</script>

<section>
  <SectionHeader
    eyebrow="Profundidad técnica autorizada"
    title="Workers"
    description="Capacidades internas vinculadas a servicios visibles. La vista expone salud y actividad resumida, nunca secretos ni credenciales."
  />

  {#if consoleContext.bootstrap.uiHints.technicalDepth !== "business"}
    <div class="mt-7 grid gap-4 xl:grid-cols-2">
      {#each visibleWorkers as worker}
        <Card variant="flat">
          <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <h2 class="text-sm font-bold text-[#31536b]">{worker.name}</h2>
              <p class="mt-2 text-sm leading-5 text-[#78909f]">{serviceName(worker.serviceId)}</p>
            </div>
            <div class="flex flex-wrap gap-2">
              <StatusBadge status={worker.status} />
              <StatusBadge status={worker.health} />
            </div>
          </div>
          <dl class="mt-5 flex flex-col divide-y divide-[#edf1f2] rounded-2xl border border-[#edf1f2] bg-[#fcfdfd] overflow-hidden sm:flex-row sm:divide-y-0 sm:divide-x">
            <div class="flex-1 p-4">
              <dt class="text-xs font-bold uppercase tracking-wider text-[#91a2ad]">Última ejecución</dt>
              <dd class="mt-1 text-sm font-bold text-[#587184]">{formatDateTime(worker.lastRunAt, consoleContext.locale)}</dd>
            </div>
            <div class="flex-1 p-4">
              <dt class="text-xs font-bold uppercase tracking-wider text-[#91a2ad]">Errores</dt>
              <dd class="mt-1 text-sm font-bold text-[#587184]">{worker.errorCount}</dd>
            </div>
            <div class="flex-1 p-4">
              <dt class="text-xs font-bold uppercase tracking-wider text-[#91a2ad]">Duración media</dt>
              <dd class="mt-1 text-sm font-bold text-[#587184]">{worker.averageDurationSeconds ? formatDuration(worker.averageDurationSeconds, consoleContext.locale) : "Pendiente"}</dd>
            </div>
          </dl>
        </Card>
      {/each}
      {#if visibleWorkers.length === 0}
        <EmptyState
          title="Todavía no hay workers vinculados."
          description="Los workers aparecerán cuando un servicio técnico tenga una capacidad interna asociada."
          nextStep="Revisar servicios asignados o esperar la primera activación."
        />
      {/if}
    </div>
  {:else}
    <EmptyState
      class="mt-7"
      variant="permission"
      title="Esta vista técnica no está incluida en tu perfil de diseño."
      description="Tu navegación muestra servicios, resultados y acciones visibles sin exponer workers internos."
      nextStep="Usar las secciones disponibles o solicitar soporte si necesitas revisar un servicio."
    />
  {/if}
</section>
