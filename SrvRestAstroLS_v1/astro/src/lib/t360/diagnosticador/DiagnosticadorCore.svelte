<script lang="ts">
  import { onMount } from "svelte";
  import { PUBLIC_DIAGNOSIS_CONTEXT, sendPublicTurn } from "../../api/publicDiagnosis";
  import type { StructuredDiagnosis, TurnDecision, TurnLanguage } from "../../api/publicDiagnosis";
  import { loadPublicVeraSession, savePublicVeraSession, clearPublicVeraSession } from "../../publicVeraSession";
  import DiagnosisResult from "../../../components/diagnosis/DiagnosisResult.svelte";
  import { sectionTitle, isValidDiagnosis } from "../../api/diagnosisPresentation";
  import T360InteractionRenderer from "../interaction/T360InteractionRenderer.svelte";
  import { normalizeT360DiagnosisTurn } from "../diagnosis/normalizer";
  import { renderMarkdown } from "../diagnosis/markdown";
  import { t360InteractionEventToTurnRequest } from "../diagnosis/adapter";
  import type { T360InteractionEventDetail } from "../diagnosis/types";
  import type { T360MissingRequirement } from "../interaction/types";

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

  let {
    assistantName = "Diagnosticador",
    mailtoHref = "",
    sessionId = $bindable(null),
    messages = $bindable([]),
    inputText = $bindable(""),
    turnDisplayName = $bindable(""),
  }: {
    assistantName?: string;
    mailtoHref?: string;
    sessionId?: string | null;
    messages?: ChatMessage[];
    inputText?: string;
    turnDisplayName?: string;
  } = $props();
  let isLoading = $state(false);
  let chatError = $state("");
  let currentLocale = $state<string>(PUBLIC_DIAGNOSIS_CONTEXT.locale);
  let interactionEventRoot = $state<HTMLElement | undefined>();
  let consumedByMsgIdx = $state<Record<number, boolean>>({});

  const assistantDisplayName = $derived(turnDisplayName || assistantName);

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

  function isProductFitBlock(block: unknown): block is import("../interaction/types").T360ProductFitCardBlock {
    if (typeof block !== "object" || block === null) return false;
    const b = block as Record<string, unknown>;
    return b.type === "product_fit_card" && typeof b.product_code === "string" && typeof b.product_name === "string";
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
      if (result.assistant_display_name) {
        turnDisplayName = result.assistant_display_name;
      }
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
      chatError = sectionTitle("error_503", currentLocale, { name: assistantDisplayName });
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
    consumedByMsgIdx = {};
    clearPublicVeraSession();
  }

  onMount(() => {
    const eventNames = ["t360action", "t360choice", "t360choices"];
    const handler = (event: Event) => {
      if (!(event instanceof CustomEvent) || isLoading) return;

      for (let i = messages.length - 1; i >= 0; i--) {
        const m = messages[i];
        if (m.role === "assistant" && m.interactionBlock !== undefined) {
          if (consumedByMsgIdx[i]) return;
          consumedByMsgIdx = { ...consumedByMsgIdx, [i]: true };
          break;
        }
      }

      const turn = t360InteractionEventToTurnRequest(event.detail as T360InteractionEventDetail);
      void sendRuntimeMessage(turn.message, turn.display_text, false, turn.interaction_response as Record<string, unknown> | undefined);
    };
    const target = interactionEventRoot;
    if (!target) return;
    eventNames.forEach((eventName) => target.addEventListener(eventName, handler));
    return () => eventNames.forEach((eventName) => target.removeEventListener(eventName, handler));
  });
</script>

<div bind:this={interactionEventRoot} class="rounded-[1.75rem] border border-[#d7e5e7] bg-white p-5 shadow-[0_28px_70px_-58px_rgba(16,45,79,0.72)] sm:p-6" data-testid="diagnosticador-core">
  {#if messages.length === 0 && !sessionId}
    <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <p class="text-sm font-bold text-[#153854]">{assistantDisplayName}</p>
        <p class="mt-1 text-xs font-semibold text-[#78909f]">{PUBLIC_DIAGNOSIS_CONTEXT.service_code}</p>
      </div>
      <span class="inline-flex w-fit rounded-full bg-[#e8f7f5] px-3 py-1 text-[0.68rem] font-bold uppercase tracking-[0.12em] text-[#168b88]">
        Conversación
      </span>
    </div>

    <label class="mt-5 block">
      <span class="sr-only">Mensaje para {assistantDisplayName}</span>
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
      {#if mailtoHref}
        <a
          data-testid="public-vera-mailto"
          class="inline-flex min-h-12 justify-center rounded-full border border-[#c9dcdd] bg-white px-5 py-3 text-sm font-bold text-[#244966] transition hover:border-[#9fc8c7] hover:bg-[#f7fbfa] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#168b88]"
          href={mailtoHref}
        >
          Solicitar revisión
        </a>
      {/if}
    </div>
  {:else}
    <div class="flex items-center justify-between gap-2">
      <div>
        <p class="text-sm font-bold text-[#153854]">{assistantDisplayName}</p>
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
      {#each messages as msg, i}
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
                actionButtons={extracted.actionButtons as import("../interaction/types").T360Action[]}
                actionBlockType={extracted.blockType as import("../interaction/types").T360InteractionKind}
                actionSessionId={msg.sessionId ?? sessionId ?? ""}
                actionDisabled={isLoading || (consumedByMsgIdx[i] ?? false)}
                productFitData={isProductFitBlock(msg.interactionBlock) ? msg.interactionBlock : null}
              />
            </div>
          {/if}
          {#if msg.interactionBlock !== undefined && !(isMissingRequirementsBlock(msg.interactionBlock) && msg.diagnosis) && !(isActionCardBlock(msg.interactionBlock) && msg.diagnosis) && !(isProductFitBlock(msg.interactionBlock) && msg.diagnosis)}
            <div
              class="w-full"
              data-testid="public-vera-interaction-block"
              data-valid={msg.interactionBlockValid ? "true" : "false"}
            >
              <T360InteractionRenderer
                block={msg.interactionBlock}
                sessionId={msg.sessionId ?? sessionId ?? ""}
                disabled={isLoading || (consumedByMsgIdx[i] ?? false)}
                consumed={consumedByMsgIdx[i] ?? false}
              />
            </div>
          {/if}
        {/if}
      {/each}
      {#if isLoading}
        <div class="self-start flex items-center gap-2 rounded-2xl rounded-bl-sm border border-[#d5e2e5] bg-white px-4 py-2.5 text-sm text-[#78909f]">
          <span class="inline-block h-2 w-2 animate-pulse rounded-full bg-[#168b88]"></span>
          {assistantDisplayName} está escribiendo...
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
      {#if mailtoHref}
        <a
          class="text-xs font-medium text-[#78909f] underline transition hover:text-[#476275]"
          href={mailtoHref}
        >
          Solicitar revisión por correo
        </a>
      {/if}
      <p class="text-[0.6rem] text-[#91a2ad]">
        Turno {messages.filter(m => m.role === 'user').length}
      </p>
    </div>
  {/if}
</div>
