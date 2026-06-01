<script lang="ts">
  let {
    label = "Cargando…",
    class: className = "",
  }: {
    label?: string;
    class?: string;
  } = $props();
</script>

<span class={`inline-flex items-center gap-2 ${className}`} role="status">
  <span class="loading loading-spinner loading-sm" aria-hidden="true"></span>
  <span aria-live="polite">{label}</span>
</span>
