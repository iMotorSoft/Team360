import { saveAnswer, startSession, type DiagnosisSession } from "./diagnosis";

export const PUBLIC_DIAGNOSIS_CONTEXT = {
  assistant_instance_code: "team360_sales_diagnosis",
  assistant_display_name: "Vera",
  source_channel: "home_public",
  site_channel: "team360.live",
  locale: "es",
  lead_owner: "team360_live",
  service_code: "svc_sales_diagnosis",
  package_code: "pkg_sales_diagnosis",
  knowledge_scope_code: "ks_team360_sales_diagnosis",
  template_code: "team360_sales_automation_diagnosis",
} as const;

export interface PublicDiagnosisRequest {
  text: string;
  sourceUrl: string;
  visitorAnonymousId: string;
}

export interface PublicDiagnosisResponse {
  session: DiagnosisSession;
  message: string;
}

function buildPreliminaryMessage(text: string): string {
  const normalized = text.trim();
  const shortText = normalized.length > 160 ? `${normalized.slice(0, 157)}...` : normalized;

  return [
    "Gracias. Lo tomo como punto de partida para el diagnóstico.",
    `Entendí esta oportunidad inicial: "${shortText}"`,
    "Para avanzar sin convertir esto en un formulario, el siguiente paso es revisar qué sistemas participan, dónde se pierde seguimiento y qué parte conviene automatizar primero.",
  ].join(" ");
}

export async function startPublicDiagnosis(request: PublicDiagnosisRequest): Promise<PublicDiagnosisResponse> {
  const text = request.text.trim();

  if (!text) {
    throw new Error("Escribí qué proceso querés mejorar antes de analizar la oportunidad.");
  }

  const session = await startSession({
    source_url: request.sourceUrl,
    locale: PUBLIC_DIAGNOSIS_CONTEXT.locale,
    assistant_instance_id: PUBLIC_DIAGNOSIS_CONTEXT.assistant_instance_code,
    visitor: {
      anonymous_id: request.visitorAnonymousId,
      source_channel: PUBLIC_DIAGNOSIS_CONTEXT.source_channel,
      site_channel: PUBLIC_DIAGNOSIS_CONTEXT.site_channel,
      assistant_display_name: PUBLIC_DIAGNOSIS_CONTEXT.assistant_display_name,
      lead_owner: PUBLIC_DIAGNOSIS_CONTEXT.lead_owner,
      service_code: PUBLIC_DIAGNOSIS_CONTEXT.service_code,
      package_code: PUBLIC_DIAGNOSIS_CONTEXT.package_code,
      knowledge_scope_code: PUBLIC_DIAGNOSIS_CONTEXT.knowledge_scope_code,
      template_code: PUBLIC_DIAGNOSIS_CONTEXT.template_code,
      initial_text_length: text.length,
    },
  });

  await saveAnswer(session.id, "process_to_automate", { free_text: text });

  return {
    session,
    message: buildPreliminaryMessage(text),
  };
}
