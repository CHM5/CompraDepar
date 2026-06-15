/**
 * analytics.ts
 * ─────────────
 * Session tracking + anonymous auth state, all via localStorage.
 * No server needed — real OAuth can replace simulateLogin() later.
 */

export type EventType =
  | "search"
  | "filter_apply"
  | "login"
  | "login_click"
  | "login_success"
  | "logout"
  | "result_view"
  | "property_click"
  | "upgrade_click"
  | "no_results"
  | "favorite_add"
  | "favorite_remove"
  | "scoring_open"
  | "scoring_prefs_save";

export interface ScoringPrefs {
  barrio: number;    // 1-5 importance
  m2: number;        // 1-5
  balcon: number;    // 1-5
  price_m2: number;  // 1-5
  cochera: number;   // 1-5
}

export const DEFAULT_PREFS: ScoringPrefs = {
  barrio: 3,
  m2: 3,
  balcon: 3,
  price_m2: 3,
  cochera: 2,
};

// ── Session ID ────────────────────────────────────────────────────────────────

export function getSessionId(): string {
  if (typeof window === "undefined") return "";
  let id = localStorage.getItem("df_session_id");
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem("df_session_id", id);
  }
  return id;
}

// ── Event tracking ────────────────────────────────────────────────────────────

export function trackEvent(type: EventType, data?: Record<string, unknown>): void {
  if (typeof window === "undefined") return;
  const sessionId = getSessionId();
  const events = JSON.parse(localStorage.getItem("df_events") ?? "[]") as unknown[];
  events.push({ type, session_id: sessionId, ts: Date.now(), ...data });
  localStorage.setItem("df_events", JSON.stringify(events.slice(-200)));
}

// ── Auth state (simulated; swap for real OAuth later) ─────────────────────────

export function isLoggedIn(): boolean {
  if (typeof window === "undefined") return false;
  return localStorage.getItem("df_logged_in") === "true";
}

export function simulateLogin(): void {
  if (typeof window === "undefined") return;
  localStorage.setItem("df_logged_in", "true");
  trackEvent("login_success");
}

// ── Scoring preferences ───────────────────────────────────────────────────────

export function loadScoringPrefs(): ScoringPrefs {
  if (typeof window === "undefined") return DEFAULT_PREFS;
  try {
    const raw = localStorage.getItem("df_scoring_prefs");
    if (raw) return { ...DEFAULT_PREFS, ...(JSON.parse(raw) as Partial<ScoringPrefs>) };
  } catch {
    /* ignore */
  }
  return DEFAULT_PREFS;
}

export function saveScoringPrefs(prefs: ScoringPrefs): void {
  if (typeof window === "undefined") return;
  localStorage.setItem("df_scoring_prefs", JSON.stringify(prefs));
  trackEvent("scoring_prefs_save");
}
