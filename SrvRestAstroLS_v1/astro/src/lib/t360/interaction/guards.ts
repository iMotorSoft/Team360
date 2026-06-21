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

const requirementStatuses = new Set(["missing", "partial", "confirmed"]);
const requiredForValues = new Set(["preliminary_diagnosis", "full_diagnosis", "implementation", "pricing", "handoff"]);
const confidenceValues = new Set(["low", "medium", "high"]);
const MAX_ACTIONS = 3;
const MAX_OPTIONS = 8;
const MAX_REQUIREMENTS = 8;
const MAX_TEXT_ITEMS = 6;
const MAX_TEXT_LENGTH = 320;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isString(value: unknown, maxLength = MAX_TEXT_LENGTH): value is string {
  return typeof value === "string" && value.trim().length > 0 && value.trim().length <= maxLength;
}

function isOptionalString(value: unknown, maxLength = MAX_TEXT_LENGTH): boolean {
  return value === undefined || isString(value, maxLength);
}

function isIntegerInRange(value: unknown, min: number, max: number): value is number {
  return Number.isInteger(value) && Number(value) >= min && Number(value) <= max;
}

function hasUniqueIds(values: unknown[]): boolean {
  const ids = values.map((value) => isRecord(value) && typeof value.id === "string" ? value.id : undefined);
  return ids.every(Boolean) && new Set(ids).size === values.length;
}

function isBoundedArray(value: unknown, min: number, max: number): value is unknown[] {
  return Array.isArray(value) && value.length >= min && value.length <= max;
}

function isStringList(value: unknown): value is string[] {
  return isBoundedArray(value, 1, MAX_TEXT_ITEMS) && value.every((item) => isString(item));
}

export function isT360AvailabilityStatus(value: unknown): value is T360AvailabilityStatus {
  return typeof value === "string" && availabilityStatuses.has(value as T360AvailabilityStatus);
}

export function isT360Action(value: unknown): value is T360Action {
  if (!isRecord(value)) return false;
  if (!isString(value.id) || !isString(value.label)) return false;
  if (!isOptionalString(value.value) || !isOptionalString(value.helper_text)) return false;
  if (typeof value.intent !== "string" || !actionIntents.has(value.intent as T360Action["intent"])) {
    return false;
  }
  if (value.style !== undefined && (typeof value.style !== "string" || !actionStyles.has(value.style))) {
    return false;
  }
  if (value.disabled !== undefined && typeof value.disabled !== "boolean") return false;
  return true;
}

function isActionArray(value: unknown, min = 0): value is T360Action[] {
  if (!isBoundedArray(value, min, MAX_ACTIONS) || !value.every(isT360Action)) return false;
  return hasUniqueIds(value);
}

function isOption(value: unknown) {
  if (!isRecord(value)) return false;
  if (!isString(value.id) || !isString(value.label) || !isString(value.value)) return false;
  if (!isOptionalString(value.description) || !isOptionalString(value.badge, 80)) return false;
  if (value.availability_status !== undefined && !isT360AvailabilityStatus(value.availability_status)) return false;
  return true;
}

function isOptionArray(value: unknown): value is Array<{ id: string }> {
  if (!isBoundedArray(value, 1, MAX_OPTIONS) || !value.every(isOption)) return false;
  return hasUniqueIds(value);
}

function isRequirement(value: unknown) {
  if (!isRecord(value)) return false;
  if (!isString(value.id) || !isString(value.label)) return false;
  if (!isOptionalString(value.description)) return false;
  if (typeof value.status !== "string" || !requirementStatuses.has(value.status)) return false;
  return typeof value.required_for === "string" && requiredForValues.has(value.required_for);
}

function isRequirementArray(value: unknown): value is Array<{ id: string }> {
  if (!isBoundedArray(value, 1, MAX_REQUIREMENTS) || !value.every(isRequirement)) return false;
  return hasUniqueIds(value);
}

function isValidChoiceBounds(value: Record<string, unknown>, optionCount: number, requireSubmitAction: boolean): boolean {
  if (!isString(value.question)) return false;
  if (!isOptionalString(value.helper_text)) return false;
  if (!isOptionArray(value.options)) return false;
  if (value.required !== undefined && typeof value.required !== "boolean") return false;

  if (value.min_selected !== undefined && !isIntegerInRange(value.min_selected, 0, optionCount)) return false;
  if (value.max_selected !== undefined && !isIntegerInRange(value.max_selected, 1, optionCount)) return false;
  if (
    value.min_selected !== undefined
    && value.max_selected !== undefined
    && Number(value.min_selected) > Number(value.max_selected)
  ) {
    return false;
  }

  if (requireSubmitAction) return isT360Action(value.submit_action);
  return value.submit_action === undefined || isT360Action(value.submit_action);
}

export function isT360InteractionBlock(value: unknown): value is T360InteractionBlock {
  if (!isRecord(value) || typeof value.type !== "string" || !interactionKinds.has(value.type as T360InteractionKind)) {
    return false;
  }

  switch (value.type) {
    case "next_step_choice":
      return isOptionalString(value.title) && isOptionalString(value.description) && isActionArray(value.actions, 1);
    case "single_choice":
      return isValidChoiceBounds(value, Array.isArray(value.options) ? value.options.length : 0, false);
    case "multi_choice":
      return isValidChoiceBounds(value, Array.isArray(value.options) ? value.options.length : 0, true);
    case "missing_requirements":
      return isString(value.title) && isOptionalString(value.description) && isRequirementArray(value.requirements)
        && (value.actions === undefined || isActionArray(value.actions));
    case "product_fit_card":
      return isString(value.product_code) && isString(value.product_name) && isString(value.summary)
        && (value.fit_score === undefined || isIntegerInRange(value.fit_score, 0, 100))
        && isT360AvailabilityStatus(value.status)
        && (value.good_fit_reasons === undefined || isStringList(value.good_fit_reasons))
        && (value.limitations === undefined || isStringList(value.limitations))
        && isOptionalString(value.recommended_next_step)
        && (value.actions === undefined || isActionArray(value.actions));
    case "diagnosis_action_card":
      return isString(value.title) && isString(value.summary)
        && isT360AvailabilityStatus(value.status)
        && (value.confidence === undefined || (typeof value.confidence === "string" && confidenceValues.has(value.confidence)))
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
