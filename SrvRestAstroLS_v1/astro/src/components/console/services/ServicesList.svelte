<script lang="ts">
  import {
    Card,
    EmptyState,
    SectionHeader,
    StatCard,
    StatusBadge,
  } from "../../ui";
  import { formatDateTime } from "../../../lib/formatters";
  import {
    getOrganizationNameForWorkspace,
    getVisibleServices,
    getWorkspaceName,
  } from "../../../lib/mock";
  import {
    buildServiceDetailRoute,
    deriveConsoleAudience,
  } from "../../../lib/navigation/derive";
  import { consoleContext } from "../../../stores/consoleContext.svelte";

  const audience = $derived(deriveConsoleAudience(consoleContext.bootstrap));
  const visibleServices = $derived.by(() => {
    const services = getVisibleServices(consoleContext.bootstrap);
    return audience === "client"
      ? services.filter(
          ({ workspaceId }) =>
            workspaceId === consoleContext.activeWorkspace.id,
        )
      : services;
  });
  const activeServices = $derived(
    visibleServices.filter(({ status }) => status === "active").length,
  );
  const attentionServices = $derived(
    visibleServices.filter(({ health }) =>
      ["warning", "critical", "pending"].includes(health),
    ).length,
  );
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
    <StatCard
      label="Servicios visibles"
      value={String(visibleServices.length)}
      description="Según perfil y alcance mock."
    />
    <StatCard
      label="Activos"
      value={String(activeServices)}
      description="Prestaciones en funcionamiento."
    />
    <StatCard
      label="Con seguimiento"
      value={String(attentionServices)}
      description="Requieren revisión o configuración."
    />
  </div>

  <div class="mt-6 grid gap-6">
    {#each visibleServices as service}
      <Card variant="large" class="flex flex-col justify-between">
        <div>
          <!-- Cabecera: Títulos y Estado -->
          <div
            class="flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between"
          >
            <div class="max-w-3xl">
              <div class="flex flex-wrap items-baseline gap-x-3">
                <span class="top-badge">
                  {service.packageName}
                </span>
                <span class="text-[#cbd5db]">•</span>
                <span class="text-base font-semibold text-[#78909f]">
                  {service.category}
                </span>
              </div>
              <h2
                class="mt-3 text-3xl font-bold tracking-[-0.035em] text-[#173b5b]"
              >
                {service.name}
              </h2>
              <p class="mt-3 text-lg leading-relaxed text-[#69808f]">
                {audience === "client"
                  ? service.clientSummary
                  : service.description}
              </p>
            </div>
            <div
              class="flex shrink-0 flex-col items-start sm:items-end gap-3 mt-4 sm:mt-0"
            >
              <div class="flex flex-wrap justify-end gap-2">
                <StatusBadge status={service.status} />
                <StatusBadge status={service.health} />
              </div>
              <p class="text-base font-medium text-[#91a2ad]">
                Actualizado: {formatDateTime(
                  service.lastRunAt,
                  consoleContext.locale,
                )}
              </p>
            </div>
          </div>

          <!-- Contexto (si no es cliente) -->
          {#if audience !== "client"}
            <div
              class="mt-6 flex flex-wrap items-center gap-x-6 gap-y-3 rounded-2xl border border-[#edf1f2]
              bg-[#fcfdfd] px-5 py-4 text-base"
            >
              <div class="flex items-center gap-2.5">
                <span class="text-[#91a2ad]">Organización:</span>
                <span class="font-bold text-[#47657b]"
                  >{getOrganizationNameForWorkspace(service.workspaceId)}</span
                >
              </div>
              <div class="hidden h-5 w-px bg-[#edf1f2] sm:block"></div>
              <div class="flex items-center gap-2.5">
                <span class="text-[#91a2ad]">Workspace:</span>
                <span class="font-bold text-[#47657b]"
                  >{getWorkspaceName(service.workspaceId)}</span
                >
              </div>
            </div>
          {/if}

          <!-- Métricas -->
          {#if service.metrics.length > 0}
            <div class="mt-8 grid gap-4 sm:grid-cols-3">
              {#each service.metrics.slice(0, 3) as metric}
                <div
                  class="rounded-2xl bg-green-100 border border-transparent hover:border-primary/20 p-5 transition-colors
                  "
                >
                  <p class="top-badge">
                    {metric.label}
                  </p>
                  <div class="mt-3 flex items-baseline gap-3">
                    <p class="text-4xl font-bold tracking-tight text-[#214762]">
                      {metric.value}
                    </p>
                    {#if metric.trend}
                      <p class="text-lg font-bold text-[#168b88]">
                        {metric.trend}
                      </p>
                    {/if}
                  </div>
                </div>
              {/each}
            </div>
          {/if}
        </div>

        <!-- Footer: Próximo Paso y Acción -->
        <div
          class="mt-8 flex flex-col gap-5 border-t border-[#edf1f2] pt-6 sm:flex-row sm:items-center sm:justify-between"
        >
          <div>
            <p
              class="text-sm font-bold uppercase tracking-[0.15em] text-[#91a2ad]"
            >
              Próximo paso
            </p>
            <p class="mt-1 text-lg font-bold text-[#47657b]">
              {service.nextStep}
            </p>
          </div>
          <a
            class="inline-flex shrink-0 items-center justify-center rounded-full bg-[#153b5b] px-6 py-3
            text-base font-bold text-white transition hover:bg-[#153b5b]/80"
            href={buildServiceDetailRoute(
              service.workspaceId,
              service.id,
              consoleContext.activeProfile,
            )}
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
