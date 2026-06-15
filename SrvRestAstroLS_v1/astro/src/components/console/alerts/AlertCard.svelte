<script lang="ts">
  import { Card, StatusBadge } from "../../ui";
  import { formatDate, formatDateTime } from "../../../lib/formatters";
  import { consoleContext } from "../../../stores/consoleContext.svelte";
  import { services, workspaces } from "../../../lib/mock";

  // ── Tipos soportados ────────────────────────────────────────────────────────

  interface AlertData {
    kind?: "alert";
    id: string;
    title: string;
    severity: string;
    createdAt: string | Date;
    status: string;
    serviceId: string;
    workspaceId: string;
    suggestedAction?: string;
  }

  interface TaskData {
    kind: "task";
    id: string;
    title: string;
    priority: string;
    dueDate: string;
    status: string;
    serviceId: string;
    workspaceId: string;
  }

  interface ReportData {
    kind: "report";
    id: string;
    title: string;
    status: string;
    generatedAt: string | null;
    period: string;
    serviceId: string;
    workspaceId: string;
  }

  type ItemData = AlertData | TaskData | ReportData;

  // ── Props ───────────────────────────────────────────────────────────────────

  let {
    alert: item,
    cardVariant = "flat",
    layout = "default",
    noCard = false,
    showDate = true,
    showStatus = false,
    showService = false,
    showWorkspace = false,
    showAction = false,
    class: className = "",
  }: {
    alert: ItemData;
    cardVariant?:
      | "default"
      | "light"
      | "flat"
      | "flat-large"
      | "large"
      | "mini";
    /** "default": diseño apilado con badge de severity encima.
     *  "compact": horizontal, título + subtítulo a la izquierda, status badge a la derecha. */
    layout?: "default" | "compact";
    noCard?: boolean;
    showDate?: boolean;
    showStatus?: boolean;
    showService?: boolean;
    showWorkspace?: boolean;
    showAction?: boolean;
    class?: string;
  } = $props();

  // ── Derivaciones según tipo ─────────────────────────────────────────────────

  /** Badge principal (izquierda): severity para alertas, priority para tasks, type label para reports */
  const badgeStatus = $derived(
    item.kind === "task"
      ? item.priority
      : item.kind === "report"
        ? item.status
        : (item as AlertData).severity,
  );

  /** Texto secundario debajo del título */
  const subtitle = $derived.by(() => {
    if (item.kind === "task") {
      return `Vence: ${formatDate(item.dueDate, consoleContext.locale)}`;
    }
    if (item.kind === "report") {
      return item.period;
    }
    return null; // alertas no usan subtitle fijo
  });

  /** Fecha que se muestra a la derecha (solo alertas y reports con generatedAt) */
  const dateLabel = $derived.by(() => {
    if (item.kind === "task") return null;
    if (item.kind === "report")
      return formatDateTime(item.generatedAt, consoleContext.locale);
    return formatDateTime((item as AlertData).createdAt, consoleContext.locale);
  });

  /** Acción sugerida (solo alertas) */
  const suggestedAction = $derived(
    item.kind === undefined || item.kind === "alert"
      ? (item as AlertData).suggestedAction
      : undefined,
  );

  // ── Mocks ───────────────────────────────────────────────────────────────────

  const serviceName = $derived(
    services.find(({ id }) => id === item.serviceId)?.name ??
      "Servicio no disponible",
  );

  const workspaceName = $derived(
    workspaces.find(({ id }) => id === item.workspaceId)?.name ??
      "Workspace no disponible",
  );
</script>

{#snippet defaultContent()}
  <div
    class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between"
  >
    <div>
      <div class="flex flex-wrap gap-2">
        <StatusBadge status={badgeStatus} />
        {#if showStatus}
          <StatusBadge status={item.status} />
        {/if}
      </div>

      <h3 class="mt-3 text-base font-semibold leading-5 text-console-subtitle">
        {item.title}
      </h3>

      {#if subtitle}
        <p class="mt-1 text-base leading-5 text-console-muted">{subtitle}</p>
      {/if}

      {#if showService || showWorkspace}
        <p class="mt-2 text-base leading-5 text-console-muted">
          {#if showService && showWorkspace}
            {serviceName} · {workspaceName}
          {:else if showService}
            Servicio: {serviceName}
          {:else if showWorkspace}
            Workspace: {workspaceName}
          {/if}
        </p>
      {/if}
    </div>

    {#if showDate && dateLabel}
      <span class="text-sm text-console-muted whitespace-nowrap sm:mt-1">
        {dateLabel}
      </span>
    {/if}
  </div>

  {#if showAction && suggestedAction}
    <p
      class="mt-4 rounded-xl bg-[#f8fbfa] px-3 py-2.5 text-base font-semibold leading-5 text-console-subtitle"
    >
      Acción sugerida: {suggestedAction}
    </p>
  {/if}
{/snippet}

{#snippet compactContent()}
  <div>
    <p class="text-lg font-bold text-console-subtitle">{item.title}</p>
    {#if subtitle}
      <p class="mt-1 text-base text-console-muted">{subtitle}</p>
    {/if}
    {#if showDate && dateLabel}
      <p class="mt-1 text-sm text-console-muted">{dateLabel}</p>
    {/if}
    {#if showService || showWorkspace}
      <p class="mt-1 text-sm text-console-muted">
        {#if showService && showWorkspace}
          {serviceName} · {workspaceName}
        {:else if showService}
          {serviceName}
        {:else if showWorkspace}
          {workspaceName}
        {/if}
      </p>
    {/if}
  </div>
  <StatusBadge status={item.status} />
{/snippet}

{#if noCard}
  <article class={`rounded-xl p-3 transition hover:bg-base-100 ${className}`}>
    {#if layout === "compact"}
      <div class="flex items-center justify-between gap-3">
        {@render compactContent()}
      </div>
    {:else}
      {@render defaultContent()}
    {/if}
  </article>
{:else if layout === "compact"}
  <Card
    variant={cardVariant}
    class="flex items-center justify-between gap-3 px-3 py-3 {className}"
  >
    {@render compactContent()}
  </Card>
{:else}
  <Card variant={cardVariant} class={className}>
    {@render defaultContent()}
  </Card>
{/if}
