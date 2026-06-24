<script lang="ts">
  import { normalizeT360InteractionBlock } from "./guards";
  import T360ActionCard from "./T360ActionCard.svelte";
  import T360MissingRequirements from "./T360MissingRequirements.svelte";
  import T360MultiChoice from "./T360MultiChoice.svelte";
  import T360ProductFitCard from "./T360ProductFitCard.svelte";
  import T360SingleChoice from "./T360SingleChoice.svelte";
  let {
    block,
    sessionId,
    disabled = false,
    consumed = false,
  }: {
    block?: unknown;
    sessionId: string;
    disabled?: boolean;
    consumed?: boolean;
  } = $props();

  const safeBlock = $derived(normalizeT360InteractionBlock(block));
</script>

{#if !safeBlock}
  <section class="card bg-base-100 border border-base-300 shadow-sm" data-testid="t360-block-invalid">
    <div class="card-body p-4">
      <p class="text-sm leading-6 text-base-content/60">No hay interacción disponible para mostrar.</p>
    </div>
  </section>
{:else if safeBlock.type === "next_step_choice"}
  <T360ActionCard block={safeBlock} {sessionId} {disabled} />
{:else if safeBlock.type === "single_choice"}
  <T360SingleChoice block={safeBlock} {sessionId} {disabled} answered={consumed} />
{:else if safeBlock.type === "multi_choice"}
  <T360MultiChoice block={safeBlock} {sessionId} {disabled} answered={consumed} />
{:else if safeBlock.type === "missing_requirements"}
  <T360MissingRequirements block={safeBlock} {sessionId} {disabled} />
{:else if safeBlock.type === "product_fit_card"}
  <T360ProductFitCard block={safeBlock} {sessionId} {disabled} />
{:else if safeBlock.type === "diagnosis_action_card"}
  <T360ActionCard block={safeBlock} {sessionId} {disabled} />
{/if}
