import type {
  TurnLanguage,
  TurnDecision,
  StructuredDiagnosis,
} from "../../api/publicDiagnosis";
import type {
  T360ChoiceSelectedEvent,
  T360ChoicesSubmittedEvent,
  T360InteractionActionEvent,
} from "../interaction/events";
import type { T360InteractionBlock } from "../interaction/types";

export type T360DiagnosisBackendTurnResponse = {
  session_id: string;
  response_text: string;
  assistant_display_name?: string;
  turn_count: number;
  is_new: boolean;
  language?: TurnLanguage | null;
  turn_decision?: TurnDecision | null;
  diagnosis?: StructuredDiagnosis | null;
  interaction_block?: unknown;
};

export type T360NormalizedDiagnosisTurn = {
  session_id: string;
  assistant_text: string;
  assistant_display_name?: string;
  turn_count: number;
  is_new: boolean;
  language?: TurnLanguage | null;
  turn_decision?: TurnDecision | null;
  diagnosis?: StructuredDiagnosis | null;
  interaction_block?: unknown;
  valid_interaction_block?: T360InteractionBlock;
  has_interaction_block_payload: boolean;
  interaction_block_valid: boolean;
};

export type T360InteractionEventDetail =
  | T360InteractionActionEvent
  | T360ChoiceSelectedEvent
  | T360ChoicesSubmittedEvent;

export type T360InteractionTurnRequest = {
  message: string;
  display_text: string;
  interaction_response?: {
    block_type: "single_choice" | "multi_choice";
    action_id: string;
    option_id?: string;
    value?: string;
    values?: string[];
    label?: string;
    labels?: string[];
  };
};
