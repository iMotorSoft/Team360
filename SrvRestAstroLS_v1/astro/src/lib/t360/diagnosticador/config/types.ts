export interface DiagnosticadorSessionData {
  session_id: string | null;
  initial_language: string;
  current_language: string;
  preferred_response_language: string;
  explicit_language_preference: boolean;
}

export interface PublicDiagnosisContext {
  assistant_instance_code: string;
  source_channel: string;
  site_channel: string;
  locale: string;
  lead_owner: string;
  service_code: string;
  package_code: string;
  knowledge_scope_code: string;
  template_code: string;
}
