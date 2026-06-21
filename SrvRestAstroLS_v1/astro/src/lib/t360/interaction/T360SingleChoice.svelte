<script lang="ts">
  import { dispatchChoiceSelectedEvent } from "./events";
  import T360ChoiceGroup from "./T360ChoiceGroup.svelte";
  import type { T360Action, T360SingleChoiceBlock, T360SingleChoiceOption } from "./types";

  let {
    block,
    sessionId,
    disabled = false,
    answered = false,
  }: {
    block: T360SingleChoiceBlock;
    sessionId: string;
    disabled?: boolean;
    answered?: boolean;
  } = $props();

  let selectedId = $state<string | undefined>(undefined);
  const selectedOption = $derived(block.options.find((option) => option.id === selectedId));
  const submitAction = $derived<T360Action>(block.submit_action ?? {
    id: "submit-single-choice",
    label: "Continuar",
    style: "primary",
    intent: "answer_choice",
  });
  const canSubmit = $derived(Boolean(selectedOption));

  function selectOption(option: T360SingleChoiceOption) {
    if (disabled) return;
    selectedId = option.id;
  }

  function submit(event: MouseEvent) {
    if (!canSubmit || !selectedOption) return;
    if (!event.currentTarget) return;
    dispatchChoiceSelectedEvent(event.currentTarget, sessionId, submitAction, selectedOption);
  }
</script>

{#if answered && selectedOption}
  <section class="card bg-base-100 border border-base-300 shadow-sm" data-testid="t360-block-single_choice-answered" data-interaction-state="answered">
    <div class="card-body p-3">
      <p class="text-xs font-semibold uppercase tracking-wider text-base-content/50">Tu respuesta</p>
      <p class="text-sm font-semibold leading-5">{selectedOption.label}</p>
    </div>
  </section>
{:else}
  <section class="card bg-base-100 border border-primary/30 shadow-sm" data-testid="t360-block-single_choice" data-interaction-state="requires-response">
    <div class="card-body p-4">
      <div class="flex flex-col gap-1">
        <span class="badge badge-primary badge-sm mb-1 w-fit px-2 py-1 text-[0.6rem] font-semibold uppercase tracking-wider">Paso necesario</span>
        <h2 class="text-base font-bold leading-6">{block.question}</h2>
        {#if block.helper_text}
          <p class="text-sm leading-6 text-base-content/65">{block.helper_text}</p>
        {/if}
      </div>

      <T360ChoiceGroup
        options={block.options}
        selectedIds={selectedId ? [selectedId] : []}
        name={block.question}
        {disabled}
        onToggle={selectOption}
      />

      {#if !selectedOption}
        <p class="text-xs leading-5 text-base-content/55" aria-live="polite">Elegí una opción para continuar.</p>
      {/if}

      <button
        type="button"
        class="btn btn-sm btn-primary min-h-10 w-full sm:w-auto"
        disabled={disabled || !canSubmit}
        data-testid="t360-single-submit"
        onclick={submit}
      >
        {submitAction.label}
      </button>
    </div>
  </section>
{/if}
