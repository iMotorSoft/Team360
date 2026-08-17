<script lang="ts">
  import type { FlowSectorConfiguration } from "../../../lib/t360/flow/configuration";

  let {
    sectors,
    selectedId,
    onSelect = () => undefined,
  }: {
    sectors: FlowSectorConfiguration[];
    selectedId: string | null;
    onSelect?: (sectorId: string) => void;
  } = $props();
</script>

<aside class="rounded-2xl border border-card-border bg-card-bg p-4" aria-label="Sectores de Flow">
  <div class="flex items-start justify-between gap-3">
    <div>
      <p class="text-xs font-bold uppercase tracking-[0.16em] text-[#168b88]">Sectores</p>
      <p class="mt-1 text-xs leading-5 text-[#78909f]">Elegí el circuito que querés revisar.</p>
    </div>
    <span class="rounded-full bg-[#eef6f5] px-2 py-1 text-[0.62rem] font-bold uppercase tracking-[0.08em] text-[#47716f]">
      {sectors.length} {sectors.length === 1 ? "sector" : "sectores"}
    </span>
  </div>

  {#if sectors.length === 0}
    <div class="mt-4 rounded-xl border border-dashed border-[#d7e3e5] bg-[#f8fbfa] p-4">
      <p class="text-sm font-semibold text-[#31536b]">Todavía no hay sectores configurados</p>
      <p class="mt-1 text-xs leading-5 text-[#78909f]">Cuando exista el catálogo de Flow, sus sectores aparecerán aquí.</p>
    </div>
  {:else}
    <div class="mt-4 space-y-2" role="listbox" aria-label="Seleccionar sector">
      {#each sectors as sector (sector.sectorId)}
        <button
          type="button"
          role="option"
          aria-selected={selectedId === sector.sectorId}
          onclick={() => onSelect(sector.sectorId)}
          class={`w-full rounded-xl border px-3.5 py-3 text-start transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#168b88] ${
            selectedId === sector.sectorId
              ? "border-[#8bcac5] bg-[#e4f5f3] text-[#126d6b] shadow-[0_12px_30px_-24px_rgba(22,139,136,0.8)]"
              : "border-card-border bg-white text-[#31536b] hover:border-[#b7dfdc] hover:bg-[#f8fbfa]"
          }`}
        >
          <span class="flex items-center justify-between gap-3">
            <span class="min-w-0">
              <span class="block truncate text-sm font-bold">{sector.displayName}</span>
              <span class="mt-0.5 block text-xs opacity-75">{sector.levels.length} {sector.levels.length === 1 ? "nivel operativo" : "niveles operativos"}</span>
            </span>
            <span class="grid size-7 shrink-0 place-items-center rounded-full bg-white/80 text-sm" aria-hidden="true">›</span>
          </span>
        </button>
      {/each}
    </div>
  {/if}
</aside>
