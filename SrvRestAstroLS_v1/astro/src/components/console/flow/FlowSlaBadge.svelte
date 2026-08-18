<script lang="ts">
  import { flowDateTime } from "../../../lib/t360/flow/format";
  import type { SlaItem } from "../../../lib/t360/flow/types";

  let { sla }: { sla: SlaItem } = $props();

  const meta = $derived.by(() => {
    switch (sla.status) {
      case "MET":
        return { label: "Cumplido", icon: "✓", tone: "success" };
      case "BREACHED":
        return { label: "Vencido", icon: "✕", tone: "danger" };
      default:
        return { label: "Dentro de SLA", icon: "◷", tone: "warning" };
    }
  });

  const toneClasses = $derived.by(() => {
    switch (meta.tone) {
      case "success":
        return "border-[#b9e7cc] bg-[#e8f8ef] text-[#17663d]";
      case "danger":
        return "border-[#f1c7c2] bg-[#fdf0ee] text-[#9b3328]";
      default:
        return "border-[#f1dfa2] bg-[#fff7d9] text-[#765d00]";
    }
  });
</script>

<span class={`inline-flex flex-col gap-1 rounded-xl border px-3 py-2 ${toneClasses}`}>
  <span class="flex items-center gap-1.5 text-xs font-bold leading-none">
    <span aria-hidden="true">{meta.icon}</span>
    <span>Nivel {sla.level} · {meta.label}</span>
  </span>
  <span class="text-[0.62rem] leading-4 opacity-80">
    {#if sla.status === "MET"}
      Respondido {flowDateTime(sla.first_response_at ?? null)}
    {:else if sla.status === "BREACHED"}
      Vencía {flowDateTime(sla.due_at ?? null)}
    {:else}
      Vence {flowDateTime(sla.due_at ?? null)}
    {/if}
  </span>
</span>
