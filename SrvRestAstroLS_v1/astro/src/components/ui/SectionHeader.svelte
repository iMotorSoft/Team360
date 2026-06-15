<script lang="ts">
  import type { Snippet } from "svelte";
  import { Card } from ".";

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

<Card variant="dark">
  <div>
    <p class="text-sm font-bold uppercase tracking-[0.15em] text-base-400">
      {eyebrow}
    </p>
    <h1 class="title-h1">{title}</h1>
    <p class="mt-3 max-w-3xl text-lg leading-6 text-base-300">{description}</p>
  </div>
  {#if actions}
    <div class="shrink-0">{@render actions()}</div>
  {/if}
</Card>
