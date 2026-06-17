<script lang="ts">
  import { Card, EmptyState, SectionHeader, StatusBadge } from "../../ui";
  import { formatDateTime, formatDuration } from "../../../lib/formatters";
  import {
    getAccessibleWorkspaceIds,
    services,
    workers,
  } from "../../../lib/mock";
  import { consoleContext } from "../../../stores/consoleContext.svelte";

  const visibleWorkers = $derived.by(() => {
    const workspaceIds = getAccessibleWorkspaceIds(consoleContext.bootstrap);
    const serviceIds = new Set(
      services
        .filter(({ workspaceId }) => workspaceIds.has(workspaceId))
        .map(({ id }) => id),
    );
    return workers.filter(({ serviceId }) => serviceIds.has(serviceId));
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
    eyebrow="Profundidad técnica autorizada"
    title="Workers"
    description="Capacidades internas vinculadas a servicios visibles. La vista expone salud y actividad resumida, nunca secretos ni credenciales."
  />

  {#if consoleContext.bootstrap.uiHints.technicalDepth !== "business"}
    <div class="mt-7 grid gap-4 xl:grid-cols-2">
      {#each visibleWorkers as worker}
        <Card variant="flat">
          <div
            class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between"
          >
            <div>
              <h2 class="text-lg font-bold text-[#31536b]">{worker.name}</h2>
              <p class="mt-2 text-lg leading-5 text-[#78909f]">
                {serviceName(worker.serviceId)}
              </p>
            </div>
            <div class="flex flex-wrap gap-2">
              <StatusBadge status={worker.status} />
              <StatusBadge status={worker.health} />
            </div>
          </div>
          <dl
            class="mt-6 flex flex-col sm:flex-row divide-y sm:divide-y-0 sm:divide-x divide-[#edf1f2] rounded-2xl border border-[#edf1f2] bg-[#fcfdfd] overflow-hidden"
          >
            <div class="flex-1 p-4 sm:p-5 text-start">
              <dt
                class="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-[#91a2ad]"
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
                Última ejecución
              </dt>
              <dd class="mt-2 text-lg font-bold text-[#47657b]">
                {formatDateTime(worker.lastRunAt, consoleContext.locale)}
              </dd>
            </div>
            <div class="flex-1 p-4 sm:p-5 text-text-start">
              <dt
                class="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-[#91a2ad]"
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
              <dd class="mt-2 text-lg font-bold text-[#47657b]">
                {worker.errorCount}
              </dd>
            </div>
            <div class="flex-1 p-4 sm:p-5 text-start">
              <dt
                class="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-[#91a2ad]"
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
                Duración media
              </dt>
              <dd class="mt-2 text-lg font-bold text-[#47657b]">
                {worker.averageDurationSeconds
                  ? formatDuration(
                      worker.averageDurationSeconds,
                      consoleContext.locale,
                    )
                  : "Pendiente"}
              </dd>
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
