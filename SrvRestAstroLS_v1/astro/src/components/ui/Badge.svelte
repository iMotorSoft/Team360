<script lang="ts">
  import type { Snippet } from "svelte";

  type BadgeVariant = "neutral" | "primary" | "secondary" | "success" | "warning" | "info" | "danger";

  let {
    children,
    variant = "neutral",
    class: className = "",
  }: {
    children?: Snippet;
    variant?: BadgeVariant;
    class?: string;
  } = $props();

  const variantClasses: Record<BadgeVariant, string> = {
    neutral: "badge-neutral",
    primary: "badge-primary",
    secondary: "badge-secondary",
    success: "badge-success",
    warning: "badge-warning",
    info: "badge-info",
    danger: "badge-error",
  };
</script>

<span class={`badge ${variantClasses[variant]} ${className}`}>
  {@render children?.()}
</span>
