<script lang="ts">
  import T360ActionButtons from "./T360ActionButtons.svelte";
  import T360MissingRequirements from "./T360MissingRequirements.svelte";
  import T360StatusBadge from "./T360StatusBadge.svelte";
  import T360StepList from "./T360StepList.svelte";
  import type { T360DiagnosisSnapshot } from "./types";

  let {
    diagnosis,
    sessionId,
    disabled = false,
  }: {
    diagnosis: T360DiagnosisSnapshot;
    sessionId: string;
    disabled?: boolean;
  } = $props();

  const missingBlock = $derived(diagnosis.missing_requirements?.length
    ? {
        type: "missing_requirements" as const,
        title: "Requisitos pendientes",
        requirements: diagnosis.missing_requirements,
      }
    : undefined);
</script>

<section class="card bg-base-100 border border-base-300 shadow-sm" data-testid="t360-diagnosis-summary">
  <div class="card-body p-4">
    <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div class="min-w-0">
        <p class="text-xs font-semibold uppercase text-base-content/50">Resumen de diagnóstico</p>
        <h2 class="text-base font-bold leading-6">{diagnosis.title ?? "Diagnóstico Team360"}</h2>
      </div>
      <div class="flex shrink-0 flex-wrap gap-2">
        <T360StatusBadge status={diagnosis.status} />
        <T360StatusBadge status={diagnosis.availability_status} />
      </div>
    </div>

    <p class="text-sm leading-6 text-base-content/75">{diagnosis.summary}</p>

    {#if diagnosis.automation_fit}
      <div class="rounded-box border border-base-300 bg-base-200 p-3">
        <div class="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p class="text-xs font-semibold uppercase text-base-content/50">Encaje de automatización</p>
            <p class="text-sm leading-6 text-base-content/70">{diagnosis.automation_fit.score ?? "Sin score"}{typeof diagnosis.automation_fit.score === "number" ? "%" : ""}</p>
          </div>
          <T360StatusBadge status={diagnosis.automation_fit.label} />
        </div>
      </div>
    {/if}

    {#if diagnosis.detected_use_case}
      <div class="rounded-box border border-base-300 p-3">
        <p class="text-xs font-semibold uppercase text-base-content/50">Caso detectado</p>
        <p class="mt-1 text-sm font-semibold leading-5">{diagnosis.detected_use_case.label}</p>
        {#if diagnosis.detected_use_case.category}
          <p class="mt-1 text-xs text-base-content/55">{diagnosis.detected_use_case.category}</p>
        {/if}
      </div>
    {/if}

    {#if diagnosis.recommended_path?.length}
      <div>
        <h3 class="mb-2 text-sm font-semibold">Camino recomendado</h3>
        <T360StepList items={diagnosis.recommended_path} ordered />
      </div>
    {/if}

    {#if diagnosis.risks?.length}
      <div class="rounded-box bg-warning/10 p-3">
        <h3 class="mb-2 text-sm font-semibold">Riesgos</h3>
        <T360StepList items={diagnosis.risks} />
      </div>
    {/if}

    {#if diagnosis.suggested_products?.length}
      <div>
        <h3 class="mb-2 text-sm font-semibold">Productos sugeridos</h3>
        <div class="flex flex-col gap-2">
          {#each diagnosis.suggested_products as product}
            <article class="rounded-box border border-base-300 p-3">
              <div class="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                <div class="min-w-0">
                  <p class="text-xs font-semibold uppercase text-base-content/50">{product.product_code}</p>
                  <h4 class="text-sm font-semibold leading-5">{product.product_name}</h4>
                </div>
                <div class="flex shrink-0 flex-wrap gap-1.5">
                  <T360StatusBadge status={product.status} compact />
                  {#if typeof product.fit_score === "number"}
                    <span class="badge badge-outline h-auto px-2 py-1 text-[0.66rem]">{product.fit_score}%</span>
                  {/if}
                </div>
              </div>
            </article>
          {/each}
        </div>
      </div>
    {/if}
  </div>
</section>

{#if missingBlock}
  <T360MissingRequirements block={missingBlock} {sessionId} {disabled} />
{/if}

{#if diagnosis.next_best_action}
  <section class="card bg-base-100 border border-base-300 shadow-sm">
    <div class="card-body p-4">
      <h2 class="text-base font-bold leading-6">Mejor próxima acción</h2>
      <T360ActionButtons actions={[diagnosis.next_best_action]} {sessionId} blockType="diagnosis_action_card" {disabled} />
    </div>
  </section>
{/if}
