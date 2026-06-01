<script lang="ts">
  import type { Snippet } from "svelte";

  type ButtonVariant = "primary" | "secondary" | "ghost" | "neutral" | "danger" | "success" | "warning" | "info";

  let {
    children,
    variant = "primary",
    loading = false,
    disabled = false,
    type = "button",
    class: className = "",
  }: {
    children?: Snippet;
    variant?: ButtonVariant;
    loading?: boolean;
    disabled?: boolean;
    type?: "button" | "submit" | "reset";
    class?: string;
  } = $props();

  const variantClasses: Record<ButtonVariant, string> = {
    primary: "btn-primary",
    secondary: "btn-secondary",
    ghost: "btn-ghost",
    neutral: "btn-neutral",
    danger: "btn-error",
    success: "btn-success",
    warning: "btn-warning",
    info: "btn-info",
  };
</script>

<button
  {type}
  class={`btn ${variantClasses[variant]} focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#168b88] ${className}`}
  disabled={disabled || loading}
  aria-busy={loading}
>
  {#if loading}
    <span class="loading loading-spinner loading-xs" aria-hidden="true"></span>
  {/if}
  {@render children?.()}
</button>
