<script lang="ts">
  import { EmptyState, SectionHeader, StatusBadge } from "../../ui";
  import { formatDateTime } from "../../../lib/formatters";
  import { getAccessibleWorkspaceIds, getWorkspaceName, reports, services } from "../../../lib/mock";
  import { deriveConsoleAudience } from "../../../lib/navigation/derive";
  import { consoleContext } from "../../../stores/consoleContext.svelte";

  const audience = $derived(deriveConsoleAudience(consoleContext.bootstrap));
  const visibleReports = $derived.by(() => {
    const workspaceIds = getAccessibleWorkspaceIds(consoleContext.bootstrap);
    return reports.filter(({ workspaceId }) =>
      audience === "client" ? workspaceId === consoleContext.activeWorkspace.id : workspaceIds.has(workspaceId),
    );
  });

  function serviceName(serviceId: string) {
    return services.find(({ id }) => id === serviceId)?.name ?? "Servicio no disponible";
  }

  function reportTypeLabel(type: string) {
    return (
      {
        alerts: "Alertas y pendientes",
        catalog: "Catálogo",
        executive_summary: "Resumen ejecutivo",
        operations: "Operación",
        reconciliation: "Conciliación",
      }[type] ?? type
    );
  }
</script>

<section>
  <SectionHeader
    eyebrow="Resultados consultables"
    title="Reportes"
    description="Revisa entregables generados, períodos cubiertos y estado de preparación. Las acciones de descarga son visuales en esta fase mock."
  />

  {#if visibleReports.length > 0}
    <div class="mt-7 grid gap-3 md:hidden">
      {#each visibleReports as report}
        <article class="rounded-2xl border border-[#e0e8ea] bg-white p-4">
          <div class="flex items-start justify-between gap-3">
            <div>
              <h2 class="text-sm font-bold text-[#31536b]">{report.title}</h2>
              <p class="mt-1 text-xs text-[#91a2ad]">{reportTypeLabel(report.type)} · {report.generatedAt ? formatDateTime(report.generatedAt, consoleContext.locale) : "Generación pendiente"}</p>
            </div>
            <StatusBadge status={report.status} />
          </div>
          <dl class="mt-4 space-y-2 border-t border-[#edf1f2] pt-3 text-xs">
            <div><dt class="text-[#91a2ad]">Servicio</dt><dd class="mt-1 font-semibold text-[#587184]">{serviceName(report.serviceId)}</dd></div>
            <div><dt class="text-[#91a2ad]">Período</dt><dd class="mt-1 font-semibold text-[#587184]">{report.period}</dd></div>
            <div><dt class="text-[#91a2ad]">Workspace</dt><dd class="mt-1 font-semibold text-[#587184]">{getWorkspaceName(report.workspaceId)}</dd></div>
          </dl>
          <button class="mt-4 rounded-full border border-[#d5e4e4] px-3 py-1.5 text-xs font-bold text-[#78909f]" disabled type="button">
            {report.status === "ready" ? "Descarga no disponible en mock" : "Preparación en curso"}
          </button>
        </article>
      {/each}
    </div>
    <div class="mt-7 hidden overflow-hidden rounded-3xl border border-[#e0e8ea] bg-white shadow-[0_24px_60px_-54px_rgba(16,45,79,0.7)] md:block">
    <div class="overflow-x-auto">
      <table class="w-full min-w-[58rem] text-start text-sm">
        <thead class="bg-[#f4f8f8] text-[0.65rem] uppercase tracking-[0.15em] text-[#78909f]">
          <tr>
            <th class="px-5 py-3 text-start">Reporte</th>
            <th class="px-5 py-3 text-start">Servicio</th>
            <th class="px-5 py-3 text-start">Período</th>
            <th class="px-5 py-3 text-start">Workspace</th>
            <th class="px-5 py-3 text-start">Estado</th>
            <th class="px-5 py-3 text-start">Acción mock</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-[#edf1f2]">
          {#each visibleReports as report}
            <tr class="text-[#567184]">
              <td class="px-5 py-4">
                <p class="font-bold text-[#31536b]">{report.title}</p>
                <p class="mt-1 text-xs text-[#91a2ad]">{reportTypeLabel(report.type)} · {report.generatedAt ? formatDateTime(report.generatedAt, consoleContext.locale) : "Generación pendiente"}</p>
              </td>
              <td class="px-5 py-4 text-xs font-semibold">{serviceName(report.serviceId)}</td>
              <td class="px-5 py-4 text-xs">{report.period}</td>
              <td class="px-5 py-4 text-xs">{getWorkspaceName(report.workspaceId)}</td>
              <td class="px-5 py-4"><StatusBadge status={report.status} /></td>
              <td class="px-5 py-4">
                <button class="rounded-full border border-[#d5e4e4] px-3 py-1.5 text-xs font-bold text-[#78909f]" disabled type="button">
                  {report.status === "ready" ? "Descarga no disponible en mock" : "Preparación en curso"}
                </button>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </div>
  {:else}
    <EmptyState
      class="mt-7"
      title="Todavía no hay reportes generados."
      description="Los entregables aparecerán cuando el servicio complete su primer período de análisis."
      nextStep="Revisar el estado del servicio o esperar la próxima generación programada."
    />
  {/if}
</section>
