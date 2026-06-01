<script lang="ts">
  import type { Snippet } from "svelte";

  let {
    children,
    title,
    class: className = "",
  }: {
    children?: Snippet;
    title?: string;
    class?: string;
  } = $props();
</script>

<section class={`card bg-base-100 shadow-sm ${className}`}>
  <div class="card-body">
    {#if title}
      <h2 class="card-title">{title}</h2>
    {/if}
    {@render children?.()}
  </div>
</section>
