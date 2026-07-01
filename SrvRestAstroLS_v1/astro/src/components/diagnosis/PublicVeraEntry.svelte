<script lang="ts">
  import {
    PUBLIC_DIAGNOSIS_CONTEXT,
    sendPublicTurn,
  } from "../../lib/api/publicDiagnosis";
  import type {
    StructuredDiagnosis,
    TurnDecision,
    TurnLanguage,
  } from "../../lib/api/publicDiagnosis";
  import {
    loadPublicVeraSession,
    savePublicVeraSession,
    clearPublicVeraSession,
  } from "../../lib/publicVeraSession";
  import DiagnosisResult from "./DiagnosisResult.svelte";
  import {
    sectionTitle,
    isValidDiagnosis,
  } from "../../lib/api/diagnosisPresentation";

  interface ChatMessage {
    role: "user" | "assistant";
    text: string;
    diagnosis?: StructuredDiagnosis | null;
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
  let showDeleteConfirm = $state(false);

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
      initial_language:
        langInfo?.initial_language || session.initial_language || currentLocale,
      current_language: langInfo?.current_language || currentLocale,
      preferred_response_language:
        langInfo?.preferred_response_language || currentLocale,
      explicit_language_preference: Boolean(
        langInfo?.explicit_language_preference,
      ),
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

  function getDiagnosis(
    diagnosis: StructuredDiagnosis | null | undefined,
  ): StructuredDiagnosis | null {
    if (isValidDiagnosis(diagnosis)) {
      return diagnosis;
    }
    return null;
  }

  function isGenerationFallback(td: TurnDecision | null | undefined): boolean {
    return td?.generation?.status === "fallback";
  }

  async function sendMessage() {
    const text = inputText.trim();
    if (!text || isLoading) return;

    messages = [...messages, { role: "user", text }];
    inputText = "";
    isLoading = true;
    chatError = "";
    scrollToBottom();

    try {
      const result = await sendPublicTurn({
        session_id: sessionId ?? undefined,
        message: text,
        locale: currentLocale,
      });
      sessionId = result.session_id;
      const turnDecision = result.turn_decision ?? null;
      const diagnosis = getDiagnosis(result.diagnosis);
      const isFallback = isGenerationFallback(turnDecision);

      messages = [
        ...messages,
        {
          role: "assistant",
          text: result.response_text,
          diagnosis,
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

  function newConversation() {
    sessionId = null;
    messages = [];
    inputText = "";
    chatError = "";
    clearPublicVeraSession();
    showDeleteConfirm = false;
  }

  const mailHref = $derived.by(() => {
    const subject = encodeURIComponent("Solicitar revisión con Vera");
    const body = encodeURIComponent(
      messages.length > 0
        ? `Conversación con Vera:\n\n${messages.map((m) => `${m.role === "user" ? "Usuario" : "Vera"}: ${m.text}`).join("\n")}\n\nGracias.`
        : "Hola Team360,\n\nQuiero revisar esta oportunidad de automatización.\n\nGracias.",
    );
    return `mailto:contacto@team360.live?subject=${subject}&body=${body}`;
  });
</script>

<section
  id="vera"
  class="scroll-mt-24 border-y border-[#dbe7e9] bg-[#f6fbfa] py-20 sm:py-24"
  data-testid="public-vera-entry"
>
  <div
    class="mx-auto grid max-w-7xl gap-10 px-5 sm:px-8 lg:grid-cols-[0.82fr_1.18fr] lg:items-start lg:px-10"
  >
    <div>
      <p class="top-badge">Diagnóstico abierto</p>
      <h2
        class="mt-4 text-4xl font-semibold leading-tight tracking-[-0.01em]
        text-[#102d4f] sm:text-5xl"
      >
        Hablá con Vera
      </h2>
      <p
        class="mt-5 max-w-xl font-poppins text-base leading-7 text-[#5b7283] md:text-2xl"
      >
        Contanos qué proceso querés mejorar o automatizar.
      </p>
      <p class="mt-4 max-w-xl text-sm leading-6 text-[#6d8290] md:text-lg">
        No necesitás completar un formulario. Escribí en tus palabras qué querés
        mejorar.
      </p>

      <div class="mt-7 space-y-2">
        {#each examples as example}
          <button
            type="button"
            class="block w-full rounded-2xl border border-[#d6e5e6] bg-white/75 px-4
            py-3 text-left text-sm md:text-base font-semibold leading-5 text-[#476275] transition
            hover:border-[#9fd4cf] hover:bg-white focus-visible:outline-2
            focus-visible:outline-offset-2 focus-visible:outline-[#168b88]"
            onclick={() => useExample(example)}
          >
            {example}
          </button>
        {/each}
      </div>
    </div>

    <div
      class="rounded-[1.75rem] border border-[#d7e5e7] bg-white p-5 shadow-[0_28px_70px_-58px_rgba(16,45,79,0.72)] sm:p-6"
    >
      {#if messages.length === 0 && !sessionId}
        <!-- Initial state: show header + textarea -->
        <div
          class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"
        >
          <div>
            <p
              class="text-sm md:text-base font-bold text-[#153854] font-poppins"
            >
              Asistente Inteligente Vera
            </p>
            <p class="mt-1 text-xs md:text-sm font-semibold text-[#78909f]">
              {PUBLIC_DIAGNOSIS_CONTEXT.service_code}
            </p>
          </div>
          <span
            class="inline-flex w-fit rounded-full bg-[#e8f7f5] px-3 py-1 md:text-xs text-[0.68rem] font-bold uppercase tracking-[0.12em] text-[#168b88]"
          >
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
            class="inline-flex min-h-12 justify-center rounded-full bg-primary
            px-6 py-3 text-sm md:text-base font-bold text-white transition hover:bg-[#126d6b]
            focus-visible:outline-2 focus-visible:outline-offset-2
            focus-visible:outline-primary disabled:cursor-not-allowed
            disabled:bg-gray-300"
            onclick={sendMessage}
          >
            {isLoading ? "Analizando..." : "Enviar"}
          </button>
          <a
            data-testid="public-vera-mailto"
            class="inline-flex min-h-12 justify-center rounded-full border
            border-[#c9dcdd] bg-white px-5 py-3 text-sm md:text-base font-bold text-[#244966]
            transition hover:border-[#9fc8c7] hover:bg-[#f7fbfa] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#168b88]"
            href={mailHref}
          >
            Solicitar revisión
          </a>
        </div>
      {:else}
        <!-- Chat mode -->
        <div class="flex items-center justify-between gap-2">
          <div>
            <p class="text-sm font-bold text-[#153854]">
              Asistente Inteligente Vera
            </p>
            <p class="mt-1 text-xs font-semibold text-[#78909f]">
              {PUBLIC_DIAGNOSIS_CONTEXT.service_code}
              {#if sessionId}
                <span class="ml-1 text-[0.6rem] text-[#91a2ad]"
                  >· {sessionId.slice(0, 16)}…</span
                >
              {/if}
            </p>
          </div>
          <button
            type="button"
            data-testid="public-vera-new-conversation"
            class="flex items-center justify-center rounded-full cursor-pointer border border-[#c9dcdd] p-2 text-[#476275] transition hover:border-[#f3c7c7] hover:bg-[#fff7f7] hover:text-[#8f3940]"
            aria-label="Eliminar conversación"
            title="Eliminar conversación"
            onclick={() => (showDeleteConfirm = true)}
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
              <path d="M3 6h18" />
              <path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6" />
              <path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2" />
              <line x1="10" x2="10" y1="11" y2="17" />
              <line x1="14" x2="14" y1="11" y2="17" />
            </svg>
          </button>
        </div>

        <div
          data-chat-messages
          class="mt-4 flex max-h-96 flex-col gap-3 overflow-y-auto rounded-2xl border border-[#d5e2e5] bg-[#fbfdfc] p-3"
        >
          {#each messages as msg}
            {#if msg.role === "user"}
              <div
                data-testid="public-vera-user-message"
                class="self-end max-w-[85%] rounded-2xl rounded-br-sm bg-[#168b88] px-4 py-2.5 text-sm leading-6 text-white"
              >
                {msg.text}
              </div>
            {:else}
              <div
                data-testid="public-vera-assistant-message"
                class="self-start max-w-full rounded-2xl rounded-bl-sm border border-[#d5e2e5] bg-white px-4 py-2.5 text-sm leading-6 text-[#203c55]"
              >
                {msg.text}
              </div>
              {#if msg.diagnosis}
                <div class="w-full">
                  <DiagnosisResult
                    diagnosis={msg.diagnosis}
                    isFallback={msg.isFallback ?? false}
                    locale={currentLocale}
                  />
                </div>
              {/if}
            {/if}
          {/each}
          {#if isLoading}
            <div
              class="self-start flex items-center gap-2 rounded-2xl rounded-bl-sm border border-[#d5e2e5] bg-white px-4 py-2.5 text-sm text-[#78909f]"
            >
              <span
                class="inline-block h-2 w-2 animate-pulse rounded-full bg-[#168b88]"
              ></span>
              Vera está escribiendo...
            </div>
          {/if}
        </div>

        {#if chatError}
          <div
            data-testid="public-vera-error"
            class="mt-3 rounded-2xl border border-[#f3c7c7] bg-[#fff7f7] p-3 text-sm leading-5 text-[#8f3940]"
          >
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
            class="inline-flex h-[3.5rem] w-[3.5rem] shrink-0 items-center justify-center rounded-full bg-[#168b88] text-white transition hover:bg-[#126d6b] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#168b88] disabled:cursor-not-allowed disabled:opacity-45"
            aria-label="Enviar"
            title="Enviar"
            onclick={sendMessage}
          >
            {#if isLoading}
              <svg
                class="animate-spin h-5 w-5"
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
              >
                <circle
                  class="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  stroke-width="4"
                ></circle>
                <path
                  class="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                ></path>
              </svg>
            {:else}
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width="22"
                height="22"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
                class="-ml-1"
              >
                <path d="m22 2-7 20-4-9-9-4Z" />
                <path d="M22 2 11 13" />
              </svg>
            {/if}
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
            Turno {messages.filter((m) => m.role === "user").length}
          </p>
        </div>
      {/if}
    </div>
  </div>

  {#if showDeleteConfirm}
    <!-- svelte-ignore a11y_click_events_have_key_events -->
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div
      class="fixed inset-0 z-50 flex items-center justify-center bg-[#102d4f]/40 p-4 backdrop-blur-sm transition-opacity"
      onclick={(e) => {
        if (e.target === e.currentTarget) showDeleteConfirm = false;
      }}
    >
      <div class="w-full max-w-sm rounded-[1.5rem] bg-white p-6 shadow-2xl">
        <h3 class="text-lg font-bold text-[#153854] font-poppins">
          Eliminar conversación
        </h3>
        <p class="mt-2 text-sm text-[#5b7283]">
          ¿Estás seguro que querés eliminar la conversación actual? Esta acción
          no se puede deshacer.
        </p>
        <div class="mt-6 flex justify-end gap-3">
          <button
            type="button"
            class="rounded-full px-4 py-2 text-sm font-semibold text-[#476275] transition hover:bg-[#f6fbfa]"
            onclick={() => (showDeleteConfirm = false)}
          >
            Cancelar
          </button>
          <button
            type="button"
            class="rounded-full bg-[#8f3940] px-4 py-2 text-sm font-bold text-white transition hover:bg-[#722d33] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#8f3940]"
            onclick={newConversation}
          >
            Eliminar
          </button>
        </div>
      </div>
    </div>
  {/if}
</section>
