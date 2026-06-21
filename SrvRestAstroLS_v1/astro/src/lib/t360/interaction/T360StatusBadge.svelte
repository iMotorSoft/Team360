<script lang="ts">
  import type { T360AvailabilityStatus, T360DiagnosisSnapshot, T360MissingRequirement } from "./types";

  type BadgeTone = "neutral" | "success" | "info" | "warning" | "error";

  let {
    status,
    label,
    compact = false,
  }: {
    status: T360AvailabilityStatus | T360MissingRequirement["status"] | T360DiagnosisSnapshot["status"] | T360DiagnosisSnapshot["automation_fit"]["label"] | string;
    label?: string;
    compact?: boolean;
  } = $props();

  const statusLabels: Record<string, string> = {
    available_today: "Disponible hoy",
    feasible: "Factible",
    requires_integration: "Requiere integración",
    planned_extension: "Extensión planificada",
    not_recommended: "No recomendable",
    missing: "Faltante",
    partial: "Parcial",
    confirmed: "Confirmado",
    not_ready: "No listo",
    preliminary: "Preliminar",
    usable: "Usable",
    final_like: "Similar final",
    low: "Bajo",
    medium: "Medio",
    good: "Buen encaje",
    high: "Alto",
  };

  const toneByStatus: Record<string, BadgeTone> = {
    available_today: "success",
    feasible: "info",
    requires_integration: "warning",
    planned_extension: "neutral",
    not_recommended: "error",
    missing: "error",
    partial: "warning",
    confirmed: "success",
    not_ready: "neutral",
    preliminary: "info",
    usable: "success",
    final_like: "success",
    low: "warning",
    medium: "info",
    good: "success",
    high: "success",
  };

  const visibleLabel = $derived(label ?? statusLabels[status] ?? status);
  const tone = $derived(toneByStatus[status] ?? "neutral");
  const toneClass = $derived({
    neutral: "badge-neutral",
    success: "badge-success",
    info: "badge-info",
    warning: "badge-warning",
    error: "badge-error",
  }[tone]);
</script>

<span class={`badge ${toneClass} h-auto ${compact ? "badge-sm px-2 py-1 text-[0.66rem]" : "px-2.5 py-2 text-xs"} font-semibold leading-tight`}>
  {visibleLabel}
</span>
