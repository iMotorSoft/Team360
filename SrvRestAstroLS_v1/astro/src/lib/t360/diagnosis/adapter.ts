import type {
  T360InteractionEventDetail,
  T360InteractionTurnRequest,
} from "./types";

function selectedValues(detail: T360InteractionEventDetail): string[] {
  if (detail.type === "t360.choice.submitted") {
    return [detail.selected_option.value];
  }
  if (detail.type === "t360.choices.submitted") {
    return detail.selected_options.map((option) => option.value);
  }
  return [];
}

function valuesLabel(values: string[]): string {
  return values.filter(Boolean).join(", ");
}

export function t360InteractionEventToTurnRequest(
  detail: T360InteractionEventDetail,
): T360InteractionTurnRequest {
  if (detail.type === "t360.choice.submitted") {
    const value = detail.selected_option.value;
    return {
      message: `Selecciono la opción "${value}". Continuá el diagnóstico con esa respuesta.`,
      display_text: `Seleccioné: ${value}`,
    };
  }

  if (detail.type === "t360.choices.submitted") {
    const label = valuesLabel(selectedValues(detail));
    return {
      message: `Selecciono estas opciones: ${label}. Continuá el diagnóstico con esas respuestas.`,
      display_text: `Seleccioné: ${label}`,
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
