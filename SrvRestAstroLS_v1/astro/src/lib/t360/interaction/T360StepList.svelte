<script lang="ts">
  let {
    items = [],
    ordered = false,
    emptyLabel = "Sin datos para mostrar",
  }: {
    items?: string[];
    ordered?: boolean;
    emptyLabel?: string;
  } = $props();
</script>

{#if items.length > 0}
  {#if ordered}
    <ol class="flex flex-col gap-2">
      {#each items as item, index}
        <li class="flex items-start gap-2 text-sm leading-6 text-base-content/75">
          <span class="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-base-200 text-[0.68rem] font-bold text-base-content/70">
            {index + 1}
          </span>
          <span>{item}</span>
        </li>
      {/each}
    </ol>
  {:else}
    <ul class="flex flex-col gap-2">
      {#each items as item}
        <li class="flex items-start gap-2 text-sm leading-6 text-base-content/75">
          <span class="mt-2 size-1.5 shrink-0 rounded-full bg-primary"></span>
          <span>{item}</span>
        </li>
      {/each}
    </ul>
  {/if}
{:else}
  <p class="text-sm text-base-content/55">{emptyLabel}</p>
{/if}
