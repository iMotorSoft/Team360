<script lang="ts">
  import { Card, EmptyState, SectionHeader, StatusBadge } from "../../ui";
  import { formatDateTime, formatDuration } from "../../../lib/formatters";
  import { getAccessibleWorkspaceIds, runs, services } from "../../../lib/mock";
  import { consoleContext } from "../../../stores/consoleContext.svelte";

  const visibleRuns = $derived.by(() => {
    const workspaceIds = getAccessibleWorkspaceIds(consoleContext.bootstrap);
    const serviceIds = new Set(services.filter(({ workspaceId }) => workspaceIds.has(workspaceId)).map(({ id }) => id));
    return runs.filter(({ serviceId }) => serviceIds.has(serviceId));
  });

  function serviceName(serviceId: string) {
    return services.find(({ id }) => id === serviceId)?.name ?? "Servicio no disponible";
  }
</script>

<section>
  <SectionHeader
    eyebrow="Actividad técnica segura"
    title="Ejecuciones"
    description="Runs recientes con estado, duración, errores y resumen operativo. No se exponen payloads, logs sensibles ni credenciales."
  />

  {#if consoleContext.bootstrap.uiHints.technicalDepth !== "business"}
    <div class="mt-7 space-y-3">
      {#each visibleRuns as run}
        <Card variant="flat">
          <div class="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
            <div>
              <div class="flex flex-wrap gap-2">
                <StatusBadge status={run.status} />
                <StatusBadge status={run.health} />
              </div>
              <h2 class="mt-3 text-sm font-bold text-[#31536b]">{run.workerName}</h2>
              <p class="mt-1 text-sm text-[#8396a2]">{serviceName(run.serviceId)}</p>
              <p class="mt-3 text-sm leading-5 text-[#668092]">{run.summary}</p>
            </div>
            <dl class="flex shrink-0 flex-col divide-y divide-[#edf1f2] rounded-2xl border border-[#edf1f2] bg-[#fcfdfd] overflow-hidden sm:flex-row sm:divide-y-0 sm:divide-x xl:min-w-[28rem]">
              <div class="flex-1 p-4">
                <dt class="text-xs font-bold uppercase tracking-wider text-[#91a2ad]">Inicio</dt>
                <dd class="mt-1 text-sm font-bold text-[#587184]">{formatDateTime(run.startedAt, consoleContext.locale)}</dd>
              </div>
              <div class="flex-1 p-4">
                <dt class="text-xs font-bold uppercase tracking-wider text-[#91a2ad]">Duración</dt>
                <dd class="mt-1 text-sm font-bold text-[#587184]">{formatDuration(run.durationSeconds, consoleContext.locale)}</dd>
              </div>
              <div class="flex-1 p-4">
                <dt class="text-xs font-bold uppercase tracking-wider text-[#91a2ad]">Errores</dt>
                <dd class="mt-1 text-sm font-bold text-[#587184]">{run.errorCount}</dd>
              </div>
            </dl>
          </div>
        </Card>
      {/each}
      {#if visibleRuns.length === 0}
        <EmptyState
          title="Todavía no hay ejecuciones registradas."
          description="La actividad técnica resumida aparecerá después de la primera ejecución del servicio."
          nextStep="Revisar el estado de activación del servicio."
        />
      {/if}
    </div>
  {:else}
    <EmptyState
      class="mt-7"
      variant="permission"
      title="Esta vista técnica no está incluida en tu perfil de diseño."
      description="Tu navegación resume el avance del servicio sin mostrar ejecuciones internas."
      nextStep="Consultar resultados, reportes o soporte desde las secciones disponibles."
    />
  {/if}
</section>
