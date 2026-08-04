<script lang="ts">
  let {
    label,
    value,
    description,
    trend,
  }: {
    label: string;
    value: string;
    description?: string;
    trend?: string;
  } = $props();
</script>

<article class="rounded-2xl border border-card-border bg-card-bg p-4 shadow-card-default sm:p-5">
  <p class="text-[0.68rem] font-bold uppercase tracking-[0.15em] text-console-muted">{label}</p>
  <p class="mt-3 text-2xl font-bold tracking-[-0.06em] text-console-title sm:text-3xl">{value}</p>
  {#if trend}<p class="mt-2 text-xs font-bold text-console-brand">{trend}</p>{/if}
  {#if description}<p class="mt-2 text-xs leading-5 text-[#82939d]">{description}</p>{/if}
</article>
