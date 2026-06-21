<script lang="ts">
  import T360StatusBadge from "./T360StatusBadge.svelte";
  import type { T360SingleChoiceOption } from "./types";

  let {
    options = [],
    selectedIds = [],
    multiple = false,
    disabled = false,
    name = "t360-choice",
    onToggle,
  }: {
    options?: T360SingleChoiceOption[];
    selectedIds?: string[];
    multiple?: boolean;
    disabled?: boolean;
    name?: string;
    onToggle?: (option: T360SingleChoiceOption) => void;
  } = $props();

  function isSelected(optionId: string) {
    return selectedIds.includes(optionId);
  }
</script>

<div class="flex flex-col gap-2">
  {#each options as option}
    <button
      type="button"
      class={`rounded-box border p-3 text-left transition ${isSelected(option.id) ? "border-primary bg-primary/10" : "border-base-300 bg-base-100 hover:border-primary/60"} ${disabled ? "cursor-not-allowed opacity-60" : ""}`}
      aria-pressed={isSelected(option.id)}
      disabled={disabled}
      data-testid={`t360-option-${option.id}`}
      onclick={() => onToggle?.(option)}
    >
      <span class="flex items-start gap-3">
        <span class={`mt-1 flex size-5 shrink-0 items-center justify-center border ${multiple ? "rounded" : "rounded-full"} ${isSelected(option.id) ? "border-primary bg-primary text-primary-content" : "border-base-300 bg-base-100"}`}>
          {#if isSelected(option.id)}
            <span class="text-xs font-black">✓</span>
          {/if}
        </span>
        <span class="min-w-0 flex-1">
          <span class="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <span class="font-semibold leading-5 text-base-content">{option.label}</span>
            <span class="flex flex-wrap gap-1.5">
              {#if option.badge}
                <span class="badge badge-outline h-auto px-2 py-1 text-[0.66rem]">{option.badge}</span>
              {/if}
              {#if option.availability_status}
                <T360StatusBadge status={option.availability_status} compact />
              {/if}
            </span>
          </span>
          {#if option.description}
            <span class="mt-1 block text-sm leading-6 text-base-content/65">{option.description}</span>
          {/if}
        </span>
      </span>
      <span class="sr-only">{multiple ? "Opción múltiple" : "Opción simple"} {name}</span>
    </button>
  {/each}
</div>
