<script lang="ts">
  import { PUBLIC_DIAGNOSIS_CONTEXT, sendPublicTurn } from "../../lib/api/publicDiagnosis";
  import { loadPublicVeraSession, savePublicVeraSession, clearPublicVeraSession } from "../../lib/publicVeraSession";

  interface ChatMessage {
    role: "user" | "assistant";
    text: string;
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

  const canSend = $derived(inputText.trim().length > 0 && !isLoading);

  function restoreSession() {
    const session = loadPublicVeraSession();
    if (session.session_id) {
      sessionId = session.session_id;
    }
    if (session.preferred_response_language) {
      currentLocale = session.preferred_response_language;
    }
  }

  function persistSession(langInfo: Record<string, unknown> | null | undefined) {
    const session = loadPublicVeraSession();
    savePublicVeraSession({
      session_id: sessionId,
      initial_language: (langInfo as any)?.initial_language || session.initial_language || currentLocale,
      current_language: (langInfo as any)?.current_language || currentLocale,
      preferred_response_language: (langInfo as any)?.preferred_response_language || currentLocale,
      explicit_language_preference: Boolean((langInfo as any)?.explicit_language_preference),
    });
    if (langInfo && typeof (langInfo as any).preferred_response_language === "string") {
      currentLocale = (langInfo as any).preferred_response_language;
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
      messages = [...messages, { role: "assistant", text: result.response_text }];
      persistSession(result.language);
    } catch {
      chatError = "No pudimos procesar tu mensaje ahora. Podés intentar de nuevo o contactarnos por correo.";
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
              <div class="self-end max-w-[85%] rounded-2xl rounded-br-sm bg-[#168b88] px-4 py-2.5 text-sm leading-6 text-white">
                {msg.text}
              </div>
            {:else}
              <div class="self-start max-w-[85%] rounded-2xl rounded-bl-sm border border-[#d5e2e5] bg-white px-4 py-2.5 text-sm leading-6 text-[#203c55]">
                {msg.text}
              </div>
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
          <div class="mt-3 rounded-2xl border border-[#f3c7c7] bg-[#fff7f7] p-3 text-sm leading-5 text-[#8f3940]">
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
