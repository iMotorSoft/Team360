<script lang="ts">
  import type { Snippet } from "svelte";

  let {
    children,
    label,
    class: className = "",
  }: {
    children?: Snippet;
    label: string;
    class?: string;
  } = $props();

</script>

<div class={`overflow-hidden rounded-3xl border border-card-border bg-card-bg shadow-card-large ${className}`}>
  <div
    aria-label={label}
    class="overflow-x-auto"
    role="region"
  >
    {@render children?.()}
  </div>
</div>
