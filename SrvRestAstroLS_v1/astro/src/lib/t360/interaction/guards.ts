import type {
  T360Action,
  T360AvailabilityStatus,
  T360InteractionBlock,
  T360InteractionKind,
} from "./types";

const availabilityStatuses = new Set<T360AvailabilityStatus>([
  "available_today",
  "feasible",
  "requires_integration",
  "planned_extension",
  "not_recommended",
]);

const interactionKinds = new Set<T360InteractionKind>([
  "next_step_choice",
  "single_choice",
  "multi_choice",
  "missing_requirements",
  "product_fit_card",
  "diagnosis_action_card",
]);

const actionIntents = new Set<T360Action["intent"]>([
  "continue_conversation",
  "show_preliminary_diagnosis",
  "show_current_diagnosis",
  "answer_choice",
  "submit_choices",
  "request_contact",
  "request_human_review",
  "restart",
  "close",
]);

const actionStyles = new Set([
  "primary",
  "secondary",
  "ghost",
  "outline",
  "warning",
  "danger",
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

export function isT360AvailabilityStatus(value: unknown): value is T360AvailabilityStatus {
  return typeof value === "string" && availabilityStatuses.has(value as T360AvailabilityStatus);
}

export function isT360Action(value: unknown): value is T360Action {
  if (!isRecord(value)) return false;
  if (!isString(value.id) || !isString(value.label)) return false;
  if (typeof value.intent !== "string" || !actionIntents.has(value.intent as T360Action["intent"])) {
    return false;
  }
  if (value.style !== undefined && (typeof value.style !== "string" || !actionStyles.has(value.style))) {
    return false;
  }
  if (value.disabled !== undefined && typeof value.disabled !== "boolean") return false;
  return true;
}

function isActionArray(value: unknown): value is T360Action[] {
  return Array.isArray(value) && value.every(isT360Action);
}

function isOption(value: unknown) {
  if (!isRecord(value)) return false;
  if (!isString(value.id) || !isString(value.label) || !isString(value.value)) return false;
  if (value.availability_status !== undefined && !isT360AvailabilityStatus(value.availability_status)) return false;
  return true;
}

function isRequirement(value: unknown) {
  if (!isRecord(value)) return false;
  if (!isString(value.id) || !isString(value.label)) return false;
  if (!["missing", "partial", "confirmed"].includes(String(value.status))) return false;
  return ["preliminary_diagnosis", "full_diagnosis", "implementation", "pricing", "handoff"].includes(String(value.required_for));
}

export function isT360InteractionBlock(value: unknown): value is T360InteractionBlock {
  if (!isRecord(value) || typeof value.type !== "string" || !interactionKinds.has(value.type as T360InteractionKind)) {
    return false;
  }

  switch (value.type) {
    case "next_step_choice":
      return isActionArray(value.actions);
    case "single_choice":
      return isString(value.question) && Array.isArray(value.options) && value.options.every(isOption)
        && (value.submit_action === undefined || isT360Action(value.submit_action));
    case "multi_choice":
      return isString(value.question) && Array.isArray(value.options) && value.options.every(isOption)
        && isT360Action(value.submit_action);
    case "missing_requirements":
      return isString(value.title) && Array.isArray(value.requirements) && value.requirements.every(isRequirement)
        && (value.actions === undefined || isActionArray(value.actions));
    case "product_fit_card":
      return isString(value.product_code) && isString(value.product_name) && isString(value.summary)
        && isT360AvailabilityStatus(value.status)
        && (value.actions === undefined || isActionArray(value.actions));
    case "diagnosis_action_card":
      return isString(value.title) && isString(value.summary)
        && isT360AvailabilityStatus(value.status)
        && isT360Action(value.primary_action)
        && (value.secondary_actions === undefined || isActionArray(value.secondary_actions));
    default:
      return false;
  }
}

export function normalizeT360InteractionBlock(value: unknown): T360InteractionBlock | undefined {
  return isT360InteractionBlock(value) ? value : undefined;
}

export function getStableBlockKey(value: unknown): string {
  if (!isRecord(value)) return "invalid";
  if (typeof value.type !== "string") return "unknown";
  if (isString(value.id)) return `${value.type}:${value.id}`;
  return value.type;
}
