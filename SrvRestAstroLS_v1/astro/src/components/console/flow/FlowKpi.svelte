<script lang="ts">
  import type { FlowKpi } from "../../../lib/mock/flow";

  let { kpi }: { kpi: FlowKpi } = $props();

  const toneClasses = $derived.by(() => {
    switch (kpi.tone) {
      case "success":
        return "border-[#b9e7cc] text-[#17663d]";
      case "warning":
        return "border-[#f1dfa2] text-[#765d00]";
      case "danger":
        return "border-[#f1c7c2] text-[#9b3328]";
      case "info":
        return "border-[#b9def0] text-[#1d6688]";
      default:
        return "border-[#dce6e8] text-[#587184]";
    }
  });

  const barColor = $derived.by(() => {
    switch (kpi.tone) {
      case "success":
        return "bg-[#30ae69]";
      case "warning":
        return "bg-[#d7ba12]";
      case "danger":
        return "bg-[#d23a2a]";
      case "info":
        return "bg-[#2ca2da]";
      default:
        return "bg-[#78909f]";
    }
  });
</script>

<article class="rounded-2xl border border-card-border bg-card-bg p-4 shadow-[0_18px_45px_-42px_rgba(16,45,79,0.7)]">
  <div class="flex items-start justify-between gap-2">
    <p class="text-[0.65rem] font-bold uppercase tracking-[0.14em] text-[#78909f]">{kpi.label}</p>
    <span class={`h-2 w-2 shrink-0 rounded-full ${barColor}`} aria-hidden="true"></span>
  </div>
  <p class={`mt-2 text-3xl font-bold tracking-[-0.03em] ${toneClasses}`}>{kpi.value}</p>
  <p class="mt-1 text-xs leading-4 text-[#78909f]">{kpi.hint}</p>
</article>
