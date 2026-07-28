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
  .t360-vera-embed {
    max-width: 52rem;
    margin: 0 auto;
    padding: 0;
  }

  .t360-vera-embed.compact {
    max-width: 42rem;
  }
</style>
