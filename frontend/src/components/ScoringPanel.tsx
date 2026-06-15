"use client";

import { useEffect, useState, useCallback } from "react";
import { X, Info, BarChart2 } from "lucide-react";
import {
  DEFAULT_PREFS,
  loadScoringPrefs,
  saveScoringPrefs,
  trackEvent,
  type ScoringPrefs,
} from "@/lib/analytics";
import type { PropertyResult } from "@/types/property";
import { cn } from "@/lib/utils";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ── Scoring config shape (mirrors GET /api/v1/scoring) ───────────────────────

interface ScoringConfig {
  barrios: Record<string, number>;
  disposicion: Record<string, number>;
  balcon: number;
  cochera: number;
  piso_5_mas: number;
  antiguedad_10_menos: number;
  m2_tiers: [number, number][];
  amenities: Record<string, number>;
  expensas_tiers: [number, number, number][];
  usd_m2_excelente_umbral: number;
  usd_m2_bueno_umbral: number;
  usd_m2_excelente_pts: number;
  usd_m2_bueno_pts: number;
  clasificaciones: { excelente: number; alerta: number; exportar: number };
}

// ── Client-side re-scoring ────────────────────────────────────────────────────

const BARRIO_PTS: Record<string, number> = {
  Palermo: 50, Belgrano: 45, "Villa Crespo": 40, Almagro: 35, Núñez: 30, Saavedra: 25,
};
const M2_TIERS: [number, number][] = [
  [60, 60], [55, 50], [50, 40], [45, 30], [40, 20], [35, 10],
];

/** Returns a custom sort score for the given property using the user's prefs. */
export function computeCustomScore(p: PropertyResult, prefs: ScoringPrefs): number {
  let score = 0;
  const scale = (base: number, importance: number) => base * (importance / 3);

  // Barrio
  score += scale(BARRIO_PTS[p.barrio ?? ""] ?? 5, prefs.barrio);

  // M²
  const m2 = p.m2_totales ?? p.m2_cubiertos ?? 0;
  let m2Base = 0;
  for (const [threshold, pts] of M2_TIERS) {
    if (m2 > threshold) { m2Base = pts; break; }
  }
  score += scale(m2Base, prefs.m2);

  // Balcón
  if (p.balcon) score += scale(15, prefs.balcon);

  // Precio/m²
  if (p.precio_usd && m2 > 0) {
    const ppm2 = p.precio_usd / m2;
    if (ppm2 < 1800) score += scale(10, prefs.price_m2);
    else if (ppm2 < 2200) score += scale(5, prefs.price_m2);
  }

  // Cochera
  if (p.cochera) score += scale(5, prefs.cochera);

  return score;
}

/** Re-sorts results using the user's custom scoring preferences. */
export function sortByPrefs(
  results: PropertyResult[],
  prefs: ScoringPrefs,
): PropertyResult[] {
  // Only re-sort if prefs differ from defaults (avoid unnecessary re-renders)
  const isDefault =
    prefs.barrio === 3 &&
    prefs.m2 === 3 &&
    prefs.balcon === 3 &&
    prefs.price_m2 === 3 &&
    prefs.cochera === 2;
  if (isDefault) return results;
  return [...results].sort(
    (a, b) => computeCustomScore(b, prefs) - computeCustomScore(a, prefs),
  );
}

// ── Slider sub-component ──────────────────────────────────────────────────────

const LABELS = ["Nada", "Poco", "Normal", "Bastante", "Máximo"];

function PrefSlider({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <div className="flex items-center gap-3">
      <span className="w-28 shrink-0 text-xs text-neutral-700">{label}</span>
      <input
        type="range"
        min={1}
        max={5}
        step={1}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="h-1.5 flex-1 cursor-pointer accent-blue-600"
      />
      <span className="w-16 shrink-0 text-right text-xs font-medium text-blue-600">
        {LABELS[value - 1]}
      </span>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

interface Props {
  open: boolean;
  onClose: () => void;
  onPrefsChange: (prefs: ScoringPrefs) => void;
}

export function ScoringPanel({ open, onClose, onPrefsChange }: Props) {
  const [tab, setTab] = useState<"info" | "prefs">("info");
  const [config, setConfig] = useState<ScoringConfig | null>(null);
  const [prefs, setPrefs] = useState<ScoringPrefs>(DEFAULT_PREFS);

  // Load prefs from localStorage on open
  useEffect(() => {
    if (!open) return;
    setPrefs(loadScoringPrefs());
    trackEvent("scoring_open");
  }, [open]);

  // Fetch scoring config from API
  useEffect(() => {
    if (!open || config) return;
    fetch(`${API_URL}/api/v1/scoring`)
      .then((r) => r.json())
      .then((d) => setConfig(d as ScoringConfig))
      .catch(() => setConfig(null));
  }, [open, config]);

  const updatePref = useCallback(
    (key: keyof ScoringPrefs, val: number) => {
      setPrefs((prev) => {
        const next = { ...prev, [key]: val };
        onPrefsChange(next);
        return next;
      });
    },
    [onPrefsChange],
  );

  function handleSave() {
    saveScoringPrefs(prefs);
    onClose();
  }

  function handleReset() {
    setPrefs(DEFAULT_PREFS);
    saveScoringPrefs(DEFAULT_PREFS);
    onPrefsChange(DEFAULT_PREFS);
  }

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/40 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="relative w-full max-h-[88vh] sm:max-w-xl overflow-y-auto rounded-t-2xl sm:rounded-2xl bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="sticky top-0 z-10 flex items-center justify-between gap-2 border-b border-neutral-100 bg-white px-5 py-4">
          <div className="flex items-center gap-2">
            <BarChart2 className="h-5 w-5 text-blue-600" />
            <h2 className="text-base font-bold text-neutral-900">Sistema de puntuación</h2>
          </div>
          <button onClick={onClose} className="rounded-lg p-1 hover:bg-neutral-100">
            <X className="h-5 w-5 text-neutral-400" />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 border-b border-neutral-100 px-5 pt-3">
          {(["info", "prefs"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={cn(
                "rounded-t-lg px-4 py-2 text-xs font-semibold transition-colors",
                tab === t
                  ? "border-b-2 border-blue-600 text-blue-600"
                  : "text-neutral-400 hover:text-neutral-700",
              )}
            >
              {t === "info" ? "Cómo se puntúa" : "Mis preferencias"}
            </button>
          ))}
        </div>

        <div className="px-5 py-5">
          {/* ── Tab: info ── */}
          {tab === "info" && (
            <div className="space-y-5">
              <p className="text-sm text-neutral-500">
                Cada propiedad recibe puntos según los criterios a continuación. A mayor puntaje, mejor posición en los resultados.
              </p>

              {/* Clasificaciones */}
              <div>
                <h3 className="mb-2 text-[11px] font-bold uppercase tracking-wide text-neutral-400">
                  Clasificaciones
                </h3>
                <div className="grid grid-cols-3 gap-2">
                  {[
                    { label: "Excelente", pts: `≥ ${config?.clasificaciones.excelente ?? 90}`, color: "bg-green-100 text-green-700" },
                    { label: "Muy interesante", pts: `≥ ${config?.clasificaciones.alerta ?? 80}`, color: "bg-yellow-100 text-yellow-700" },
                    { label: "Revisar", pts: `≥ ${config?.clasificaciones.exportar ?? 70}`, color: "bg-neutral-100 text-neutral-600" },
                  ].map((c) => (
                    <div key={c.label} className={`rounded-xl px-3 py-2 text-center text-xs font-medium ${c.color}`}>
                      <div className="text-sm font-bold">{c.pts}</div>
                      <div className="mt-0.5">{c.label}</div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Barrios */}
              <div>
                <h3 className="mb-2 text-[11px] font-bold uppercase tracking-wide text-neutral-400">
                  Barrios
                </h3>
                <div className="grid grid-cols-2 gap-1 sm:grid-cols-3">
                  {Object.entries(config?.barrios ?? BARRIO_PTS)
                    .sort((a, b) => b[1] - a[1])
                    .map(([b, pts]) => (
                      <div
                        key={b}
                        className="flex items-center justify-between rounded-lg bg-neutral-50 px-2.5 py-1.5 text-xs"
                      >
                        <span className="text-neutral-700">{b}</span>
                        <span className="font-bold text-blue-600">+{pts}</span>
                      </div>
                    ))}
                </div>
                <p className="mt-1.5 text-[11px] text-neutral-400">
                  Otros barrios de CABA reciben +10 pts.
                </p>
              </div>

              {/* Superficie */}
              <div>
                <h3 className="mb-2 text-[11px] font-bold uppercase tracking-wide text-neutral-400">
                  Superficie m²
                </h3>
                <div className="space-y-1">
                  {(config?.m2_tiers ?? M2_TIERS).map(([u, pts]) => (
                    <div
                      key={u}
                      className="flex items-center justify-between rounded-lg bg-neutral-50 px-2.5 py-1.5 text-xs"
                    >
                      <span className="text-neutral-700">Más de {u} m²</span>
                      <span className="font-bold text-blue-600">+{pts}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Características */}
              <div>
                <h3 className="mb-2 text-[11px] font-bold uppercase tracking-wide text-neutral-400">
                  Características
                </h3>
                <div className="grid grid-cols-2 gap-1">
                  {[
                    ["Balcón", config?.balcon ?? 15],
                    ["Disposición frente", config?.disposicion?.frente ?? 20],
                    ["Disposición contrafrente", config?.disposicion?.contrafrente ?? 15],
                    ["Cochera", config?.cochera ?? 5],
                    ["Piso ≥ 5", config?.piso_5_mas ?? 5],
                    ["Antigüedad ≤ 10 años", config?.antiguedad_10_menos ?? 10],
                    ...Object.entries(config?.amenities ?? { pileta: 3, sum: 2, gimnasio: 2 }).map(
                      ([k, v]) => [k.charAt(0).toUpperCase() + k.slice(1), v],
                    ),
                  ].map(([label, pts]) => (
                    <div
                      key={String(label)}
                      className="flex items-center justify-between rounded-lg bg-neutral-50 px-2.5 py-1.5 text-xs"
                    >
                      <span className="capitalize text-neutral-700">{String(label)}</span>
                      <span className="font-bold text-blue-600">+{pts}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Precio / m² */}
              <div>
                <h3 className="mb-2 text-[11px] font-bold uppercase tracking-wide text-neutral-400">
                  Precio / m² (USD)
                </h3>
                <div className="space-y-1">
                  <div className="flex items-center justify-between rounded-lg bg-neutral-50 px-2.5 py-1.5 text-xs">
                    <span className="text-neutral-700">
                      ≤ USD {(config?.usd_m2_excelente_umbral ?? 1800).toLocaleString()}/m²
                    </span>
                    <span className="font-bold text-blue-600">+{config?.usd_m2_excelente_pts ?? 10}</span>
                  </div>
                  <div className="flex items-center justify-between rounded-lg bg-neutral-50 px-2.5 py-1.5 text-xs">
                    <span className="text-neutral-700">
                      ≤ USD {(config?.usd_m2_bueno_umbral ?? 2200).toLocaleString()}/m²
                    </span>
                    <span className="font-bold text-blue-600">+{config?.usd_m2_bueno_pts ?? 5}</span>
                  </div>
                </div>
              </div>

              <div className="flex items-start gap-2 rounded-xl border border-blue-100 bg-blue-50 p-3 text-xs text-blue-700">
                <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span>
                  El puntaje se calcula en el momento del scraping y se guarda en la base de datos. Usá la pestaña{" "}
                  <strong>Mis preferencias</strong> para reordenar los resultados actuales según lo que más te importa.
                </span>
              </div>
            </div>
          )}

          {/* ── Tab: prefs ── */}
          {tab === "prefs" && (
            <div className="space-y-5">
              <p className="text-sm text-neutral-500">
                Ajustá la importancia de cada criterio. Los resultados se reordenan en tiempo real según tus preferencias.
              </p>

              <div className="space-y-4 rounded-xl border border-neutral-100 bg-neutral-50 p-4">
                <PrefSlider
                  label="🏙️ Barrio premium"
                  value={prefs.barrio}
                  onChange={(v) => updatePref("barrio", v)}
                />
                <PrefSlider
                  label="📐 Superficie m²"
                  value={prefs.m2}
                  onChange={(v) => updatePref("m2", v)}
                />
                <PrefSlider
                  label="🌿 Balcón"
                  value={prefs.balcon}
                  onChange={(v) => updatePref("balcon", v)}
                />
                <PrefSlider
                  label="💰 Precio / m² bajo"
                  value={prefs.price_m2}
                  onChange={(v) => updatePref("price_m2", v)}
                />
                <PrefSlider
                  label="🚗 Cochera"
                  value={prefs.cochera}
                  onChange={(v) => updatePref("cochera", v)}
                />
              </div>

              <p className="text-xs text-neutral-400">
                💡 Las preferencias se aplican solo en tu pantalla y se guardan localmente en tu navegador.
              </p>

              <div className="flex items-center justify-between gap-3 border-t border-neutral-100 pt-4">
                <button
                  onClick={handleReset}
                  className="text-xs font-medium text-neutral-400 hover:text-neutral-700 transition-colors"
                >
                  Restaurar valores por defecto
                </button>
                <button
                  onClick={handleSave}
                  className="rounded-xl bg-blue-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-blue-700 transition-colors"
                >
                  Guardar preferencias
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
