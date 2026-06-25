<script lang="ts">
  import { onMount } from "svelte";
  import { Loading, Alert, Badge, Card } from "../../ui";
  import {
    startSession,
    saveAnswer,
    classifySession,
    GUIDED_STEPS,
    OPTION_LABELS,
    type DiagnosisSession,
    type DiagnosisResult,
  } from "../../../lib/api/diagnosis";

  let { assistantName = "Diagnosticador" }: { assistantName?: string } = $props();

  type FlowState = "idle" | "starting" | "answering" | "classifying" | "result" | "error";

  let state = $state<FlowState>("idle");
  let session = $state<DiagnosisSession | null>(null);
  let result = $state<DiagnosisResult | null>(null);
  let currentStepIndex = $state(0);
  let errorMessage = $state("");
  let isHydrated = $state(false);

  let textInput = $state("");
  let selectedOptions = $state<string[]>([]);

  const displayName = $derived(session?.assistant_display_name || assistantName);

  const currentStep = $derived(GUIDED_STEPS[currentStepIndex]);
  const totalSteps = GUIDED_STEPS.length;
  const progress = $derived(Math.round(((currentStepIndex + (state === "result" ? 1 : 0)) / totalSteps) * 100));
  const isFirstStep = $derived(currentStepIndex === 0);
  const isLastStep = $derived(currentStepIndex === totalSteps - 1);
  const isTextStep = $derived(currentStep.type === "controlled_text");
  const isMultiChoice = $derived(currentStep.type === "multi_choice_with_text");
  const isSingleChoice = $derived(currentStep.type === "single_choice_with_text");
  const canProceed = $derived(
    isTextStep ? textInput.trim().length > 0 : selectedOptions.length > 0,
  );

  const classificationInfo = $derived.by(() => {
    if (!result) return null;
    const labels: Record<string, { title: string; desc: string; variant: string }> = {
      standard_package: {
        title: "Paquete estándar",
        desc: "Este caso califica para un paquete de automatización Team360. Se recomienda agendar una revisión de alcance.",
        variant: "success",
      },
      operational_automation: {
        title: "Automatización operativa",
        desc: "Este caso puede resolverse con automatización operativa asistida. Se recomienda una llamada de descubrimiento técnico.",
        variant: "info",
      },
      consulting_required: {
        title: "Requiere consultoría",
        desc: "Este caso requiere un análisis más profundo antes de recomendar automatización. Aplica una consultoría paga o mapeo de procesos.",
        variant: "warning",
      },
      not_recommended: {
        title: "No recomendado",
        desc: "Por razones de seguridad, cumplimiento o viabilidad, este proceso no se recomienda para automatización en este momento.",
        variant: "danger",
      },
    };
    return labels[result.classification] ?? { title: result.classification, desc: "", variant: "neutral" };
  });

  onMount(() => {
    isHydrated = true;
  });

  function reset() {
    state = "idle";
    session = null;
    result = null;
    currentStepIndex = 0;
    textInput = "";
    selectedOptions = [];
    errorMessage = "";
  }

  async function handleStart() {
    state = "starting";
    errorMessage = "";
    try {
      session = await startSession({
        source_url: window.location.href,
        locale: "es",
      });
      state = "answering";
    } catch (err: unknown) {
      state = "error";
      errorMessage = err instanceof Object && "detail" in (err as Record<string, unknown>)
        ? (err as Record<string, string>).detail
        : "No se pudo iniciar la sesión de diagnóstico. Verifique que el backend esté corriendo.";
    }
  }

  function toggleOption(option: string) {
    if (isSingleChoice) {
      selectedOptions = [option];
    } else {
      if (selectedOptions.includes(option)) {
        selectedOptions = selectedOptions.filter((o) => o !== option);
      } else {
        selectedOptions = [...selectedOptions, option];
      }
    }
  }

  async function handleNext() {
    if (!session || !canProceed) return;

    const answer = isTextStep
      ? { free_text: textInput }
      : { selected: selectedOptions };

    try {
      await saveAnswer(session.id, currentStep.id, answer);
      textInput = "";
      selectedOptions = [];

      if (isLastStep) {
        state = "classifying";
        result = await classifySession(session.id);
        state = "result";
      } else {
        currentStepIndex++;
      }
    } catch (err: unknown) {
      errorMessage = err instanceof Object && "detail" in (err as Record<string, unknown>)
        ? (err as Record<string, string>).detail
        : "Error al guardar la respuesta.";
    }
  }
</script>

<section data-testid="diagnosis-root" data-hydrated={isHydrated ? "true" : "false"}>
  <div class="mb-6">
    <p class="text-xs font-bold uppercase tracking-[0.2em] text-[#168b88]">
      {state === "result" ? "Resultado del diagnóstico" : "Diagnóstico de automatización"}
    </p>
    <h1 class="mt-2 text-3xl font-bold tracking-[-0.055em] text-[#102d4f] sm:text-4xl">
      {state === "idle"
        ? displayName
        : state === "starting"
          ? "Iniciando..."
          : state === "error"
            ? "Error"
            : state === "result"
              ? "Resultado"
              : `Pregunta ${currentStepIndex + 1} de ${totalSteps}`}
    </h1>
  </div>

  {#if state === "idle"}
    <div data-testid="diagnosis-welcome">
      <Card class="p-6 sm:p-8">
        <div class="max-w-2xl">
          <p class="text-sm leading-6 text-[#567184]">
            Responda este cuestionario guiado para recibir un diagnóstico preliminar
            de automatización para su proceso. El asistente analizará sus respuestas
            y recomendará el tipo de solución más adecuado.
          </p>
          <ul class="mt-4 space-y-2 text-sm text-[#69808f]">
            <li class="flex items-start gap-2">
              <span class="mt-0.5 text-[#168b88]">•</span>
              <span>{totalSteps} preguntas sobre el proceso a automatizar</span>
            </li>
            <li class="flex items-start gap-2">
              <span class="mt-0.5 text-[#168b88]">•</span>
              <span>Análisis con IA y reglas de negocio</span>
            </li>
            <li class="flex items-start gap-2">
              <span class="mt-0.5 text-[#168b88]">•</span>
              <span>Recomendación de paquete y próximos pasos</span>
            </li>
          </ul>
          <button
            onclick={handleStart}
            data-testid="btn-start-diagnosis"
            class="mt-6 inline-flex items-center gap-2 rounded-full bg-[#168b88] px-6 py-2.5 text-sm font-bold text-white transition hover:bg-[#126d6b]"
          >
            Comenzar diagnóstico
          </button>
        </div>
      </Card>
    </div>

  {:else if state === "starting"}
    <Loading />

  {:else if state === "error"}
    <div class="rounded-2xl border border-[#fecaca] bg-[#fef2f2] p-6" data-testid="diagnosis-error">
      <p class="text-sm font-bold text-[#991b1b]">Error</p>
      <p class="mt-2 text-sm text-[#b91c1c]">{errorMessage}</p>
      <button
        onclick={reset}
        data-testid="btn-retry"
        class="mt-4 rounded-full bg-[#991b1b] px-4 py-2 text-xs font-bold text-white transition hover:bg-[#7f1d1d]"
      >
        Reintentar
      </button>
    </div>

  {:else if state === "answering"}
    <div class="mb-6">
      <div class="h-2 w-full overflow-hidden rounded-full bg-[#e0e8ea]">
        <div
          class="h-full rounded-full bg-[#168b88] transition-all duration-300"
          style="width: {progress}%"
        ></div>
      </div>
      <p class="mt-2 text-xs text-[#8396a2]">{currentStepIndex + 1} de {totalSteps}</p>
    </div>

    <div data-testid="question-card" data-step-id={currentStep.id}>
      <Card class="p-6 sm:p-8">
        <h2 class="text-xl font-bold tracking-[-0.03em] text-[#173b5b]">{currentStep.label}</h2>
        <p class="mt-2 text-sm leading-6 text-[#567184]">{currentStep.description}</p>

        {#if isTextStep}
          <div class="mt-5">
            <textarea
              bind:value={textInput}
              data-testid="answer-textarea"
              rows="4"
              class="w-full rounded-xl border border-[#d5e0e2] bg-white px-4 py-3 text-sm text-[#203c55] outline-none transition focus:border-[#168b88] focus:ring-2 focus:ring-[#168b88]/20"
              placeholder="Escriba su respuesta aquí..."
            ></textarea>
          </div>

        {:else if currentStep.options}
          <div class="mt-5 grid gap-2 sm:grid-cols-2">
            {#each currentStep.options as option}
              <button
                onclick={() => toggleOption(option)}
                data-testid="option-{option}"
                class="rounded-xl border px-4 py-3 text-start text-sm leading-5 transition
                  {selectedOptions.includes(option)
                    ? 'border-[#168b88] bg-[#f0fafa] text-[#126d6b] font-bold'
                    : 'border-[#d5e0e2] text-[#567184] hover:border-[#a0b8be]'}"
              >
                {OPTION_LABELS[option] ?? option}
              </button>
            {/each}
          </div>
        {/if}

        <div class="mt-6 flex items-center justify-between">
          <button
            onclick={() => {
              if (isFirstStep) { reset(); } else { currentStepIndex--; textInput = ""; selectedOptions = []; }
            }}
            data-testid="btn-back"
            class="rounded-full border border-[#d5e0e2] px-4 py-2 text-xs font-bold text-[#567184] transition hover:border-[#a0b8be]"
          >
            {isFirstStep ? "Cancelar" : "Anterior"}
          </button>

          <button
            onclick={handleNext}
            disabled={!canProceed}
            data-testid="btn-next"
            class="rounded-full bg-[#168b88] px-6 py-2 text-xs font-bold text-white transition hover:bg-[#126d6b] disabled:opacity-40"
          >
            {isLastStep ? "Clasificar" : "Siguiente"}
          </button>
        </div>
      </Card>
    </div>

  {:else if state === "classifying"}
    <div data-testid="diagnosis-classifying">
      <Card class="p-8 text-center">
        <Loading />
        <p class="mt-4 text-sm font-bold text-[#31536b]">Analizando respuestas...</p>
        <p class="mt-2 text-xs text-[#8396a2]">{displayName} está procesando el diagnóstico.</p>
      </Card>
    </div>

  {:else if state === "result" && result}
    <div class="grid gap-6 lg:grid-cols-[1fr_18rem]" data-testid="diagnosis-result">
      <div class="space-y-5">
        <Card class="p-6">
          <div class="flex items-start justify-between gap-4">
            <div>
              <p class="text-xs font-bold uppercase tracking-[0.16em] text-[#168b88]">Diagnóstico</p>
              <h2 class="mt-2 text-2xl font-bold tracking-[-0.04em] text-[#102d4f]">{classificationInfo?.title}</h2>
              <p class="mt-3 text-sm leading-6 text-[#567184]">{classificationInfo?.desc}</p>
            </div>
            {#if classificationInfo}
              <span data-testid="result-classification">
                <Badge
                  variant={classificationInfo.variant as "success" | "warning" | "danger" | "info" | "neutral"}
                  class="h-auto shrink-0 px-3 py-1.5 text-[0.65rem]"
                >
                  {result.classification}
                </Badge>
              </span>
            {/if}
          </div>
        </Card>

        <Card class="p-6">
          <p class="text-xs font-bold uppercase tracking-[0.16em] text-[#168b88]">Detalles</p>
          <dl class="mt-4 grid gap-3 sm:grid-cols-2">
            <div class="rounded-xl bg-[#f3f8f8] p-3">
              <dt class="text-[0.65rem] font-bold uppercase tracking-[0.12em] text-[#78909f]">Puntaje</dt>
              <dd class="mt-1 text-2xl font-bold tracking-[-0.04em] text-[#173b5b]" data-testid="result-score">{result.score_total}</dd>
            </div>
            <div class="rounded-xl bg-[#f3f8f8] p-3">
              <dt class="text-[0.65rem] font-bold uppercase tracking-[0.12em] text-[#78909f]">Modo</dt>
              <dd class="mt-1 text-sm font-bold text-[#173b5b]" data-testid="result-mode">{result.automation_mode}</dd>
            </div>
            <div class="rounded-xl bg-[#f3f8f8] p-3">
              <dt class="text-[0.65rem] font-bold uppercase tracking-[0.12em] text-[#78909f]">Paquete</dt>
              <dd class="mt-1 text-sm font-bold text-[#173b5b]" data-testid="result-package">{result.recommended_package_type}</dd>
            </div>
            <div class="rounded-xl bg-[#f3f8f8] p-3">
              <dt class="text-[0.65rem] font-bold uppercase tracking-[0.12em] text-[#78909f]">Aprobación humana</dt>
              <dd class="mt-1 text-sm font-bold text-[#173b5b]" data-testid="result-human-approval">{result.requires_human_approval ? "Requerida" : "No requerida"}</dd>
            </div>
          </dl>
        </Card>

        {#if result.risk_flags.length > 0}
          <Card class="p-6" data-testid="result-risk-flags">
            <p class="text-xs font-bold uppercase tracking-[0.16em] text-[#b91c1c]">Riesgos detectados</p>
            <ul class="mt-4 space-y-2">
              {#each result.risk_flags as flag}
                <li class="flex items-start gap-2 text-sm text-[#991b1b]">
                  <span class="mt-0.5 shrink-0">⚠</span>
                  <span>{flag}</span>
                </li>
              {/each}
            </ul>
          </Card>
        {/if}

        {#if result.blocked_actions.length > 0}
          <Card class="p-6" data-testid="result-blocked-actions">
            <p class="text-xs font-bold uppercase tracking-[0.16em] text-[#b91c1c]">Acciones bloqueadas</p>
            <ul class="mt-4 space-y-2">
              {#each result.blocked_actions as action}
                <li class="flex items-start gap-2 text-sm text-[#991b1b]">
                  <span class="mt-0.5 shrink-0">✕</span>
                  <span>{action}</span>
                </li>
              {/each}
            </ul>
          </Card>
        {/if}

        {#if result.score_breakdown}
          <Card class="p-6" data-testid="result-score-breakdown">
            <p class="text-xs font-bold uppercase tracking-[0.16em] text-[#168b88]">Desglose de puntaje</p>
            <dl class="mt-4 grid gap-2 sm:grid-cols-3">
              {#each Object.entries(result.score_breakdown) as [key, value]}
                <div class="rounded-xl border border-[#e0e8ea] p-3">
                  <dt class="text-[0.6rem] font-bold uppercase tracking-[0.12em] text-[#78909f]">{key}</dt>
                  <dd class="mt-1 text-lg font-bold text-[#173b5b]">{value}</dd>
                </div>
              {/each}
            </dl>
          </Card>
        {/if}
      </div>

      <aside class="space-y-4" data-testid="result-aside">
        <Card class="p-5" data-testid="result-recommendation">
          <p class="text-xs font-bold uppercase tracking-[0.16em] text-[#168b88]">Recomendación</p>
          <p class="mt-3 text-sm leading-6 text-[#567184]" data-testid="result-next-step">
            {result.internal_card?.next_step === "package_scope_review"
              ? "Agendar revisión de alcance para el paquete recomendado."
              : result.internal_card?.next_step === "technical_discovery_call"
                ? "Coordinar llamada de descubrimiento técnico."
                : result.internal_card?.next_step === "paid_discovery_or_process_mapping"
                  ? "Iniciar proceso de consultoría o mapeo de procesos."
                  : "Evaluar alternativa manual o rechazar automatización."}
          </p>
        </Card>

        {#if result.suggested_worker_definitions.length > 0}
          <Card class="p-5" data-testid="result-suggested-workers">
            <p class="text-xs font-bold uppercase tracking-[0.16em] text-[#168b88]">Workers sugeridos</p>
            <ul class="mt-3 space-y-2">
              {#each result.suggested_worker_definitions as def}
                <li class="text-sm text-[#47657b]">• {def}</li>
              {/each}
            </ul>
          </Card>
        {/if}

        <button
          onclick={reset}
          data-testid="btn-new-diagnosis"
          class="w-full rounded-full bg-[#168b88] px-6 py-2.5 text-sm font-bold text-white transition hover:bg-[#126d6b]"
        >
          Nuevo diagnóstico
        </button>
      </aside>
    </div>
  {/if}
</section>
