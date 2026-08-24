<script lang="ts">
  import { flowDateTime } from "../../../lib/t360/flow/format";
  import type {
    ExecutiveCaseListItem,
    ExecutiveCaseListPagination,
  } from "../../../lib/t360/flow/types";
  import FlowStatusBadge from "./FlowStatusBadge.svelte";

  type FilterId = "all" | "open" | "breached" | "escalated" | "approval" | "resolved";

  let {
    cases,
    selectedId,
    pagination = { page: 1, page_size: 20, total: 0, has_next: false },
    loading = false,
    localFiltering = false,
    sectors = [],
    onSelect = () => undefined,
    onSearchChange = () => undefined,
    onFilterChange = () => undefined,
    onPageChange = () => undefined,
    onSectorChange = () => undefined,
  }: {
    cases: ExecutiveCaseListItem[];
    selectedId: string | null;
    pagination?: ExecutiveCaseListPagination;
    loading?: boolean;
    localFiltering?: boolean;
    sectors?: { sector_id: string; display_name: string }[];
    onSelect?: (requestId: string) => void;
    onSearchChange?: (query: string) => void;
    onFilterChange?: (filter: FilterId) => void;
    onPageChange?: (page: number) => void;
    onSectorChange?: (sectorId: string | undefined) => void;
  } = $props();

  let query = $state("");
  let filter = $state<FilterId>("all");
  let debounceTimer: ReturnType<typeof setTimeout> | null = null;

  const filters: { id: FilterId; label: string }[] = [
    { id: "all", label: "Todos" },
    { id: "open", label: "Activos" },
    { id: "breached", label: "SLA vencidos" },
    { id: "escalated", label: "Escalados" },
    { id: "approval", label: "Pendientes" },
    { id: "resolved", label: "Resueltos" },
  ];

  function matchesFilter(item: ExecutiveCaseListItem): boolean {
    switch (filter) {
      case "open":
        return item.status_fact === "open";
      case "breached":
        return item.has_breached_sla;
      case "escalated":
        return item.escalation_count > 0;
      case "approval":
        return item.status_fact === "pending_approval";
      case "resolved":
        return item.status_fact === "closed";
      default:
        return true;
    }
  }

  const visibleCases = $derived.by(() => {
    if (!localFiltering) return cases;
    const normalized = query.trim().toLowerCase();
    return cases.filter((item) => {
      if (!matchesFilter(item)) return false;
      if (!normalized) return true;
      return [
        item.request_id,
        item.conversation_id,
        item.request.description,
        item.request.sector_name,
        item.request.category,
        item.request.location,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(normalized);
    });
  });

  function handleQueryInput(event: Event) {
    query = (event.currentTarget as HTMLInputElement).value;
    if (localFiltering) return;
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => onSearchChange(query.trim()), 300);
  }

  function selectFilter(next: FilterId) {
    filter = next;
    if (!localFiltering) onFilterChange(next);
  }

  function selectCase(requestId: string) {
    if (debounceTimer) {
      clearTimeout(debounceTimer);
      debounceTimer = null;
    }
    onSelect(requestId);
  }

  function selectSector(event: Event) {
    const value = (event.currentTarget as HTMLSelectElement).value;
    onSectorChange(value || undefined);
  }

  function shortId(requestId: string): string {
    return `#${requestId.slice(0, 8)}`;
  }

  function levelLabel(item: ExecutiveCaseListItem): string {
    return item.current_level && item.current_level > 0
      ? `Nivel ${item.current_level}`
      : "Sin nivel asignado";
  }

  const count = $derived(localFiltering ? visibleCases.length : pagination.total);
</script>

<div class="space-y-4">
  <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
    <div class="relative w-full sm:max-w-xs">
      <label class="sr-only" for="flow-case-search">Buscar caso</label>
      <input
        id="flow-case-search"
        type="search"
        placeholder="Buscar por descripción, sector o referencia…"
        value={query}
        disabled={loading}
        oninput={handleQueryInput}
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
          onclick={() => selectFilter(item.id)}
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

  {#if !localFiltering && sectors.length > 0}
    <label class="flex w-full max-w-xs items-center gap-2 text-xs font-bold text-[#587184]" for="flow-case-sector">
      <span>Sector</span>
      <select
        id="flow-case-sector"
        disabled={loading}
        onchange={selectSector}
        class="min-w-0 flex-1 rounded-xl border border-card-border bg-white px-3 py-2 text-xs font-semibold text-[#31536b] focus:outline-2 focus:outline-offset-1 focus:outline-[#168b88] disabled:opacity-60"
      >
        <option value="">Todos los sectores</option>
        {#each sectors as sector (sector.sector_id)}
          <option value={sector.sector_id}>{sector.display_name}</option>
        {/each}
      </select>
    </label>
  {/if}

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
  {:else if visibleCases.length === 0}
    <div class="rounded-2xl border border-dashed border-[#d7e3e5] bg-white/70 p-6 text-center">
      <p class="text-sm font-bold text-[#31536b]">No encontramos casos con estos filtros</p>
      <p class="mt-1 text-xs text-[#78909f]">Ajustá la búsqueda o el filtro para consultar otros casos.</p>
    </div>
  {:else}
    <ul class="divide-y divide-card-border-mini overflow-hidden rounded-2xl border border-card-border bg-card-bg">
      {#each visibleCases as item (item.request_id)}
        <li>
          <button
            type="button"
            onclick={() => selectCase(item.request_id)}
            aria-pressed={selectedId === item.request_id}
            class={`flex w-full items-center gap-4 px-4 py-4 text-start transition ${
              selectedId === item.request_id ? "bg-[#e4f5f3]/60" : "hover:bg-base-200/60"
            }`}
          >
            <span
              class={`mt-1 grid size-2.5 shrink-0 place-items-center rounded-full ${
                item.status_fact === "closed"
                  ? "bg-[#30ae69]"
                  : item.has_breached_sla
                    ? "bg-[#d23a2a]"
                    : item.status_fact === "pending_approval"
                      ? "bg-[#d7ba12]"
                      : "bg-[#2ca2da]"
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
                {#if item.escalation_count > 0} · Escalado{/if}
                {#if item.has_breached_sla} · SLA vencido{/if}
              </span>
            </span>
            <span class="hidden shrink-0 text-end sm:block">
              <span class="block max-w-48 truncate text-xs font-semibold text-[#587184]">{item.current_destination ?? "—"}</span>
              <span class="mt-0.5 block text-[0.62rem] text-[#91a2ad]">{flowDateTime(item.updated_at)}</span>
            </span>
          </button>
        </li>
      {/each}
    </ul>
  {/if}

  <div class="flex flex-wrap items-center justify-between gap-3" aria-live="polite">
    <p class="text-xs text-[#91a2ad]">{localFiltering ? `${visibleCases.length} de ${cases.length}` : `${count} casos`}</p>
    {#if !localFiltering && pagination.total > 0}
      <nav class="flex items-center gap-2" aria-label="Paginación de casos">
        <button
          type="button"
          disabled={loading || pagination.page <= 1}
          onclick={() => onPageChange(pagination.page - 1)}
          class="rounded-full border border-card-border bg-white px-3 py-1.5 text-xs font-bold text-[#587184] disabled:cursor-not-allowed disabled:opacity-40"
        >
          Anterior
        </button>
        <span class="text-xs font-semibold text-[#78909f]">Página {pagination.page}</span>
        <button
          type="button"
          disabled={loading || !pagination.has_next}
          onclick={() => onPageChange(pagination.page + 1)}
          class="rounded-full border border-card-border bg-white px-3 py-1.5 text-xs font-bold text-[#587184] disabled:cursor-not-allowed disabled:opacity-40"
        >
          Siguiente
        </button>
      </nav>
    {/if}
  </div>
</div>
