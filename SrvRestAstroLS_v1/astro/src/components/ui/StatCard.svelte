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

<article class="rounded-2xl border border-[#e0e8ea] bg-white p-4 shadow-[0_18px_45px_-42px_rgba(16,45,79,0.7)] sm:p-5">
  <p class="text-[0.68rem] font-bold uppercase tracking-[0.15em] text-[#78909f]">{label}</p>
  <p class="mt-3 text-2xl font-bold tracking-[-0.06em] text-[#173b5b] sm:text-3xl">{value}</p>
  {#if trend}<p class="mt-2 text-xs font-bold text-[#168b88]">{trend}</p>{/if}
  {#if description}<p class="mt-2 text-xs leading-5 text-[#82939d]">{description}</p>{/if}
</article>
