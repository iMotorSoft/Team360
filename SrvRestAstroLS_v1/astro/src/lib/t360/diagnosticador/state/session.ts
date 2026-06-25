import type { DiagnosticadorSessionData } from "../config/types";

const DEFAULT_SESSION: DiagnosticadorSessionData = {
  session_id: null,
  initial_language: "",
  current_language: "",
  preferred_response_language: "",
  explicit_language_preference: false,
};

function isBrowser(): boolean {
  return typeof window !== "undefined";
}

export function loadSession(storageKey: string): DiagnosticadorSessionData {
  if (!isBrowser()) return { ...DEFAULT_SESSION };
  try {
    const raw = sessionStorage.getItem(storageKey);
    if (!raw) return { ...DEFAULT_SESSION };
    const parsed = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null) return { ...DEFAULT_SESSION };
    return {
      session_id: typeof parsed.session_id === "string" ? parsed.session_id : null,
      initial_language: typeof parsed.initial_language === "string" ? parsed.initial_language : "",
      current_language: typeof parsed.current_language === "string" ? parsed.current_language : "",
      preferred_response_language:
        typeof parsed.preferred_response_language === "string"
          ? parsed.preferred_response_language
          : "",
      explicit_language_preference:
        typeof parsed.explicit_language_preference === "boolean"
          ? parsed.explicit_language_preference
          : false,
    };
  } catch {
    return { ...DEFAULT_SESSION };
  }
}

export function saveSession(storageKey: string, data: Partial<DiagnosticadorSessionData>): void {
  if (!isBrowser()) return;
  try {
    const current = loadSession(storageKey);
    const merged = { ...current, ...data };
    sessionStorage.setItem(storageKey, JSON.stringify(merged));
  } catch {}
}

export function clearSession(storageKey: string): void {
  if (!isBrowser()) return;
  try {
    sessionStorage.removeItem(storageKey);
  } catch {}
}

export function mergeSession(storageKey: string, partial: Partial<DiagnosticadorSessionData>): DiagnosticadorSessionData {
  const current = loadSession(storageKey);
  const merged = { ...current, ...partial };
  saveSession(storageKey, merged);
  return merged;
}

export function resetConversationOnPageLoad(storageKey: string): void {
  if (!isBrowser()) return;
  try {
    const stored = loadSession(storageKey);
    if (!stored.session_id) return;
    saveSession(storageKey, {
      session_id: null,
      initial_language: stored.initial_language,
      current_language: stored.current_language,
      preferred_response_language: stored.preferred_response_language,
      explicit_language_preference: stored.explicit_language_preference,
    });
  } catch {}
}
