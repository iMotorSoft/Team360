<script lang="ts">
  import type { Snippet } from "svelte";

  let {
    children,
    title,
    tag = "section",
    variant = "default",
    class: className = "",
  }: {
    children?: Snippet;
    title?: string;
    tag?: "article" | "aside" | "div" | "section";
    variant?: "default" | "large" | "flat" | "light" | "dark" | "mini";
    class?: string;
  } = $props();

  const variantClasses = {
    default: "rounded-2xl border border-card-border bg-card-bg p-5 shadow-card-default",
    large: "rounded-3xl border border-card-border bg-card-bg p-5 shadow-card-large sm:p-6",
    flat: "rounded-2xl border border-card-border bg-card-bg p-5",
    light: "rounded-2xl border border-card-border-light bg-card-bg-light p-4",
    dark: "rounded-3xl bg-card-bg-dark p-5 text-white shadow-card-large sm:p-6",
    mini: "rounded-xl border border-card-border-mini p-3",
  } as const;
</script>

<svelte:element this={tag} class={`${variantClasses[variant]} ${className}`}>
  {#if title}
    <h2 class="text-xl font-bold tracking-[-0.035em] text-console-title">{title}</h2>
  {/if}
  {@render children?.()}
</svelte:element>
