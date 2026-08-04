<script lang="ts">
  import type { Snippet } from "svelte";
  import type { HTMLButtonAttributes } from "svelte/elements";

  type ButtonVariant = "primary" | "secondary" | "ghost" | "neutral" | "danger" | "success" | "warning" | "info";
  type ButtonSize = "sm" | "md" | "lg" | "icon";

  type Props = Omit<HTMLButtonAttributes, "children"> & {
    children?: Snippet;
    variant?: ButtonVariant;
    size?: ButtonSize;
    loading?: boolean;
  };

  let {
    children,
    variant = "primary",
    size = "md",
    loading = false,
    disabled = false,
    type = "button",
    class: className = "",
    ...rest
  }: Props = $props();

  const variantClasses: Record<ButtonVariant, string> = {
    primary: "border-[#168b88] bg-[#168b88] text-white hover:border-[#126d6b] hover:bg-[#126d6b]",
    secondary: "border-[#cddbdd] bg-white text-[#47657b] hover:border-[#9fb6bb] hover:bg-[#f4f8f8]",
    ghost: "border-transparent bg-transparent text-[#587184] hover:bg-[#eef4f4] hover:text-[#31536b]",
    neutral: "border-[#31536b] bg-[#31536b] text-white hover:border-[#203f57] hover:bg-[#203f57]",
    danger: "border-[#a94438] bg-[#a94438] text-white hover:border-[#87352d] hover:bg-[#87352d]",
    success: "border-[#238454] bg-[#238454] text-white hover:border-[#1b6b43] hover:bg-[#1b6b43]",
    warning: "border-[#d6ae12] bg-[#f1cf45] text-[#4f4108] hover:bg-[#e5bf22]",
    info: "border-[#328fba] bg-[#328fba] text-white hover:border-[#267495] hover:bg-[#267495]",
  };

  const sizeClasses: Record<ButtonSize, string> = {
    sm: "min-h-10 px-3.5 py-2 text-xs",
    md: "min-h-11 px-5 py-2.5 text-sm",
    lg: "min-h-12 px-6 py-3 text-sm",
    icon: "size-11 p-0",
  };
</script>

<button
  {...rest}
  {type}
  class={`inline-flex cursor-pointer items-center justify-center gap-2 rounded-full border font-bold transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#168b88] disabled:cursor-not-allowed disabled:opacity-50 ${variantClasses[variant]} ${sizeClasses[size]} ${className}`}
  disabled={disabled || loading}
  aria-busy={loading || undefined}
>
  {#if loading}
    <span class="size-4 animate-spin rounded-full border-2 border-current border-e-transparent" aria-hidden="true"></span>
  {/if}
  {@render children?.()}
</button>
