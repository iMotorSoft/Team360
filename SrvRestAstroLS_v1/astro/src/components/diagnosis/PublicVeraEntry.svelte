<script lang="ts">
  import { onMount } from "svelte";
  import { PUBLIC_DIAGNOSIS_CONTEXT, sendPublicTurn } from "../../lib/api/publicDiagnosis";
  import type { StructuredDiagnosis, TurnDecision, TurnLanguage } from "../../lib/api/publicDiagnosis";
  import { loadPublicVeraSession, savePublicVeraSession, clearPublicVeraSession } from "../../lib/publicVeraSession";
  import DiagnosisResult from "./DiagnosisResult.svelte";
  import { sectionTitle, isValidDiagnosis } from "../../lib/api/diagnosisPresentation";
  import T360InteractionRenderer from "../../lib/t360/interaction/T360InteractionRenderer.svelte";
  import { normalizeT360DiagnosisTurn } from "../../lib/t360/diagnosis/normalizer";
  import { renderMarkdown } from "../../lib/t360/diagnosis/markdown";
  import { t360InteractionEventToTurnRequest } from "../../lib/t360/diagnosis/adapter";
  import type { T360InteractionEventDetail } from "../../lib/t360/diagnosis/types";
  import type { T360MissingRequirement } from "../../lib/t360/interaction/types";

  interface ChatMessage {
    role: "user" | "assistant";
    text: string;
    diagnosis?: StructuredDiagnosis | null;
    interactionBlock?: unknown;
    interactionBlockValid?: boolean;
    sessionId?: string;
    isFallback?: boolean;
    turnDecision?: TurnDecision | null;
  }

  const examples = [
    "Recibo leads por WhatsApp y no sé quién los sigue.",
    "Quiero medir campañas de Facebook contra ventas.",
    "Tengo reportes en Excel que armamos manualmente.",
  ];

  let sessionId = $state<string | null>(null);
  let messages = $state<ChatMessage[]>([]);
  let inputText = $state("");
  let isLoading = $state(false);
  let chatError = $state("");
  let currentLocale = $state<string>(PUBLIC_DIAGNOSIS_CONTEXT.locale);
  let interactionEventRoot = $state<HTMLElement | undefined>();

  const canSend = $derived(inputText.trim().length > 0 && !isLoading);

  function restoreSession() {
    const session = loadPublicVeraSession();
    if (session.session_id) {
      savePublicVeraSession({
        session_id: null,
        initial_language: session.initial_language,
        current_language: session.current_language,
        preferred_response_language: session.preferred_response_language,
        explicit_language_preference: session.explicit_language_preference,
      });
      sessionId = null;
    }
    const updated = loadPublicVeraSession();
    if (updated.preferred_response_language) {
      currentLocale = updated.preferred_response_language;
    }
  }

  function persistSession(langInfo: TurnLanguage | null | undefined) {
    const session = loadPublicVeraSession();
    savePublicVeraSession({
      session_id: sessionId,
      initial_language: langInfo?.initial_language || session.initial_language || currentLocale,
      current_language: langInfo?.current_language || currentLocale,
      preferred_response_language: langInfo?.preferred_response_language || currentLocale,
      explicit_language_preference: Boolean(langInfo?.explicit_language_preference),
    });
    if (langInfo?.preferred_response_language) {
      currentLocale = langInfo.preferred_response_language;
    }
  }

  restoreSession();

  function useExample(example: string) {
    inputText = example;
  }

  function scrollToBottom() {
    requestAnimationFrame(() => {
      const container = document.querySelector("[data-chat-messages]");
      if (container) container.scrollTop = container.scrollHeight;
    });
  }

  function getDiagnosis(diagnosis: StructuredDiagnosis | null | undefined): StructuredDiagnosis | null {
    if (isValidDiagnosis(diagnosis)) {
      return diagnosis;
    }
    return null;
  }

  function isGenerationFallback(td: TurnDecision | null | undefined): boolean {
    return td?.generation?.status === "fallback";
  }

  function isActionCardBlock(block: unknown): block is { type: "next_step_choice" | "diagnosis_action_card"; actions?: unknown[]; primary_action?: unknown; secondary_actions?: unknown[] } {
    if (typeof block !== "object" || block === null) return false;
    const b = block as Record<string, unknown>;
    return b.type === "next_step_choice" || b.type === "diagnosis_action_card";
  }

  function extractActionButtons(block: unknown, sessionId: string): { actionButtons: unknown[]; blockType: string } {
    if (!isActionCardBlock(block)) return { actionButtons: [], blockType: "diagnosis_action_card" };
    const b = block as Record<string, unknown>;
    if (b.type === "next_step_choice") {
      return { actionButtons: (b.actions as unknown[]) ?? [], blockType: "next_step_choice" };
    }
    const primary = b.primary_action;
    const secondary = (b.secondary_actions as unknown[]) ?? [];
    return {
      actionButtons: primary ? [primary, ...secondary] : secondary,
      blockType: "diagnosis_action_card",
    };
  }

  function isMissingRequirementsBlock(block: unknown): block is { type: "missing_requirements"; requirements: T360MissingRequirement[] } {
    return (
      typeof block === "object" &&
      block !== null &&
      (block as Record<string, unknown>).type === "missing_requirements" &&
      Array.isArray((block as Record<string, unknown>).requirements)
    );
  }

  function extractCompactRequirements(block: unknown): T360MissingRequirement[] {
    if (isMissingRequirementsBlock(block)) {
      return block.requirements;
    }
    return [];
  }

  function stripDiagnosisMarkdown(text: string): string {
    const idx = text.search(/\n#{1,3}\s/);
    if (idx === -1) return text;
    return text.slice(0, idx).trim();
  }

  async function sendRuntimeMessage(text: string, displayText = text, clearComposer = true, interactionResponse?: Record<string, unknown>) {
    const requestText = text.trim();
    const userText = displayText.trim();
    if (!requestText || isLoading) return;

    messages = [...messages, { role: "user", text: userText || requestText }];
    if (clearComposer) {
      inputText = "";
    }
    isLoading = true;
    chatError = "";
    scrollToBottom();

    try {
      const result = normalizeT360DiagnosisTurn(await sendPublicTurn({
        session_id: sessionId ?? undefined,
        message: requestText,
        locale: currentLocale,
        interaction_response: interactionResponse,
      }));
      sessionId = result.session_id;
      const turnDecision = result.turn_decision ?? null;
      const diagnosis = getDiagnosis(result.diagnosis);
      const isFallback = isGenerationFallback(turnDecision);

      messages = [
        ...messages,
        {
          role: "assistant",
          text: result.assistant_text,
          diagnosis,
          interactionBlock: result.has_interaction_block_payload ? result.interaction_block : undefined,
          interactionBlockValid: result.interaction_block_valid,
          sessionId: result.session_id,
          isFallback,
          turnDecision,
        },
      ];
      persistSession(result.language);
    } catch {
      chatError = sectionTitle("error_503", currentLocale);
    } finally {
      isLoading = false;
      scrollToBottom();
    }
  }

  async function sendMessage() {
    const text = inputText.trim();
    if (!text || isLoading) return;

    await sendRuntimeMessage(text);
  }

  function newConversation() {
    sessionId = null;
    messages = [];
    inputText = "";
    chatError = "";
    clearPublicVeraSession();
  }

  const mailHref = $derived.by(() => {
    const subject = encodeURIComponent("Solicitar revisión con Vera");
    const body = encodeURIComponent(
      messages.length > 0
        ? `Conversación con Vera:\n\n${messages.map(m => `${m.role === 'user' ? 'Usuario' : 'Vera'}: ${m.text}`).join("\n")}\n\nGracias.`
        : "Hola Team360,\n\nQuiero revisar esta oportunidad de automatización.\n\nGracias."
    );
    return `mailto:contacto@team360.live?subject=${subject}&body=${body}`;
  });

  onMount(() => {
    const eventNames = ["t360action", "t360choice", "t360choices"];
    const handler = (event: Event) => {
      if (!(event instanceof CustomEvent) || isLoading) return;
      const turn = t360InteractionEventToTurnRequest(event.detail as T360InteractionEventDetail);
      void sendRuntimeMessage(turn.message, turn.display_text, false, turn.interaction_response as Record<string, unknown> | undefined);
    };
    const target = interactionEventRoot;
    if (!target) return;
    eventNames.forEach((eventName) => target.addEventListener(eventName, handler));
    return () => eventNames.forEach((eventName) => target.removeEventListener(eventName, handler));
  });
</script>

<section
  id="vera"
  bind:this={interactionEventRoot}
  class="scroll-mt-24 border-y border-[#dbe7e9] bg-[#f6fbfa] py-20 sm:py-24"
  data-testid="public-vera-entry"
>
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

    <div class="rounded-[1.75rem] border border-[#d7e5e7] bg-white p-5 shadow-[0_28px_70px_-58px_rgba(16,45,79,0.72)] sm:p-6">
      {#if messages.length === 0 && !sessionId}
        <!-- Initial state: show header + textarea -->
        <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p class="text-sm font-bold text-[#153854]">Asistente Inteligente Vera</p>
            <p class="mt-1 text-xs font-semibold text-[#78909f]">{PUBLIC_DIAGNOSIS_CONTEXT.service_code}</p>
          </div>
          <span class="inline-flex w-fit rounded-full bg-[#e8f7f5] px-3 py-1 text-[0.68rem] font-bold uppercase tracking-[0.12em] text-[#168b88]">
            Conversación
          </span>
        </div>

        <label class="mt-5 block">
          <span class="sr-only">Mensaje para Vera</span>
          <textarea
            bind:value={inputText}
            data-testid="public-vera-text"
            rows="5"
            class="min-h-36 w-full resize-y rounded-2xl border border-[#d5e2e5] bg-[#fbfdfc] px-4 py-4 text-base leading-7 text-[#203c55] outline-none transition placeholder:text-[#91a2ad] focus:border-[#168b88] focus:ring-2 focus:ring-[#168b88]/20"
            placeholder="Ejemplo: recibimos consultas por WhatsApp, email y formularios. Hoy nadie sabe rápido quién respondió, qué lead quedó pendiente y qué campaña trajo cada venta..."
          ></textarea>
        </label>

        <div class="mt-5 flex flex-col gap-3 sm:flex-row sm:items-center">
          <button
            type="button"
            data-testid="public-vera-submit"
            disabled={!canSend}
            class="inline-flex min-h-12 justify-center rounded-full bg-[#168b88] px-6 py-3 text-sm font-bold text-white transition hover:bg-[#126d6b] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#168b88] disabled:cursor-not-allowed disabled:opacity-45"
            onclick={sendMessage}
          >
            {isLoading ? "Analizando..." : "Enviar"}
          </button>
          <a
            data-testid="public-vera-mailto"
            class="inline-flex min-h-12 justify-center rounded-full border border-[#c9dcdd] bg-white px-5 py-3 text-sm font-bold text-[#244966] transition hover:border-[#9fc8c7] hover:bg-[#f7fbfa] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#168b88]"
            href={mailHref}
          >
            Solicitar revisión
          </a>
        </div>
      {:else}
        <!-- Chat mode -->
        <div class="flex items-center justify-between gap-2">
          <div>
            <p class="text-sm font-bold text-[#153854]">Asistente Inteligente Vera</p>
            <p class="mt-1 text-xs font-semibold text-[#78909f]">
              {PUBLIC_DIAGNOSIS_CONTEXT.service_code}
              {#if sessionId}
                <span class="ml-1 text-[0.6rem] text-[#91a2ad]">· {sessionId.slice(0, 16)}…</span>
              {/if}
            </p>
          </div>
          <button
            type="button"
            data-testid="public-vera-new-conversation"
            class="rounded-full border border-[#c9dcdd] px-3 py-1.5 text-[0.65rem] font-semibold text-[#476275] transition hover:border-[#9fc8c7] hover:bg-[#f7fbfa]"
            onclick={newConversation}
          >
            Nueva conversación
          </button>
        </div>

        <div
          data-chat-messages
          class="mt-4 flex max-h-96 flex-col gap-3 overflow-y-auto rounded-2xl border border-[#d5e2e5] bg-[#fbfdfc] p-3"
        >
          {#each messages as msg}
            {#if msg.role === "user"}
              <div data-testid="public-vera-user-message" class="self-end max-w-[85%] rounded-2xl rounded-br-sm bg-[#168b88] px-4 py-2.5 text-sm leading-6 text-white">
                {msg.text}
              </div>
            {:else}
              {@const displayText = (msg.diagnosis && msg.interactionBlock !== undefined)
                ? stripDiagnosisMarkdown(msg.text)
                : msg.text}
              <div data-testid="public-vera-assistant-message" class="self-start max-w-full rounded-2xl rounded-bl-sm border border-[#d5e2e5] bg-white px-4 py-2.5 text-sm leading-6 text-[#203c55] [&_ul]:list-disc [&_ul]:pl-5 [&_li]:mb-0.5 [&_p]:mb-2 [&_p:last-child]:mb-0 [&_strong]:font-semibold [&_a]:underline [&_a]:text-[#168b88] [&_code]:rounded [&_code]:bg-[#f0f4f5] [&_code]:px-1 [&_code]:text-xs">
                {@html renderMarkdown(displayText)}
              </div>
              {#if msg.diagnosis}
                {@const extracted = extractActionButtons(msg.interactionBlock, msg.sessionId ?? sessionId ?? "")}
                <div class="w-full">
                  <DiagnosisResult
                    diagnosis={msg.diagnosis}
                    isFallback={msg.isFallback ?? false}
                    locale={currentLocale}
                    compactMissingRequirements={extractCompactRequirements(msg.interactionBlock)}
                    actionButtons={extracted.actionButtons as import("../../lib/t360/interaction/types").T360Action[]}
                    actionBlockType={extracted.blockType as import("../../lib/t360/interaction/types").T360InteractionKind}
                    actionSessionId={msg.sessionId ?? sessionId ?? ""}
                    actionDisabled={isLoading}
                  />
                </div>
              {/if}
              {#if msg.interactionBlock !== undefined && !(isMissingRequirementsBlock(msg.interactionBlock) && msg.diagnosis) && !(isActionCardBlock(msg.interactionBlock) && msg.diagnosis)}
                <div
                  class="w-full"
                  data-testid="public-vera-interaction-block"
                  data-valid={msg.interactionBlockValid ? "true" : "false"}
                >
                  <T360InteractionRenderer
                    block={msg.interactionBlock}
                    sessionId={msg.sessionId ?? sessionId ?? ""}
                    disabled={isLoading}
                  />
                </div>
              {/if}
            {/if}
          {/each}
          {#if isLoading}
            <div class="self-start flex items-center gap-2 rounded-2xl rounded-bl-sm border border-[#d5e2e5] bg-white px-4 py-2.5 text-sm text-[#78909f]">
              <span class="inline-block h-2 w-2 animate-pulse rounded-full bg-[#168b88]"></span>
              Vera está escribiendo...
            </div>
          {/if}
        </div>

        {#if chatError}
          <div data-testid="public-vera-error" class="mt-3 rounded-2xl border border-[#f3c7c7] bg-[#fff7f7] p-3 text-sm leading-5 text-[#8f3940]">
            {chatError}
          </div>
        {/if}

        <div class="mt-4 flex gap-2">
          <textarea
            bind:value={inputText}
            data-testid="public-vera-chat-input"
            rows="2"
            class="min-h-[3.5rem] flex-1 resize-none rounded-2xl border border-[#d5e2e5] bg-[#fbfdfc] px-4 py-3 text-sm leading-5 text-[#203c55] outline-none transition placeholder:text-[#91a2ad] focus:border-[#168b88] focus:ring-2 focus:ring-[#168b88]/20"
            placeholder="Escribí tu mensaje..."
          ></textarea>
          <button
            type="button"
            data-testid="public-vera-chat-submit"
            disabled={!canSend}
            class="inline-flex min-h-[3.5rem] items-center justify-center rounded-full bg-[#168b88] px-5 text-sm font-bold text-white transition hover:bg-[#126d6b] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#168b88] disabled:cursor-not-allowed disabled:opacity-45"
            onclick={sendMessage}
          >
            {isLoading ? "..." : "Enviar"}
          </button>
        </div>

        <div class="mt-3 flex items-center justify-between">
          <a
            class="text-xs font-medium text-[#78909f] underline transition hover:text-[#476275]"
            href={mailHref}
          >
            Solicitar revisión por correo
          </a>
          <p class="text-[0.6rem] text-[#91a2ad]">
            Turno {messages.filter(m => m.role === 'user').length}
          </p>
        </div>
      {/if}
    </div>
  </div>
</section>
