<script lang="ts">
  import type { ExecutiveView } from "../../../lib/t360/flow/types";

  let { view }: { view: ExecutiveView } = $props();

  const rows = $derived.by(() => {
    const result: { label: string; value: string }[] = [];
    result.push({ label: "Request ID", value: view.request_id });
    if (view.audit?.audit_record_id) {
      result.push({ label: "Audit record", value: view.audit.audit_record_id });
      if (view.audit.snapshot_sha256) {
        result.push({ label: "Hash de auditoría", value: view.audit.snapshot_sha256 });
      }
    }
    for (const routing of view.routing_history) {
      result.push({ label: `Routing N${routing.level}`, value: routing.routing_id });
    }
    for (const escalation of view.escalations) {
      if (escalation.escalation_id) {
        result.push({ label: `Escalamiento N${escalation.from_level}→N${escalation.to_level}`, value: escalation.escalation_id });
      }
    }
    for (const sla of view.sla) {
      if (sla.sla_id) {
        result.push({ label: `SLA N${sla.level}`, value: sla.sla_id });
      }
    }
    for (const event of view.operational_events) {
      if (event.event_id) {
        result.push({ label: `Evento operacional N${event.level ?? ""}`.trim(), value: event.event_id });
      }
    }
    if (view.resolution?.resolution_id) {
      result.push({ label: "Propuesta de resolución", value: view.resolution.resolution_id });
    }
    if (view.closure_approval?.approval_id) {
      result.push({ label: "Aprobación de cierre", value: view.closure_approval.approval_id });
    }
    return result;
  });
</script>

<details class="group rounded-xl border border-card-border bg-card-bg-light">
  <summary class="flex cursor-pointer list-none items-center justify-between gap-2 px-4 py-3 text-xs font-bold uppercase tracking-[0.14em] text-[#78909f] transition hover:text-[#31536b]">
    <span>Evidencia y trazabilidad</span>
    <span class="text-[#168b88] transition group-open:rotate-90" aria-hidden="true">›</span>
  </summary>
  <div class="border-t border-card-border-mini px-4 py-3">
    <dl class="grid gap-2 sm:grid-cols-2">
      {#each rows as row (row.value)}
        <div class="min-w-0 rounded-lg border border-card-border-mini bg-white px-3 py-2">
          <dt class="text-[0.62rem] font-semibold uppercase tracking-[0.1em] text-[#91a2ad]">{row.label}</dt>
          <dd class="mt-0.5 truncate font-mono text-[0.72rem] text-[#587184]" title={row.value}>{row.value}</dd>
        </div>
      {/each}
    </dl>
  </div>
</details>
