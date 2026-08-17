<script lang="ts">
  import type { StatusFact } from "../../../lib/t360/flow/types";

  let { statusFact, dataSource }: { statusFact: StatusFact; dataSource?: string | null } = $props();

  const meta = $derived.by(() => {
    switch (statusFact) {
      case "closed":
        return { label: "Resuelto", icon: "check", tone: "success", note: "Registro final auditado" };
      case "pending_approval":
        return { label: "Pendiente de aprobación", icon: "clock", tone: "warning", note: "Espera decisión de supervisor" };
      default:
        return { label: "Activo", icon: "pulse", tone: "info", note: dataSource === "AUDIT_SNAPSHOT" ? "Auditado" : "Estado actual" };
    }
  });

  const toneClasses = $derived.by(() => {
    switch (meta.tone) {
      case "success":
        return "border-[#b9e7cc] bg-[#e8f8ef] text-[#17663d]";
      case "warning":
        return "border-[#f1dfa2] bg-[#fff7d9] text-[#765d00]";
      case "danger":
        return "border-[#f1c7c2] bg-[#fdf0ee] text-[#9b3328]";
      default:
        return "border-[#b9def0] bg-[#e9f6fc] text-[#1d6688]";
    }
  });
</script>

<span
  class={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-bold leading-none ${toneClasses}`}
  aria-label={`${meta.label}. ${meta.note}`}
>
  <span class="sr-only">{meta.note}.</span>
  <!-- Icono + texto: no depende solo del color. -->
  <span aria-hidden="true" class="text-[0.7rem]">
    {#if meta.icon === "check"}✓{/if}
    {#if meta.icon === "clock"}◷{/if}
    {#if meta.icon === "pulse"}●{/if}
  </span>
  {meta.label}
</span>
