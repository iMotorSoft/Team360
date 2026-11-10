<script lang="ts">
  import { onMount, tick } from "svelte";
  import { askLuna, verifyLunaSession, type LunaResult } from '../../lib/api/telchiLuna';

  type ExperienceState = "empty" | "processing" | "ready";

  const suggestions = [
    "Dame las ventas de septiembre",
    "¿Qué productos están vendiendo menos?",
    "¿Cómo están los almacenes?",
    "¿Qué clientes tienen deuda vencida?",
  ];

  type Turn = { question: string; answer?: string; result?: LunaResult; error?: string };
  let turns = $state<Turn[]>([]);
  let token = '';
  let authenticated = $state(false);
  let sessionMessage = $state('Cargá el archivo de sesión emitido por el login real de Console (CLI). No se utilizan perfiles mock.');
  let conversationId = '';
  let controller: AbortController | undefined;

  let query = $state("");
  let experienceState = $state<ExperienceState>("empty");
  let currentProgress = $state('');
  let historyOpen = $state(false);
  let textarea: HTMLTextAreaElement;
  let historyButton: HTMLButtonElement;
  let closeHistoryButton: HTMLButtonElement;
  const canSubmit = $derived(authenticated && query.trim().length > 0 && experienceState !== "processing");

  async function loadSession(event: Event) {
    const input = event.currentTarget as HTMLInputElement;
    const file = input.files?.[0];
    if (!file || experienceState === 'processing') return;
    token = '';
    authenticated = false;
    turns = [];
    experienceState = 'empty';
    conversationId = crypto.randomUUID();
    try {
      if (file.size > 16384) throw new Error('El archivo de sesión es demasiado grande.');
      const candidate = (await file.text()).trim();
      const session = await verifyLunaSession(candidate);
      token = candidate;
      authenticated = true;
      sessionMessage = `Sesión Console verificada · Workspace ${session.workspace}`;
    } catch (error) {
      sessionMessage = error instanceof Error ? error.message : 'No se pudo verificar la sesión.';
    } finally {
      input.value = '';
    }
  }

  function resizeTextarea() {
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 144)}px`;
  }

  async function useSuggestion(suggestion: string) {
    query = suggestion;
    await tick();
    resizeTextarea();
    textarea.focus();
  }

  async function submitQuery() {
    const cleanQuery = query.trim();
    if (!cleanQuery || !canSubmit) return;
    const index = turns.length;
    turns.push({ question: cleanQuery });
    query = '';
    experienceState = 'processing';
    currentProgress = 'Esperando la ejecución del servidor…';
    controller = new AbortController();
    const started = performance.now();
    void tick().then(resizeTextarea);
    try {
      const result = await askLuna(token, cleanQuery, conversationId, controller.signal,
        (message) => { currentProgress = message; });
      const answer = result.clarification || result.business_answer;
      if (!answer) throw new Error('La investigación terminó sin una respuesta acreditada. Podés reintentar; no asumimos un resultado.');
      turns[index] = { question: cleanQuery, answer, result: {
        ...result, elapsed_seconds: Math.round((performance.now() - started) / 100) / 10,
      } };
    } catch (error) {
      turns[index] = { question: cleanQuery, error: error instanceof Error ? error.message : 'No se pudo completar la investigación.' };
      // The bridge invalidates failed context. Never imply continuity after failure.
      conversationId = crypto.randomUUID();
      turns[index].error += ' El próximo turno iniciará un contexto nuevo; incluí nuevamente el período y los filtros.';
      query = cleanQuery;
    } finally {
      experienceState = 'ready';
      controller = undefined;
      void tick().then(resizeTextarea);
    }
  }

  function handleKeydown(event: KeyboardEvent) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submitQuery();
    }
  }

  function startNewConversation() {
    if (experienceState === 'processing') return;
    query = "";
    turns = [];
    conversationId = crypto.randomUUID();
    currentProgress = '';
    experienceState = "empty";
    void tick().then(() => {
      resizeTextarea();
      textarea.focus();
    });
  }

  async function openHistory() {
    historyOpen = true;
    await tick();
    closeHistoryButton?.focus();
  }

  function closeHistory() {
    historyOpen = false;
    void tick().then(() => historyButton?.focus());
  }

  function handleWindowKeydown(event: KeyboardEvent) {
    if (event.key === "Escape" && historyOpen) closeHistory();
  }

  onMount(() => {
    resizeTextarea();
    conversationId = crypto.randomUUID();
    return () => { controller?.abort(); token = ''; };
  });
</script>

<svelte:window onkeydown={handleWindowKeydown} />

<div class="telchiai-shell" data-testid="telchiai-shell" data-state={experienceState}>
  <header class="product-bar" aria-label="TelchiAI">
    <a class="product-identity" href="/telchiai" aria-label="TelchiAI, inicio">
      <span class="product-mark" aria-hidden="true">T</span>
      <span>Telchi<span class="ai-suffix">AI</span></span>
    </a>

    <button
      bind:this={historyButton}
      class="history-button"
      type="button"
      aria-haspopup="dialog"
      aria-expanded={historyOpen}
      onclick={openHistory}
    >
      <svg aria-hidden="true" viewBox="0 0 24 24">
        <path d="M3 12a9 9 0 1 0 3-6.7L3 8"></path>
        <path d="M3 3v5h5M12 7v5l3 2"></path>
      </svg>
      <span>Análisis anteriores</span>
    </button>
  </header>

  <section class="session-access" aria-label="Sesión empresarial">
    <p role="status">{sessionMessage}</p>
    <label>
      {authenticated ? 'Cambiar sesión Console' : 'Cargar sesión Console'}
      <input type="file" accept=".txt,.token,text/plain" onchange={loadSession} disabled={experienceState === 'processing'} />
    </label>
    <small>El token se mantiene solo en memoria hasta cerrar o recargar esta página. No cargues archivos de configuración ni claves privadas.</small>
  </section>

  <main id="contenido-telchiai" class:conversation-active={experienceState !== "empty"}>
    {#if experienceState === "empty"}
      <section class="welcome" aria-labelledby="welcome-title">
        <p class="eyebrow">Tu negocio, en palabras simples</p>
        <h1 id="welcome-title">¿Qué querés saber de Telchi?</h1>
        <p class="welcome-copy">Preguntá como lo harías normalmente. TelchiAI te ayuda a entender qué está pasando.</p>

        <form class="composer composer-primary" aria-label="Nueva consulta" onsubmit={(event) => { event.preventDefault(); submitQuery(); }}>
          <label class="sr-only" for="telchiai-query">Escribí una consulta sobre Telchi</label>
          <textarea
            bind:this={textarea}
            bind:value={query}
            id="telchiai-query"
            name="query"
            rows="1"
            enterkeyhint="send"
            autocomplete="off"
            placeholder="Escribí tu consulta…"
            aria-describedby="query-help"
            oninput={resizeTextarea}
            onkeydown={handleKeydown}
          ></textarea>
          <button class="send-button" type="submit" aria-label="Enviar consulta" disabled={!canSubmit}>
            <svg aria-hidden="true" viewBox="0 0 24 24">
              <path d="m5 12 14-7-4 14-3-6-7-1Z"></path>
              <path d="m12 13 7-8"></path>
            </svg>
          </button>
        </form>
        <p id="query-help" class="input-help">Enter para enviar · Shift + Enter para otra línea</p>

        <div class="suggestions" aria-labelledby="suggestions-title">
          <p id="suggestions-title">También podés preguntar</p>
          <div class="suggestion-list">
            {#each suggestions as suggestion}
              <button type="button" onclick={() => useSuggestion(suggestion)}>{suggestion}</button>
            {/each}
          </div>
        </div>
      </section>
    {:else}
      <section class="conversation" aria-label="Consulta actual">
        <div class="conversation-heading">
          <p>Consulta actual</p>
          {#if experienceState === "ready"}
            <button type="button" onclick={startNewConversation}>Nueva conversación</button>
          {/if}
        </div>

        {#each turns as turn}
          <article class="user-message" aria-label="Tu consulta"><p>{turn.question}</p></article>
          {#if turn.answer}
            <article class="prepared-state" aria-label="Respuesta de Luna">
              <p class="result-label">Luna · {turn.result?.status}</p>
              <p class="luna-answer">{turn.answer}</p>
              <small>Foundation {turn.result?.publication} · Snapshot {turn.result?.snapshot}</small>
              <p class="input-help">Cobertura: {turn.result?.question_coverage || 'Ver alcance y fechas efectivas en la respuesta'} · Tiempo completo: {turn.result?.elapsed_seconds} s</p>
            </article>
          {:else if turn.error}
            <p role="alert">{turn.error}</p>
          {/if}
        {/each}

        <div class="analysis-space" aria-live="polite" aria-busy={experienceState === "processing"}>
          {#if experienceState === "processing"}
            <div class="progress-state">
              <span class="progress-indicator" aria-hidden="true"><i></i><i></i><i></i></span>
              <div>
                <p>{currentProgress}</p>
                <span>La investigación puede demorar. Esta página conserva tus mensajes mientras esperás.</span>
              </div>
            </div>
          {/if}
        </div>

        <form class="composer composer-conversation" aria-label="Continuar consulta" onsubmit={(event) => { event.preventDefault(); submitQuery(); }}>
          <label class="sr-only" for="telchiai-follow-up">Continuá la consulta</label>
          <textarea
            bind:this={textarea}
            bind:value={query}
            id="telchiai-follow-up"
            name="follow-up"
            rows="1"
            enterkeyhint="send"
            autocomplete="off"
            placeholder="Continuá la consulta…"
            disabled={experienceState === "processing"}
            oninput={resizeTextarea}
            onkeydown={handleKeydown}
          ></textarea>
          <button class="send-button" type="submit" aria-label="Enviar continuación" disabled={!canSubmit}>
            <svg aria-hidden="true" viewBox="0 0 24 24">
              <path d="m5 12 14-7-4 14-3-6-7-1Z"></path>
              <path d="m12 13 7-8"></path>
            </svg>
          </button>
        </form>
      </section>
    {/if}
  </main>
</div>

{#if historyOpen}
  <div class="drawer-layer" role="presentation">
    <button class="drawer-backdrop" type="button" aria-label="Cerrar análisis anteriores" onclick={closeHistory}></button>
    <aside class="history-drawer" role="dialog" aria-modal="true" aria-labelledby="history-title">
      <div class="drawer-heading">
        <div>
          <p class="eyebrow">Memoria de TelchiAI</p>
          <h2 id="history-title">Análisis anteriores</h2>
        </div>
        <button bind:this={closeHistoryButton} class="close-button" type="button" aria-label="Cerrar" onclick={closeHistory}>
          <svg aria-hidden="true" viewBox="0 0 24 24"><path d="m6 6 12 12M18 6 6 18"></path></svg>
        </button>
      </div>
      <div class="history-empty">
        <span aria-hidden="true">01</span>
        <h3>Acá vas a encontrar tus análisis</h3>
        <p>La conversación actual permanece visible en esta página. El histórico persistente todavía no está disponible; recargar cierra la sesión y el contexto.</p>
      </div>
    </aside>
  </div>
{/if}

<style>
  .session-access { max-width: 850px; margin: 1rem auto; padding: 1rem; font-size: .85rem; }
  .session-access label { display: block; margin: .5rem 0; }
  .session-access input { display: block; max-width: 100%; }
  .luna-answer { white-space: pre-wrap; overflow-wrap: anywhere; }
  :global(body) {
    background: #f7fafb;
  }

  .telchiai-shell {
    min-height: calc(100svh - 73px);
    color: #143653;
  }

  .product-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    width: min(100% - 2rem, 72rem);
    margin-inline: auto;
    padding-block: 1rem;
  }

  .product-identity {
    display: inline-flex;
    align-items: center;
    gap: 0.65rem;
    color: #102d4f;
    font-family: var(--font-poppins);
    font-size: 1.08rem;
    font-weight: 700;
    letter-spacing: -0.035em;
  }

  .product-mark {
    display: grid;
    width: 2.25rem;
    height: 2.25rem;
    place-items: center;
    border-radius: 0.72rem;
    background: #102d4f;
    color: white;
    font-size: 0.95rem;
    letter-spacing: 0;
  }

  .ai-suffix { color: #168b88; }

  .history-button {
    display: inline-flex;
    min-height: 2.75rem;
    align-items: center;
    gap: 0.5rem;
    border-radius: 999px;
    padding-inline: 0.8rem;
    color: #587184;
    font-size: 0.78rem;
    font-weight: 650;
    transition: background 160ms ease, color 160ms ease;
  }

  .history-button:hover { background: #edf5f5; color: #193f5d; }
  .history-button svg { width: 1.1rem; fill: none; stroke: currentColor; stroke-linecap: round; stroke-linejoin: round; stroke-width: 1.7; }

  main {
    display: grid;
    min-height: calc(100svh - 145px);
    place-items: center;
    padding: 2.5rem 1rem max(2rem, env(safe-area-inset-bottom));
  }

  .welcome {
    width: min(100%, 46rem);
    text-align: center;
  }

  .eyebrow {
    color: #168b88;
    font-size: 0.7rem;
    font-weight: 750;
    letter-spacing: 0.14em;
    text-transform: uppercase;
  }

  h1 {
    max-width: 14ch;
    margin: 0.85rem auto 0;
    font-family: var(--font-poppins);
    font-size: clamp(2.15rem, 8.8vw, 4rem);
    font-weight: 600;
    letter-spacing: -0.055em;
    line-height: 1.06;
  }

  .welcome-copy {
    max-width: 34rem;
    margin: 1rem auto 0;
    color: #60798b;
    font-size: clamp(0.98rem, 2.7vw, 1.1rem);
    line-height: 1.7;
  }

  .composer {
    display: flex;
    align-items: flex-end;
    gap: 0.65rem;
    border: 1px solid #cfdddf;
    border-radius: 1.2rem;
    background: white;
    padding: 0.55rem;
    box-shadow: 0 20px 50px -38px rgba(16, 45, 79, 0.8);
    transition: border-color 160ms ease, box-shadow 160ms ease;
  }

  .composer:focus-within {
    border-color: #168b88;
    box-shadow: 0 0 0 3px rgba(22, 139, 136, 0.12), 0 24px 60px -42px rgba(16, 45, 79, 0.85);
  }

  .composer-primary { margin-top: 2rem; }

  textarea {
    min-width: 0;
    min-height: 3rem;
    flex: 1;
    resize: none;
    border: 0;
    background: transparent;
    padding: 0.75rem 0.65rem;
    color: #173b5b;
    font: inherit;
    font-size: 1rem;
    line-height: 1.5;
    outline: none;
    overflow-y: auto;
  }

  textarea::placeholder { color: #91a3ad; }
  textarea:disabled { cursor: wait; color: #879aa5; }

  .send-button {
    display: grid;
    width: 3rem;
    height: 3rem;
    flex: 0 0 auto;
    place-items: center;
    border-radius: 0.9rem;
    background: #102d4f;
    color: white;
    transition: background 160ms ease, transform 160ms ease, opacity 160ms ease;
  }

  .send-button:hover:not(:disabled) { background: #168b88; transform: translateY(-1px); }
  .send-button:disabled { cursor: not-allowed; opacity: 0.28; }
  .send-button svg { width: 1.25rem; fill: none; stroke: currentColor; stroke-linecap: round; stroke-linejoin: round; stroke-width: 1.8; }

  .input-help {
    margin-top: 0.65rem;
    color: #8a9ca6;
    font-size: 0.72rem;
  }

  .suggestions { margin-top: 2rem; }
  .suggestions > p { color: #79909e; font-size: 0.78rem; font-weight: 650; }

  .suggestion-list {
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: 0.55rem;
    margin-top: 0.8rem;
  }

  .suggestion-list button {
    min-height: 2.75rem;
    border: 1px solid #dbe5e6;
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.76);
    padding: 0.65rem 0.9rem;
    color: #506b7e;
    font-size: 0.78rem;
    font-weight: 600;
    transition: border-color 160ms ease, background 160ms ease, color 160ms ease;
  }

  .suggestion-list button:hover { border-color: #9bcac7; background: white; color: #174b61; }

  main.conversation-active { align-items: start; }
  .conversation { width: min(100%, 48rem); padding-top: 1.5rem; }

  .conversation-heading {
    display: flex;
    min-height: 2.75rem;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
  }

  .conversation-heading > p {
    color: #78909f;
    font-size: 0.72rem;
    font-weight: 750;
    letter-spacing: 0.12em;
    text-transform: uppercase;
  }

  .conversation-heading button {
    min-height: 2.75rem;
    color: #168b88;
    font-size: 0.78rem;
    font-weight: 700;
  }

  .user-message {
    width: fit-content;
    max-width: min(90%, 36rem);
    margin: 1rem 0 0 auto;
    border-radius: 1.15rem 1.15rem 0.3rem 1.15rem;
    background: #e9f3f5;
    padding: 0.9rem 1rem;
    color: #254b63;
    font-size: 0.95rem;
    line-height: 1.6;
  }

  .analysis-space { min-height: 15rem; padding: 2.5rem 0; }

  .progress-state {
    display: flex;
    align-items: center;
    gap: 0.9rem;
    color: #31566c;
  }

  .progress-state p { font-weight: 700; }
  .progress-state span { color: #8195a0; font-size: 0.78rem; }

  .progress-indicator { display: flex; gap: 0.22rem; }
  .progress-indicator i {
    width: 0.34rem;
    height: 0.34rem;
    border-radius: 999px;
    background: #168b88;
    animation: pulse 1.2s infinite ease-in-out;
  }
  .progress-indicator i:nth-child(2) { animation-delay: 120ms; }
  .progress-indicator i:nth-child(3) { animation-delay: 240ms; }

  .prepared-state {
    border-left: 2px solid #76c8c1;
    padding: 0.2rem 0 0.2rem 1.15rem;
  }
  .result-label { color: #168b88; font-size: 0.7rem; font-weight: 750; letter-spacing: 0.13em; text-transform: uppercase; }
  .prepared-state h2 { margin-top: 0.65rem; font-family: var(--font-poppins); font-size: 1.45rem; font-weight: 600; letter-spacing: -0.035em; }
  .prepared-state > p:last-child { max-width: 39rem; margin-top: 0.75rem; color: #657d8d; font-size: 0.9rem; line-height: 1.7; }
  .composer-conversation { position: sticky; bottom: max(1rem, env(safe-area-inset-bottom)); }

  .drawer-layer { position: fixed; inset: 0; z-index: 80; }
  .drawer-backdrop { position: absolute; inset: 0; width: 100%; height: 100%; background: rgba(10, 32, 48, 0.34); backdrop-filter: blur(2px); }
  .history-drawer {
    position: absolute;
    inset: 0 0 0 auto;
    width: min(100%, 27rem);
    overflow-y: auto;
    background: #fbfdfd;
    padding: max(1.25rem, env(safe-area-inset-top)) 1.25rem max(1.5rem, env(safe-area-inset-bottom));
    box-shadow: -24px 0 70px -48px rgba(16, 45, 79, 0.85);
    animation: drawer-in 180ms ease-out;
  }

  .drawer-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem; }
  .drawer-heading h2 { margin-top: 0.5rem; font-family: var(--font-poppins); font-size: 1.55rem; font-weight: 600; letter-spacing: -0.04em; }
  .close-button { display: grid; width: 2.75rem; height: 2.75rem; place-items: center; border-radius: 999px; color: #60798b; }
  .close-button:hover { background: #edf4f4; }
  .close-button svg { width: 1.2rem; fill: none; stroke: currentColor; stroke-linecap: round; stroke-width: 1.8; }
  .history-empty { margin-top: 4rem; border-top: 1px solid #e0e8e9; padding-top: 1.4rem; }
  .history-empty > span { color: #b3c0c6; font-family: var(--font-poppins); font-size: 0.75rem; font-weight: 700; letter-spacing: 0.12em; }
  .history-empty h3 { margin-top: 0.7rem; font-family: var(--font-poppins); font-size: 1.1rem; font-weight: 600; }
  .history-empty p { margin-top: 0.65rem; color: #708694; font-size: 0.88rem; line-height: 1.65; }

  @keyframes pulse { 0%, 60%, 100% { opacity: 0.28; transform: translateY(0); } 30% { opacity: 1; transform: translateY(-0.18rem); } }
  @keyframes drawer-in { from { transform: translateX(1rem); opacity: 0; } to { transform: translateX(0); opacity: 1; } }

  @media (max-width: 639px) {
    .telchiai-shell { min-height: calc(100svh - 65px); }
    .product-bar { width: min(100% - 1.25rem, 72rem); padding-block: 0.7rem; }
    .history-button span { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; }
    .history-button { width: 2.75rem; justify-content: center; padding: 0; }
    main { min-height: calc(100svh - 126px); padding-inline: 1rem; padding-top: 1.5rem; }
    .welcome { margin-top: -1.5rem; }
    .welcome-copy { max-width: 29ch; }
    .composer-primary { margin-top: 1.65rem; }
    .input-help { display: none; }
    .suggestions { margin-top: 1.5rem; text-align: left; }
    .suggestion-list { display: grid; grid-template-columns: 1fr; justify-content: stretch; gap: 0.45rem; }
    .suggestion-list button { border-radius: 0.9rem; text-align: left; }
    .conversation { padding-top: 0.25rem; }
    .analysis-space { min-height: 12rem; }
  }

  @media (min-width: 640px) {
    .product-bar { padding-block: 1.2rem; }
    main { padding-inline: 2rem; }
  }

  @media (prefers-reduced-motion: reduce) {
    .progress-indicator i, .history-drawer { animation: none; }
  }
</style>
