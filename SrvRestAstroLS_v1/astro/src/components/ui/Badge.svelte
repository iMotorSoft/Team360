<script lang="ts">
  import type { Snippet } from "svelte";

  type BadgeVariant =
    | "neutral"
    | "primary"
    | "secondary"
    | "success"
    | "warning"
    | "info"
    | "danger";

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
    neutral: "bg-slate-100 text-slate-500 border-slate-200 font-bold",
    primary: "bg-blue-100 text-blue-700 border-blue-200 font-bold",
    secondary: "bg-violet-100 text-violet-700 border-violet-200 font-bold",
    success: "bg-green-100 text-green-700 border-green-200 font-bold",
    warning: "bg-yellow-100 text-yellow-700 border-yellow-200 font-bold",
    info: "bg-teal-100 text-teal-700 border-teal-200 font-bold",
    danger: "bg-red-100 text-red-700 border-red-200 font-bold",
  };
</script>

<span class={`badge ${variantClasses[variant]} ${className}`}>
  {@render children?.()}
</span>
