<script lang="ts">
  import { PUBLIC_DIAGNOSIS_CONTEXT, startPublicDiagnosis } from "../../lib/api/publicDiagnosis";
  import type { PublicDiagnosisResponse } from "../../lib/api/publicDiagnosis";

  type EntryState = "idle" | "submitting" | "response" | "error";

  const examples = [
    "Recibo leads por WhatsApp y no sé quién los sigue.",
    "Quiero medir campañas de Facebook contra ventas.",
    "Tengo reportes en Excel que armamos manualmente.",
  ];

  let state = $state<EntryState>("idle");
  let text = $state("");
  let responseMessage = $state("");
  let errorMessage = $state("");
  let visitorAnonymousId = $state("");
  let lastResponse = $state<PublicDiagnosisResponse | null>(null);

  const canSubmit = $derived(text.trim().length > 0 && state !== "submitting");
  const mailHref = $derived.by(() => {
    const subject = encodeURIComponent("Solicitar revisión con Vera");
    const body = encodeURIComponent(`Hola Team360,\n\nQuiero revisar esta oportunidad de automatización:\n\n${text.trim()}\n\nGracias.`);
    return `mailto:contacto@team360.live?subject=${subject}&body=${body}`;
  });

  function ensureVisitorAnonymousId(): string {
    if (visitorAnonymousId) {
      return visitorAnonymousId;
    }

    const storageKey = "team360_public_visitor_id";
    const existing = window.localStorage.getItem(storageKey);

    if (existing) {
      visitorAnonymousId = existing;
      return existing;
    }

    const generated = window.crypto?.randomUUID?.() ?? `anon_${Date.now()}_${Math.random().toString(36).slice(2)}`;
    window.localStorage.setItem(storageKey, generated);
    visitorAnonymousId = generated;
    return generated;
  }

  function useExample(example: string) {
    text = example;
    state = "idle";
    errorMessage = "";
    responseMessage = "";
    lastResponse = null;
  }

  async function handleSubmit(event: SubmitEvent) {
    event.preventDefault();

    const trimmed = text.trim();
    if (!trimmed || state === "submitting") {
      return;
    }

    state = "submitting";
    errorMessage = "";
    responseMessage = "";
    lastResponse = null;

    try {
      const result = await startPublicDiagnosis({
        text: trimmed,
        sourceUrl: window.location.href,
        visitorAnonymousId: ensureVisitorAnonymousId(),
      });
      responseMessage = result.message;
      lastResponse = result;
      state = "response";
    } catch {
      errorMessage = "No pudimos iniciar el diagnóstico automático ahora. Podés contactarnos y enviarnos este resumen.";
      state = "error";
    }
  }

  const CLASSIFICATION_LABELS: Record<string, string> = {
    standard_package: "Paquete estándar",
    operational_automation: "Automatización operativa",
    consulting_required: "Requiere consultoría",
    not_recommended: "No recomendado ahora",
  };

  const MODE_LABELS: Record<string, string> = {
    read_only: "Solo consulta",
    assisted: "Con supervisión humana",
    approval_required: "Requiere aprobación",
    execution: "Automatizable",
    blocked: "No recomendado",
  };

  const PRIORITY_LABELS: Record<string, string> = {
    "90": "Alta factibilidad",
    "80": "Buena factibilidad",
    "70": "Factibilidad media",
    "60": "Factibilidad media",
    "50": "Factibilidad baja",
    "40": "Factibilidad baja",
    "30": "Factibilidad baja",
    "20": "Complejo",
    "10": "Complejo",
    "0": "Muy complejo",
  };

  function scoreLabel(score: number): string {
    return PRIORITY_LABELS[String(Math.floor(score / 10) * 10)] ?? `Puntaje: ${score}`;
  }

  function classificationLabel(key: string): string {
    return CLASSIFICATION_LABELS[key] ?? key;
  }

  function modeLabel(key: string): string {
    return MODE_LABELS[key] ?? key;
  }

  function formatRiskFlags(flags: string[]): string {
    if (!flags || flags.length === 0) return "Sin riesgos relevantes.";
    return flags.slice(0, 4).join(" · ");
  }
</script>

<section id="vera" class="scroll-mt-24 border-y border-[#dbe7e9] bg-[#f6fbfa] py-20 sm:py-24" data-testid="public-vera-entry">
  <div class="mx-auto grid max-w-7xl gap-10 px-5 sm:px-8 lg:grid-cols-[0.82fr_1.18fr] lg:items-start lg:px-10">
    <div>
      <p class="text-xs font-bold uppercase tracking-[0.2em] text-[#168b88]">Diagnóstico abierto</p>
      <h2 class="mt-4 text-4xl font-semibold leading-tight tracking-[-0.06em] text-[#102d4f] sm:text-5xl">
        Hablá con Vera
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

    <form class="rounded-[1.75rem] border border-[#d7e5e7] bg-white p-5 shadow-[0_28px_70px_-58px_rgba(16,45,79,0.72)] sm:p-6" onsubmit={handleSubmit}>
      <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p class="text-sm font-bold text-[#153854]">Asistente Inteligente Vera</p>
          <p class="mt-1 text-xs font-semibold text-[#78909f]">{PUBLIC_DIAGNOSIS_CONTEXT.service_code}</p>
        </div>
        <span class="inline-flex w-fit rounded-full bg-[#e8f7f5] px-3 py-1 text-[0.68rem] font-bold uppercase tracking-[0.12em] text-[#168b88]">
          Texto libre
        </span>
      </div>

      <label class="mt-5 block">
        <span class="sr-only">Resumen del proceso a mejorar</span>
        <textarea
          bind:value={text}
          data-testid="public-vera-text"
          rows="7"
          class="min-h-44 w-full resize-y rounded-2xl border border-[#d5e2e5] bg-[#fbfdfc] px-4 py-4 text-base leading-7 text-[#203c55] outline-none transition placeholder:text-[#91a2ad] focus:border-[#168b88] focus:ring-2 focus:ring-[#168b88]/20"
          placeholder="Ejemplo: recibimos consultas por WhatsApp, email y formularios. Hoy nadie sabe rápido quién respondió, qué lead quedó pendiente y qué campaña trajo cada venta..."
        ></textarea>
      </label>

      <div class="mt-5 flex flex-col gap-3 sm:flex-row sm:items-center">
        <button
          type="submit"
          data-testid="public-vera-submit"
          disabled={!canSubmit}
          class="inline-flex min-h-12 justify-center rounded-full bg-[#168b88] px-6 py-3 text-sm font-bold text-white transition hover:bg-[#126d6b] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#168b88] disabled:cursor-not-allowed disabled:opacity-45"
        >
          {state === "submitting" ? "Analizando..." : "Analizar oportunidad"}
        </button>
        <a
          data-testid="public-vera-mailto"
          class="inline-flex min-h-12 justify-center rounded-full border border-[#c9dcdd] bg-white px-5 py-3 text-sm font-bold text-[#244966] transition hover:border-[#9fc8c7] hover:bg-[#f7fbfa] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#168b88]"
          href={mailHref}
        >
          Solicitar revisión
        </a>
      </div>

      {#if state === "response"}
        <div class="mt-5 rounded-2xl border border-[#bfe5df] bg-[#effaf8] p-4" data-testid="public-vera-response">
              {#if lastResponse?.diagnosis_real}
            <div class="flex items-center gap-2">
              <p class="text-sm font-bold text-[#126d6b]">Diagnóstico</p>
              <span class="rounded-full bg-[#21b99f]/15 px-2 py-0.5 text-[0.65rem] font-bold text-[#126d6b]">En línea</span>
            </div>
            <div class="mt-2 flex flex-wrap gap-1.5">
              {#if lastResponse.classification}
                <span class="rounded-full bg-[#102d4f]/10 px-2.5 py-1 text-[0.7rem] font-semibold text-[#102d4f]">{classificationLabel(lastResponse.classification)}</span>
              {/if}
              {#if lastResponse.score_total !== undefined}
                <span class="rounded-full bg-[#168b88]/10 px-2.5 py-1 text-[0.7rem] font-semibold text-[#168b88]">{scoreLabel(lastResponse.score_total)}</span>
              {/if}
              {#if lastResponse.automation_mode}
                <span class="rounded-full bg-[#102d4f]/10 px-2.5 py-1 text-[0.7rem] font-semibold text-[#102d4f]">{modeLabel(lastResponse.automation_mode)}</span>
              {/if}
            </div>
            {#if lastResponse.risk_flags && lastResponse.risk_flags.length > 0}
              <p class="mt-3 text-xs font-semibold text-[#8f6b2a]">Riesgos destacados: {formatRiskFlags(lastResponse.risk_flags)}</p>
            {/if}
            <p class="mt-2 whitespace-pre-line text-sm leading-6 text-[#476275]">{responseMessage}</p>
            <p class="mt-3 text-xs leading-5 text-[#6d8290]">
              Este es un diagnóstico inicial de orientación. No ejecuta acciones, no crea leads, no confirma por WhatsApp y no deriva datos sin autorización.
            </p>
          {:else}
            <p class="text-sm font-bold text-[#126d6b]">Vera respondió</p>
            <p class="mt-2 text-sm leading-6 text-[#476275]">{responseMessage}</p>
            <p class="mt-3 text-xs leading-5 text-[#6d8290]">
              Todavía no capturamos datos de contacto ni generamos un resultado final. Podés solicitar una revisión y enviar este resumen al equipo.
            </p>
          {/if}
        </div>
      {:else if state === "error"}
        <div class="mt-5 rounded-2xl border border-[#f3c7c7] bg-[#fff7f7] p-4" data-testid="public-vera-error">
          <p class="text-sm font-bold text-[#991b1b]">No se pudo iniciar ahora</p>
          <p class="mt-2 text-sm leading-6 text-[#8f3940]">{errorMessage}</p>
        </div>
      {:else}
        <p class="mt-5 text-xs leading-5 text-[#71878e]">
          La primera respuesta es preliminar. El diagnóstico completo y la captura de lead se habilitan en una etapa posterior.
        </p>
      {/if}
    </form>
  </div>
</section>
