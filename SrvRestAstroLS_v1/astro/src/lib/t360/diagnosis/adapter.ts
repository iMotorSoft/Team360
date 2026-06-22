import type {
  T360InteractionEventDetail,
  T360InteractionTurnRequest,
} from "./types";

export function t360InteractionEventToTurnRequest(
  detail: T360InteractionEventDetail,
): T360InteractionTurnRequest {
  if (detail.type === "t360.choice.submitted") {
    const option = detail.selected_option;
    return {
      message: `Sistema de gestión que uso actualmente: ${option.label}.`,
      display_text: `${option.label}`,
      interaction_response: {
        block_type: "single_choice",
        action_id: detail.action_id,
        option_id: option.option_id,
        value: option.value,
        label: option.label,
      },
    };
  }

  if (detail.type === "t360.choices.submitted") {
    const opts = detail.selected_options;
    const labels = opts.map((o) => o.label).join(", ");
    const vals = opts.map((o) => o.value);
    return {
      message: `Prioridades de automatización: ${vals.join(", ")}.`,
      display_text: `${labels}`,
      interaction_response: {
        block_type: "multi_choice",
        action_id: detail.action_id,
        values: vals,
        labels: labels.split(", "),
      },
    };
  }

  switch (detail.intent) {
    case "show_preliminary_diagnosis":
    case "show_current_diagnosis":
      return {
        message: "Dame el diagnóstico actual con la conclusión, factibilidad y próximos pasos.",
        display_text: "Ver diagnóstico",
      };
    case "continue_conversation":
      return {
        message: "Quiero seguir conversando y aportar más contexto.",
        display_text: "Seguir conversando",
      };
    case "request_human_review":
      return {
        message: "Quiero pedir una revisión humana del diagnóstico.",
        display_text: "Pedir revisión humana",
      };
    case "request_contact":
      return {
        message: "Quiero que Team360 me contacte para revisar este diagnóstico.",
        display_text: "Solicitar contacto",
      };
    case "restart":
      return {
        message: "Quiero reiniciar el diagnóstico desde cero.",
        display_text: "Reiniciar diagnóstico",
      };
    case "close":
      return {
        message: "Quiero cerrar esta conversación por ahora.",
        display_text: "Cerrar",
      };
    default:
      return {
        message: `Ejecutá la acción "${detail.action_id}" para continuar el diagnóstico.`,
        display_text: "Continuar",
      };
  }
}
