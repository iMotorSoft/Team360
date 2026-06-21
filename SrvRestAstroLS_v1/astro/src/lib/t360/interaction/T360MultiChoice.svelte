<script lang="ts">
  import { dispatchChoicesSubmittedEvent } from "./events";
  import T360ChoiceGroup from "./T360ChoiceGroup.svelte";
  import type { T360MultiChoiceBlock, T360SingleChoiceOption } from "./types";

  let {
    block,
    sessionId,
    disabled = false,
  }: {
    block: T360MultiChoiceBlock;
    sessionId: string;
    disabled?: boolean;
  } = $props();

  let selectedIds = $state<string[]>([]);
  const selectedOptions = $derived(block.options.filter((option) => selectedIds.includes(option.id)));
  const minSelected = $derived(block.min_selected ?? 1);
  const maxSelected = $derived(block.max_selected);
  const selectionLabel = $derived(`${selectedIds.length}${maxSelected ? `/${maxSelected}` : ""} seleccionadas`);
  const canSubmit = $derived(selectedIds.length >= minSelected && selectedIds.length > 0);
  const reachedMax = $derived(Boolean(maxSelected && selectedIds.length >= maxSelected));
  const disabledOptionIds = $derived(reachedMax
    ? block.options.filter((option) => !selectedIds.includes(option.id)).map((option) => option.id)
    : []);
  const selectionFeedback = $derived(selectedIds.length < minSelected
    ? `Seleccioná al menos ${minSelected}.`
    : reachedMax
      ? "Llegaste al máximo de opciones para este bloque."
      : "Selección lista para enviar.");

  function toggleOption(option: T360SingleChoiceOption) {
    if (disabled) return;
    if (selectedIds.includes(option.id)) {
      selectedIds = selectedIds.filter((id) => id !== option.id);
      return;
    }
    if (maxSelected && selectedIds.length >= maxSelected) return;
    selectedIds = [...selectedIds, option.id];
  }

  function submit(event: MouseEvent) {
    if (!canSubmit) return;
    if (!event.currentTarget) return;
    dispatchChoicesSubmittedEvent(event.currentTarget, sessionId, block.submit_action, selectedOptions);
  }
</script>

<section class="card bg-base-100 border border-base-300 shadow-sm" data-testid="t360-block-multi_choice">
  <div class="card-body p-4">
    <div class="flex flex-col gap-1">
      <div class="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <h2 class="text-base font-bold leading-6">{block.question}</h2>
        <span class="badge badge-outline h-auto px-2 py-1 text-xs">{selectionLabel}</span>
      </div>
      {#if block.helper_text}
        <p class="text-sm leading-6 text-base-content/65">{block.helper_text}</p>
      {/if}
    </div>

    <T360ChoiceGroup
      options={block.options}
      {selectedIds}
      multiple
      name={block.question}
      {disabled}
      disabledIds={disabledOptionIds}
      disabledReason="Máximo seleccionado"
      onToggle={toggleOption}
    />

    <p class="text-xs leading-5 text-base-content/55" aria-live="polite">{selectionFeedback}</p>

    <button
      type="button"
      class="btn btn-sm btn-primary min-h-10 w-full sm:w-auto"
      disabled={disabled || !canSubmit}
      data-testid="t360-multi-submit"
      onclick={submit}
    >
      {block.submit_action.label}
    </button>
  </div>
</section>
