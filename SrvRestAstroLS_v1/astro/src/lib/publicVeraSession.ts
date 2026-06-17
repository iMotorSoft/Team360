const SESSION_KEY = "team360.vera.session.v1";

export interface VeraSessionData {
  session_id: string | null;
  initial_language: string;
  current_language: string;
  preferred_response_language: string;
  explicit_language_preference: boolean;
}

const DEFAULT_SESSION: VeraSessionData = {
  session_id: null,
  initial_language: "",
  current_language: "",
  preferred_response_language: "",
  explicit_language_preference: false,
};

function isBrowser(): boolean {
  return typeof window !== "undefined";
}

export function loadPublicVeraSession(): VeraSessionData {
  if (!isBrowser()) return { ...DEFAULT_SESSION };
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
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

export function savePublicVeraSession(data: Partial<VeraSessionData>): void {
  if (!isBrowser()) return;
  try {
    const current = loadPublicVeraSession();
    const merged = { ...current, ...data };
    sessionStorage.setItem(SESSION_KEY, JSON.stringify(merged));
  } catch {}
}

export function clearPublicVeraSession(): void {
  if (!isBrowser()) return;
  try {
    sessionStorage.removeItem(SESSION_KEY);
  } catch {}
}

export function mergePublicVeraSession(partial: Partial<VeraSessionData>): VeraSessionData {
  const current = loadPublicVeraSession();
  const merged = { ...current, ...partial };
  savePublicVeraSession(merged);
  return merged;
}
