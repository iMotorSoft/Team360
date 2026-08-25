<script lang="ts">
  import { flowDateTime } from "../../../lib/t360/flow/format";
  import { resendApprovalRequest, type ApprovalResendError } from "../../../lib/api/flowExecutive";
  import { currentAssignee, currentLevel } from "../../../lib/t360/flow/types";
  import type { ExecutiveView } from "../../../lib/t360/flow/types";
  import type { ExecutiveFetchError } from "../../../lib/api/flowExecutive";
  import FlowEvidence from "./FlowEvidence.svelte";
  import FlowSlaBadge from "./FlowSlaBadge.svelte";
  import FlowStatusBadge from "./FlowStatusBadge.svelte";
  import FlowTimeline from "./FlowTimeline.svelte";

  let {
    view,
    loading = false,
    error = null,
    onBack = () => undefined,
    onApprovalResent = () => undefined,
  }: {
    view: ExecutiveView | null;
    loading?: boolean;
    error?: ExecutiveFetchError | null;
    onBack?: () => void;
    onApprovalResent?: () => void | Promise<void>;
  } = $props();

  let resendConfirming = $state(false);
  let resendLoading = $state(false);
  let resendMessage = $state<string | null>(null);
  let resendError = $state<ApprovalResendError | null>(null);

  const errorCopy = $derived.by(() => {
    switch (error) {
      case "unauthorized":
        return { title: "Sesión requerida", detail: "Necesitás autenticarte para ver este caso." };
      case "forbidden":
        return { title: "Sin permiso", detail: "Tu rol no tiene acceso de Directorio (flow.executive.read)." };
      case "not_found":
        return { title: "Caso no encontrado", detail: "El identificador no corresponde a un caso de Flow." };
      default:
        return { title: "No se pudo cargar", detail: "El backend ejecutivo no está disponible en este momento." };
    }
  });

  const levelText = $derived(view ? (currentLevel(view) > 0 ? `Nivel ${currentLevel(view)}` : "Sin nivel asignado") : "");

  const canResendApproval = $derived(
    view?.data_source === "LIVE"
      && view.status_fact === "pending_approval"
      && (view.closure_approval?.decision === "PENDING" || view.closure_approval?.decision === null),
  );

  function resendErrorCopy(error: ApprovalResendError): string {
    switch (error) {
      case "forbidden": return "No tenés permiso para reenviar aprobaciones.";
      case "not_found": return "El caso ya no está disponible.";
      case "conflict": return "El caso ya no está pendiente de aprobación.";
      case "invalid": return "La aprobación no tiene un destinatario válido.";
      case "unauthorized": return "La sesión ya no está autorizada.";
      default: return "No se pudo reenviar la solicitud. Intentá nuevamente.";
    }
  }

  async function resendApproval() {
    if (!view || resendLoading || !canResendApproval) return;
    resendConfirming = false;
    resendLoading = true;
    resendMessage = null;
    resendError = null;
    const result = await resendApprovalRequest(view.request_id);
    resendLoading = false;
    if (result.error || !result.data) {
      resendError = result.error ?? "unavailable";
      return;
    }
    resendMessage = `Solicitud reenviada a ${result.data.approver_destination}.`;
    await onApprovalResent();
  }
</script>

<div class="space-y-5">
  {#if loading}
    <div class="rounded-2xl border border-card-border bg-card-bg p-6">
      <div class="animate-pulse space-y-3">
        <div class="h-4 w-1/3 rounded bg-base-200"></div>
        <div class="h-8 w-2/3 rounded bg-base-200"></div>
        <div class="h-3 w-1/2 rounded bg-base-200"></div>
      </div>
    </div>
  {:else if error || !view}
    <div class="rounded-2xl border border-dashed border-[#d7e3e5] bg-white/70 p-8 text-center">
      <p class="text-sm font-bold text-[#31536b]">{errorCopy.title}</p>
      <p class="mt-2 text-xs leading-5 text-[#78909f]">{errorCopy.detail}</p>
      <button
        type="button"
        onclick={onBack}
        class="mt-4 rounded-full border border-[#b7dfdc] bg-[#e4f5f3] px-4 py-2 text-xs font-bold text-[#126d6b] transition hover:bg-[#d7efec]"
      >
        Volver al listado
      </button>
    </div>
  {:else}
    <button
      type="button"
      onclick={onBack}
      class="inline-flex items-center gap-1 text-xs font-bold text-[#168b88] hover:text-[#126d6b] lg:hidden"
    >
      <span aria-hidden="true">‹</span> Volver al listado
    </button>

    <header class="rounded-2xl border border-card-border bg-card-bg p-5 shadow-[0_18px_45px_-42px_rgba(16,45,79,0.7)]">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div class="min-w-0">
          <div class="flex flex-wrap items-center gap-2">
            <span class="font-mono text-sm font-bold text-[#168b88]">#{view.request_id.slice(0, 8)}</span>
            <FlowStatusBadge statusFact={view.status_fact} dataSource={view.data_source} />
          </div>
          <h2 class="mt-2 text-lg font-bold leading-6 tracking-[-0.02em] text-[#173b5b]">{view.request.description}</h2>
          <p class="mt-1 text-sm text-[#78909f]">
            {view.request.sector_name ?? "Sector"} · {view.request.location ?? "Ubicación no informada"} · {levelText}
          </p>
        </div>
        <div class="text-start sm:text-end">
          <p class="text-xs font-semibold text-[#587184]">Responsable actual</p>
          <p class="mt-0.5 text-sm font-bold text-[#31536b]">{currentAssignee(view) ?? "Sin asignar"}</p>
          <p class="mt-1 text-[0.62rem] text-[#91a2ad]">
            {#if view.data_source === "AUDIT_SNAPSHOT"}
              Registro final auditado
            {:else}
              Estado actual en vivo
            {/if}
          </p>
        </div>
      </div>
    </header>

    {#if view.executive_summary}
      <section class="rounded-2xl border border-card-border bg-card-bg p-5">
        <div class="flex items-center gap-2">
          <span class="grid size-6 place-items-center rounded-full bg-[#e4f5f3] text-xs font-bold text-[#126d6b]" aria-hidden="true">Σ</span>
          <h3 class="text-xs font-bold uppercase tracking-[0.16em] text-[#168b88]">Resumen ejecutivo</h3>
        </div>
        <p class="mt-3 max-w-3xl text-sm leading-6 text-[#31536b]">{view.executive_summary}</p>
        <p class="mt-2 text-[0.62rem] text-[#91a2ad]">Generado a partir de los hechos persistidos; la evidencia estructurada se muestra abajo.</p>
      </section>
    {:else}
      <section class="rounded-2xl border border-dashed border-[#d7e3e5] bg-white/60 p-4">
        <p class="text-xs font-semibold text-[#587184]">Resumen ejecutivo no disponible</p>
        <p class="mt-1 text-[0.62rem] text-[#91a2ad]">La evidencia estructurada continúa disponible.</p>
      </section>
    {/if}

    {#if view.sla.length > 0}
      <section>
        <h3 class="text-xs font-bold uppercase tracking-[0.16em] text-[#78909f]">SLA por nivel</h3>
        <div class="mt-2 flex flex-wrap gap-2">
          {#each view.sla as sla (sla.sla_id ?? `${sla.level}`)}
            <FlowSlaBadge {sla} />
          {/each}
        </div>
      </section>
    {/if}

    {#if view.escalations.length > 0}
      <section>
        <h3 class="text-xs font-bold uppercase tracking-[0.16em] text-[#78909f]">Escalamientos</h3>
        <div class="mt-2 space-y-2">
          {#each view.escalations as escalation (escalation.escalation_id ?? `${escalation.from_level}-${escalation.to_level}`)}
            <div class="flex items-center gap-3 rounded-xl border border-card-border bg-card-bg-light px-4 py-3">
              <span class="grid size-8 shrink-0 place-items-center rounded-full bg-[#fff7d9] text-sm font-bold text-[#765d00]" aria-hidden="true">↑</span>
              <div class="min-w-0">
                <p class="text-sm font-semibold text-[#31536b]">Nivel {escalation.from_level} → Nivel {escalation.to_level}</p>
                <p class="text-xs text-[#78909f]">
                  {escalation.trigger === "FIRST_RESPONSE_SLA_BREACHED" ? "SLA de primera respuesta vencido" : escalation.trigger ?? "Escalamiento"} · {flowDateTime(escalation.created_at ?? null)}
                </p>
              </div>
              <span class="ms-auto text-xs font-bold text-[#30ae69]">{escalation.status === "COMPLETED" ? "Completado" : escalation.status}</span>
            </div>
          {/each}
        </div>
      </section>
    {/if}

    {#if view.resolution || view.closure_approval}
      <section class="rounded-2xl border border-card-border bg-card-bg p-5">
        <h3 class="text-xs font-bold uppercase tracking-[0.16em] text-[#168b88]">Resolución y cierre</h3>
        {#if view.resolution}
          <div class="mt-3">
            <p class="text-sm font-semibold text-[#31536b]">Propuesta del técnico</p>
            <p class="mt-1 text-sm leading-6 text-[#587184]">{view.resolution.resolution_text ?? "—"}</p>
            <p class="mt-1 text-xs text-[#78909f]">{view.resolution.proposed_by ?? "—"} · {flowDateTime(view.resolution.proposed_at ?? null)}</p>
          </div>
        {/if}
        {#if view.closure_approval}
          <div class="mt-3 border-t border-card-border-mini pt-3">
            <p class="text-sm font-semibold text-[#31536b]">Decisión del supervisor</p>
            {#if view.closure_approval.decision === "APPROVED"}
              <p class="mt-1 text-sm font-bold text-[#17663d]">Aprobado</p>
              <p class="mt-1 text-xs text-[#587184]">
                Autorizado por {view.closure_approval.approver ?? "—"}
                {#if view.closure_approval.approver_level}{`(Nivel ${view.closure_approval.approver_level})`}{/if}
                {#if view.result.resolved_at} · Cerrado el {flowDateTime(view.result.resolved_at)}{/if}
              </p>
            {:else if view.closure_approval.decision === "REJECTED"}
              <p class="mt-1 text-sm font-bold text-[#9b3328]">Rechazado</p>
              <p class="mt-1 text-xs leading-5 text-[#587184]">{view.closure_approval.decision_reason ?? "Sin motivo registrado"}</p>
              {#if view.status_fact === "open"}
                <p class="mt-1.5 inline-flex items-center gap-1 rounded-full border border-[#f1dfa2] bg-[#fff7d9] px-2.5 py-1 text-[0.68rem] font-bold text-[#765d00]">
                  El caso continúa activo
                </p>
              {/if}
            {:else}
              <p class="mt-1 text-sm font-bold text-[#765d00]">Pendiente de decisión</p>
              {#if view.status_fact === "pending_approval"}
                <p class="mt-1 text-xs leading-5 text-[#587184]">El caso sigue abierto hasta la decisión del supervisor.</p>
              {/if}
              {#if canResendApproval}
                <div class="mt-4 rounded-xl border border-[#d8e9e8] bg-[#f5fbfa] p-3">
                  {#if resendConfirming}
                    <p class="text-xs leading-5 text-[#31536b]">Se reenviará la solicitud al aprobador configurado. El caso, la aprobación y el SLA no cambiarán.</p>
                    <div class="mt-3 flex flex-wrap gap-2">
                      <button
                        type="button"
                        onclick={resendApproval}
                        disabled={resendLoading}
                        class="rounded-full bg-[#168b88] px-3 py-2 text-xs font-bold text-white transition hover:bg-[#126d6b] disabled:cursor-wait disabled:opacity-60"
                      >
                        {resendLoading ? "Reenviando…" : "Confirmar reenvío"}
                      </button>
                      <button
                        type="button"
                        onclick={() => { resendConfirming = false; }}
                        disabled={resendLoading}
                        class="rounded-full border border-[#cddede] bg-white px-3 py-2 text-xs font-bold text-[#587184] disabled:opacity-60"
                      >
                        Cancelar
                      </button>
                    </div>
                  {:else}
                    <button
                      type="button"
                      onclick={() => { resendConfirming = true; resendMessage = null; resendError = null; }}
                      disabled={resendLoading}
                      class="rounded-full border border-[#9ed4d0] bg-white px-3 py-2 text-xs font-bold text-[#126d6b] transition hover:bg-[#e4f5f3] disabled:cursor-wait disabled:opacity-60"
                    >
                      {resendLoading ? "Reenviando…" : "Reenviar solicitud de aprobación"}
                    </button>
                  {/if}
                  {#if resendMessage}
                    <p class="mt-2 text-xs font-semibold text-[#17663d]" role="status">{resendMessage}</p>
                  {/if}
                  {#if resendError}
                    <p class="mt-2 text-xs font-semibold text-[#9b3328]" role="alert">{resendErrorCopy(resendError)}</p>
                  {/if}
                </div>
              {/if}
            {/if}
            {#if view.closure_approval.decision_reason && view.closure_approval.decision !== "REJECTED"}
              <p class="mt-1 text-xs leading-5 text-[#587184]">{view.closure_approval.decision_reason}</p>
            {/if}
          </div>
        {/if}
      </section>
    {/if}

    <section class="rounded-2xl border border-card-border bg-card-bg p-5">
      <h3 class="text-xs font-bold uppercase tracking-[0.16em] text-[#78909f]">Historia del caso</h3>
      <div class="mt-4">
        {#if view.timeline.length > 0}
          <FlowTimeline events={view.timeline} />
        {:else}
          <p class="text-xs leading-5 text-[#78909f]">Sin eventos registrados para este caso.</p>
        {/if}
      </div>
    </section>

    <FlowEvidence {view} />
  {/if}
</div>
