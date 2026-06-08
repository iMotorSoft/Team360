<script lang="ts">
  import { Badge, StatusBadge } from "../../ui";
  import { formatDate, formatDateTime } from "../../../lib/formatters";
  import {
    buildConsoleRoute,
    deriveConsoleAudience,
  } from "../../../lib/navigation/derive";
  import {
    alerts,
    getMockWorkspaceContext,
    organizations,
    reports,
    runs,
    services,
    tasks,
  } from "../../../lib/mock";
  import { consoleContext } from "../../../stores/consoleContext.svelte";

  const audience = $derived(deriveConsoleAudience(consoleContext.bootstrap));
  const context = $derived(
    getMockWorkspaceContext(consoleContext.activeWorkspace.id, {
      includeTechnicalDetails:
        consoleContext.bootstrap.uiHints.technicalDepth !== "business",
    }),
  );
  const accessibleWorkspaceIds = $derived(
    new Set(consoleContext.bootstrap.accessibleWorkspaces.map(({ id }) => id)),
  );
  const visibleServices = $derived(
    services.filter(({ workspaceId }) =>
      accessibleWorkspaceIds.has(workspaceId),
    ),
  );
  const visibleAlerts = $derived(
    alerts.filter(
      ({ status, workspaceId }) =>
        status !== "resolved" && accessibleWorkspaceIds.has(workspaceId),
    ),
  );
  const visibleTasks = $derived(
    tasks.filter(
      ({ status, workspaceId }) =>
        status !== "completed" && accessibleWorkspaceIds.has(workspaceId),
    ),
  );
  const visibleReports = $derived(
    reports.filter(({ workspaceId }) =>
      accessibleWorkspaceIds.has(workspaceId),
    ),
  );
  const visibleRuns = $derived(
    runs.filter(({ serviceId }) =>
      visibleServices.some(({ id }) => id === serviceId),
    ),
  );

  const cards = $derived.by(() => {
    if (audience === "owner") {
      return [
        [
          "Organizaciones activas",
          String(
            organizations.filter(({ status }) => status === "active").length,
          ),
          "Red completa visible",
        ],
        [
          "Partners activos",
          String(
            organizations.filter(
              ({ type, status }) => type === "partner" && status === "active",
            ).length,
          ),
          "Canales regionales habilitados",
        ],
        [
          "Clientes directos",
          String(
            organizations.filter(({ type }) => type === "direct_client").length,
          ),
          "Contratación Team360",
        ],
        [
          "Servicios activos",
          String(
            visibleServices.filter(({ status }) => status === "active").length,
          ),
          "Prestaciones de la red",
        ],
      ];
    }

    if (audience === "partner") {
      return [
        [
          "Clientes propios",
          String(
            consoleContext.bootstrap.accessibleOrganizations.filter(
              ({ type }) => type === "partner_client",
            ).length,
          ),
          "Subárbol autorizado",
        ],
        [
          "Servicios activos",
          String(
            visibleServices.filter(({ status }) => status === "active").length,
          ),
          "Propios y de clientes",
        ],
        [
          "Reportes recientes",
          String(
            visibleReports.filter(({ status }) => status === "ready").length,
          ),
          "Resultados disponibles",
        ],
        [
          "Tareas pendientes",
          String(visibleTasks.length),
          "Seguimiento requerido",
        ],
      ];
    }

    if (audience === "operator") {
      return [
        [
          "Servicios asignados",
          String(visibleServices.length),
          "Alcance operativo autorizado",
        ],
        [
          "Ejecuciones recientes",
          String(visibleRuns.length),
          "Actividad técnica resumida",
        ],
        [
          "Alertas abiertas",
          String(visibleAlerts.length),
          "Revisión recomendada",
        ],
        [
          "Tareas pendientes",
          String(visibleTasks.length),
          "Acciones del equipo",
        ],
      ];
    }

    return [
      [
        "Servicios contratados",
        String(context.services.length),
        "Prestaciones visibles",
      ],
      [
        "Reportes disponibles",
        String(
          context.reports.filter(({ status }) => status === "ready").length,
        ),
        "Resultados consultables",
      ],
      [
        "Alertas abiertas",
        String(
          context.alerts.filter(({ status }) => status !== "resolved").length,
        ),
        "Situaciones visibles",
      ],
      [
        "Tareas pendientes",
        String(
          context.tasks.filter(({ status }) => status !== "completed").length,
        ),
        "Próximos pasos",
      ],
    ];
  });
</script>

<section>
  <div class="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
    <div>
      <p class="text-sm font-bold uppercase tracking-[0.2em] text-[#168b88]">
        Centro de operaciones
      </p>
      <h1
        class="mt-2 text-4xl font-bold tracking-[-0.055em] text-[#102d4f] sm:text-4xl"
      >
        {#if audience === "owner"}
          Estado general de la red
        {:else if audience === "operator"}
          Servicios asignados y revisión operativa
        {:else if audience === "partner"}
          Tu red, servicios y próximos pasos
        {:else}
          Resumen de tu operación
        {/if}
      </h1>
      <p class="mt-3 max-w-3xl text-lg leading-6 text-[#69808f]">
        {#if audience === "owner"}
          Visibilidad consolidada para priorizar servicios, alertas y actividad
          reciente sin perder el contexto de cada organización.
        {:else if audience === "operator"}
          Seguimiento moderado de servicios, ejecuciones y acciones pendientes
          dentro del alcance asignado.
        {:else if audience === "partner"}
          Una vista clara de los clientes autorizados, las activaciones
          pendientes y los resultados disponibles.
        {:else}
          Servicios contratados, resultados recientes y acciones que requieren
          atención en lenguaje operativo.
        {/if}
      </p>
    </div>
    <Badge
      variant="info"
      class="h-auto w-fit rounded-full px-3 py-2 text-xs font-bold uppercase tracking-[0.15em]"
    >
      Mock funcional
    </Badge>
  </div>

  <div class="mt-7 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
    {#each cards as [label, value, description]}
      <article
        class="rounded-2xl border border-[#e0e8ea] bg-white p-5 shadow-[0_18px_45px_-42px_rgba(16,45,79,0.7)]"
      >
        <p class="text-sm font-bold uppercase tracking-[0.15em] text-[#78909f]">
          {label}
        </p>
        <p class="mt-4 text-3xl font-bold tracking-[-0.06em] text-[#173b5b]">
          {value}
        </p>
        <p class="mt-2 text-sm leading-5 text-[#82939d]">{description}</p>
      </article>
    {/each}
  </div>

  <div class="mt-6 grid gap-5 xl:grid-cols-[1.45fr_0.85fr]">
    <section
      class="rounded-3xl border border-[#e0e8ea] bg-white p-5 shadow-[0_24px_60px_-52px_rgba(16,45,79,0.65)] sm:p-6"
    >
      <div class="flex items-center justify-between gap-3">
        <div>
          <p
            class="text-sm font-bold uppercase tracking-[0.17em] text-[#168b88]"
          >
            Servicios
          </p>
          <h2
            class="mt-1.5 text-3xl font-bold tracking-[-0.035em] text-[#173b5b]"
          >
            {audience === "owner"
              ? "Prestaciones destacadas de la red"
              : audience === "operator"
                ? "Servicios asignados"
                : "Servicios del contexto activo"}
          </h2>
        </div>
        <a
          class="text-sm font-bold text-[#168b88] hover:text-[#102d4f]"
          href={buildConsoleRoute(
            consoleContext.activeWorkspace.id,
            "services",
            consoleContext.activeProfile,
          )}
        >
          Ver servicios
        </a>
      </div>

      <div class="mt-5 space-y-3">
        {#each audience === "owner" ? visibleServices.slice(0, 4) : context.services.slice(0, 4) as service}
          <article class="rounded-2xl border border-[#e8eef0] bg-[#fbfcfb] p-4">
            <div
              class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between"
            >
              <div>
                <p class="text-lg font-bold text-[#284c67]">{service.name}</p>
                <p class="mt-1 text-base leading-5 text-[#7c909b]">
                  {service.description}
                </p>
              </div>
              <StatusBadge status={service.health} />
            </div>
            <div
              class="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-sm font-semibold text-[#78909f]"
            >
              <span>{service.packageName}</span>
              <span>Próximo paso: {service.nextStep}</span>
            </div>
          </article>
        {/each}
      </div>
    </section>

    <section
      class="rounded-3xl border border-[#e0e8ea] bg-white p-5 shadow-[0_24px_60px_-52px_rgba(16,45,79,0.65)] sm:p-6"
    >
      <p class="text-sm font-bold uppercase tracking-[0.17em] text-[#168b88]">
        Atención requerida
      </p>
      <h2 class="mt-2 text-3xl font-bold tracking-[-0.035em]">
        Prioridades visibles
      </h2>
      <div class="mt-5 space-y-3">
        {#each (audience === "client" ? context.alerts : visibleAlerts).slice(0, 4) as alert}
          <article class="rounded-2xl border border-[#e8eef0] bg-[#fbfcfb] p-4">
            <div class="flex items-center justify-between gap-3">
              <StatusBadge status={alert.severity} />
              <span class="text-sm text-[#7c909b]"
                >{formatDateTime(alert.createdAt, consoleContext.locale)}</span
              >
            </div>
            <p class="mt-2 text-base font-semibold leading-5 text-[#284c67]">
              {alert.title}
            </p>
          </article>
        {:else}
          <p
            class="rounded-2xl border border-white/10 bg-white/[0.07] p-4 text-base leading-5 text-white/70"
          >
            No hay alertas abiertas en el contexto activo.
          </p>
        {/each}
      </div>
    </section>
  </div>

  <div class="mt-6 grid gap-5 xl:grid-cols-2">
    <section class="rounded-3xl border border-[#e0e8ea] bg-white p-5 sm:p-6">
      <p class="text-sm font-bold uppercase tracking-[0.17em] text-[#168b88]">
        {audience === "owner" || audience === "operator"
          ? "Actividad técnica"
          : "Próximos pasos"}
      </p>
      <h2 class="mt-1.5 text-3xl font-bold tracking-[-0.035em] text-[#173b5b]">
        {audience === "owner" || audience === "operator"
          ? "Ejecuciones recientes"
          : "Tareas pendientes"}
      </h2>
      <div class="mt-5 space-y-2">
        {#if audience === "owner" || audience === "operator"}
          {#each visibleRuns.slice(0, 4) as run}
            <article
              class="flex items-center justify-between gap-3 rounded-xl border border-[#edf1f2] px-3 py-3"
            >
              <div>
                <p class="text-sm font-bold text-[#36566f]">{run.workerName}</p>
                <p class="mt-1 text-sm text-[#8a9ba6]">{run.summary}</p>
              </div>
              <StatusBadge status={run.status} />
            </article>
          {/each}
        {:else}
          {#each context.tasks
            .filter(({ status }) => status !== "completed")
            .slice(0, 4) as task}
            <article
              class="flex items-center justify-between gap-3 rounded-xl border border-[#edf1f2] px-3 py-3"
            >
              <div>
                <p class="text-base font-bold text-[#36566f]">{task.title}</p>
                <p class="mt-1 text-base text-[#8a9ba6]">
                  Vence: {formatDate(task.dueDate, consoleContext.locale)}
                </p>
              </div>
              <StatusBadge status={task.status} />
            </article>
          {:else}
            <p class="rounded-xl bg-[#f4f8f8] p-4 text-base text-[#718793]">
              No hay tareas pendientes en este workspace.
            </p>
          {/each}
        {/if}
      </div>
    </section>

    <section class="rounded-3xl border border-[#e0e8ea] bg-white p-5 sm:p-6">
      <p class="text-sm font-bold uppercase tracking-[0.17em] text-[#168b88]">
        Resultados
      </p>
      <h2 class="mt-1.5 text-3xl font-bold tracking-[-0.035em] text-[#173b5b]">
        Reportes recientes
      </h2>
      <div class="mt-5 space-y-2">
        {#each (audience === "client" ? context.reports : visibleReports).slice(0, 4) as report}
          <article
            class="flex items-center justify-between gap-3 rounded-xl border border-[#edf1f2] px-3 py-3"
          >
            <div>
              <p class="text-lg font-bold text-[#36566f]">{report.title}</p>
              <p class="mt-1 text-lg text-[#8a9ba6]">{report.period}</p>
            </div>
            <StatusBadge status={report.status} />
          </article>
        {:else}
          <p class="rounded-xl bg-[#f4f8f8] p-4 text-base text-[#718793]">
            Todavía no hay reportes disponibles.
          </p>
        {/each}
      </div>
    </section>
  </div>
</section>
