<script lang="ts">
  import { dispatchActionEvent } from "./events";
  import type { T360Action, T360InteractionKind } from "./types";

  let {
    actions = [],
    sessionId,
    blockType,
    disabled = false,
    payload,
  }: {
    actions?: T360Action[];
    sessionId: string;
    blockType: T360InteractionKind;
    disabled?: boolean;
    payload?: Record<string, unknown>;
  } = $props();

  const visibleActions = $derived(actions.slice(0, 3));

  const styleClasses: Record<NonNullable<T360Action["style"]>, string> = {
    primary: "btn-primary",
    secondary: "btn-secondary",
    ghost: "btn-ghost",
    outline: "btn-outline",
    warning: "btn-warning",
    danger: "btn-error",
  };

  function actionClass(action: T360Action) {
    return styleClasses[action.style ?? "primary"];
  }

  function handleAction(event: MouseEvent, action: T360Action) {
    if (disabled || action.disabled) return;
    if (!event.currentTarget) return;
    dispatchActionEvent(event.currentTarget, {
      sessionId,
      blockType,
      action,
      payload,
    });
  }
</script>

{#if visibleActions.length > 0}
  <div class="flex flex-col gap-2 sm:flex-row sm:flex-wrap" data-testid={`t360-actions-${blockType}`}>
    {#each visibleActions as action}
      <div class="flex flex-col gap-1">
        <button
          type="button"
          class={`btn btn-sm min-h-10 w-full sm:w-auto ${actionClass(action)}`}
          disabled={disabled || action.disabled}
          data-testid={`t360-action-${action.id}`}
          onclick={(event) => handleAction(event, action)}
        >
          {action.label}
        </button>
        {#if action.helper_text}
          <span class="text-xs leading-5 text-base-content/55">{action.helper_text}</span>
        {/if}
      </div>
    {/each}
  </div>
{/if}
