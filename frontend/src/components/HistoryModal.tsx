"use client";

import { X, History, Clock, SearchX, Trash2 } from "lucide-react";
import { useSearchHistory } from "@/hooks/useSearchHistory";

interface Props {
  email: string;
  onSearch: (query: string) => void;
  onClose: () => void;
}

function formatRelativeTime(ts: number): string {
  const diff = Date.now() - ts;
  const mins = Math.floor(diff / 60_000);
  const hours = Math.floor(diff / 3_600_000);
  const days = Math.floor(diff / 86_400_000);
  if (mins < 1) return "ahora";
  if (mins < 60) return `hace ${mins} min`;
  if (hours < 24) return `hace ${hours} h`;
  if (days === 1) return "ayer";
  return `hace ${days} días`;
}

export function HistoryModal({ email, onSearch, onClose }: Props) {
  const { history, clearHistory } = useSearchHistory(email);

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 backdrop-blur-sm sm:items-center"
      onClick={onClose}
    >
      <div
        className="relative max-h-[88vh] w-full overflow-y-auto rounded-t-2xl bg-white shadow-xl sm:max-w-lg sm:rounded-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-neutral-100 bg-white px-5 py-4">
          <div className="flex items-center gap-2">
            <History className="h-5 w-5 text-blue-500" />
            <h2 className="text-base font-bold text-neutral-900">
              Historial de búsquedas
            </h2>
          </div>
          <div className="flex items-center gap-2">
            {history.length > 0 && (
              <button
                onClick={clearHistory}
                className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs text-neutral-400 hover:bg-neutral-100 hover:text-neutral-600"
                title="Limpiar historial"
              >
                <Trash2 className="h-3.5 w-3.5" />
                Limpiar
              </button>
            )}
            <button
              onClick={onClose}
              className="rounded-lg p-1 hover:bg-neutral-100"
            >
              <X className="h-5 w-5 text-neutral-400" />
            </button>
          </div>
        </div>

        <div className="p-5">
          {history.length === 0 ? (
            <div className="flex flex-col items-center gap-3 py-16 text-center">
              <SearchX className="h-10 w-10 text-neutral-200" />
              <p className="font-semibold text-neutral-600">
                Sin búsquedas recientes
              </p>
              <p className="max-w-xs text-sm text-neutral-400">
                Tus búsquedas aparecerán aquí para que puedas repetirlas
                rápidamente.
              </p>
            </div>
          ) : (
            <ul className="space-y-2">
              {history.map((entry) => (
                <li key={entry.timestamp}>
                  <button
                    onClick={() => {
                      onClose();
                      onSearch(entry.query);
                    }}
                    className="flex w-full items-start gap-3 rounded-xl border border-neutral-100 bg-neutral-50 px-4 py-3 text-left transition-colors hover:border-blue-200 hover:bg-blue-50"
                  >
                    <Clock className="mt-0.5 h-4 w-4 shrink-0 text-neutral-300" />
                    <div className="flex-1 min-w-0">
                      <p className="truncate text-sm font-medium text-neutral-800">
                        {entry.query}
                      </p>
                      <p className="mt-0.5 text-xs text-neutral-400">
                        {entry.results > 0
                          ? `${entry.results} resultado${entry.results !== 1 ? "s" : ""}`
                          : "Sin resultados"}{" "}
                        · {formatRelativeTime(entry.timestamp)}
                      </p>
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
