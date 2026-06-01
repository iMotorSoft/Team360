<script lang="ts">
  import type { Snippet } from "svelte";

  let {
    eyebrow,
    title,
    description,
    actions,
  }: {
    eyebrow: string;
    title: string;
    description: string;
    actions?: Snippet;
  } = $props();
</script>

<header class="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
  <div>
    <p class="text-xs font-bold uppercase tracking-[0.2em] text-[#168b88]">{eyebrow}</p>
    <h1 class="mt-2 text-3xl font-bold tracking-[-0.055em] text-[#102d4f] sm:text-4xl">{title}</h1>
    <p class="mt-3 max-w-3xl text-sm leading-6 text-[#69808f]">{description}</p>
  </div>
  {#if actions}
    <div class="shrink-0">{@render actions()}</div>
  {/if}
</header>
