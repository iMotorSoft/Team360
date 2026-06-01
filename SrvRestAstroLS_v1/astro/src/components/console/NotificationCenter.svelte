<script lang="ts">
  import { StatusBadge } from "../ui";
  import { formatDateTime } from "../../lib/formatters";
  import { getMockWorkspaceContext } from "../../lib/mock";
  import { consoleContext } from "../../stores/consoleContext.svelte";
  import ConsoleIcon from "./ConsoleIcon.svelte";

  let open = $state(false);
  const alerts = $derived(getMockWorkspaceContext(consoleContext.activeWorkspace.id).alerts.filter(({ status }) => status !== "resolved"));
</script>

<div class="relative">
  <button
    aria-expanded={open}
    aria-label="Abrir notificaciones"
    class="relative grid size-10 place-items-center rounded-xl border border-[#e0e8eb] bg-white text-[#526d81] transition hover:border-[#badbd9] hover:text-[#167f7c]"
    onclick={() => (open = !open)}
    type="button"
  >
    <ConsoleIcon name="alert" />
    {#if consoleContext.notificationSummary.activeWorkspaceAlerts > 0}
      <span class="absolute -right-1 -top-1 grid size-4 place-items-center rounded-full bg-[#e86852] text-[0.58rem] font-bold text-white">
        {consoleContext.notificationSummary.activeWorkspaceAlerts}
      </span>
    {/if}
  </button>

  {#if open}
    <div class="absolute end-0 z-50 mt-3 w-[min(22rem,calc(100vw-2rem))] overflow-hidden rounded-2xl border border-[#dfe8ea] bg-white shadow-[0_24px_70px_-28px_rgba(16,45,79,0.35)]">
      <div class="border-b border-[#edf1f2] px-4 py-3">
        <p class="text-sm font-bold text-[#173b5b]">Notificaciones</p>
        <p class="mt-1 text-xs text-[#78909f]">Contexto: {consoleContext.activeWorkspace.name}</p>
      </div>
      <div class="max-h-80 space-y-1 overflow-y-auto p-2">
        {#each alerts as alert}
          <article class="rounded-xl px-3 py-3 transition hover:bg-[#f4f8f8]">
            <div class="flex items-center justify-between gap-3">
              <StatusBadge status={alert.severity} />
              <span class="text-[0.68rem] text-[#8a9ba6]">{formatDateTime(alert.createdAt, consoleContext.locale)}</span>
            </div>
            <p class="mt-2 text-xs font-semibold leading-5 text-[#36566f]">{alert.title}</p>
          </article>
        {:else}
          <p class="px-3 py-6 text-center text-xs text-[#78909f]">Sin alertas abiertas en este workspace.</p>
        {/each}
      </div>
    </div>
  {/if}
</div>
