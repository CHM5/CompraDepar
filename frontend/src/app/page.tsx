"use client";

import { useEffect, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import Image from "next/image";
import { BarChart2, Info } from "lucide-react";
import { SearchBox } from "@/components/SearchBox";
import { ResultsList } from "@/components/ResultsList";
import { RefinementPanel } from "@/components/RefinementPanel";
import { ScoringPanel } from "@/components/ScoringPanel";
import { searchProperties, HAS_BACKEND } from "@/lib/api";
import { getSessionId, trackEvent, loadScoringPrefs, type ScoringPrefs } from "@/lib/analytics";
import type { SearchApiResponse, ExtraFilters, FiltersApplied } from "@/types/property";

const EXAMPLES = [
  "Palermo, entre USD 90k y 120k, desde 40m²",
  "¿Cuánto sale el m² en Palermo?",
  "Monoambiente en Recoleta hasta USD 100k",
  "¿Qué barrio tiene mejor relación precio/m²?",
  "2 ambientes en Belgrano con balcón",
  "¿Conviene invertir en Caballito?",
];

const EMPTY_FILTERS: FiltersApplied = {
  operacion: "venta",
  tipo: null,
  barrios: [],
  m2_min: null,
  m2_max: null,
  precio_min: null,
  precio_max: null,
  ambientes_min: null,
  ambientes_max: null,
  balcon: null,
  terraza: null,
  cochera: null,
  antiguedad_max: null,
  expensas_max: null,
};

type SearchParams = { query: string; extraFilters?: ExtraFilters | null };

function buildQueryFromFilters(extra: ExtraFilters): string {
  const parts: string[] = [];
  if (extra.barrios?.length) {
    parts.push("departamentos en " + extra.barrios.slice(0, 3).join(" o "));
  } else {
    parts.push("departamentos en CABA");
  }
  if (extra.operacion === "alquiler") parts.push("en alquiler");
  if (extra.ambientes_min === 1 && extra.ambientes_max === 1) parts.push("monoambiente");
  else if (extra.ambientes_min) parts.push(`${extra.ambientes_min} ambientes`);
  if (extra.precio_max) parts.push(`hasta USD ${extra.precio_max.toLocaleString()}`);
  if (extra.m2_min) parts.push(`desde ${extra.m2_min} m²`);
  if (extra.balcon) parts.push("con balcón");
  if (extra.terraza) parts.push("con terraza");
  if (extra.cochera) parts.push("con cochera");
  return parts.join(" ");
}

export default function HomePage() {
  const [hasSearched, setHasSearched] = useState(false);
  const [lastQuery, setLastQuery] = useState("");
  const [scoringOpen, setScoringOpen] = useState(false);
  const [scoringPrefs, setScoringPrefs] = useState<ScoringPrefs>(() => loadScoringPrefs());

  // Init anonymous session on mount
  useEffect(() => {
    getSessionId(); // creates if not exists
  }, []);

  const { mutate, data, isPending, error, reset, variables } = useMutation<
    SearchApiResponse,
    Error,
    SearchParams
  >({
    mutationFn: ({ query, extraFilters }) =>
      searchProperties(query, "free", extraFilters),
  });

  function handleSearch(query: string) {
    setHasSearched(true);
    setLastQuery(query);
    reset();
    mutate({ query });
    trackEvent("search", { query });
  }

  function handleApplyFilters(extra: ExtraFilters) {
    const q = lastQuery.trim() || buildQueryFromFilters(extra);
    setHasSearched(true);
    setLastQuery(q);
    reset();
    mutate({ query: q, extraFilters: extra });
    trackEvent("filter_apply", { query: q });
  }

  const currentFilters: FiltersApplied =
    data?.intent === "search" && data?.filters_applied
      ? (data.filters_applied as FiltersApplied)
      : EMPTY_FILTERS;

  return (
    <main className="mx-auto min-h-screen max-w-5xl px-4 pb-16 pt-12 sm:pt-16">
      {/* Hero */}
      <div
        className={`text-center transition-all duration-300 ${
          hasSearched ? "mb-6" : "mb-10"
        }`}
      >
        <div className="mb-2 flex items-center justify-center gap-2">
          <Image
            src="/depar-finder-logo.svg"
            alt="Depar Finder"
            width={36}
            height={36}
            className="h-9 w-9 rounded-lg"
            priority
          />
          <h1 className="text-3xl font-bold tracking-tight text-neutral-900 sm:text-4xl">
            Depar Finder
          </h1>
          {/* Scoring info button */}
          <button
            onClick={() => setScoringOpen(true)}
            title="Cómo se puntúan las propiedades"
            className="ml-1 rounded-lg p-1.5 text-neutral-400 transition-colors hover:bg-neutral-100 hover:text-blue-600"
          >
            <BarChart2 className="h-5 w-5" />
          </button>
        </div>
        {!hasSearched && (
          <p className="mx-auto mt-2 max-w-lg text-base text-neutral-500">
            Buscá propiedades o preguntame sobre el mercado inmobiliario de CABA.
          </p>
        )}
      </div>

      {/* Banner demo */}
      {!HAS_BACKEND && (
        <div className="mx-auto mb-6 max-w-2xl flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3">
          <Info className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
          <p className="text-sm text-amber-800">
            <span className="font-semibold">Demo estática</span> — las búsquedas requieren el backend.
            Para probarlo en vivo ejecutá{" "}
            <code className="rounded bg-amber-100 px-1 font-mono text-xs">./start.sh</code>{" "}
            en tu máquina y abrí{" "}
            <code className="rounded bg-amber-100 px-1 font-mono text-xs">localhost:3000</code>.
          </p>
        </div>
      )}

      {/* Input */}
      <div
        className={`mx-auto transition-all duration-300 ${
          hasSearched ? "max-w-3xl" : "max-w-2xl"
        }`}
      >
        <SearchBox onSearch={handleSearch} isLoading={isPending} />

        {!hasSearched && (
          <div className="mt-4 flex flex-wrap justify-center gap-2">
            {EXAMPLES.map((q) => (
              <button
                key={q}
                onClick={() => handleSearch(q)}
                className="rounded-full border border-neutral-200 bg-white px-3.5 py-1.5 text-xs text-neutral-600 transition-colors hover:border-blue-200 hover:bg-blue-50 hover:text-blue-700"
              >
                {q}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Refinement panel — always visible */}
      <div className="mx-auto mt-5 max-w-3xl">
        <RefinementPanel
          key={hasSearched ? lastQuery : "initial"}
          initialFilters={currentFilters}
          onApply={handleApplyFilters}
          isLoading={isPending}
        />
      </div>

      {/* Results */}
      <div className="mx-auto mt-6 max-w-5xl">
        <ResultsList
          data={data}
          isLoading={isPending}
          error={error}
          hasSearched={hasSearched}
          onSearch={handleSearch}
          loadingQuery={variables?.query}
          scoringPrefs={scoringPrefs}
        />
      </div>

      {/* Scoring modal */}
      <ScoringPanel
        open={scoringOpen}
        onClose={() => setScoringOpen(false)}
        onPrefsChange={setScoringPrefs}
      />
    </main>
  );
}

