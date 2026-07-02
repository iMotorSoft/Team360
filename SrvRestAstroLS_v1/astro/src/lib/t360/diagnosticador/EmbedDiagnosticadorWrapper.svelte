<script lang="ts">
  import DiagnosticadorCore from "./DiagnosticadorCore.svelte";
  import { requestEmbedTurnAuth } from "../../api/publicDiagnosis";
  import { DEFAULT_PUBLIC_DIAGNOSIS_CONTEXT } from "./config/defaults";

  const DEFAULT_EMBED_DEMO_SESSION_KEY = "team360.embed.demo.session.v1";

  let {
    apiBaseUrl,
    clientId,
    assistantName = "Diagnosticador Embed",
    compact = false,
    initialMessage = "",
    sessionStorageKey = DEFAULT_EMBED_DEMO_SESSION_KEY,
  }: {
    apiBaseUrl: string;
    clientId: string;
    assistantName?: string;
    compact?: boolean;
    initialMessage?: string;
    sessionStorageKey?: string;
  } = $props();

  let sessionId = $state<string | null>(null);
  let messages = $state<{ role: "user" | "assistant"; text: string }[]>([]);
  let inputText = $state(initialMessage);
  let turnDisplayName = $state("");

  async function turnAuthProvider(input: { sessionId: string; message: string }) {
    return requestEmbedTurnAuth(
      {
        clientId,
        sessionId: input.sessionId,
        message: input.message,
      },
      { apiBaseUrl },
    );
  }
</script>

<div
  class:compact
  class="t360-embed-demo-wrapper"
  data-testid="embed-demo-wrapper"
  data-t360-root
>
  <div class="demo-banner">
    <span class="demo-badge">DEMO INTERNA</span>
  </div>

  <div class="demo-header">
    <h2>Diagnosticador embebible demo</h2>
    <p class="demo-subtitle">
      Wrapper interno con firma server-side y `client_id` controlado
    </p>
  </div>

  <DiagnosticadorCore
    bind:sessionId
    bind:messages
    bind:inputText
    bind:turnDisplayName
    assistantName={assistantName}
    assistantInstanceId="team360_sales_diagnosis"
    sessionStorageKey={sessionStorageKey}
    apiBaseUrl={apiBaseUrl}
    publicDiagnosisContext={DEFAULT_PUBLIC_DIAGNOSIS_CONTEXT}
    turnAuthProvider={turnAuthProvider}
    mailtoHref=""
  />
</div>

<style>
  .t360-embed-demo-wrapper {
    max-width: 52rem;
    margin: 0 auto;
    padding: 1.5rem;
  }

  .t360-embed-demo-wrapper.compact {
    max-width: 42rem;
    padding: 1rem;
  }

  .demo-banner {
    display: flex;
    justify-content: center;
    margin-bottom: 1rem;
  }

  .demo-badge {
    display: inline-flex;
    border-radius: 9999px;
    border: 1px solid #2563eb;
    background: #eff6ff;
    padding: 0.25rem 0.75rem;
    font-size: 0.65rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #1d4ed8;
  }

  .demo-header {
    margin-bottom: 1.5rem;
    text-align: center;
  }

  .demo-header h2 {
    font-size: 1.5rem;
    font-weight: 600;
    color: #102d4f;
  }

  .demo-subtitle {
    margin-top: 0.25rem;
    font-size: 0.8rem;
    color: #78909f;
  }
</style>
