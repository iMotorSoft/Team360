<script lang="ts">
  import { flowDateTime } from "../../../lib/t360/flow/format";
  import type { TimelineEvent } from "../../../lib/t360/flow/types";

  let { events }: { events: TimelineEvent[] } = $props();

  interface Step {
    label: string;
    icon: string;
    tone: "brand" | "neutral" | "success" | "danger" | "warning";
  }

  function describe(event: TimelineEvent): Step {
    switch (event.event_type) {
      case "REQUEST_RECEIVED":
        return { label: "Reclamo recibido", icon: "inbox", tone: "brand" };
      case "REQUEST_CONFIRMED":
        return { label: "Reclamo confirmado", icon: "confirm", tone: "brand" };
      case "ROUTING_ASSIGNED":
        return { label: `Asignado a Nivel ${event.level ?? ""}`, icon: "assign", tone: "neutral" };
      case "SLA_STARTED":
        return { label: `SLA Nivel ${event.level ?? ""} iniciado`, icon: "sla", tone: "neutral" };
      case "SLA_MET":
        return { label: `SLA Nivel ${event.level ?? ""} cumplido`, icon: "check", tone: "success" };
      case "SLA_BREACHED":
        return { label: `SLA Nivel ${event.level ?? ""} vencido`, icon: "alert", tone: "danger" };
      case "ESCALATED":
        return { label: "Escalamiento de nivel", icon: "up", tone: "warning" };
      case "RESOLUTION_PROPOSED":
        return { label: "Resolución propuesta por el técnico", icon: "propose", tone: "brand" };
      case "APPROVAL_NOTIFICATION_RESENT":
        return { label: "Solicitud de aprobación reenviada", icon: "send", tone: "brand" };
      case "CLOSURE_APPROVED":
        return { label: "Cierre autorizado por supervisor", icon: "approve", tone: "success" };
      case "REQUEST_RESOLVED":
        return { label: "Caso resuelto", icon: "check", tone: "success" };
      default:
        return { label: event.event_type, icon: "dot", tone: "neutral" };
    }
  }

  const toneDot = $derived.by(() => (tone: Step["tone"]) => {
    switch (tone) {
      case "brand":
        return "bg-[#168b88]";
      case "success":
        return "bg-[#30ae69]";
      case "danger":
        return "bg-[#d23a2a]";
      case "warning":
        return "bg-[#d7ba12]";
      default:
        return "bg-[#78909f]";
    }
  });
</script>

<ol class="relative space-y-0">
  {#each events as event, index (index)}
    {@const step = describe(event)}
    <li class="relative flex gap-4 pb-5 last:pb-0">
      {#if index < events.length - 1}
        <span class="absolute start-[0.4375rem] top-5 bottom-0 w-px bg-[#e4ecee]" aria-hidden="true"></span>
      {/if}
      <span class={`relative z-10 mt-1 grid size-3.5 shrink-0 place-items-center rounded-full ring-4 ring-white ${toneDot(step.tone)}`} aria-hidden="true">
      </span>
      <div class="min-w-0">
        <p class="text-sm font-semibold leading-5 text-[#31536b]">{step.label}</p>
        <p class="mt-0.5 text-xs text-[#78909f]">
          {flowDateTime(event.timestamp ?? null)}
          {#if event.level !== null && event.level !== undefined && ["ROUTING_ASSIGNED", "SLA_STARTED", "SLA_MET", "SLA_BREACHED", "ESCALATED"].includes(event.event_type)}
            · Nivel {event.level}
          {/if}
          {#if event.event_type === "APPROVAL_NOTIFICATION_RESENT" && event.recipient}
            · {event.recipient}
          {/if}
        </p>
      </div>
    </li>
  {/each}
</ol>
