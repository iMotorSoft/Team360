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

<section
  class={`flex flex-col items-center justify-center rounded-2xl border-3 border-dashed border-slate-300 bg-slate-50/50 px-6 py-12 text-center ${className}`}
>
  <p class="top-badge mb-3">{eyebrowByVariant[variant]}</p>
  <h2 class="text-xl font-bold text-[#31536b]">{title}</h2>
  <p class="mt-2 max-w-md text-lg leading-relaxed text-[#78909f]">
    {description}
  </p>
  {#if nextStep}
    <p
      class="mt-4 rounded-lg px-3 py-1.5 text-base border border-slate-300 font-medium text-[#587184]"
    >
      Próximo paso: {nextStep}
    </p>
  {/if}
  {#if actions}
    <div class="mt-6">{@render actions()}</div>
  {/if}
</section>
