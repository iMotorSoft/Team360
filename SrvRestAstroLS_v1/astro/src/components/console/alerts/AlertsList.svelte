<script lang="ts">
  import { EmptyState, SectionHeader } from "../../ui";
  import { alerts, getAccessibleWorkspaceIds, getWorkspaceName, services, type AlertType } from "../../../lib/mock";
  import { deriveConsoleAudience } from "../../../lib/navigation/derive";
  import { consoleContext } from "../../../stores/consoleContext.svelte";
  import AlertCard from "./AlertCard.svelte";

  const audience = $derived(deriveConsoleAudience(consoleContext.bootstrap));
  const visibleAlerts = $derived.by(() => {
    const workspaceIds = getAccessibleWorkspaceIds(consoleContext.bootstrap);
    return alerts.filter(({ workspaceId }) =>
      audience === "client" ? workspaceId === consoleContext.activeWorkspace.id : workspaceIds.has(workspaceId),
    );
  });
  const sections: Array<{ type: AlertType; title: string; description: string }> = [
    { type: "business", title: "Alertas de negocio", description: "Situaciones que pueden afectar resultados o continuidad operativa." },
    { type: "approval", title: "Aprobaciones pendientes", description: "Acciones que conservan revisión humana antes de continuar." },
    { type: "technical", title: "Alertas técnicas", description: "Configuraciones o estados operativos que requieren seguimiento." },
  ];

  function serviceName(serviceId: string) {
    return services.find(({ id }) => id === serviceId)?.name ?? "Servicio no disponible";
  }
</script>

<section>
  <SectionHeader
    eyebrow="Atención priorizada"
    title="Alertas"
    description="Separa alertas de negocio, aprobaciones y seguimiento técnico para orientar la próxima acción permitida."
  />

  <div class="mt-7 space-y-6">
    {#each sections as section}
      <section>
        <h2 class="text-lg font-bold tracking-[-0.03em] text-[#173b5b]">{section.title}</h2>
        <p class="mt-1 text-xs leading-5 text-[#78909f]">{section.description}</p>
        <div class="mt-3 space-y-3">
          {#each visibleAlerts.filter(({ type }) => type === section.type) as alert}
            <AlertCard
              {alert}
              contextLabel={`${serviceName(alert.serviceId)} · ${getWorkspaceName(alert.workspaceId)}`}
              showAction
            />
          {:else}
            <EmptyState
              compact
              title="Sin alertas de este tipo"
              description="No hay situaciones registradas para esta categoría dentro del alcance visible."
            />
          {/each}
        </div>
      </section>
    {/each}
  </div>
</section>
