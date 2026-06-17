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

<div>
  <p class="top-badge">
    {eyebrow}
  </p>
  <h1 class="title-h1">{title}</h1>
  <p class="max-w-3xl details-text">{description}</p>
</div>
{#if actions}
  <div class="shrink-0">{@render actions()}</div>
{/if}
