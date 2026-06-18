import { API_BASE_URL } from "../../components/global.js";

const API_BASE = `${API_BASE_URL}/automation-diagnosis`;

export interface DiagnosisSession {
  id: string;
  organization_id: string;
  workspace_id: string;
  assistant_instance_id: string;
  automation_package_id: string;
  knowledge_scope_id: string;
  source_url: string;
  site_channel: string;
  lead_owner: string;
  locale: string;
  market: string;
  visitor: Record<string, unknown>;
  package_worker_ids: string[];
  cost_attribution: Record<string, unknown>;
  metadata: Record<string, unknown>;
  status: string;
  correlation_id: string;
  answers: Record<string, unknown>;
  events: unknown[];
  created_at_utc: string;
  updated_at_utc: string;
}

export interface SaveAnswerResponse {
  session_id: string;
  answer: {
    step_id: string;
    selected: string[];
    free_text: string;
    normalized_text: string;
    metadata: Record<string, unknown>;
  };
}

export interface DiagnosisResult {
  classification: string;
  score_total: number;
  automation_mode: string;
  recommended_package_type: string;
  suggested_worker_definitions: string[];
  required_package_worker_config: Record<string, unknown>;
  required_credential_refs: unknown[];
  required_knowledge_scope: Record<string, unknown>;
  risk_flags: string[];
  blocked_actions: string[];
  requires_human_approval: boolean;
  user_response: Record<string, unknown>;
  internal_card: Record<string, unknown>;
  ai_interpretation: Record<string, unknown>;
  retrieved_context: Record<string, unknown>;
  score_breakdown: Record<string, number>;
  rule_hits: string[];
}

export interface ApiError {
  detail: string;
  status_code: number;
}

export async function startSession(payload?: {
  source_url?: string;
  locale?: string;
  visitor?: Record<string, unknown>;
  assistant_instance_id?: string;
}): Promise<DiagnosisSession> {
  const res = await fetch(`${API_BASE}/session/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload ?? {}),
  });
  if (!res.ok) {
    const err: ApiError = { detail: await res.text(), status_code: res.status };
    throw err;
  }
  return res.json();
}

export async function saveAnswer(
  sessionId: string,
  stepId: string,
  answer: Record<string, unknown>,
): Promise<SaveAnswerResponse> {
  const res = await fetch(`${API_BASE}/session/${encodeURIComponent(sessionId)}/answer`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ step_id: stepId, answer }),
  });
  if (!res.ok) {
    const err: ApiError = { detail: await res.text(), status_code: res.status };
    throw err;
  }
  return res.json();
}

export async function classifySession(sessionId: string): Promise<DiagnosisResult> {
  const res = await fetch(`${API_BASE}/session/${encodeURIComponent(sessionId)}/classify`, {
    method: "POST",
  });
  if (!res.ok) {
    const err: ApiError = { detail: await res.text(), status_code: res.status };
    throw err;
  }
  return res.json();
}

export const GUIDED_STEPS = [
  {
    id: "process_to_automate",
    label: "Proceso a automatizar",
    type: "controlled_text",
    description: "¿Qué proceso necesita automatizar? Descríbalo brevemente.",
    required: true,
  },
  {
    id: "business_pain",
    label: "Dolor de negocio",
    type: "controlled_text",
    description: "¿Qué problema concreto resuelve esta automatización?",
    required: true,
  },
  {
    id: "systems_involved",
    label: "Sistemas involucrados",
    type: "multi_choice_with_text",
    description: "¿Qué sistemas utiliza hoy para este proceso?",
    options: ["excel", "erp", "sap_b1", "whatsapp", "email", "browser_portal", "desktop_app", "api", "other"],
    required: true,
  },
  {
    id: "frequency_volume",
    label: "Frecuencia y volumen",
    type: "multi_choice_with_text",
    description: "¿Con qué frecuencia y en qué volumen se realiza?",
    options: ["daily", "weekly", "monthly", "low_volume", "medium_volume", "high_volume"],
    required: true,
  },
  {
    id: "rules_clarity",
    label: "Claridad de reglas",
    type: "single_choice_with_text",
    description: "¿Qué tan claras están las reglas del proceso?",
    options: ["clear", "partially_clear", "mostly_manual", "unknown"],
    required: true,
  },
  {
    id: "human_dependency",
    label: "Dependencia humana",
    type: "single_choice_with_text",
    description: "¿Cuánto criterio humano requiere el proceso?",
    options: ["low", "medium", "high", "expert_judgement"],
    required: true,
  },
  {
    id: "access_security",
    label: "Accesos, permisos y MFA",
    type: "multi_choice_with_text",
    description: "¿Qué métodos de acceso y autenticación intervienen?",
    options: ["password", "role_permissions", "email_otp", "sms_otp", "totp", "push_or_qr", "fido2_hardware", "biometric", "unknown"],
    required: true,
  },
  {
    id: "data_sensitivity",
    label: "Sensibilidad de datos",
    type: "multi_choice_with_text",
    description: "¿Qué nivel de sensibilidad tienen los datos involucrados?",
    options: ["public", "personal_data", "financial_data", "erp_operational_data", "religious_or_sensitive", "banking_or_payments"],
    required: true,
  },
  {
    id: "expected_result",
    label: "Resultado esperado",
    type: "controlled_text",
    description: "¿Qué resultado concreto espera obtener de la automatización?",
    required: true,
  },
  {
    id: "economic_impact",
    label: "Impacto económico",
    type: "single_choice_with_text",
    description: "¿Cuál es el impacto económico u operativo estimado?",
    options: ["low", "medium", "high", "critical"],
    required: true,
  },
] as const;

export const OPTION_LABELS: Record<string, string> = {
  excel: "Excel / Hojas de cálculo",
  erp: "ERP",
  sap_b1: "SAP Business One",
  whatsapp: "WhatsApp",
  email: "Correo electrónico",
  browser_portal: "Portal web / intranet",
  desktop_app: "Aplicación de escritorio",
  api: "API / integración",
  other: "Otro",
  daily: "Diario",
  weekly: "Semanal",
  monthly: "Mensual",
  low_volume: "Bajo volumen",
  medium_volume: "Volumen moderado",
  high_volume: "Alto volumen",
  clear: "Reglas claras y documentadas",
  partially_clear: "Reglas parcialmente claras",
  mostly_manual: "Mayormente manual / criterio humano",
  unknown: "Desconocido / no hay reglas escritas",
  low: "Bajo",
  medium: "Medio",
  high: "Alto",
  expert_judgement: "Requiere juicio de experto",
  password: "Contraseña",
  role_permissions: "Permisos por rol",
  email_otp: "Código por correo",
  sms_otp: "Código por SMS",
  totp: "App de autenticación (TOTP)",
  push_or_qr: "Notificación push / QR",
  fido2_hardware: "Llave de seguridad (FIDO2)",
  biometric: "Biometría",
  public: "Públicos",
  personal_data: "Datos personales",
  financial_data: "Datos financieros",
  erp_operational_data: "Datos operativos ERP",
  religious_or_sensitive: "Datos sensibles / religiosos",
  banking_or_payments: "Banca / pagos",
};
