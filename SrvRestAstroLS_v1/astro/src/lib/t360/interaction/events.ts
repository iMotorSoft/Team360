import type {
  T360Action,
  T360InteractionKind,
  T360SingleChoiceOption,
} from "./types";

export type T360InteractionActionEvent = {
  type: "t360.interaction.action";
  session_id: string;
  block_type: T360InteractionKind;
  action_id: string;
  intent: T360Action["intent"];
  payload?: Record<string, unknown>;
};

export type T360ChoiceSelectedEvent = {
  type: "t360.choice.selected";
  session_id: string;
  block_type: "single_choice";
  option_id: string;
  value: string;
};

export type T360ChoicesSubmittedEvent = {
  type: "t360.choices.submitted";
  session_id: string;
  block_type: "multi_choice";
  selected_options: Array<{
    option_id: string;
    value: string;
  }>;
};

export type T360InteractionDomEventName = "t360action" | "t360choice" | "t360choices";

export function createActionEventDetail(params: {
  sessionId: string;
  blockType: T360InteractionKind;
  action: T360Action;
  payload?: Record<string, unknown>;
}): T360InteractionActionEvent {
  return {
    type: "t360.interaction.action",
    session_id: params.sessionId,
    block_type: params.blockType,
    action_id: params.action.id,
    intent: params.action.intent,
    payload: params.payload,
  };
}

export function dispatchActionEvent(
  target: EventTarget,
  params: {
    sessionId: string;
    blockType: T360InteractionKind;
    action: T360Action;
    payload?: Record<string, unknown>;
  },
) {
  target.dispatchEvent(new CustomEvent<T360InteractionActionEvent>("t360action", {
    bubbles: true,
    composed: true,
    detail: createActionEventDetail(params),
  }));
}

export function dispatchChoiceSelectedEvent(
  target: EventTarget,
  sessionId: string,
  option: T360SingleChoiceOption,
) {
  target.dispatchEvent(new CustomEvent<T360ChoiceSelectedEvent>("t360choice", {
    bubbles: true,
    composed: true,
    detail: {
      type: "t360.choice.selected",
      session_id: sessionId,
      block_type: "single_choice",
      option_id: option.id,
      value: option.value,
    },
  }));
}

export function dispatchChoicesSubmittedEvent(
  target: EventTarget,
  sessionId: string,
  options: T360SingleChoiceOption[],
) {
  target.dispatchEvent(new CustomEvent<T360ChoicesSubmittedEvent>("t360choices", {
    bubbles: true,
    composed: true,
    detail: {
      type: "t360.choices.submitted",
      session_id: sessionId,
      block_type: "multi_choice",
      selected_options: options.map((option) => ({
        option_id: option.id,
        value: option.value,
      })),
    },
  }));
}
