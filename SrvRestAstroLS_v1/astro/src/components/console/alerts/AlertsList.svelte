<script lang="ts">
  import { Card, SectionHeader, StatusBadge } from "../../ui";
  import AlertCard from "./AlertCard.svelte";
  import { formatDateTime } from "../../../lib/formatters";
  import {
    alerts,
    getAccessibleWorkspaceIds,
    getWorkspaceName,
    services,
    type AlertType,
  } from "../../../lib/mock";
  import { deriveConsoleAudience } from "../../../lib/navigation/derive";
  import { consoleContext } from "../../../stores/consoleContext.svelte";

  const audience = $derived(deriveConsoleAudience(consoleContext.bootstrap));
  const visibleAlerts = $derived.by(() => {
    const workspaceIds = getAccessibleWorkspaceIds(consoleContext.bootstrap);
    return alerts.filter(({ workspaceId }) =>
      audience === "client"
        ? workspaceId === consoleContext.activeWorkspace.id
        : workspaceIds.has(workspaceId),
    );
  });
  const sections: Array<{
    type: AlertType;
    title: string;
    description: string;
  }> = [
    {
      type: "business",
      title: "Alertas de negocio",
      description:
        "Situaciones que pueden afectar resultados o continuidad operativa.",
    },
    {
      type: "approval",
      title: "Aprobaciones pendientes",
      description: "Acciones que conservan revisión humana antes de continuar.",
    },
    {
      type: "technical",
      title: "Alertas técnicas",
      description:
        "Configuraciones o estados operativos que requieren seguimiento.",
    },
  ];

  function serviceName(serviceId: string) {
    return (
      services.find(({ id }) => id === serviceId)?.name ??
      "Servicio no disponible"
    );
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
        <h2 class="text-3xl font-bold tracking-[-0.03em] text-[#173b5b]">
          {section.title}
        </h2>
        <p class="mt-1 text-base leading-5 text-[#78909f]">
          {section.description}
        </p>
        <div class="mt-3 space-y-3">
          {#each visibleAlerts.filter(({ type }) => type === section.type) as alert}
            <AlertCard
              alert={alert}
              cardVariant="flat"
              showStatus={true}
              showService={true}
              showWorkspace={true}
              showAction={true}
            />
          {:else}
            <p
              class="rounded-2xl border border-dashed border-[#d7e3e5] bg-white/60 p-4 text-xs text-[#8396a2]"
            >
              Sin alertas de este tipo en el alcance visible.
            </p>
          {/each}
        </div>
      </section>
    {/each}
  </div>
</section>
