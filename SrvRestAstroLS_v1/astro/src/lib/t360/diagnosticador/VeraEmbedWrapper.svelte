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

{@html "<style id=\"t360-embed-styles\">\
.t360-vera-embed,.t360-vera-embed *{box-sizing:border-box}\
.t360-vera-embed{max-width:820px;margin:0 auto;padding:1rem;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;color:#203c55;line-height:1.5}\
.t360-vera-embed.compact{max-width:42rem}\
.vera-embed-header{text-align:center;margin-bottom:.75rem}\
.vera-embed-badge{display:inline-block;font-size:.68rem;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:#168b88;background:#ecfaf8;padding:.3rem .9rem;border-radius:9999px;white-space:nowrap}\
.t360-vera-embed [data-testid=diagnosticador-core]{background:#fff;border:1px solid #dbe7e9;border-radius:1.5rem;padding:1.25rem!important;box-shadow:0 2px 24px rgba(16,45,79,.08);overflow:visible}\
.t360-vera-embed [data-testid=diagnosticador-core] .text-sm.font-bold{font-size:1rem!important;font-weight:700!important;color:#153854!important;margin:0}\
.t360-vera-embed [data-testid=diagnosticador-core] .text-xs.font-semibold{margin-top:.15rem!important;font-size:.75rem!important;font-weight:600!important;color:#78909f!important}\
.t360-vera-embed button{font-family:inherit;cursor:pointer;border:none;outline:none;transition:all .15s;appearance:none;-webkit-appearance:none}\
.t360-vera-embed button:focus-visible{outline:2px solid #168b88;outline-offset:2px}\
.t360-vera-embed [data-testid=public-vera-submit],.t360-vera-embed [data-testid=public-vera-chat-submit]{display:inline-flex!important;align-items:center;justify-content:center;min-height:2.75rem!important;padding:.5rem 1.5rem!important;font-size:.88rem!important;font-weight:700!important;color:#fff!important;background:#168b88!important;border-radius:9999px!important;border:none!important}\
.t360-vera-embed [data-testid=public-vera-submit]:hover:not(:disabled),.t360-vera-embed [data-testid=public-vera-chat-submit]:hover:not(:disabled){background:#126d6b!important}\
.t360-vera-embed [data-testid=public-vera-submit]:disabled,.t360-vera-embed [data-testid=public-vera-chat-submit]:disabled{opacity:.45;cursor:not-allowed}\
.t360-vera-embed [data-testid=public-vera-new-conversation]{display:inline-flex!important;align-items:center;padding:.3rem .8rem!important;font-size:.65rem!important;font-weight:600!important;color:#476275!important;background:#fff!important;border:1px solid #c9dcdd!important;border-radius:9999px!important;line-height:1.3!important}\
.t360-vera-embed [data-testid=public-vera-new-conversation]:hover{border-color:#9fc8c7!important;background:#f7fbfa!important}\
.t360-vera-embed textarea{font-family:inherit;font-size:.9rem;line-height:1.6;color:#203c55;background:#fbfdfc;border:1px solid #d5e2e5;border-radius:1rem;padding:.75rem 1rem!important;width:100%!important;resize:vertical;outline:none;transition:border-color .2s,box-shadow .2s;appearance:none;-webkit-appearance:none;box-sizing:border-box!important}\
.t360-vera-embed textarea:focus{border-color:#168b88;box-shadow:0 0 0 3px rgba(22,139,136,.15);outline:none}\
.t360-vera-embed textarea::placeholder{color:#91a2ad;opacity:1}\
.t360-vera-embed [data-testid=public-vera-text]{min-height:8rem!important;resize:vertical!important}\
.t360-vera-embed [data-testid=public-vera-chat-input]{min-height:3.25rem!important;flex:1;resize:none!important}\
.t360-vera-embed [data-chat-messages]{display:flex!important;flex-direction:column!important;gap:.75rem!important;max-height:24rem!important;overflow-y:auto!important;padding:.75rem!important;background:#fbfdfc!important;border:1px solid #d5e2e5!important;border-radius:1rem!important;margin:1rem 0!important}\
.t360-vera-embed [data-testid=public-vera-user-message]{align-self:flex-end!important;max-width:85%!important;background:#168b88!important;color:#fff!important;padding:.55rem .9rem!important;border-radius:1rem 1rem .25rem 1rem!important;font-size:.88rem!important;line-height:1.5!important;word-break:break-word}\
.t360-vera-embed [data-testid=public-vera-assistant-message]{align-self:flex-start!important;max-width:100%!important;background:#fff!important;border:1px solid #d5e2e5!important;padding:.55rem .9rem!important;border-radius:1rem 1rem 1rem .25rem!important;font-size:.88rem!important;line-height:1.5!important;word-break:break-word;color:#203c55!important}\
.t360-vera-embed .animate-pulse{display:inline-block;width:.5rem;height:.5rem;background:#168b88;border-radius:50%;margin-right:.5rem;animation:t360-pulse 1.4s infinite}\
@keyframes t360-pulse{0%,100%{opacity:1}50%{opacity:.3}}\
.t360-vera-embed [data-testid=public-vera-error]{background:#fff7f7!important;border:1px solid #f3c7c7!important;border-radius:1rem!important;padding:.75rem 1rem!important;margin-top:.75rem!important;font-size:.85rem!important;color:#8f3940!important;line-height:1.4!important}\
.vera-embed-footer{text-align:center;margin-top:1.25rem;padding-top:.75rem;font-size:.62rem;color:#9bb2be;letter-spacing:.04em;border-top:1px solid #edf2f3}\
.vera-embed-footer strong{color:#5b7283;font-weight:600}\
@media(max-width:640px){.t360-vera-embed{padding:.5rem}.t360-vera-embed [data-testid=diagnosticador-core]{padding:1rem!important;border-radius:1rem}.t360-vera-embed [data-testid=public-vera-text]{min-height:6rem!important}}\
</style>"}