<script lang="ts">
  import { onMount } from "svelte";
  import {
    Button,
    Card,
    EmptyState,
    SectionHeader,
    StatCard,
    StatusBadge,
    Tabs,
  } from "../../ui";
  import {
    formatDate,
    formatDateTime,
    formatDuration,
  } from "../../../lib/formatters";
  import {
    alerts,
    getOrganizationNameForWorkspace,
    getVisibleServiceById,
    getWorkspaceName,
    reports,
    runs,
    tasks,
    workers,
  } from "../../../lib/mock";
  import {
    buildConsoleRoute,
    deriveConsoleAudience,
  } from "../../../lib/navigation/derive";
  import { consoleContext } from "../../../stores/consoleContext.svelte";

  let { serviceId }: { serviceId: string } = $props();

  const audience = $derived(deriveConsoleAudience(consoleContext.bootstrap));
  const service = $derived(
    getVisibleServiceById(consoleContext.bootstrap, serviceId),
  );
  const serviceReports = $derived(
    reports.filter((report) => report.serviceId === serviceId),
  );
  const serviceAlerts = $derived(
    alerts.filter((alert) => alert.serviceId === serviceId),
  );
  const serviceTasks = $derived(
    tasks.filter((task) => task.serviceId === serviceId),
  );
  const serviceRuns = $derived(
    runs.filter((run) => run.serviceId === serviceId),
  );
  const serviceWorkers = $derived(
    workers.filter((worker) => worker.serviceId === serviceId),
  );
  const tabs = $derived.by(() => {
    const items = [
      { id: "summary", label: "Resumen" },
      { id: "results", label: "Resultados" },
      { id: "reports", label: "Reportes" },
      { id: "alerts", label: "Alertas" },
      { id: "tasks", label: "Tareas" },
      {
        id: "history",
        label: audience === "client" ? "Historial y soporte" : "Historial",
      },
    ];

    if (audience !== "client") {
      items.push({ id: "configuration", label: "Configuración" });
    }

    if (audience === "owner" || audience === "operator") {
      items.push({ id: "technical", label: "Técnico" });
    }

    return items;
  });
  let activeTab = $state("summary");

  function setActiveTab(tabId: string) {
    activeTab = tabId;

    const url = new URL(window.location.href);
    url.searchParams.set("tab", tabId);
    window.history.replaceState({}, "", url);
  }

  onMount(() => {
    const requestedTab = new URLSearchParams(window.location.search).get("tab");
    if (requestedTab && tabs.some(({ id }) => id === requestedTab)) {
      activeTab = requestedTab;
    }
  });

  $effect(() => {
    if (!tabs.some(({ id }) => id === activeTab)) {
      activeTab = "summary";
    }
  });
</script>

{#if service}
  <section>
    <a
      class="inline-flex text-sm font-bold text-[#168b88] transition hover:text-[#102d4f]"
      href={buildConsoleRoute(
        service.workspaceId,
        "services",
        consoleContext.activeProfile,
      )}
    >
      ← Volver a servicios
    </a>

    <div class="mt-4">
      <SectionHeader
        eyebrow={service.packageName}
        title={service.name}
        description={audience === "client"
          ? service.clientSummary
          : service.description}
      >
        {#snippet actions()}
          <div class="flex flex-wrap gap-2">
            <StatusBadge status={service.status} />
            <StatusBadge status={service.health} />
          </div>
        {/snippet}
      </SectionHeader>
    </div>

    <div class="mt-6">
      <Tabs {tabs} {activeTab} onChange={setActiveTab} />
    </div>

    {#if activeTab === "summary"}
      <div class="mt-6 grid gap-5 xl:grid-cols-[1.25fr_0.75fr]">
        <Card tag="section" variant="large">
          <p
            class="text-sm font-bold uppercase tracking-[0.16em] text-[#168b88]"
          >
            Cómo funciona
          </p>
          <div class="mt-5 space-y-3">
            {#each service.workflowSteps as step, index}
              <div class="flex items-center gap-3 rounded-xl bg-[#f8fbfa] p-3">
                <span
                  class="grid size-8 shrink-0 place-items-center rounded-full bg-[#153b5b] text-xs font-bold text-white"
                  >{index + 1}</span
                >
                <p class="text-sm font-semibold text-[#587184]">{step}</p>
              </div>
            {/each}
          </div>
        </Card>

        <aside class="space-y-4">
          <Card tag="section" variant="dark">
            <p
              class="text-sm font-bold uppercase tracking-[0.16em] text-[#86ddd5]"
            >
              Próximo paso
            </p>
            <p class="mt-3 text-base font-semibold leading-6 text-white/85">
              {service.nextStep}
            </p>
          </Card>
          <Card tag="section" variant="flat" rounded="rounded-3xl">
            <p
              class="text-sm font-bold uppercase tracking-[0.16em] text-[#168b88]"
            >
              Contexto
            </p>
            <dl class="mt-4 space-y-3 text-base">
              <div class="flex justify-between gap-3">
                <dt class="text-[#91a2ad]">Organización</dt>
                <dd class="font-bold text-[#587184]">
                  {getOrganizationNameForWorkspace(service.workspaceId)}
                </dd>
              </div>
              <div class="flex justify-between gap-3">
                <dt class="text-[#91a2ad]">Workspace</dt>
                <dd class="font-bold text-[#587184]">
                  {getWorkspaceName(service.workspaceId)}
                </dd>
              </div>
              <div class="flex justify-between gap-3">
                <dt class="text-[#91a2ad]">Categoría</dt>
                <dd class="font-bold text-[#587184]">{service.category}</dd>
              </div>
              <div class="flex justify-between gap-3">
                <dt class="text-[#91a2ad]">Última ejecución</dt>
                <dd class="font-bold text-[#587184]">
                  {formatDateTime(service.lastRunAt, consoleContext.locale)}
                </dd>
              </div>
            </dl>
          </Card>
        </aside>
      </div>
    {:else if activeTab === "results"}
      <div class="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {#each service.metrics as metric}
          <StatCard
            label={metric.label}
            value={metric.value}
            trend={metric.trend}
            description="Indicador visible del servicio seleccionado."
          />
        {/each}
      </div>
    {:else if activeTab === "reports"}
      <div class="mt-6 space-y-3">
        {#each serviceReports as report}
          <Card variant="flat">
            <div
              class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between"
            >
              <div>
                <p class="text-base font-bold text-[#31536b]">{report.title}</p>
                <p class="mt-1 text-sm text-[#8396a2]">
                  {report.period} · {report.type}
                </p>
              </div>
              <StatusBadge status={report.status} />
            </div>
            <Button
              class="mt-4 h-auto min-h-0 rounded-full px-3 py-1.5 text-sm"
              disabled
              variant="ghost"
            >
              {report.status === "ready"
                ? "Descarga no disponible en mock"
                : "Preparación en curso"}
            </Button>
          </Card>
        {:else}
          <EmptyState
            title="Todavía no hay reportes asociados."
            description="Los entregables aparecerán después del primer período de análisis del servicio."
            nextStep="Esperar la próxima generación programada."
          />
        {/each}
      </div>
    {:else if activeTab === "alerts"}
      <div class="mt-6 space-y-3">
        {#each serviceAlerts as alert}
          <Card variant="flat">
            <div class="flex flex-wrap gap-2">
              <StatusBadge status={alert.severity} />
              <StatusBadge status={alert.status} />
            </div>
            <p class="mt-3 text-base font-bold text-[#31536b]">{alert.title}</p>
            <p
              class="mt-3 rounded-xl bg-[#f8fbfa] px-3 py-2.5 text-sm font-semibold leading-5 text-[#668092]"
            >
              Acción sugerida: {alert.suggestedAction}
            </p>
          </Card>
        {:else}
          <EmptyState
            title="No hay alertas registradas."
            description="El servicio no presenta situaciones visibles que requieran seguimiento."
            nextStep="Continuar con el monitoreo habitual."
          />
        {/each}
      </div>
    {:else if activeTab === "tasks"}
      <div class="mt-6 space-y-3">
        {#each serviceTasks as task}
          <Card
            variant="flat"
            class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"
          >
            <div>
              <p class="text-base font-bold text-[#31536b]">{task.title}</p>
              <p class="mt-1 text-sm text-[#8396a2]">
                {task.assigneeLabel} · vence {formatDate(
                  task.dueDate,
                  consoleContext.locale,
                )}
              </p>
            </div>
            <div class="flex flex-wrap gap-2">
              <StatusBadge
                status={task.priority}
                label={`Prioridad ${task.priority}`}
              /><StatusBadge status={task.status} />
            </div>
          </Card>
        {:else}
          <EmptyState
            title="No hay acciones pendientes."
            description="Este servicio no requiere aprobaciones ni tareas manuales en este momento."
            nextStep="Continuar con la revisión periódica de resultados."
          />
        {/each}
      </div>
    {:else if activeTab === "history"}
      <div class="mt-6 grid gap-5 xl:grid-cols-[1.2fr_0.8fr]">
        <Card tag="section" variant="flat" rounded="rounded-3xl">
          <p
            class="text-sm font-bold uppercase tracking-[0.16em] text-[#168b88]"
          >
            Actividad reciente
          </p>
          <div class="mt-4 space-y-3">
            {#each serviceRuns.slice(0, 4) as run}
              <article
                class="border-b border-[#edf1f2] pb-3 last:border-0 last:pb-0"
              >
                <div class="flex items-center justify-between gap-3">
                  <p class="text-base font-bold text-[#47657b]">
                    {audience === "client"
                      ? "Actualización del servicio"
                      : run.workerName}
                  </p>
                  <StatusBadge status={run.status} />
                </div>
                <p class="mt-2 text-sm leading-5 text-[#8396a2]">
                  {run.summary}
                </p>
              </article>
            {:else}
              <p class="text-sm leading-5 text-[#8396a2]">
                La primera ejecución todavía está pendiente.
              </p>
            {/each}
          </div>
        </Card>
        <Card tag="section" variant="dark">
          <p
            class="text-sm font-bold uppercase tracking-[0.16em] text-[#86ddd5]"
          >
            Soporte contextual
          </p>
          <p class="mt-3 text-base leading-6 text-white/75">
            El equipo puede revisar este servicio con su contexto, alertas y
            tareas visibles sin exponer datos internos innecesarios.
          </p>
          <Button
            class="mt-5 h-auto min-h-0 rounded-full bg-[#72d9cf] px-4 py-2 text-base text-[#123653]"
            disabled
            variant="ghost">Soporte no disponible en mock</Button
          >
        </Card>
      </div>
    {:else if activeTab === "configuration"}
      <div class="mt-6 grid gap-5 xl:grid-cols-2">
        <Card tag="section" variant="flat" rounded="rounded-3xl">
          <p
            class="text-sm font-bold uppercase tracking-[0.16em] text-[#168b88]"
          >
            Integraciones visibles
          </p>
          <div class="mt-4 space-y-3">
            {#each service.integrationNames as integration}
              <div
                class="flex items-center justify-between gap-3 rounded-xl bg-[#f8fbfa] px-3 py-3"
              >
                <p class="text-sm font-bold text-[#47657b]">{integration}</p>
                <StatusBadge status="review" label="Referencia mock" />
              </div>
            {/each}
          </div>
        </Card>
        <Card tag="section" variant="flat" rounded="rounded-3xl">
          <p
            class="text-sm font-bold uppercase tracking-[0.16em] text-[#168b88]"
          >
            Parámetros delegados
          </p>
          <p class="mt-3 text-base leading-5 text-[#78909f]">
            Esta vista prepara el diseño de configuración permitida. No guarda
            cambios ni contiene accesos reales.
          </p>
          <Button
            class="mt-5 h-auto min-h-0 rounded-full border border-[#d5e4e4] px-4 py-2 text-lg"
            disabled
            variant="ghost">Edición no disponible en mock</Button
          >
        </Card>
      </div>
    {:else if activeTab === "technical"}
      <div class="mt-6 grid gap-5 xl:grid-cols-2">
        <Card tag="section" variant="flat" rounded="rounded-3xl">
          <p
            class="text-sm font-bold uppercase tracking-[0.16em] text-[#168b88]"
          >
            Workers vinculado
          </p>
          <div class="mt-4 space-y-3">
            {#each serviceWorkers as worker}
              <article class="rounded-xl bg-[#f8fbfa] px-3 py-3">
                <div class="flex items-center justify-between gap-3">
                  <p class="text-sm font-bold text-[#47657b]">{worker.name}</p>
                  <StatusBadge status={worker.health} />
                </div>
                <p class="mt-2 text-sm text-[#91a2ad]">
                  Errores: {worker.errorCount} · duración media: {worker.averageDurationSeconds
                    ? formatDuration(
                        worker.averageDurationSeconds,
                        consoleContext.locale,
                      )
                    : "pendiente"}
                </p>
              </article>
            {:else}
              <p class="text-sm text-[#8396a2]">Sin worker mock vinculado.</p>
            {/each}
          </div>
        </Card>
        <Card tag="section" variant="flat" rounded="rounded-3xl">
          <p
            class="text-sm font-bold uppercase tracking-[0.16em] text-[#168b88]"
          >
            Runs resumidos
          </p>
          <div class="mt-4 space-y-3">
            {#each serviceRuns.slice(0, 4) as run}
              <article class="rounded-xl bg-[#f8fbfa] px-3 py-3">
                <div class="flex items-center justify-between gap-3">
                  <p class="text-sm font-bold text-[#47657b]">{run.id}</p>
                  <StatusBadge status={run.health} />
                </div>
                <p class="mt-2 text-base text-[#91a2ad]">{run.summary}</p>
              </article>
            {:else}
              <p class="text-sm text-[#8396a2]">Sin runs mock registrados.</p>
            {/each}
          </div>
        </Card>
      </div>
    {/if}
  </section>
{:else}
  <Card tag="section" variant="flat" rounded="rounded-3xl" padding="p-6">
    <p class="text-sm font-bold uppercase tracking-[0.16em] text-[#168b88]">
      Servicio no disponible
    </p>
    <h1 class="mt-3 text-3xl font-bold tracking-[-0.04em] text-[#173b5b]">
      No puedes consultar este servicio desde el contexto activo.
    </h1>
    <p class="mt-3 text-base leading-6 text-[#78909f]">
      Vuelve al listado o cambia a un workspace autorizado mediante el selector
      mock.
    </p>
    <a
      class="mt-5 inline-flex rounded-full bg-[#153b5b] px-4 py-2 text-sm font-bold text-white"
      href={buildConsoleRoute(
        consoleContext.activeWorkspace.id,
        "services",
        consoleContext.activeProfile,
      )}
    >
      Volver a servicios
    </a>
  </Card>
{/if}
