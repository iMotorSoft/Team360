<script lang="ts">
  import type { Snippet } from "svelte";

  type EmptyStateVariant = "empty" | "error" | "permission";

  let {
    title,
    description,
    nextStep,
    variant = "empty",
    actions,
    class: className = "",
  }: {
    title: string;
    description: string;
    nextStep?: string;
    variant?: EmptyStateVariant;
    actions?: Snippet;
    class?: string;
  } = $props();

  const eyebrowByVariant: Record<EmptyStateVariant, string> = {
    empty: "Sin datos todavía",
    error: "No se pudo mostrar la información",
    permission: "Visibilidad limitada",
  };
</script>

<section class={`rounded-2xl border border-dashed border-[#d7e3e5] bg-white/70 p-5 ${className}`}>
  <p class="text-[0.65rem] font-bold uppercase tracking-[0.16em] text-[#168b88]">{eyebrowByVariant[variant]}</p>
  <h2 class="mt-2 text-sm font-bold text-[#31536b]">{title}</h2>
  <p class="mt-2 max-w-2xl text-xs leading-5 text-[#78909f]">{description}</p>
  {#if nextStep}
    <p class="mt-3 text-xs font-semibold leading-5 text-[#587184]">Próximo paso: {nextStep}</p>
  {/if}
  {#if actions}
    <div class="mt-4">{@render actions()}</div>
  {/if}
</section>
