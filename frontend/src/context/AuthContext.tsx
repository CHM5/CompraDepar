"use client";

/**
 * context/AuthContext.tsx
 * ───────────────────────
 * Global auth state. Works with real Firebase (when configured) or
 * with a localStorage mock for local development without Firebase setup.
 */

import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import {
  FIREBASE_CONFIGURED,
  signInWithGoogle,
  signOutFirebase,
  subscribeToAuthChanges,
  type User,
} from "@/lib/firebase";
import { trackEvent } from "@/lib/analytics";

// ── Types ─────────────────────────────────────────────────────────────────────

export interface AppUser {
  uid: string;
  displayName: string;
  email: string;
  photoURL: string | null;
}

export type UserPlan = "free" | "premium";

// ── Admin list from env var (comma-separated emails) ─────────────────────────

const ADMIN_EMAILS: string[] = (process.env.NEXT_PUBLIC_ADMIN_EMAILS ?? "")
  .split(",")
  .map((e) => e.trim())
  .filter(Boolean);

// ── Context shape ─────────────────────────────────────────────────────────────

interface AuthContextValue {
  user: AppUser | null;
  loading: boolean;
  plan: UserPlan;
  isAdmin: boolean;
  login: () => Promise<void>;
  logout: () => Promise<void>;
  setPlan: (plan: UserPlan) => void;
}

const AuthContext = createContext<AuthContextValue>({
  user: null,
  loading: true,
  plan: "free",
  isAdmin: false,
  login: async () => {},
  logout: async () => {},
  setPlan: () => {},
});

// ── Helpers ───────────────────────────────────────────────────────────────────

function planKey(email: string) {
  return `df_plan_${email}`;
}

function getPlan(email: string): UserPlan {
  if (ADMIN_EMAILS.includes(email)) return "premium";
  if (typeof window === "undefined") return "premium";
  return (localStorage.getItem(planKey(email)) as UserPlan) ?? "premium";
}

function appUserFromFirebase(fb: User): AppUser {
  return {
    uid: fb.uid,
    displayName: fb.displayName ?? "Usuario",
    email: fb.email ?? "",
    photoURL: fb.photoURL,
  };
}

// ── Provider ──────────────────────────────────────────────────────────────────

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AppUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [plan, setPlanState] = useState<UserPlan>("free");

  function applyUser(appUser: AppUser | null) {
    setUser(appUser);
    setPlanState(appUser ? getPlan(appUser.email) : "free");
    setLoading(false);
  }

  useEffect(() => {
    if (FIREBASE_CONFIGURED) {
      // ── Real Firebase auth ──────────────────────────────────────────────────
      const unsub = subscribeToAuthChanges((fb) => {
        applyUser(fb ? appUserFromFirebase(fb) : null);
      });
      return unsub;
    } else {
      // ── Mock auth: restore from localStorage ────────────────────────────────
      if (typeof window !== "undefined") {
        const raw = localStorage.getItem("df_mock_user");
        if (raw) {
          try {
            applyUser(JSON.parse(raw) as AppUser);
            return;
          } catch {
            /* corrupt data — ignore */
          }
        }
      }
      setLoading(false);
    }
  }, []);

  async function login() {
    setLoading(true);
    try {
      if (FIREBASE_CONFIGURED) {
        // Firebase signs in and the onAuthStateChanged listener picks it up
        await signInWithGoogle();
      } else {
        // Mock login for local dev (no Firebase configured)
        const mock: AppUser = {
          uid: "mock-uid-" + Date.now(),
          displayName: "Usuario Demo",
          email: "demo@localhost",
          photoURL: null,
        };
        if (typeof window !== "undefined") {
          localStorage.setItem("df_mock_user", JSON.stringify(mock));
          localStorage.setItem("df_logged_in", "true");
        }
        applyUser(mock);
        trackEvent("login_success", { email: mock.email });
      }
    } finally {
      if (!FIREBASE_CONFIGURED) setLoading(false);
    }
  }

  async function logout() {
    if (FIREBASE_CONFIGURED) {
      await signOutFirebase();
      // onAuthStateChanged fires with null → applyUser(null)
    } else {
      if (typeof window !== "undefined") {
        localStorage.removeItem("df_mock_user");
        localStorage.removeItem("df_logged_in");
      }
      applyUser(null);
    }
  }

  function setPlan(p: UserPlan) {
    if (user) localStorage.setItem(planKey(user.email), p);
    setPlanState(p);
  }

  const isAdmin =
    ADMIN_EMAILS.length > 0 && !!user && ADMIN_EMAILS.includes(user.email);

  return (
    <AuthContext.Provider
      value={{ user, loading, plan, isAdmin, login, logout, setPlan }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
