"use client";

import { useEffect, useState } from "react";
import { SlidersHorizontal, Loader2 } from "lucide-react";
import type { ExtraFilters, FiltersApplied } from "@/types/property";
import { cn } from "@/lib/utils";

// ── Types ─────────────────────────────────────────────────────────────────────

interface FormState {
  barrios: string[];
  operacion: "venta" | "alquiler";
  ambientes_min: number | null;
  ambientes_max: number | null;
  precio_min: string;
  precio_max: string;
  m2_min: string;
  m2_max: string;
  balcon: boolean;
  terraza: boolean;
  cochera: boolean;
  antiguedad_max: string;
  expensas_max: string;
}

const CABA_BARRIOS = [
  "Agronomía", "Almagro", "Balvanera", "Barracas", "Belgrano", "Boedo", "Caballito", "Chacarita",
  "Coghlan", "Colegiales", "Constitución", "Flores", "Floresta", "La Boca", "La Paternal", "Liniers",
  "Mataderos", "Monserrat", "Monte Castro", "Nueva Pompeya", "Núñez", "Palermo", "Parque Avellaneda",
  "Parque Chacabuco", "Parque Chas", "Parque Patricios", "Puerto Madero", "Recoleta", "Retiro", "Saavedra",
  "San Cristóbal", "San Nicolás", "San Telmo", "Vélez Sársfield", "Versalles", "Villa Crespo", "Villa del Parque",
  "Villa Devoto", "Villa General Mitre", "Villa Lugano", "Villa Luro", "Villa Ortúzar", "Villa Pueyrredón",
  "Villa Real", "Villa Riachuelo", "Villa Santa Rita", "Villa Soldati", "Villa Urquiza",
];

// ── Helpers ───────────────────────────────────────────────────────────────────

function buildInitialForm(f: FiltersApplied): FormState {
  return {
    barrios: Array.isArray(f.barrios) ? f.barrios : [],
    operacion: (f.operacion as "venta" | "alquiler") ?? "venta",
    ambientes_min: f.ambientes_min ?? null,
    ambientes_max: f.ambientes_max ?? null,
    precio_min: f.precio_min != null ? String(f.precio_min) : "",
    precio_max: f.precio_max != null ? String(f.precio_max) : "",
    m2_min: f.m2_min != null ? String(f.m2_min) : "",
    m2_max: f.m2_max != null ? String(f.m2_max) : "",
    balcon: f.balcon === true,
    terraza: f.terraza === true,
    cochera: f.cochera === true,
    antiguedad_max: f.antiguedad_max != null ? String(f.antiguedad_max) : "",
    expensas_max: f.expensas_max != null ? String(f.expensas_max) : "",
  };
}

function toInt(s: string): number | null {
  const n = parseInt(s.replace(/[.,\s$]/g, ""), 10);
  return isNaN(n) || n <= 0 ? null : n;
}

function countActive(form: FormState, initial: FiltersApplied): number {
  let n = 0;
  if ((form.barrios ?? []).join("|") !== (initial.barrios ?? []).join("|")) n++;
  if (form.operacion !== (initial.operacion ?? "venta")) n++;
  if (form.ambientes_min !== (initial.ambientes_min ?? null)) n++;
  if (form.ambientes_max !== (initial.ambientes_max ?? null)) n++;
  if (form.precio_min && toInt(form.precio_min) !== initial.precio_min) n++;
  if (form.precio_max && toInt(form.precio_max) !== initial.precio_max) n++;
  if (form.m2_min && toInt(form.m2_min) !== initial.m2_min) n++;
  if (form.m2_max && toInt(form.m2_max) !== initial.m2_max) n++;
  if (form.balcon && !initial.balcon) n++;
  if (form.terraza && !initial.terraza) n++;
  if (form.cochera && !initial.cochera) n++;
  if (form.antiguedad_max) n++;
  if (form.expensas_max) n++;
  return n;
}

// ── Sub-components ────────────────────────────────────────────────────────────

function Label({ children }: { children: React.ReactNode }) {
  return (
    <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-neutral-400">
      {children}
    </p>
  );
}

function NumberInput({
  placeholder,
  value,
  onChange,
  prefix,
  suffix,
}: {
  placeholder: string;
  value: string;
  onChange: (v: string) => void;
  prefix?: string;
  suffix?: string;
}) {
  return (
    <div className="relative flex-1">
      {prefix && (
        <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-xs text-neutral-400 pointer-events-none">
          {prefix}
        </span>
      )}
      <input
        type="number"
        min={0}
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={cn(
          "w-full rounded-xl border border-neutral-200 py-2 text-xs text-neutral-700 outline-none",
          "focus:border-blue-400 focus:ring-1 focus:ring-blue-100 transition-colors",
          prefix ? "pl-6 pr-2" : suffix ? "pl-3 pr-10" : "px-3",
        )}
      />
      {suffix && (
        <span className="absolute right-2.5 top-1/2 -translate-y-1/2 text-xs text-neutral-400 pointer-events-none">
          {suffix}
        </span>
      )}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

interface Props {
  initialFilters: FiltersApplied;
  onApply: (extra: ExtraFilters) => void;
  isLoading: boolean;
}

const AMB_OPTS: { label: string; min: number; max: number | null }[] = [
  { label: "1", min: 1, max: 1 },
  { label: "2", min: 2, max: 2 },
  { label: "3", min: 3, max: 3 },
  { label: "4+", min: 4, max: null },
];

export function RefinementPanel({ initialFilters, onApply, isLoading }: Props) {
  const [form, setForm] = useState<FormState>(() => buildInitialForm(initialFilters));

  useEffect(() => {
    setForm(buildInitialForm(initialFilters));
  }, [initialFilters]);

  function set<K extends keyof FormState>(key: K, val: FormState[K]) {
    setForm((prev) => ({ ...prev, [key]: val }));
  }

  function toggleBarrio(barrio: string) {
    setForm((prev) => {
      const exists = prev.barrios.includes(barrio);
      return {
        ...prev,
        barrios: exists ? prev.barrios.filter((b) => b !== barrio) : [...prev.barrios, barrio],
      };
    });
  }

  function selectAmb(min: number, max: number | null) {
    const active = form.ambientes_min === min && form.ambientes_max === max;
    setForm((prev) => ({
      ...prev,
      ambientes_min: active ? null : min,
      ambientes_max: active ? null : max,
    }));
  }

  function handleReset() {
    setForm(buildInitialForm(initialFilters));
  }

  function handleApply() {
    const extra: ExtraFilters = {
      barrios: form.barrios.length ? form.barrios : null,
      operacion: form.operacion,
      precio_min: toInt(form.precio_min),
      precio_max: toInt(form.precio_max),
      m2_min: toInt(form.m2_min),
      m2_max: toInt(form.m2_max),
      ambientes_min: form.ambientes_min,
      ambientes_max: form.ambientes_max,
      balcon: form.balcon ? true : null,
      terraza: form.terraza ? true : null,
      cochera: form.cochera ? true : null,
      antiguedad_max: toInt(form.antiguedad_max),
      expensas_max: toInt(form.expensas_max),
    };
    // Strip null/undefined keys
    const clean = Object.fromEntries(
      Object.entries(extra).filter(([, v]) => v != null),
    ) as ExtraFilters;
    onApply(clean);
  }

  const activeCount = countActive(form, initialFilters);

  return (
    <div className="w-full overflow-hidden rounded-2xl border border-neutral-200 bg-white shadow-sm">
      {/* Header */}
      <div className="flex w-full items-center justify-between gap-2 px-5 py-3.5">
        <div className="flex items-center gap-2">
          <SlidersHorizontal className="h-4 w-4 text-neutral-500" />
          <span className="text-sm font-semibold text-neutral-700">Refinar búsqueda (fijo)</span>
          {activeCount > 0 && (
            <span className="rounded-full bg-blue-600 px-1.5 py-0.5 text-[10px] font-bold leading-none text-white">
              {activeCount}
            </span>
          )}
        </div>
      </div>

      <div className="border-t border-neutral-100 px-5 pb-5 pt-4">
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">

            {/* Barrios CABA */}
            <div className="sm:col-span-2 lg:col-span-3">
              <Label>Barrios CABA</Label>
              <div className="max-h-32 overflow-y-auto rounded-xl border border-neutral-200 p-2">
                <div className="flex flex-wrap gap-1.5">
                  {CABA_BARRIOS.map((b) => {
                    const active = form.barrios.includes(b);
                    return (
                      <button
                        key={b}
                        type="button"
                        onClick={() => toggleBarrio(b)}
                        className={cn(
                          "rounded-full border px-2.5 py-1 text-[11px] font-medium transition-all",
                          active
                            ? "border-blue-600 bg-blue-600 text-white"
                            : "border-neutral-200 bg-white text-neutral-600 hover:border-blue-300 hover:text-blue-700",
                        )}
                      >
                        {b}
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>

            {/* Operación */}
            <div>
              <Label>Operación</Label>
              <div className="flex overflow-hidden rounded-xl border border-neutral-200 bg-neutral-100 p-0.5">
                {(["venta", "alquiler"] as const).map((op) => (
                  <button
                    key={op}
                    type="button"
                    onClick={() => set("operacion", op)}
                    className={cn(
                      "flex-1 rounded-lg py-1.5 text-xs font-medium capitalize transition-all",
                      form.operacion === op
                        ? "bg-white text-neutral-900 shadow-sm"
                        : "text-neutral-500 hover:text-neutral-700",
                    )}
                  >
                    {op === "venta" ? "🏠 Venta" : "🔑 Alquiler"}
                  </button>
                ))}
              </div>
            </div>

            {/* Ambientes */}
            <div>
              <Label>Ambientes</Label>
              <div className="flex gap-1.5">
                {AMB_OPTS.map(({ label, min, max }) => {
                  const active = form.ambientes_min === min && form.ambientes_max === max;
                  return (
                    <button
                      key={label}
                      type="button"
                      onClick={() => selectAmb(min, max)}
                      className={cn(
                        "flex-1 rounded-xl border py-2 text-xs font-semibold transition-all",
                        active
                          ? "border-blue-600 bg-blue-600 text-white shadow-sm"
                          : "border-neutral-200 bg-white text-neutral-600 hover:border-blue-300 hover:text-blue-700",
                      )}
                    >
                      {label}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Características */}
            <div>
              <Label>Características</Label>
              <div className="flex flex-wrap gap-2">
                {(
                  [
                    { key: "balcon" as const, label: "🌿 Balcón" },
                    { key: "terraza" as const, label: "🏡 Terraza" },
                    { key: "cochera" as const, label: "🚗 Cochera" },
                  ] as const
                ).map(({ key, label }) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => set(key, !form[key])}
                    className={cn(
                      "rounded-xl border px-3.5 py-2 text-xs font-medium transition-all",
                      form[key]
                        ? "border-blue-600 bg-blue-600 text-white shadow-sm"
                        : "border-neutral-200 bg-white text-neutral-600 hover:border-blue-300 hover:text-blue-700",
                    )}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>

            {/* Precio USD */}
            <div>
              <Label>Precio (USD)</Label>
              <div className="flex items-center gap-2">
                <NumberInput
                  prefix="$"
                  placeholder="Desde"
                  value={form.precio_min}
                  onChange={(v) => set("precio_min", v)}
                />
                <span className="text-xs text-neutral-300">—</span>
                <NumberInput
                  prefix="$"
                  placeholder="Hasta"
                  value={form.precio_max}
                  onChange={(v) => set("precio_max", v)}
                />
              </div>
            </div>

            {/* Superficie m² */}
            <div>
              <Label>Superficie (m²)</Label>
              <div className="flex items-center gap-2">
                <NumberInput
                  placeholder="Desde"
                  value={form.m2_min}
                  onChange={(v) => set("m2_min", v)}
                  suffix="m²"
                />
                <span className="text-xs text-neutral-300">—</span>
                <NumberInput
                  placeholder="Hasta"
                  value={form.m2_max}
                  onChange={(v) => set("m2_max", v)}
                  suffix="m²"
                />
              </div>
            </div>

            {/* Antigüedad + Expensas */}
            <div className="flex gap-3">
              <div className="flex-1">
                <Label>Antigüedad máx.</Label>
                <NumberInput
                  placeholder="Ej: 20"
                  value={form.antiguedad_max}
                  onChange={(v) => set("antiguedad_max", v)}
                  suffix="años"
                />
              </div>
              <div className="flex-1">
                <Label>Expensas máx.</Label>
                <NumberInput
                  placeholder="ARS"
                  value={form.expensas_max}
                  onChange={(v) => set("expensas_max", v)}
                  suffix="$"
                />
              </div>
            </div>

          </div>

          {/* Footer */}
          <div className="mt-5 flex items-center justify-between gap-3 border-t border-neutral-100 pt-4">
            <p className="text-xs text-neutral-400">
              {activeCount > 0
                ? `${activeCount} filtro${activeCount !== 1 ? "s" : ""} activo${activeCount !== 1 ? "s" : ""}`
                : "Sin filtros adicionales"}
            </p>
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={handleReset}
                className="text-xs font-medium text-neutral-400 transition-colors hover:text-neutral-700"
              >
                Limpiar
              </button>
              <button
                type="button"
                onClick={handleApply}
                disabled={isLoading}
                className={cn(
                  "flex items-center gap-1.5 rounded-xl px-5 py-2.5 text-sm font-semibold transition-all",
                  isLoading
                    ? "cursor-not-allowed bg-neutral-100 text-neutral-400"
                    : "bg-blue-600 text-white shadow-sm hover:bg-blue-700",
                )}
              >
                {isLoading ? (
                  <>
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    Buscando…
                  </>
                ) : (
                  "Buscar con filtros →"
                )}
              </button>
            </div>
          </div>
      </div>
    </div>
  );
}
