/**
 * lib/firebase.ts
 * ───────────────
 * Firebase initialisation. The app works with OR without Firebase:
 *  - With NEXT_PUBLIC_FIREBASE_API_KEY set → real Google Sign-In via Firebase.
 *  - Without it                            → mock auth backed by localStorage.
 *
 * To enable real auth:
 *   1. Create a Firebase project at https://console.firebase.google.com/
 *   2. Enable Google Sign-In in Authentication → Sign-in method
 *   3. Add localhost and your domain to Authorized domains
 *   4. Copy the config values to .env.local (see .env.local.example)
 */

import type { FirebaseApp } from "firebase/app";
import type { Auth, User } from "firebase/auth";

export const FIREBASE_CONFIGURED = !!(
  process.env.NEXT_PUBLIC_FIREBASE_API_KEY &&
  process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID
);

let _app: FirebaseApp | undefined;
let _auth: Auth | undefined;

async function getFirebase() {
  if (!FIREBASE_CONFIGURED) return null;
  if (_auth) return _auth;

  const { initializeApp, getApps } = await import("firebase/app");
  const { getAuth, GoogleAuthProvider: GP } = await import("firebase/auth");

  const config = {
    apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
    authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
    projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
    storageBucket: process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET,
    messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID,
    appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
  };

  _app = !getApps().length ? initializeApp(config) : getApps()[0];
  _auth = getAuth(_app);
  return _auth;
}

/** Sign in with Google popup. Returns the Firebase User or null. */
export async function signInWithGoogle(): Promise<User | null> {
  const auth = await getFirebase();
  if (!auth) return null;
  const { GoogleAuthProvider, signInWithPopup } = await import("firebase/auth");
  const provider = new GoogleAuthProvider();
  try {
    const result = await signInWithPopup(auth, provider);
    return result.user;
  } catch (err: unknown) {
    const code = (err as { code?: string }).code ?? "";
    if (code === "auth/popup-blocked") {
      throw new Error("El popup fue bloqueado. Permitá los popups para este sitio.");
    }
    if (code === "auth/popup-closed-by-user") return null; // user cancelled
    throw err;
  }
}

/** Sign out from Firebase. */
export async function signOutFirebase(): Promise<void> {
  const auth = await getFirebase();
  if (!auth) return;
  const { signOut } = await import("firebase/auth");
  await signOut(auth);
}

/**
 * Subscribe to Firebase auth state changes.
 * Returns an unsubscribe function (or a no-op if Firebase not configured).
 */
export function subscribeToAuthChanges(callback: (user: User | null) => void): () => void {
  if (!FIREBASE_CONFIGURED) return () => {};
  // We need to subscribe lazily since Firebase may not be initialized yet
  let unsubscribe: (() => void) | undefined;
  void getFirebase().then((auth) => {
    if (!auth) return callback(null);
    import("firebase/auth").then(({ onAuthStateChanged }) => {
      unsubscribe = onAuthStateChanged(auth, callback);
    });
  });
  return () => unsubscribe?.();
}

export type { User };
