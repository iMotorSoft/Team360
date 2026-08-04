<script lang="ts">
  import { EmptyState } from "../ui";
  import { getMockWorkspaceContext } from "../../lib/mock";
  import { consoleContext } from "../../stores/consoleContext.svelte";
  import ConsoleIcon from "./ConsoleIcon.svelte";
  import AlertCard from "./alerts/AlertCard.svelte";

  let open = $state(false);
  let trigger = $state<HTMLButtonElement>();
  let panel = $state<HTMLDivElement>();
  const alerts = $derived(getMockWorkspaceContext(consoleContext.activeWorkspace.id).alerts.filter(({ status }) => status !== "resolved"));

  function close(returnFocus = false) {
    open = false;
    if (returnFocus) queueMicrotask(() => trigger?.focus());
  }

  function handleKeydown(event: KeyboardEvent) {
    if (!open || event.key !== "Escape") return;
    event.preventDefault();
    close(true);
  }

  function handlePointerdown(event: PointerEvent) {
    if (!open || !(event.target instanceof Node)) return;
    if (!panel?.contains(event.target) && !trigger?.contains(event.target)) close();
  }
</script>

<svelte:window onkeydown={handleKeydown} onpointerdown={handlePointerdown} />

<div class="relative">
  <button
    aria-expanded={open}
    aria-controls="console-notifications-panel"
    aria-haspopup="true"
    aria-label="Abrir notificaciones"
    bind:this={trigger}
    class="relative grid size-11 cursor-pointer place-items-center rounded-full text-[#526d81] transition hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#168b88]"
    onclick={() => (open = !open)}
    type="button"
  >
    <ConsoleIcon class="size-7" name="alert" />
    {#if consoleContext.notificationSummary.activeWorkspaceAlerts > 0}
      <span class="absolute -top-1 -end-1 grid size-4 place-items-center rounded-full bg-[#e86852] text-[0.58rem] font-bold text-white">
        {consoleContext.notificationSummary.activeWorkspaceAlerts}
      </span>
    {/if}
  </button>

  {#if open}
    <div
      aria-labelledby="console-notifications-title"
      bind:this={panel}
      class="absolute end-0 z-50 mt-3 w-[min(24rem,calc(100vw-2rem))] overflow-hidden rounded-2xl border border-[#dfe8ea] bg-white shadow-[0_24px_70px_-28px_rgba(16,45,79,0.35)]"
      id="console-notifications-panel"
      role="region"
    >
      <div class="border-b border-[#edf1f2] px-4 py-3">
        <p class="text-xl font-semibold text-[#173b5b]" id="console-notifications-title">Notificaciones</p>
        <p class="mt-1 text-base text-[#78909f]">Contexto: {consoleContext.activeWorkspace.name}</p>
      </div>
      <div class="max-h-80 space-y-1 overflow-y-auto p-3">
        {#each alerts as alert}
          <AlertCard {alert} compact showStatus={false} class="border-transparent shadow-none transition hover:bg-[#f4f8f8]" />
        {:else}
          <EmptyState
            compact
            title="Sin alertas abiertas"
            description="Este workspace no tiene notificaciones pendientes."
          />
        {/each}
      </div>
    </div>
  {/if}
</div>
