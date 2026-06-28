<script lang="ts">
  import DiagnosticadorCore from "./DiagnosticadorCore.svelte";
  import { API_BASE_URL } from "../../../components/global.js";
  import { PUBLIC_DIAGNOSIS_CONTEXT } from "../../api/publicDiagnosis";

  const LAB_SESSION_KEY = "team360.diagnosticador.lab.session.v1";

  let sessionId = $state<string | null>(null);
  let messages = $state<{ role: "user" | "assistant"; text: string }[]>([]);
  let inputText = $state("");
  let turnDisplayName = $state<string>("");
</script>

<div class="t360-diagnosticador-lab" data-t360-root>
  <div class="lab-banner">
    <span class="lab-badge">LABORATORIO INTERNO</span>
  </div>

  <div class="lab-header">
    <h2>Diagnosticador Embed Lab</h2>
    <p class="lab-subtitle">
      Core embebible fuera de /t360 — sesión aislada de Vera
    </p>
  </div>

  <DiagnosticadorCore
    bind:sessionId
    bind:messages
    bind:inputText
    bind:turnDisplayName
    assistantName="Diagnosticador Lab"
    assistantInstanceId="team360_sales_diagnosis"
    sessionStorageKey={LAB_SESSION_KEY}
    apiBaseUrl={API_BASE_URL}
    publicDiagnosisContext={PUBLIC_DIAGNOSIS_CONTEXT}
    mailtoHref=""
  />
</div>

<style>
  .t360-diagnosticador-lab {
    max-width: 48rem;
    margin: 0 auto;
    padding: 1.5rem;
  }
  .lab-banner {
    display: flex;
    justify-content: center;
    margin-bottom: 1rem;
  }
  .lab-badge {
    display: inline-flex;
    border-radius: 9999px;
    border: 1px solid #f59e0b;
    background: #fffbeb;
    padding: 0.25rem 0.75rem;
    font-size: 0.65rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #92400e;
  }
  .lab-header {
    margin-bottom: 1.5rem;
    text-align: center;
  }
  .lab-header h2 {
    font-size: 1.5rem;
    font-weight: 600;
    color: #102d4f;
  }
  .lab-subtitle {
    margin-top: 0.25rem;
    font-size: 0.8rem;
    color: #78909f;
  }
</style>
