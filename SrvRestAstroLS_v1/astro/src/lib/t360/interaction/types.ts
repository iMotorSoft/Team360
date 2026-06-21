export type T360AvailabilityStatus =
  | "available_today"
  | "feasible"
  | "requires_integration"
  | "planned_extension"
  | "not_recommended";

export type T360InteractionKind =
  | "next_step_choice"
  | "single_choice"
  | "multi_choice"
  | "missing_requirements"
  | "product_fit_card"
  | "diagnosis_action_card";

export type T360ActionStyle =
  | "primary"
  | "secondary"
  | "ghost"
  | "outline"
  | "warning"
  | "danger";

export type T360Action = {
  id: string;
  label: string;
  value?: string;
  style?: T360ActionStyle;
  disabled?: boolean;
  helper_text?: string;
  intent:
    | "continue_conversation"
    | "show_preliminary_diagnosis"
    | "show_current_diagnosis"
    | "answer_choice"
    | "submit_choices"
    | "request_contact"
    | "request_human_review"
    | "restart"
    | "close";
};

export type T360SingleChoiceOption = {
  id: string;
  label: string;
  value: string;
  description?: string;
  badge?: string;
  availability_status?: T360AvailabilityStatus;
};

export type T360NextStepChoiceBlock = {
  type: "next_step_choice";
  title?: string;
  description?: string;
  actions: T360Action[];
};

export type T360SingleChoiceBlock = {
  type: "single_choice";
  question: string;
  helper_text?: string;
  required?: boolean;
  options: T360SingleChoiceOption[];
  submit_action?: T360Action;
};

export type T360MultiChoiceBlock = {
  type: "multi_choice";
  question: string;
  helper_text?: string;
  min_selected?: number;
  max_selected?: number;
  options: T360SingleChoiceOption[];
  submit_action: T360Action;
};

export type T360MissingRequirement = {
  id: string;
  label: string;
  description?: string;
  status: "missing" | "partial" | "confirmed";
  required_for:
    | "preliminary_diagnosis"
    | "full_diagnosis"
    | "implementation"
    | "pricing"
    | "handoff";
};

export type T360MissingRequirementsBlock = {
  type: "missing_requirements";
  title: string;
  description?: string;
  requirements: T360MissingRequirement[];
  actions?: T360Action[];
};

export type T360ProductFitCardBlock = {
  type: "product_fit_card";
  product_code: string;
  product_name: string;
  fit_score?: number;
  status: T360AvailabilityStatus;
  summary: string;
  good_fit_reasons?: string[];
  limitations?: string[];
  recommended_next_step?: string;
  actions?: T360Action[];
};

export type T360DiagnosisActionCardBlock = {
  type: "diagnosis_action_card";
  title: string;
  summary: string;
  status: T360AvailabilityStatus;
  confidence?: "low" | "medium" | "high";
  primary_action: T360Action;
  secondary_actions?: T360Action[];
};

export type T360InteractionBlock =
  | T360NextStepChoiceBlock
  | T360SingleChoiceBlock
  | T360MultiChoiceBlock
  | T360MissingRequirementsBlock
  | T360ProductFitCardBlock
  | T360DiagnosisActionCardBlock;

export type T360ConversationState = {
  session_id: string;
  turn_count: number;
  phase:
    | "opening"
    | "discovery"
    | "slot_filling"
    | "preliminary_diagnosis"
    | "refinement"
    | "handoff_ready"
    | "closed";
  known_slots?: Record<string, unknown>;
  missing_slots?: string[];
  can_show_preliminary_diagnosis: boolean;
  should_offer_diagnosis_now?: boolean;
  last_user_intent?:
    | "answer"
    | "question"
    | "request_diagnosis"
    | "request_report"
    | "continue"
    | "unknown";
};

export type T360DiagnosisSnapshot = {
  status: "not_ready" | "preliminary" | "usable" | "final_like";
  title?: string;
  summary: string;
  automation_fit?: {
    score?: number;
    label: "low" | "medium" | "good" | "high";
  };
  availability_status: T360AvailabilityStatus;
  recommended_path?: string[];
  detected_use_case?: {
    label: string;
    category?: string;
  };
  suggested_products?: Array<{
    product_code: string;
    product_name: string;
    status: T360AvailabilityStatus;
    fit_score?: number;
  }>;
  risks?: string[];
  missing_requirements?: T360MissingRequirement[];
  next_best_action?: T360Action;
};

export type T360AssistantTurnResponse = {
  assistant_text: string;
  conversation_state?: T360ConversationState;
  interaction_block?: T360InteractionBlock;
  diagnosis?: T360DiagnosisSnapshot;
};
