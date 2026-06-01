<script lang="ts">
  import type { Snippet } from "svelte";

  type AlertVariant = "neutral" | "success" | "warning" | "info" | "danger";

  let {
    children,
    variant = "neutral",
    class: className = "",
  }: {
    children?: Snippet;
    variant?: AlertVariant;
    class?: string;
  } = $props();

  const variantClasses: Record<AlertVariant, string> = {
    neutral: "",
    success: "alert-success",
    warning: "alert-warning",
    info: "alert-info",
    danger: "alert-error",
  };
</script>

<div role="alert" class={`alert ${variantClasses[variant]} ${className}`}>
  {@render children?.()}
</div>
