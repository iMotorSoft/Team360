<script lang="ts">
  import { onMount } from "svelte";
  import {
    mountTeam360Diagnosticador,
    type Team360DiagnosticadorMountHandle,
  } from "./mount";

  let {
    apiBaseUrl,
    clientId,
    assistantName = "Diagnosticador Team360",
    compact = false,
    initialMessage = "",
    sessionStorageKey = "team360.embed.mount.demo.session.v1",
  }: {
    apiBaseUrl: string;
    clientId: string;
    assistantName?: string;
    compact?: boolean;
    initialMessage?: string;
    sessionStorageKey?: string;
  } = $props();

  let mountTarget = $state<HTMLElement | undefined>();
  let mountError = $state("");

  onMount(() => {
    if (!mountTarget) {
      mountError = "No se encontró el contenedor de montaje.";
      return;
    }

    let handle: Team360DiagnosticadorMountHandle | undefined;

    try {
      handle = mountTeam360Diagnosticador(mountTarget, {
        apiBaseUrl,
        clientId,
        assistantName,
        compact,
        initialMessage,
        sessionStorageKey,
      });
    } catch (error) {
      mountError = error instanceof Error ? error.message : "Falló el montaje del Diagnosticador.";
      return;
    }

    return () => {
      handle?.destroy();
    };
  });
</script>

<main class="mount-demo" data-testid="mount-demo">
  <section class="host-shell">
    <header class="host-header" data-testid="mount-demo-header">
      <p class="host-eyebrow">Mount Adapter Demo</p>
      <h1>Host controlado con adapter interno `mount()`</h1>
      <p class="host-copy">
        Esta página no importa el wrapper directamente. Usa un adapter TypeScript
        experimental para montar el Diagnosticador en un contenedor visible.
      </p>
    </header>

    <div class="host-grid">
      <aside class="host-notes" data-testid="mount-demo-notes">
        <h2>Contrato experimental mínimo</h2>
        <ul>
          <li><strong>clientId</strong>: identificador público del embed.</li>
          <li><strong>apiBaseUrl</strong>: backend público del flujo embed.</li>
          <li><strong>sessionStorageKey</strong>: aislación específica de este host.</li>
          <li><strong>assistantName</strong> y <strong>compact</strong>: solo visual.</li>
        </ul>
        <p>
          El adapter no acepta tenant, scope ni secretos. El host sigue usando
          <code>/api/diagnosis/embed/auth</code> y <code>/api/diagnosis/turn</code>.
        </p>
      </aside>

      <section class="mount-slot" data-testid="mount-demo-slot">
        <div
          bind:this={mountTarget}
          id="team360-mount-target"
          class="mount-target"
          data-testid="mount-demo-target"
        ></div>

        {#if mountError}
          <p class="mount-error" data-testid="mount-demo-error">{mountError}</p>
        {/if}
      </section>
    </div>
  </section>
</main>

<style>
  .mount-demo {
    min-height: 100vh;
    background:
      radial-gradient(circle at top left, rgba(22, 139, 136, 0.16), transparent 28rem),
      linear-gradient(180deg, #f3f7fb 0%, #eef3f7 100%);
    padding: 2rem 1rem 3rem;
  }

  .host-shell {
    margin: 0 auto;
    max-width: 78rem;
  }

  .host-header {
    margin-bottom: 1.5rem;
  }

  .host-eyebrow {
    margin-bottom: 0.5rem;
    font-size: 0.78rem;
    font-weight: 700;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: #0f766e;
  }

  .host-header h1 {
    margin: 0;
    font-size: clamp(2rem, 3vw, 3rem);
    line-height: 1.05;
    color: #11263f;
  }

  .host-copy {
    margin-top: 0.75rem;
    max-width: 44rem;
    font-size: 1rem;
    line-height: 1.6;
    color: #4a627a;
  }

  .host-grid {
    display: grid;
    gap: 1.25rem;
    align-items: start;
  }

  .host-notes,
  .mount-slot {
    border: 1px solid rgba(148, 163, 184, 0.28);
    border-radius: 1.5rem;
    background: rgba(255, 255, 255, 0.92);
    box-shadow: 0 20px 60px rgba(15, 23, 42, 0.08);
  }

  .host-notes {
    padding: 1.5rem;
    color: #24364a;
  }

  .host-notes h2 {
    margin: 0 0 0.85rem;
    font-size: 1.1rem;
    font-weight: 700;
    color: #102d4f;
  }

  .host-notes ul {
    margin: 0 0 1rem;
    padding-left: 1.25rem;
    line-height: 1.55;
  }

  .host-notes p {
    margin: 0;
    font-size: 0.96rem;
    line-height: 1.6;
    color: #5a7086;
  }

  .host-notes code {
    font-size: 0.9em;
  }

  .mount-slot {
    padding: 1rem 0.5rem;
  }

  .mount-target:empty {
    min-height: 28rem;
  }

  .mount-error {
    margin: 1rem 1rem 0;
    border-radius: 0.9rem;
    background: #fff1f2;
    padding: 0.9rem 1rem;
    font-size: 0.92rem;
    color: #be123c;
  }

  @media (min-width: 960px) {
    .host-grid {
      grid-template-columns: minmax(18rem, 24rem) minmax(0, 1fr);
    }

    .mount-slot {
      padding: 1.25rem 0.75rem;
    }
  }
</style>
