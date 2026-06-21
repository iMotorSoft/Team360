<script lang="ts">
  import T360ActionButtons from "./T360ActionButtons.svelte";
  import T360StatusBadge from "./T360StatusBadge.svelte";
  import type { T360MissingRequirement, T360MissingRequirementsBlock } from "./types";

  let {
    block,
    sessionId,
    disabled = false,
  }: {
    block: T360MissingRequirementsBlock;
    sessionId: string;
    disabled?: boolean;
  } = $props();

  const requiredForLabels: Record<T360MissingRequirement["required_for"], string> = {
    preliminary_diagnosis: "Diagnóstico preliminar",
    full_diagnosis: "Diagnóstico completo",
    implementation: "Implementación",
    pricing: "Pricing",
    handoff: "Handoff",
  };
</script>

<section class="card bg-base-100 border border-base-300 shadow-sm" data-testid="t360-block-missing_requirements">
  <div class="card-body p-4">
    <div class="flex flex-col gap-1">
      <h2 class="text-base font-bold leading-6">{block.title}</h2>
      {#if block.description}
        <p class="text-sm leading-6 text-base-content/65">{block.description}</p>
      {/if}
    </div>

    <div class="flex flex-col gap-2">
      {#each block.requirements as requirement}
        <article class="rounded-box border border-base-300 bg-base-100 p-3">
          <div class="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
            <div class="min-w-0">
              <h3 class="text-sm font-semibold leading-5">{requirement.label}</h3>
              {#if requirement.description}
                <p class="mt-1 text-sm leading-6 text-base-content/65">{requirement.description}</p>
              {/if}
            </div>
            <div class="flex shrink-0 flex-wrap gap-1.5">
              <T360StatusBadge status={requirement.status} compact />
              <span class="badge badge-outline h-auto px-2 py-1 text-[0.66rem]">
                {requiredForLabels[requirement.required_for]}
              </span>
            </div>
          </div>
        </article>
      {/each}
    </div>

    <T360ActionButtons actions={block.actions ?? []} {sessionId} blockType="missing_requirements" {disabled} />
  </div>
</section>
