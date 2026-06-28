import {
  classifySession,
  saveAnswer,
  startSession,
  type DiagnosisResult,
  type DiagnosisSession,
} from "./diagnosis";
import { API_BASE_URL } from "../../components/global.js";

export const PUBLIC_DIAGNOSIS_CONTEXT = {
  assistant_instance_code: "team360_sales_diagnosis",
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

export interface TurnRequest {
  session_id?: string;
  message: string;
  locale?: string;
  interaction_response?: Record<string, unknown>;
}

export interface TurnLanguage {
  initial_language: string;
  current_language: string;
  preferred_response_language: string;
  response_language: string;
  language_confidence: number;
  language_source: string;
  explicit_language_preference: boolean;
}

export type TurnGeneration = {
  status: "success" | "fallback" | "unavailable";
  model?: string | null;
  fallback_used: boolean;
  fallback_reason?: string | null;
};

export type TurnDecision = {
  action: "diagnose" | "reflect_and_ask";
  diagnosis_built?: boolean;
  diagnosis_status?: "gathering" | "sufficient" | "requested" | "completed";
  generation?: TurnGeneration | null;
  retrieval_query?: string;
  readiness_reason?: string;
  intent?: string;
  intent_scope?: string;
  intent_confidence?: number;
  intent_source?: string;
  matched_rule?: string | null;
  classifier_called?: boolean;
};

export interface TurnResponse {
  session_id: string;
  response_text: string;
  turn_count: number;
  is_new: boolean;
  language?: TurnLanguage | null;
  turn_decision?: TurnDecision | null;
  diagnosis?: StructuredDiagnosis | null;
  interaction_block?: unknown;
}

export type StructuredDiagnosis = {
  version: string;
  feasibility:
    | "high"
    | "medium"
    | "low"
    | "needs_validation"
    | "not_recommended";
  automation_mode:
    | "automatic"
    | "human_in_the_loop"
    | "assisted"
    | "manual_with_automation_support"
    | "not_recommended";
  confidence: "high" | "medium" | "low";
  summary: string | null;
  channels: string[];
  systems: string[];
  entities: string[];
  entity_sources: Record<string, string>;
  human_approval:
    | "required"
    | "conditional"
    | "not_required"
    | "unknown";
  automatable_steps: string[];
  human_steps: string[];
  risks: string[];
  assumptions: string[];
  validation_points: string[];
  next_step: string;
  availability:
    | "available_now"
    | "requires_validation"
    | "custom_solution"
    | "not_in_immediate_catalog"
    | "not_recommended";
};

import type { PublicDiagnosisContext } from "../t360/diagnosticador/config/types";

export async function sendPublicTurn(request: TurnRequest, options?: { apiBaseUrl?: string; publicDiagnosisContext?: PublicDiagnosisContext }): Promise<TurnResponse> {
  const baseUrl = options?.apiBaseUrl ?? API_BASE_URL;
  const ctx = options?.publicDiagnosisContext;
  const body = ctx ? { ...ctx, ...request } : request;
  const url = `${baseUrl}/diagnosis/turn`;
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "Error en la comunicación con el servidor");
    throw new Error(detail);
  }
  return res.json();
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
