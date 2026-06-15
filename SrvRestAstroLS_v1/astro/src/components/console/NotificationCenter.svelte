<script lang="ts">
  import { StatusBadge } from "../ui";
  import AlertCard from "./alerts/AlertCard.svelte";
  import { formatDateTime } from "../../lib/formatters";
  import { getMockWorkspaceContext } from "../../lib/mock";
  import { consoleContext } from "../../stores/consoleContext.svelte";
  import ConsoleIcon from "./ConsoleIcon.svelte";

  let open = $state(false);
  const alerts = $derived(
    getMockWorkspaceContext(consoleContext.activeWorkspace.id).alerts.filter(
      ({ status }) => status !== "resolved",
    ),
  );
</script>

<div class="relative">
  <button
    aria-expanded={open}
    aria-label="Abrir notificaciones"
    class="text-[#526d81] cursor-pointer size-11 grid place-items-center
    rounded-full hover:bg-slate-100 transition"
    onclick={() => (open = !open)}
    type="button"
  >
    <ConsoleIcon name="alert" class="size-7" />
    {#if consoleContext.notificationSummary.activeWorkspaceAlerts > 0}
      <span
        class="absolute -right-1 -top-1 grid size-4 place-items-center rounded-full bg-[#e86852] text-[0.58rem] font-bold text-white"
      >
        {consoleContext.notificationSummary.activeWorkspaceAlerts}
      </span>
    {/if}
  </button>

  {#if open}
    <div
      class="absolute end-0 z-50 mt-3 w-[min(24rem,calc(100vw-2rem))]
      overflow-hidden rounded-2xl border border-[#dfe8ea]
      bg-white shadow-[0_24px_70px_-28px_rgba(16,45,79,0.35)]"
    >
      <div class="border-b border-[#edf1f2] px-4 py-3">
        <p class="text-xl font-semibold text-[#173b5b]">Notificaciones</p>
        <p class="mt-1 text-base text-[#78909f]">
          Contexto: {consoleContext.activeWorkspace.name}
        </p>
      </div>
      <div class="max-h-80 space-y-1 overflow-y-auto p-3">
        {#each alerts as alert}
          <AlertCard {alert} noCard={true} />
        {:else}
          <p class="px-3 py-6 text-center text-lg text-[#78909f]">
            Sin alertas abiertas en este workspace.
          </p>
        {/each}
      </div>
    </div>
  {/if}
</div>
