<script lang="ts">
  import { onMount } from "svelte";
  import {
    fetchExecutiveCase,
    fetchExecutiveCaseList,
    type ExecutiveFetchError,
    type ExecutiveListFetchError,
  } from "../../../lib/api/flowExecutive";
  import { getFlowKpis, listFlowCases } from "../../../lib/mock/flow";
  import type {
    ExecutiveCaseListItem,
    ExecutiveCaseListPagination,
    ExecutiveCaseListSector,
    ExecutiveView,
  } from "../../../lib/t360/flow/types";
  import { currentAssignee, currentLevel } from "../../../lib/t360/flow/types";
  import FlowCaseDetail from "./FlowCaseDetail.svelte";
  import FlowCaseList from "./FlowCaseList.svelte";
  import FlowKpi from "./FlowKpi.svelte";

  type Mode = "loading" | "live" | "demo" | "auth_required" | "forbidden" | "error";
  type FilterId = "all" | "open" | "breached" | "escalated" | "approval" | "resolved";

  const DEFAULT_PAGINATION: ExecutiveCaseListPagination = {
    page: 1,
    page_size: 20,
    total: 0,
    has_next: false,
  };

  let cases: ExecutiveCaseListItem[] = $state([]);
  let demoViews: ExecutiveView[] = $state([]);
  let sectors: ExecutiveCaseListSector[] = $state([]);
  let pagination = $state<ExecutiveCaseListPagination>(DEFAULT_PAGINATION);
  let mode = $state<Mode>("loading");
  let listError = $state<ExecutiveListFetchError | null>(null);
  let selectedId = $state<string | null>(null);
  let detail = $state<ExecutiveView | null>(null);
  let detailLoading = $state(false);
  let detailError = $state<ExecutiveFetchError | null>(null);
  let listGen = $state(0);
  let detailGen = $state(0);

  let page = $state(1);
  let status = $state<string | undefined>(undefined);
  let sectorId = $state<string | undefined>(undefined);
  let search = $state("");
  let slaStatus = $state<string | undefined>(undefined);
  let escalated = $state<boolean | undefined>(undefined);

  const demoRequested = $derived(new URLSearchParams(window.location.search).has("demo"));
  const listLoading = $derived(mode === "loading");
  const selected = $derived(detail);
  const kpis = $derived(getFlowKpis(cases));

  function toListItem(view: ExecutiveView): ExecutiveCaseListItem {
    const assigned = view.routing_history
      .filter((row) => row.routing_status === "ASSIGNED")
      .sort((a, b) => b.level - a.level)[0];
    const currentSla = assigned
      ? view.sla.find((item) => item.routing_id === assigned.routing_id)
      : view.sla.at(-1);
    const updatedAt = view.timeline.at(-1)?.timestamp ?? view.request.confirmed_at ?? null;
    return {
      request_id: view.request_id,
      conversation_id: view.request.conversation_id,
      status: view.status,
      data_source: view.data_source,
      status_fact: view.status_fact,
      request: view.request,
      current_routing_id: assigned?.routing_id ?? null,
      current_level: currentLevel(view) || null,
      current_destination: currentAssignee(view),
      current_routing_status: assigned?.routing_status ?? null,
      current_work_status: assigned?.work_status ?? null,
      sla_status: currentSla?.status ?? null,
      sla_due_at: currentSla?.due_at ?? null,
      has_breached_sla: view.sla.some((item) => item.status === "BREACHED"),
      first_response_at: assigned?.first_response_at ?? null,
      resolved_at: view.result.resolved_at ?? null,
      escalation_count: view.escalations.length,
      updated_at: updatedAt,
    };
  }

  function demoItems(): ExecutiveCaseListItem[] {
    return demoViews.map(toListItem);
  }

  async function loadList() {
    const generation = ++listGen;
    mode = "loading";
    listError = null;
    selectedId = null;
    detail = null;
    detailError = null;

    if (demoRequested) {
      demoViews = listFlowCases();
      cases = demoItems();
      pagination = { page: 1, page_size: cases.length, total: cases.length, has_next: false };
      sectors = [];
      mode = "demo";
      return;
    }

    const result = await fetchExecutiveCaseList({
      page,
      pageSize: 20,
      status,
      sectorId,
      search: search || undefined,
      slaStatus,
      escalated,
    });
    if (generation !== listGen) return;
    if (result.error || !result.data) {
      listError = result.error ?? "unavailable";
      mode = result.error === "unauthorized" ? "auth_required" : result.error === "forbidden" ? "forbidden" : "error";
      return;
    }
    cases = result.data.items;
    pagination = result.data.pagination;
    sectors = result.data.sectors;
    mode = "live";
  }

  onMount(() => {
    void loadList();
  });

  function filterChanged(next: FilterId) {
    status = next === "open" ? "open" : next === "approval" ? "pending_approval" : next === "resolved" ? "resolved" : undefined;
    slaStatus = next === "breached" ? "BREACHED" : undefined;
    escalated = next === "escalated" ? true : undefined;
    page = 1;
    void loadList();
  }

  function searchChanged(next: string) {
    search = next;
    page = 1;
    void loadList();
  }

  function sectorChanged(next: string | undefined) {
    sectorId = next;
    page = 1;
    void loadList();
  }

  function pageChanged(next: number) {
    page = next;
    void loadList();
  }

  async function selectCase(requestId: string) {
    selectedId = requestId;
    detailError = null;
    detail = null;
    const generation = ++detailGen;
    if (window.matchMedia("(max-width: 1023px)").matches) {
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
    if (mode === "demo") {
      detail = demoViews.find((item) => item.request_id === requestId) ?? null;
      return;
    }
    detailLoading = true;
    const result = await fetchExecutiveCase(requestId);
    if (generation !== detailGen) return;
    detailLoading = false;
    detail = result.data;
    detailError = result.error;
  }

  function clearSelection() {
    selectedId = null;
    detail = null;
    detailError = null;
    detailLoading = false;
  }

  function retry() {
    void loadList();
  }

  function badgeMeta(): { label: string; classes: string } {
    switch (mode) {
      case "live":
        return { label: "Backend Flow · datos reales", classes: "border-[#b9e7cc] bg-[#e8f8ef] text-[#17663d]" };
      case "auth_required":
        return { label: "Se requiere acceso", classes: "border-[#f1dfa2] bg-[#fff7d9] text-[#765d00]" };
      case "forbidden":
        return { label: "Sin acceso de Directorio", classes: "border-[#f1c7c2] bg-[#fdf0ee] text-[#9b3328]" };
      case "loading":
        return { label: "Cargando…", classes: "border-[#dce6e8] bg-white text-[#587184]" };
      case "demo":
        return { label: "Datos de demostración", classes: "border-[#f1dfa2] bg-[#fff7d9] text-[#765d00]" };
      default:
        return { label: "No disponible", classes: "border-[#f1c7c2] bg-[#fdf0ee] text-[#9b3328]" };
    }
  }

  const badge = $derived(badgeMeta());
  const kpiFootnote = $derived(
    mode === "live"
      ? `Indicadores calculados sobre los ${cases.length} casos de esta página (${pagination.total} en total).`
      : mode === "demo"
        ? "Datos de demostración para revisar el diseño de la vista ejecutiva."
        : "",
  );
</script>

<div class="space-y-6">
  <header class="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
    <div class="min-w-0">
      <p class="text-xs font-bold uppercase tracking-[0.2em] text-console-brand">Directorio</p>
      <h1 class="mt-2 text-3xl font-bold tracking-[-0.055em] text-console-title sm:text-4xl">Vista Ejecutiva</h1>
      <p class="mt-3 max-w-3xl text-sm leading-6 text-console-muted">
        Seguimiento operativo de casos municipales: qué está pasando, qué requiere atención y qué quedó resuelto.
      </p>
    </div>
    <span class={`inline-flex w-fit items-center gap-1.5 rounded-full border px-3 py-1 text-[0.65rem] font-bold uppercase tracking-[0.1em] ${badge.classes}`}>
      {badge.label}
    </span>
  </header>

  {#if mode === "auth_required" || mode === "forbidden"}
    <section class="rounded-2xl border border-dashed border-[#d7e3e5] bg-white/70 p-10 text-center">
      <p class="text-sm font-bold text-[#31536b]">{mode === "auth_required" ? "Sesión requerida" : "Sin permiso de Directorio"}</p>
      <p class="mx-auto mt-2 max-w-md text-xs leading-5 text-[#78909f]">
        {mode === "auth_required" ? "Necesitás autenticarte para consultar casos de Flow." : "Tu usuario no tiene la capability flow.executive.read. Ningún dato de casos se muestra mientras el acceso no esté autorizado."}
      </p>
      <div class="mt-5 flex flex-wrap justify-center gap-3">
        {#if mode === "auth_required"}
          <a href="/login" class="rounded-full border border-[#b7dfdc] bg-[#e4f5f3] px-4 py-2 text-xs font-bold text-[#126d6b] transition hover:bg-[#d7efec]">Ir al acceso</a>
        {/if}
        <button type="button" onclick={retry} class="rounded-full border border-[#d5e4e4] bg-white px-4 py-2 text-xs font-bold text-[#587184] transition hover:bg-base-200">Reintentar</button>
      </div>
    </section>
  {:else if mode === "error"}
    <section class="rounded-2xl border border-dashed border-[#d7e3e5] bg-white/70 p-10 text-center" role="alert">
      <p class="text-sm font-bold text-[#31536b]">No se pudo cargar el listado</p>
      <p class="mx-auto mt-2 max-w-md text-xs leading-5 text-[#78909f]">El listado ejecutivo no está disponible. No se muestran datos de demostración ni resultados parciales.</p>
      <button type="button" onclick={retry} class="mt-5 rounded-full border border-[#b7dfdc] bg-[#e4f5f3] px-4 py-2 text-xs font-bold text-[#126d6b]">Reintentar</button>
    </section>
  {:else}
    <section aria-label="Indicadores" class="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5">
      {#if listLoading}
        {#each Array(5) as _, i (i)}
          <div class="h-[7.5rem] animate-pulse rounded-2xl border border-card-border bg-card-bg"></div>
        {/each}
      {:else}
        {#each kpis as kpi (kpi.id)}
          <FlowKpi {kpi} />
        {/each}
      {/if}
    </section>

    <p class="text-xs leading-5 text-[#91a2ad]" aria-live="polite">{kpiFootnote}</p>

    <div class="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,26rem)] xl:grid-cols-[minmax(0,1fr)_30rem]">
      <section class={selectedId ? "hidden lg:block" : "block"}>
        <FlowCaseList
          cases={cases}
          {selectedId}
          {pagination}
          loading={listLoading}
          localFiltering={mode === "demo"}
          {sectors}
          onSelect={selectCase}
          onSearchChange={searchChanged}
          onFilterChange={filterChanged}
          onSectorChange={sectorChanged}
          onPageChange={pageChanged}
        />
      </section>

      <section class={selectedId ? "block" : "hidden lg:block"} data-selected-id={selectedId ?? "null"} data-selected={selected ? "yes" : "no"}>
        {#if listLoading || detailLoading}
          <div class="animate-pulse space-y-3 rounded-2xl border border-card-border bg-card-bg p-6">
            <div class="h-4 w-1/3 rounded bg-base-200"></div>
            <div class="h-8 w-2/3 rounded bg-base-200"></div>
            <div class="h-3 w-1/2 rounded bg-base-200"></div>
          </div>
        {:else if selectedId}
          <FlowCaseDetail view={selected} error={detailError} onBack={clearSelection} />
        {:else}
          <div class="hidden rounded-2xl border border-dashed border-[#d7e3e5] bg-white/70 p-8 text-center lg:block">
            <p class="text-sm font-bold text-[#31536b]">Seleccioná un caso</p>
            <p class="mt-2 text-xs leading-5 text-[#78909f]">Elegí un reclamo del listado para ver su historia completa.</p>
          </div>
        {/if}
      </section>
    </div>
  {/if}
</div>
