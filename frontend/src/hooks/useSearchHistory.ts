import { useState, useEffect, useCallback } from "react";

export interface SearchHistoryEntry {
  query: string;
  results: number;
  timestamp: number;
}

const MAX_HISTORY = 20;

export function useSearchHistory(email: string | null) {
  const storageKey = email ? `df_history_${email}` : null;
  const [history, setHistory] = useState<SearchHistoryEntry[]>([]);

  useEffect(() => {
    if (!storageKey || typeof window === "undefined") {
      setHistory([]);
      return;
    }
    try {
      const raw = localStorage.getItem(storageKey);
      if (raw) setHistory(JSON.parse(raw) as SearchHistoryEntry[]);
      else setHistory([]);
    } catch {
      setHistory([]);
    }
  }, [storageKey]);

  const addEntry = useCallback(
    (entry: Omit<SearchHistoryEntry, "timestamp">) => {
      if (!storageKey) return;
      setHistory((prev) => {
        // deduplicate by query (keep most recent)
        const deduped = prev.filter((e) => e.query !== entry.query);
        const next = [{ ...entry, timestamp: Date.now() }, ...deduped].slice(
          0,
          MAX_HISTORY,
        );
        try {
          localStorage.setItem(storageKey, JSON.stringify(next));
        } catch { /* storage full */ }
        return next;
      });
    },
    [storageKey],
  );

  const clearHistory = useCallback(() => {
    if (!storageKey) return;
    localStorage.removeItem(storageKey);
    setHistory([]);
  }, [storageKey]);

  return { history, addEntry, clearHistory };
}
