<script lang="ts">
  import DiagnosticadorCore from "../../lib/t360/diagnosticador/DiagnosticadorCore.svelte";

  let { assistantName = "Diagnosticador" }: { assistantName?: string } = $props();

  let sessionId = $state<string | null>(null);
  let messages = $state<{ role: "user" | "assistant"; text: string }[]>([]);
  let inputText = $state("");
  let turnDisplayName = $state<string>("");

  const assistantDisplayName = $derived(turnDisplayName || assistantName);

  const examples = [
    "Recibo leads por WhatsApp y no sé quién los sigue.",
    "Quiero medir campañas de Facebook contra ventas.",
    "Tengo reportes en Excel que armamos manualmente.",
  ];

  const mailHref = $derived.by(() => {
    const label = assistantDisplayName;
    const subject = encodeURIComponent(`Solicitar revisión con ${label}`);
    const body = encodeURIComponent(
      messages.length > 0
        ? `Conversación con ${label}:\n\n${messages.map(m => `${m.role === 'user' ? 'Usuario' : label}: ${m.text}`).join("\n")}\n\nGracias.`
        : "Hola Team360,\n\nQuiero revisar esta oportunidad de automatización.\n\nGracias."
    );
    return `mailto:contacto@team360.live?subject=${subject}&body=${body}`;
  });

  function useExample(example: string) {
    inputText = example;
  }
</script>

<section
  id="vera"
  class="scroll-mt-24 border-y border-[#dbe7e9] bg-[#f6fbfa] py-20 sm:py-24"
  data-testid="public-vera-entry"
>
  <div class="mx-auto grid max-w-7xl gap-10 px-5 sm:px-8 lg:grid-cols-[0.82fr_1.18fr] lg:items-start lg:px-10">
    <div>
      <p class="text-xs font-bold uppercase tracking-[0.2em] text-[#168b88]">Diagnóstico abierto</p>
      <h2 class="mt-4 text-4xl font-semibold leading-tight tracking-[-0.06em] text-[#102d4f] sm:text-5xl">
        Hablá con {assistantDisplayName}
      </h2>
      <p class="mt-5 max-w-xl text-base leading-7 text-[#5b7283] sm:text-lg">
        Contanos qué proceso querés mejorar o automatizar.
      </p>
      <p class="mt-4 max-w-xl text-sm leading-6 text-[#6d8290]">
        No necesitás completar un formulario. Escribí en tus palabras qué querés mejorar.
      </p>

      <div class="mt-7 space-y-2">
        {#each examples as example}
          <button
            type="button"
            class="block w-full rounded-2xl border border-[#d6e5e6] bg-white/75 px-4 py-3 text-left text-sm font-semibold leading-5 text-[#476275] transition hover:border-[#9fd4cf] hover:bg-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#168b88]"
            onclick={() => useExample(example)}
          >
            {example}
          </button>
        {/each}
      </div>
    </div>

    <DiagnosticadorCore
      bind:sessionId
      bind:messages
      bind:inputText
      bind:turnDisplayName
      {assistantName}
      mailtoHref={mailHref}
    />
  </div>
</section>
