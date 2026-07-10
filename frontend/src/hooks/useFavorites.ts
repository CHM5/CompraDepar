import { useState, useEffect, useCallback } from "react";
import type { PropertyResult } from "@/types/property";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function syncToSheets(email: string, favs: PropertyResult[]) {
  try {
    await fetch(`${API_URL}/api/v1/favorites/sync`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, favorites: favs }),
    });
  } catch {
    // silencioso — no bloquear UI si Sheets falla
  }
}

function propKey(p: PropertyResult): string {
  return `${p.portal}::${p.url}`;
}

export interface UseFavoritesReturn {
  favs: PropertyResult[];
  toggleFav: (prop: PropertyResult) => void;
  isFav: (prop: PropertyResult) => boolean;
}

export function useFavorites(email: string | null): UseFavoritesReturn {
  const storageKey = email ? `df_favs_${email}` : null;
  const [favs, setFavs] = useState<PropertyResult[]>([]);

  // Load from localStorage on email change
  useEffect(() => {
    if (!storageKey || typeof window === "undefined") {
      setFavs([]);
      return;
    }
    try {
      const raw = localStorage.getItem(storageKey);
      if (raw) setFavs(JSON.parse(raw) as PropertyResult[]);
      else setFavs([]);
    } catch {
      setFavs([]);
    }
  }, [storageKey]);

  const toggleFav = useCallback(
    (prop: PropertyResult) => {
      if (!storageKey || !email) return;
      setFavs((prev) => {
        const key = propKey(prop);
        const exists = prev.some((p) => propKey(p) === key);
        const next = exists
          ? prev.filter((p) => propKey(p) !== key)
          : [prop, ...prev];
        try {
          localStorage.setItem(storageKey, JSON.stringify(next));
        } catch { /* storage full */ }
        // Sincronizar con Google Sheets en segundo plano
        syncToSheets(email, next);
        return next;
      });
    },
    [storageKey, email],
  );

  const isFav = useCallback(
    (prop: PropertyResult) => favs.some((p) => propKey(p) === propKey(prop)),
    [favs],
  );

  return { favs, toggleFav, isFav };
}
