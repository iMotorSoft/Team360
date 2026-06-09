<script lang="ts">
  import type { Snippet } from "svelte";

  interface Props {
    tag?: string;
    variant?:
      | "default"
      | "large"
      | "flat"
      | "flat-large"
      | "light"
      | "dark"
      | "mini";
    class?: string;
    padding?: string;
    rounded?: string;
    shadow?: string;
    border?: string;
    bg?: string;
    children?: Snippet;
  }

  let {
    tag = "article",
    variant = "default",
    class: className = "",
    padding,
    rounded,
    shadow,
    border,
    bg,
    children,
  }: Props = $props();

  // Define base style configurations using our Tailwind v4 theme variables
  const variantStyles = {
    default: {
      border: "border border-card-border",
      bg: "bg-card-bg",
      shadow: "shadow-card-default",
      rounded: "rounded-2xl",
      padding: "p-5",
      extra: "text-[#173b5b]",
    },
    large: {
      border: "border border-card-border",
      bg: "bg-card-bg",
      shadow: "shadow-card-large",
      rounded: "rounded-3xl",
      padding: "p-5 sm:p-6",
      extra: "text-[#173b5b]",
    },
    flat: {
      border: "border border-card-border",
      bg: "bg-card-bg",
      shadow: "",
      rounded: "rounded-2xl",
      padding: "p-5",
      extra: "text-[#173b5b]",
    },
    "flat-large": {
      border: "border border-card-border",
      bg: "bg-card-bg",
      shadow: "",
      rounded: "rounded-3xl",
      padding: "p-5 sm:p-6",
      extra: "text-[#173b5b]",
    },
    light: {
      border: "border border-card-border-light",
      bg: "bg-card-bg-light",
      shadow: "",
      rounded: "rounded-2xl",
      padding: "p-4",
      extra: "text-[#173b5b]",
    },
    dark: {
      border: "",
      bg: "bg-card-bg-dark",
      shadow: "",
      rounded: "rounded-3xl",
      padding: "p-5 sm:p-6",
      extra: "text-base-300",
    },
    mini: {
      border: "border border-card-border-mini",
      bg: "",
      shadow: "",
      rounded: "rounded-xl",
      padding: "p-3",
      extra: "text-[#173b5b]",
    },
  };

  const style = $derived(variantStyles[variant] || variantStyles.default);

  // Compute final styles using overrides if provided
  const finalBorder = $derived(border !== undefined ? border : style.border);
  const finalBg = $derived(bg !== undefined ? bg : style.bg);
  const finalShadow = $derived(shadow !== undefined ? shadow : style.shadow);
  const finalRounded = $derived(
    rounded !== undefined ? rounded : style.rounded,
  );
  const finalPadding = $derived(
    padding !== undefined ? padding : style.padding,
  );

  const classes = $derived(
    [
      finalBorder,
      finalBg,
      finalShadow,
      finalRounded,
      finalPadding,
      style.extra,
      className,
    ]
      .filter(Boolean)
      .join(" "),
  );
</script>

<svelte:element this={tag} class={classes}>
  {@render children?.()}
</svelte:element>
