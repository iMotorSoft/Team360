import { normalizeT360InteractionBlock } from "../interaction/guards";
import type {
  T360DiagnosisBackendTurnResponse,
  T360NormalizedDiagnosisTurn,
} from "./types";

function readInteractionBlock(value: T360DiagnosisBackendTurnResponse): unknown {
  if (!Object.prototype.hasOwnProperty.call(value, "interaction_block")) {
    return undefined;
  }
  return value.interaction_block;
}

export function normalizeT360DiagnosisTurn(
  response: T360DiagnosisBackendTurnResponse,
): T360NormalizedDiagnosisTurn {
  const interactionBlock = readInteractionBlock(response);
  const validInteractionBlock = normalizeT360InteractionBlock(interactionBlock);
  const hasInteractionBlockPayload = interactionBlock !== undefined && interactionBlock !== null;

  return {
    session_id: response.session_id,
    assistant_text: response.response_text,
    turn_count: response.turn_count,
    is_new: response.is_new,
    language: response.language,
    turn_decision: response.turn_decision,
    diagnosis: response.diagnosis,
    interaction_block: interactionBlock,
    valid_interaction_block: validInteractionBlock,
    has_interaction_block_payload: hasInteractionBlockPayload,
    interaction_block_valid: Boolean(validInteractionBlock),
  };
}
