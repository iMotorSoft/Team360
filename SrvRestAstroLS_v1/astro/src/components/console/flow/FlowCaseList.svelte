<script lang="ts">
  import { flowDateTime } from "../../../lib/t360/flow/format";
  import { caseAttention, currentLevel, hasBreachedSla, hasPendingApproval, isResolved } from "../../../lib/t360/flow/types";
  import type { ExecutiveView } from "../../../lib/t360/flow/types";
  import FlowStatusBadge from "./FlowStatusBadge.svelte";

  let {
    cases,
    selectedId,
    loading = false,
    onSelect = () => undefined,
  }: {
    cases: ExecutiveView[];
    selectedId: string | null;
    loading?: boolean;
    onSelect?: (requestId: string) => void;
  } = $props();

  type FilterId = "all" | "open" | "breached" | "escalated" | "approval" | "resolved";

  let query = $state("");
  let filter = $state<FilterId>("all");

  const filters: { id: FilterId; label: string }[] = [
    { id: "all", label: "Todos" },
    { id: "open", label: "Activos" },
    { id: "breached", label: "SLA vencidos" },
    { id: "escalated", label: "Escalados" },
    { id: "approval", label: "Pendientes" },
    { id: "resolved", label: "Resueltos" },
  ];

  function matchesFilter(item: ExecutiveView): boolean {
    switch (filter) {
      case "open":
        return item.status_fact === "open";
      case "breached":
        return hasBreachedSla(item);
      case "escalated":
        return item.escalations.length > 0;
      case "approval":
        return hasPendingApproval(item);
      case "resolved":
        return isResolved(item);
      default:
        return true;
    }
  }

  const filtered = $derived.by(() => {
    const q = query.trim().toLowerCase();
    return cases.filter((item) => {
      if (!matchesFilter(item)) return false;
      if (!q) return true;
      const haystack = [
        item.request.description,
        item.request.sector_name,
        item.request.category,
        item.request.location,
        item.request_id,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return haystack.includes(q);
    });
  });

  function shortId(requestId: string): string {
    return `#${requestId.slice(0, 8)}`;
  }

  function levelLabel(item: ExecutiveView): string {
    const level = currentLevel(item);
    return level > 0 ? `Nivel ${level}` : "Sin nivel asignado";
  }
</script>

<div class="space-y-4">
  <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
    <div class="relative w-full sm:max-w-xs">
      <label class="sr-only" for="flow-case-search">Buscar caso</label>
      <input
        id="flow-case-search"
        type="search"
        placeholder="Buscar por descripción, sector o referencia…"
        bind:value={query}
        disabled={loading}
        class="w-full rounded-xl border border-card-border bg-white px-3 py-2.5 text-sm text-[#31536b] placeholder:text-[#91a2ad] focus:outline-2 focus:outline-offset-1 focus:outline-[#168b88] disabled:opacity-60"
      />
    </div>
    <div class="flex flex-wrap items-center gap-1.5" role="tablist" aria-label="Filtrar casos">
      {#each filters as item (item.id)}
        <button
          type="button"
          role="tab"
          aria-selected={filter === item.id}
          disabled={loading}
          onclick={() => (filter = item.id)}
          class={`rounded-full border px-3 py-1.5 text-xs font-bold transition disabled:opacity-60 ${
            filter === item.id
              ? "border-[#b7dfdc] bg-[#e4f5f3] text-[#126d6b]"
              : "border-card-border bg-white text-[#587184] hover:bg-base-200"
          }`}
        >
          {item.label}
        </button>
      {/each}
    </div>
  </div>

  {#if loading}
    <div class="space-y-px overflow-hidden rounded-2xl border border-card-border bg-card-bg" aria-hidden="true">
      {#each Array(5) as _, i (i)}
        <div class="animate-pulse px-4 py-4">
          <div class="h-3 w-40 rounded bg-base-200"></div>
          <div class="mt-2 h-3 w-72 rounded bg-base-200"></div>
          <div class="mt-2 h-2.5 w-56 rounded bg-base-200"></div>
        </div>
      {/each}
    </div>
  {:else if filtered.length === 0}
    <div class="rounded-2xl border border-dashed border-[#d7e3e5] bg-white/70 p-6 text-center">
      <p class="text-sm font-bold text-[#31536b]">No hay casos que coincidan</p>
      <p class="mt-1 text-xs text-[#78909f]">Ajustá la búsqueda o el filtro para ver otros casos.</p>
    </div>
  {:else}
    <ul class="divide-y divide-card-border-mini overflow-hidden rounded-2xl border border-card-border bg-card-bg">
      {#each filtered as item (item.request_id)}
        {@const attention = caseAttention(item)}
        {@const level = currentLevel(item)}
        <li>
          <button
            type="button"
            onclick={() => onSelect(item.request_id)}
            aria-pressed={selectedId === item.request_id}
            class={`flex w-full items-center gap-4 px-4 py-4 text-start transition ${
              selectedId === item.request_id ? "bg-[#e4f5f3]/60" : "hover:bg-base-200/60"
            }`}
          >
            <span
              class={`mt-1 grid size-2.5 shrink-0 place-items-center rounded-full ${
                attention === "critical" ? "bg-[#d23a2a]" : attention === "warning" ? "bg-[#d7ba12]" : attention === "resolved" ? "bg-[#30ae69]" : "bg-[#2ca2da]"
              }`}
              aria-hidden="true"
            ></span>
            <span class="min-w-0 flex-1">
              <span class="flex flex-wrap items-center gap-2">
                <span class="font-mono text-xs font-bold text-[#168b88]">{shortId(item.request_id)}</span>
                <span class="text-xs text-[#78909f]">{item.request.sector_name ?? "Sector"}</span>
                <FlowStatusBadge statusFact={item.status_fact} dataSource={item.data_source} />
              </span>
              <span class="mt-1 block truncate text-sm font-semibold leading-5 text-[#31536b]">{item.request.description}</span>
              <span class="mt-0.5 block truncate text-xs text-[#78909f]">
                {levelLabel(item)} · {item.request.location ?? "Ubicación no informada"}
                {#if item.escalations.length > 0} · Escalado{/if}
                {#if hasBreachedSla(item)} · SLA vencido{/if}
              </span>
            </span>
            <span class="hidden shrink-0 text-end sm:block">
              <span class="block text-xs font-semibold text-[#587184]">{item.routing_history.at(-1)?.destination ?? "—"}</span>
              <span class="mt-0.5 block text-[0.62rem] text-[#91a2ad]">{flowDateTime(item.timeline.at(-1)?.timestamp ?? null)}</span>
            </span>
          </button>
        </li>
      {/each}
    </ul>
  {/if}

  <p class="text-xs text-[#91a2ad]" aria-live="polite">
    {filtered.length} de {cases.length} casos
  </p>
</div>
