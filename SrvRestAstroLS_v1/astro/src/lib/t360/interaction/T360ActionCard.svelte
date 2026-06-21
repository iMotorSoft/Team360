<script lang="ts">
  import T360ActionButtons from "./T360ActionButtons.svelte";
  import T360StatusBadge from "./T360StatusBadge.svelte";
  import type { T360DiagnosisActionCardBlock, T360NextStepChoiceBlock } from "./types";

  let {
    block,
    sessionId,
    disabled = false,
  }: {
    block: T360NextStepChoiceBlock | T360DiagnosisActionCardBlock;
    sessionId: string;
    disabled?: boolean;
  } = $props();

  const isDiagnosisAction = $derived(block.type === "diagnosis_action_card");
  const title = $derived(block.type === "diagnosis_action_card" ? block.title : (block.title ?? "Próximo paso"));
  const description = $derived(block.type === "diagnosis_action_card" ? block.summary : block.description);
  const actions = $derived(block.type === "diagnosis_action_card"
    ? [block.primary_action, ...(block.secondary_actions ?? [])]
    : block.actions);
</script>

<section class="card bg-base-100 border border-base-300 shadow-sm" data-testid={`t360-block-${block.type}`}>
  <div class="card-body p-4">
    <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div class="min-w-0">
        <h2 class="text-base font-bold leading-6">{title}</h2>
        {#if description}
          <p class="mt-1 text-sm leading-6 text-base-content/65">{description}</p>
        {/if}
      </div>
      {#if isDiagnosisAction && block.type === "diagnosis_action_card"}
        <div class="flex shrink-0 flex-wrap gap-2">
          <T360StatusBadge status={block.status} />
          {#if block.confidence}
            <T360StatusBadge status={block.confidence} label={`Confianza ${block.confidence}`} compact />
          {/if}
        </div>
      {/if}
    </div>

    <T360ActionButtons {actions} {sessionId} blockType={block.type} {disabled} />
  </div>
</section>
