<script lang="ts">
  import Badge from "./Badge.svelte";

  let {
    status,
    label,
  }: {
    status: string;
    label?: string;
  } = $props();

  const labelByStatus: Record<string, string> = {
    acknowledged: "En seguimiento",
    active: "Activo",
    attention: "Requiere atención",
    completed: "Completado",
    connected: "Conectado",
    critical: "Crítico",
    failed: "Falló",
    generating: "Generando",
    healthy: "Saludable",
    high: "Alta",
    info: "Informativa",
    in_progress: "En curso",
    invited: "Invitado",
    low: "Baja",
    medium: "Media",
    onboarding: "En activación",
    open: "Abierta",
    paused: "Pausado",
    pending: "Pendiente",
    ready: "Listo",
    resolved: "Resuelta",
    review: "Revisión recomendada",
    scheduled: "Programado",
    warning: "Revisión recomendada",
  };
  const visibleLabel = $derived(label ?? labelByStatus[status] ?? status);

  const variant = $derived.by(() => {
    if (
      [
        "active",
        "healthy",
        "completed",
        "ready",
        "connected",
        "resolved",
      ].includes(status)
    )
      return "success";
    if (
      [
        "attention",
        "warning",
        "pending",
        "onboarding",
        "in_progress",
        "generating",
        "scheduled",
        "review",
        "high",
      ].includes(status)
    )
      return "warning";
    if (["failed", "critical", "paused"].includes(status)) return "danger";
    return "info";
  });
</script>

<Badge
  {variant}
  class="h-auto px-2 py-1 text-xs font-bold uppercase tracking-[0.08em]"
>
  {visibleLabel}
</Badge>
