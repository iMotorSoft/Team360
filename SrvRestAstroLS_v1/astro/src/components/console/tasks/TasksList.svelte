<script lang="ts">
  import { EmptyState, SectionHeader, StatusBadge } from "../../ui";
  import { formatDate } from "../../../lib/formatters";
  import { getAccessibleWorkspaceIds, getWorkspaceName, services, tasks } from "../../../lib/mock";
  import { deriveConsoleAudience } from "../../../lib/navigation/derive";
  import { consoleContext } from "../../../stores/consoleContext.svelte";

  const audience = $derived(deriveConsoleAudience(consoleContext.bootstrap));
  const visibleTasks = $derived.by(() => {
    const workspaceIds = getAccessibleWorkspaceIds(consoleContext.bootstrap);
    return tasks.filter(({ workspaceId }) =>
      audience === "client" ? workspaceId === consoleContext.activeWorkspace.id : workspaceIds.has(workspaceId),
    );
  });

  function serviceName(serviceId: string) {
    return services.find(({ id }) => id === serviceId)?.name ?? "Servicio no disponible";
  }
</script>

<section>
  <SectionHeader
    eyebrow="Próximas acciones"
    title="Tareas"
    description="Trabajo manual, asistido y aprobaciones pendientes ordenadas por prioridad, responsable y vencimiento."
  />

  <div class="mt-7 space-y-3">
    {#each visibleTasks as task}
      <article class="rounded-2xl border border-[#e0e8ea] bg-white p-5">
        <div class="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <div class="flex flex-wrap gap-2">
              <StatusBadge status={task.priority} label={`Prioridad ${task.priority}`} />
              <StatusBadge status={task.status} />
            </div>
            <h2 class="mt-3 text-sm font-bold text-[#31536b]">{task.title}</h2>
            <p class="mt-2 text-xs leading-5 text-[#78909f]">{serviceName(task.serviceId)} · {getWorkspaceName(task.workspaceId)}</p>
          </div>
          <dl class="grid shrink-0 grid-cols-2 gap-3 rounded-xl bg-[#f8fbfa] p-3 text-xs sm:min-w-[19rem]">
            <div><dt class="text-[#91a2ad]">Responsable</dt><dd class="mt-1 font-bold text-[#587184]">{task.assigneeLabel}</dd></div>
            <div><dt class="text-[#91a2ad]">Vencimiento</dt><dd class="mt-1 font-bold text-[#587184]">{formatDate(task.dueDate, consoleContext.locale)}</dd></div>
          </dl>
        </div>
      </article>
    {/each}
    {#if visibleTasks.length === 0}
      <EmptyState
        title="No hay acciones pendientes."
        description="El workspace no tiene tareas abiertas ni aprobaciones esperando revisión."
        nextStep="Continuar con el seguimiento habitual de resultados y alertas."
      />
    {/if}
  </div>
</section>
