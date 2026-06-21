<script lang="ts">
  import T360ActionButtons from "./T360ActionButtons.svelte";
  import T360StatusBadge from "./T360StatusBadge.svelte";
  import T360StepList from "./T360StepList.svelte";
  import type { T360ProductFitCardBlock } from "./types";

  let {
    block,
    sessionId,
    disabled = false,
  }: {
    block: T360ProductFitCardBlock;
    sessionId: string;
    disabled?: boolean;
  } = $props();

  let detailOpen = $state(false);
</script>

<section class="card bg-base-100 border border-base-300 shadow-sm" data-testid="t360-block-product_fit_card" data-interaction-state="result">
  <div class="card-body p-4">
    <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div class="min-w-0">
        <p class="text-xs font-semibold uppercase tracking-wider text-base-content/50">Posible encaje con Team360</p>
        <h2 class="text-base font-bold leading-6">{block.product_name}</h2>
      </div>
      <div class="flex shrink-0 flex-wrap items-center gap-2">
        <T360StatusBadge status={block.status} compact />
        {#if typeof block.fit_score === "number"}
          <span class="badge badge-outline h-auto px-2 py-1 text-xs font-semibold">{block.fit_score}% afinidad</span>
        {/if}
      </div>
    </div>

    <p class="text-sm leading-6 text-base-content/75">{block.summary}</p>

    {#if detailOpen}
      {#if block.good_fit_reasons?.length}
        <div class="rounded-box bg-success/10 p-3">
          <h3 class="mb-2 text-sm font-semibold">Por qué encaja</h3>
          <T360StepList items={block.good_fit_reasons} />
        </div>
      {/if}

      {#if block.limitations?.length}
        <div class="rounded-box bg-warning/10 p-3">
          <h3 class="mb-2 text-sm font-semibold">Limitaciones a validar</h3>
          <T360StepList items={block.limitations} />
        </div>
      {/if}

      {#if block.recommended_next_step}
        <div class="rounded-box border border-base-300 bg-base-200 p-3">
          <p class="text-xs font-semibold uppercase text-base-content/50">Siguiente paso</p>
          <p class="mt-1 text-sm leading-6 text-base-content/75">{block.recommended_next_step}</p>
        </div>
      {/if}
    {:else if block.good_fit_reasons?.length}
      <button type="button" class="btn btn-ghost btn-xs w-fit -ml-1 text-primary" onclick={() => detailOpen = true}>
        Ver por qué encaja
      </button>
    {/if}

    {#if detailOpen && (block.good_fit_reasons?.length || block.limitations?.length || block.recommended_next_step)}
      <button type="button" class="btn btn-ghost btn-xs w-fit -ml-1 text-base-content/50" onclick={() => detailOpen = false}>
        Cerrar detalle
      </button>
    {/if}

    <T360ActionButtons actions={block.actions ?? []} {sessionId} blockType="product_fit_card" {disabled} />
  </div>
</section>
