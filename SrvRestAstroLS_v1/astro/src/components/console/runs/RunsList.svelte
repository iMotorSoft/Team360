<script lang="ts">
  import { EmptyState, SectionHeader, StatusBadge } from "../../ui";
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
        <article class="rounded-2xl border border-[#e0e8ea] bg-white p-5">
          <div class="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
            <div>
              <div class="flex flex-wrap gap-2">
                <StatusBadge status={run.status} />
                <StatusBadge status={run.health} />
              </div>
              <h2 class="mt-3 text-sm font-bold text-[#31536b]">{run.workerName}</h2>
              <p class="mt-1 text-xs text-[#8396a2]">{serviceName(run.serviceId)}</p>
              <p class="mt-3 text-xs leading-5 text-[#668092]">{run.summary}</p>
            </div>
            <dl class="grid shrink-0 grid-cols-3 gap-3 rounded-xl bg-[#f8fbfa] p-3 text-xs xl:min-w-[23rem]">
              <div><dt class="text-[#91a2ad]">Inicio</dt><dd class="mt-1 font-bold text-[#587184]">{formatDateTime(run.startedAt, consoleContext.locale)}</dd></div>
              <div><dt class="text-[#91a2ad]">Duración</dt><dd class="mt-1 font-bold text-[#587184]">{formatDuration(run.durationSeconds, consoleContext.locale)}</dd></div>
              <div><dt class="text-[#91a2ad]">Errores</dt><dd class="mt-1 font-bold text-[#587184]">{run.errorCount}</dd></div>
            </dl>
          </div>
        </article>
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
