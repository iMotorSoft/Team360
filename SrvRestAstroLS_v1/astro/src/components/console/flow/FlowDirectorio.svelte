<script lang="ts">
  import { getFlowKpis, listFlowCases } from "../../../lib/mock/flow";
  import type { ExecutiveView } from "../../../lib/t360/flow/types";
  import FlowCaseDetail from "./FlowCaseDetail.svelte";
  import FlowCaseList from "./FlowCaseList.svelte";
  import FlowKpi from "./FlowKpi.svelte";

  let cases: ExecutiveView[] = $state(listFlowCases());
  let selectedId = $state<string | null>(null);

  const kpis = $derived(getFlowKpis(cases));
  const selected = $derived(cases.find((c) => c.request_id === selectedId) ?? null);

  function selectCase(requestId: string) {
    selectedId = requestId;
    if (window.matchMedia("(max-width: 1023px)").matches) {
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  }
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
    <span class="inline-flex w-fit items-center gap-1.5 rounded-full border border-[#f1dfa2] bg-[#fff7d9] px-3 py-1 text-[0.65rem] font-bold uppercase tracking-[0.1em] text-[#765d00]">
      Datos de demostración
    </span>
  </header>

  <section aria-label="Indicadores" class="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5">
    {#each kpis as kpi (kpi.id)}
      <FlowKpi {kpi} />
    {/each}
  </section>

  <div class="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,26rem)] xl:grid-cols-[minmax(0,1fr)_30rem]">
    <section class={selectedId ? "hidden lg:block" : "block"}>
      <FlowCaseList {cases} {selectedId} onSelect={selectCase} />
    </section>

    <section class={selectedId ? "block" : "hidden lg:block"} data-selected-id={selectedId ?? "null"} data-selected={selected ? "yes" : "no"}>
      {#if selected}
        <FlowCaseDetail view={selected} onBack={() => (selectedId = null)} />
      {:else}
        <div class="hidden rounded-2xl border border-dashed border-[#d7e3e5] bg-white/70 p-8 text-center lg:block">
          <p class="text-sm font-bold text-[#31536b]">Seleccioná un caso</p>
          <p class="mt-2 text-xs leading-5 text-[#78909f]">Elegí un reclamo del listado para ver su historia completa.</p>
        </div>
      {/if}
    </section>
  </div>
</div>
