export interface DiagnosticadorSessionData {
  session_id: string | null;
  initial_language: string;
  current_language: string;
  preferred_response_language: string;
  explicit_language_preference: boolean;
}
