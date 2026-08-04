<script lang="ts">
  import type { Snippet } from "svelte";

  let {
    eyebrow,
    title,
    description,
    actions,
    level = 1,
    class: className = "",
  }: {
    eyebrow: string;
    title: string;
    description: string;
    actions?: Snippet;
    level?: 1 | 2;
    class?: string;
  } = $props();
</script>

<header class={`flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between ${className}`}>
  <div class="min-w-0">
    <p class="text-xs font-bold uppercase tracking-[0.2em] text-console-brand">{eyebrow}</p>
    {#if level === 1}
      <h1 class="mt-2 text-3xl font-bold tracking-[-0.055em] text-console-title sm:text-4xl">{title}</h1>
    {:else}
      <h2 class="mt-2 text-xl font-bold tracking-[-0.035em] text-console-title sm:text-2xl">{title}</h2>
    {/if}
    <p class="mt-3 max-w-3xl text-sm leading-6 text-console-muted">{description}</p>
  </div>
  {#if actions}
    <div class="flex shrink-0 flex-wrap gap-2">{@render actions()}</div>
  {/if}
</header>
