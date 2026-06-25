import {
  loadSession,
  saveSession,
  clearSession,
  mergeSession,
  resetConversationOnPageLoad,
} from "./t360/diagnosticador/state/session";
import { DEFAULT_SESSION_STORAGE_KEY } from "./t360/diagnosticador/config/defaults";
import type { DiagnosticadorSessionData } from "./t360/diagnosticador/config/types";

export type { DiagnosticadorSessionData };
export type VeraSessionData = DiagnosticadorSessionData;

export function loadPublicVeraSession(): DiagnosticadorSessionData {
  return loadSession(DEFAULT_SESSION_STORAGE_KEY);
}

export function savePublicVeraSession(data: Partial<DiagnosticadorSessionData>): void {
  saveSession(DEFAULT_SESSION_STORAGE_KEY, data);
}

export function clearPublicVeraSession(): void {
  clearSession(DEFAULT_SESSION_STORAGE_KEY);
}

export function mergePublicVeraSession(partial: Partial<DiagnosticadorSessionData>): DiagnosticadorSessionData {
  return mergeSession(DEFAULT_SESSION_STORAGE_KEY, partial);
}

export function resetConversationSessionOnPageLoad(): void {
  resetConversationOnPageLoad(DEFAULT_SESSION_STORAGE_KEY);
}
