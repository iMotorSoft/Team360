import {
  classifySession,
  saveAnswer,
  startSession,
  type DiagnosisResult,
  type DiagnosisSession,
} from "./diagnosis";

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
  /** Real diagnosis result when classify succeeded */
  classification?: string;
  score_total?: number;
  automation_mode?: string;
  risk_flags?: string[];
  requires_human_approval?: boolean;
  /** True when classify was called successfully */
  diagnosis_real: boolean;
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

function buildDiagnosisMessage(result: DiagnosisResult): string {
  const summary =
    typeof result.user_response === "object" && result.user_response !== null
      ? (result.user_response as Record<string, unknown>).summary ?? ""
      : "";

  if (summary) {
    return String(summary).trim();
  }

  const parts: string[] = [];

  if (result.score_total !== undefined) {
    const score = result.score_total;
    if (score >= 80) {
      parts.push("El proceso presenta buena factibilidad técnica para automatización.");
    } else if (score >= 50) {
      parts.push("El proceso tiene factibilidad parcial. Algunos aspectos requieren análisis adicional.");
    } else {
      parts.push("El proceso actual presenta complejidades que pueden requerir un enfoque distinto.");
    }
  }

  if (result.requires_human_approval) {
    parts.push("Este caso requiere revisión humana antes de avanzar con una solución automatizada.");
  }

  if (parts.length === 0) {
    return "Recibimos tu consulta. El diagnóstico indica que hay aspectos relevantes a considerar antes de definir una solución.";
  }

  return parts.join(" ");
}

const DEFAULT_CLASSIFY_TIMEOUT_MS = 45_000;

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

  // Save all guided steps with defaults + user text
  const defaultAnswers: Array<{ stepId: string; answer: Record<string, unknown> }> = [
    { stepId: "process_to_automate", answer: { free_text: text } },
    { stepId: "business_pain", answer: { free_text: "Quiero saber si se puede automatizar para ahorrar tiempo y evitar errores." } },
    { stepId: "systems_involved", answer: { selected: ["whatsapp", "email", "browser_portal"] } },
    { stepId: "frequency_volume", answer: { selected: ["daily", "medium_volume"] } },
    { stepId: "rules_clarity", answer: { selected: ["partially_clear"] } },
    { stepId: "human_dependency", answer: { selected: ["medium"] } },
    { stepId: "access_security", answer: { selected: ["password", "email_otp"] } },
    { stepId: "data_sensitivity", answer: { selected: ["personal_data"] } },
    { stepId: "expected_result", answer: { free_text: "Que el proceso quede automatizado y funcione sin intervención manual." } },
    { stepId: "economic_impact", answer: { selected: ["medium"] } },
  ];
  for (const { stepId, answer } of defaultAnswers) {
    await saveAnswer(session.id, stepId, answer);
  }

  // Try real diagnosis via classify with timeout
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), DEFAULT_CLASSIFY_TIMEOUT_MS);

    const result = await classifySession(session.id);
    clearTimeout(timeoutId);

    return {
      session,
      message: buildDiagnosisMessage(result),
      classification: result.classification,
      score_total: result.score_total,
      automation_mode: result.automation_mode,
      risk_flags: result.risk_flags,
      requires_human_approval: result.requires_human_approval,
      diagnosis_real: true,
    };
  } catch {
    // Fallback to preliminary message if classify fails
    return {
      session,
      message: buildPreliminaryMessage(text),
      diagnosis_real: false,
    };
  }
}
