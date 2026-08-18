<script lang="ts">
  import { onMount } from "svelte";
  import { fetchExecutiveCases } from "../../../lib/api/flowExecutive";
  import { FLOW_KNOWN_CASE_IDS } from "../../../lib/t360/flow/caseRegistry";
  import { getFlowKpis, listFlowCases } from "../../../lib/mock/flow";
  import type { ExecutiveView } from "../../../lib/t360/flow/types";
  import FlowCaseDetail from "./FlowCaseDetail.svelte";
  import FlowCaseList from "./FlowCaseList.svelte";
  import FlowKpi from "./FlowKpi.svelte";

  type Mode = "loading" | "live" | "demo" | "auth_required" | "forbidden";

  let cases: ExecutiveView[] = $state([]);
  let mode = $state<Mode>("loading");
  let selectedId = $state<string | null>(null);
  let failureCount = $state(0);
  let loadGen = $state(0);

  const demoRequested = $derived(new URLSearchParams(window.location.search).has("demo"));

  function sortByConfirmedDesc(list: ExecutiveView[]): ExecutiveView[] {
    return [...list].sort((a, b) => {
      const ta = a.request.confirmed_at ?? a.request.received_at ?? "";
      const tb = b.request.confirmed_at ?? b.request.received_at ?? "";
      return tb.localeCompare(ta);
    });
  }

  async function loadCases() {
    const gen = ++loadGen;
    mode = "loading";
    cases = [];
    selectedId = null;
    failureCount = 0;

    if (demoRequested) {
      cases = listFlowCases();
      mode = "demo";
      return;
    }

    const { cases: loaded, failed } = await fetchExecutiveCases(FLOW_KNOWN_CASE_IDS, {
      concurrency: 6,
    });
    if (gen !== loadGen) return; // un load más nuevo ya corrió

    const authFailure = failed.find(
      (f) => f.error === "unauthorized" || f.error === "forbidden",
    );
    if (authFailure) {
      mode = authFailure.error === "unauthorized" ? "auth_required" : "forbidden";
      return;
    }

    if (loaded.length > 0) {
      cases = sortByConfirmedDesc(loaded);
      mode = "live";
      failureCount = failed.length;
      return;
    }

    // Backend no disponible (o registro sin coincidencias): modo demostración
    // explícito, nunca se presenta como datos reales.
    cases = listFlowCases();
    mode = "demo";
  }

  onMount(() => {
    void loadCases();
  });

  function retry() {
    void loadCases();
  }

  const kpis = $derived(getFlowKpis(cases));
  const selected = $derived(cases.find((c) => c.request_id === selectedId) ?? null);

  function selectCase(requestId: string) {
    selectedId = requestId;
    if (window.matchMedia("(max-width: 1023px)").matches) {
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  }

  function badgeMeta(): { label: string; classes: string } {
    switch (mode) {
      case "live":
        return {
          label: "Backend Flow · datos reales",
          classes: "border-[#b9e7cc] bg-[#e8f8ef] text-[#17663d]",
        };
      case "auth_required":
        return { label: "Se requiere acceso", classes: "border-[#f1dfa2] bg-[#fff7d9] text-[#765d00]" };
      case "forbidden":
        return { label: "Sin acceso de Directorio", classes: "border-[#f1c7c2] bg-[#fdf0ee] text-[#9b3328]" };
      case "loading":
        return { label: "Cargando…", classes: "border-[#dce6e8] bg-white text-[#587184]" };
      default:
        return {
          label: "Datos de demostración",
          classes: "border-[#f1dfa2] bg-[#fff7d9] text-[#765d00]",
        };
    }
  }

  const badge = $derived(badgeMeta());
  const isLoading = $derived(mode === "loading");
  const kpiFootnote = $derived(
    mode === "live"
      ? `Indicadores calculados sobre los ${cases.length} casos disponibles en el Directorio.`
      : "Datos de demostración para revisar el diseño de la vista ejecutiva.",
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
    <span
      class={`inline-flex w-fit items-center gap-1.5 rounded-full border px-3 py-1 text-[0.65rem] font-bold uppercase tracking-[0.1em] ${badge.classes}`}
    >
      {badge.label}
    </span>
  </header>

  {#if mode === "auth_required" || mode === "forbidden"}
    <section class="rounded-2xl border border-dashed border-[#d7e3e5] bg-white/70 p-10 text-center">
      <p class="text-sm font-bold text-[#31536b]">
        {mode === "auth_required" ? "Sesión requerida" : "Sin permiso de Directorio"}
      </p>
      <p class="mx-auto mt-2 max-w-md text-xs leading-5 text-[#78909f]">
        {mode === "auth_required"
          ? "Necesitás autenticarte para consultar casos de Flow."
          : "Tu usuario no tiene la capability flow.executive.read. Ningún dato de casos se muestra mientras el acceso no esté autorizado."}
      </p>
      <div class="mt-5 flex flex-wrap justify-center gap-3">
        {#if mode === "auth_required"}
          <a
            href="/login"
            class="rounded-full border border-[#b7dfdc] bg-[#e4f5f3] px-4 py-2 text-xs font-bold text-[#126d6b] transition hover:bg-[#d7efec]"
          >
            Ir al acceso
          </a>
        {/if}
        <button
          type="button"
          onclick={retry}
          class="rounded-full border border-[#d5e4e4] bg-white px-4 py-2 text-xs font-bold text-[#587184] transition hover:bg-base-200"
        >
          Reintentar
        </button>
      </div>
    </section>
  {:else}
    <section aria-label="Indicadores" class="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5">
      {#if isLoading}
        {#each Array(5) as _, i (i)}
          <div class="h-[7.5rem] animate-pulse rounded-2xl border border-card-border bg-card-bg"></div>
        {/each}
      {:else}
        {#each kpis as kpi (kpi.id)}
          <FlowKpi {kpi} />
        {/each}
      {/if}
    </section>

    <p class="text-xs leading-5 text-[#91a2ad]" aria-live="polite">
      {kpiFootnote}
      {#if mode === "live" && failureCount > 0}
        <span class="text-[#9b3328]"> · {failureCount} casos no pudieron cargarse</span>
      {/if}
    </p>

    <div class="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,26rem)] xl:grid-cols-[minmax(0,1fr)_30rem]">
      <section class={selectedId ? "hidden lg:block" : "block"}>
        <FlowCaseList {cases} {selectedId} loading={isLoading} onSelect={selectCase} />
      </section>

      <section
        class={selectedId ? "block" : "hidden lg:block"}
        data-selected-id={selectedId ?? "null"}
        data-selected={selected ? "yes" : "no"}
      >
        {#if isLoading}
          <div class="animate-pulse space-y-3 rounded-2xl border border-card-border bg-card-bg p-6">
            <div class="h-4 w-1/3 rounded bg-base-200"></div>
            <div class="h-8 w-2/3 rounded bg-base-200"></div>
            <div class="h-3 w-1/2 rounded bg-base-200"></div>
          </div>
        {:else if selected}
          <FlowCaseDetail view={selected} onBack={() => (selectedId = null)} />
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
