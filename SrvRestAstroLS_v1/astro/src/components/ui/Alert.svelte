<script lang="ts">
  import type { Snippet } from "svelte";
  import type { HTMLAttributes } from "svelte/elements";

  type AlertVariant = "neutral" | "success" | "warning" | "info" | "danger";
  type Props = Omit<HTMLAttributes<HTMLDivElement>, "children"> & {
    children?: Snippet;
    variant?: AlertVariant;
  };

  let {
    children,
    variant = "neutral",
    class: className = "",
    ...rest
  }: Props = $props();

  const variantClasses: Record<AlertVariant, string> = {
    neutral: "border-[#dce6e8] bg-white text-[#47657b]",
    success: "border-[#b9e7cc] bg-[#eefaf3] text-[#17663d]",
    warning: "border-[#f1dfa2] bg-[#fff9e8] text-[#765d00]",
    info: "border-[#b9def0] bg-[#eef8fc] text-[#1d6688]",
    danger: "border-[#f1c7c2] bg-[#fdf2f0] text-[#9b3328]",
  };
</script>

<div {...rest} role="alert" class={`rounded-2xl border p-4 text-sm leading-6 ${variantClasses[variant]} ${className}`}>
  {@render children?.()}
</div>
