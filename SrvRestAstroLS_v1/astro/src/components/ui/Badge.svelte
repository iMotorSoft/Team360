<script lang="ts">
  import type { Snippet } from "svelte";

  type BadgeVariant = "neutral" | "primary" | "secondary" | "success" | "warning" | "info" | "danger";

  let {
    children,
    variant = "neutral",
    ariaLabel,
    class: className = "",
  }: {
    children?: Snippet;
    variant?: BadgeVariant;
    ariaLabel?: string;
    class?: string;
  } = $props();

  const variantClasses: Record<BadgeVariant, string> = {
    neutral: "border-[#dce6e8] bg-[#f2f6f6] text-[#587184]",
    primary: "border-[#b7dfdc] bg-[#e4f5f3] text-[#126d6b]",
    secondary: "border-[#c8d5df] bg-[#eaf0f5] text-[#31536b]",
    success: "border-[#b9e7cc] bg-[#e8f8ef] text-[#17663d]",
    warning: "border-[#f1dfa2] bg-[#fff7d9] text-[#765d00]",
    info: "border-[#b9def0] bg-[#e9f6fc] text-[#1d6688]",
    danger: "border-[#f1c7c2] bg-[#fdf0ee] text-[#9b3328]",
  };
</script>

<span
  aria-label={ariaLabel}
  class={`inline-flex min-h-6 items-center rounded-full border px-2.5 py-1 text-xs font-bold leading-none ${variantClasses[variant]} ${className}`}
>
  {@render children?.()}
</span>
