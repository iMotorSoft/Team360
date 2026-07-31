<script lang="ts">
  import DiagnosticadorCore from "./DiagnosticadorCore.svelte";
  import { requestEmbedTurnAuth } from "../../api/publicDiagnosis";
  import { DEFAULT_PUBLIC_DIAGNOSIS_CONTEXT } from "./config/defaults";

  let {
    apiBaseUrl,
    clientId,
    assistantName = "Vera",
    compact = false,
    initialMessage = "",
    sessionStorageKey = "team360.vera.embed.session.v1",
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
  class="t360-vera-embed"
  data-testid="vera-embed-wrapper"
  data-t360-root
>
  <div class="vera-embed-card">
    <div class="vera-embed-header">
      <span class="vera-embed-badge">Diagnóstico de factibilidad</span>
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
    <div class="vera-embed-footer">
      <span>Powered by <strong>Team360</strong></span>
    </div>
  </div>
</div>

<style>
  .t360-vera-embed {
    max-width: 52rem;
    margin: 0 auto;
    padding: 0.75rem;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  }

  .t360-vera-embed.compact {
    max-width: 42rem;
  }

  .vera-embed-card {
    min-height: 20rem;
  }

  .vera-embed-header {
    text-align: center;
    margin-bottom: 0.75rem;
  }

  .vera-embed-badge {
    display: inline-block;
    font-size: 0.68rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: #168b88;
    background: #ecfaf8;
    padding: 0.25rem 0.85rem;
    border-radius: 9999px;
  }

  .vera-embed-footer {
    text-align: center;
    margin-top: 1rem;
    font-size: 0.62rem;
    color: #9bb2be;
    letter-spacing: 0.04em;
  }

  .vera-embed-footer strong {
    color: #5b7283;
    font-weight: 600;
  }
</style>
