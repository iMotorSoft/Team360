<script lang="ts">
  import { Card, EmptyState, SectionHeader, StatusBadge } from "../../ui";
  import { formatDateTime, formatDuration } from "../../../lib/formatters";
  import { getAccessibleWorkspaceIds, runs, services } from "../../../lib/mock";
  import { consoleContext } from "../../../stores/consoleContext.svelte";

  const visibleRuns = $derived.by(() => {
    const workspaceIds = getAccessibleWorkspaceIds(consoleContext.bootstrap);
    const serviceIds = new Set(
      services
        .filter(({ workspaceId }) => workspaceIds.has(workspaceId))
        .map(({ id }) => id),
    );
    return runs.filter(({ serviceId }) => serviceIds.has(serviceId));
  });

  function serviceName(serviceId: string) {
    return (
      services.find(({ id }) => id === serviceId)?.name ??
      "Servicio no disponible"
    );
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
          <div
            class="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between"
          >
            <div>
              <div class="flex flex-wrap gap-2">
                <StatusBadge status={run.status} />
                <StatusBadge status={run.health} />
              </div>
              <h2 class="mt-3 text-lg font-bold text-[#31536b]">
                {run.workerName}
              </h2>
              <p class="mt-1 text-lg text-[#8396a2]">
                {serviceName(run.serviceId)}
              </p>
              <p class="mt-3 text-base leading-5 text-[#668092]">
                {run.summary}
              </p>
            </div>
            <dl
              class="mt-5 xl:mt-0 flex shrink-0 flex-col sm:flex-row divide-y sm:divide-y-0 sm:divide-x divide-[#edf1f2] rounded-2xl border border-[#edf1f2] bg-[#fcfdfd] overflow-hidden xl:min-w-[30rem]"
            >
              <div class="flex-1 p-4">
                <dt
                  class="flex items-center gap-2 text-sm font-bold uppercase tracking-wider text-[#91a2ad]"
                >
                  <svg
                    class="size-5 shrink-0 opacity-80"
                    xmlns="http://www.w3.org/2000/svg"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke-width="2"
                    stroke="currentColor"
                    ><path
                      stroke-linecap="round"
                      stroke-linejoin="round"
                      d="M12 6v6l4 2M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                    /></svg
                  >
                  Inicio
                </dt>
                <dd class="mt-1 text-base font-bold text-[#47657b]">
                  {formatDateTime(run.startedAt, consoleContext.locale)}
                </dd>
              </div>
              <div class="flex-1 p-4">
                <dt
                  class="flex items-center gap-2 text-sm font-bold uppercase tracking-wider text-[#91a2ad]"
                >
                  <svg
                    class="size-5 shrink-0 opacity-80"
                    xmlns="http://www.w3.org/2000/svg"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke-width="2"
                    stroke="currentColor"
                    ><path
                      stroke-linecap="round"
                      stroke-linejoin="round"
                      d="M4 4h16M4 20h16M8 4v4a4 4 0 004 4v0a4 4 0 004-4V4m-8 16v-4a4 4 0 014-4v0a4 4 0 014 4v4"
                    /></svg
                  >
                  Duración
                </dt>
                <dd class="mt-1 text-base font-bold text-[#47657b]">
                  {formatDuration(run.durationSeconds, consoleContext.locale)}
                </dd>
              </div>
              <div class="flex-1 p-4">
                <dt
                  class="flex items-center gap-2 text-sm font-bold uppercase tracking-wider text-[#91a2ad]"
                >
                  <svg
                    class="size-5 shrink-0 opacity-80"
                    xmlns="http://www.w3.org/2000/svg"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke-width="2"
                    stroke="currentColor"
                    ><path
                      stroke-linecap="round"
                      stroke-linejoin="round"
                      d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                    /></svg
                  >
                  Errores
                </dt>
                <dd class="mt-1 text-base font-bold text-[#47657b]">
                  {run.errorCount}
                </dd>
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
