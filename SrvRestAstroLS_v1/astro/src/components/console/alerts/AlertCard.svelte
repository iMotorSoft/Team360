<script lang="ts">
  import { StatusBadge } from "../../ui";
  import { formatDateTime } from "../../../lib/formatters";
  import type { Alert } from "../../../lib/mock";
  import { consoleContext } from "../../../stores/consoleContext.svelte";

  let {
    alert,
    contextLabel,
    compact = false,
    showAction = false,
    showStatus = true,
    class: className = "",
  }: {
    alert: Alert;
    contextLabel?: string;
    compact?: boolean;
    showAction?: boolean;
    showStatus?: boolean;
    class?: string;
  } = $props();
</script>

<article class={`rounded-2xl border border-card-border bg-card-bg ${compact ? "p-3" : "p-5"} ${className}`}>
  <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
    <div class="min-w-0">
      <div class="flex flex-wrap gap-2">
        <StatusBadge status={alert.severity} />
        {#if showStatus}<StatusBadge status={alert.status} />{/if}
      </div>
      <h3 class={`${compact ? "mt-2" : "mt-3"} text-sm font-bold leading-5 text-console-subtitle`}>{alert.title}</h3>
      {#if contextLabel}
        <p class="mt-2 text-xs leading-5 text-console-muted">{contextLabel}</p>
      {/if}
    </div>
    <time class="shrink-0 text-xs text-[#91a2ad]" datetime={alert.createdAt}>
      {formatDateTime(alert.createdAt, consoleContext.locale)}
    </time>
  </div>
  {#if showAction}
    <p class="mt-4 rounded-xl bg-[#f4f8f8] px-3 py-2.5 text-xs font-semibold leading-5 text-[#668092]">
      Acción sugerida: {alert.suggestedAction}
    </p>
  {/if}
</article>
