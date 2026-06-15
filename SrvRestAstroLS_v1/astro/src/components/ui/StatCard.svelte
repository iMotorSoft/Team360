<script lang="ts">
  import Card from "./Card.svelte";

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

<Card variant="default" padding="p-4 sm:p-5">
  <p class="top-badge-neutral">{label}</p>
  <p
    class="mt-3 text-2xl font-bold tracking-[-0.06em] text-[#173b5b] sm:text-3xl"
  >
    {value}
  </p>
  {#if trend}<p class="mt-2 text-base font-bold text-[#168b88]">{trend}</p>{/if}
  {#if description}<p class="mt-2 text-base leading-5 text-[#82939d]">
      {description}
    </p>{/if}
</Card>
