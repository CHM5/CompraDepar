"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import Image from "next/image";
import { SearchBox } from "@/components/SearchBox";
import { ResultsList } from "@/components/ResultsList";
import { RefinementPanel } from "@/components/RefinementPanel";
import { searchProperties, HAS_BACKEND } from "@/lib/api";
import type { SearchApiResponse, ExtraFilters } from "@/types/property";
import { Info } from "lucide-react";

const EXAMPLES = [
  "Palermo, entre USD 90k y 120k, desde 40m²",
  "¿Cuánto sale el m² en Palermo?",
  "Monoambiente en Recoleta hasta USD 100k",
  "¿Qué barrio tiene mejor relación precio/m²?",
  "2 ambientes en Belgrano con balcón",
  "¿Conviene invertir en Caballito?",
];

type SearchParams = { query: string; extraFilters?: ExtraFilters | null };

export default function HomePage() {
  const [hasSearched, setHasSearched] = useState(false);
  const [lastQuery, setLastQuery] = useState("");

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
  }

  function handleApplyFilters(extra: ExtraFilters) {
    reset();
    mutate({ query: lastQuery, extraFilters: extra });
  }

  const showRefinement =
    hasSearched &&
    !isPending &&
    data?.intent === "search" &&
    !!data?.filters_applied;

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

      {/* Refinement panel — slides in after first search results */}
      {showRefinement && (
        <div className="sticky top-3 z-20 mx-auto mt-5 max-w-3xl">
          <RefinementPanel
            key={lastQuery}
            initialFilters={data.filters_applied}
            onApply={handleApplyFilters}
            isLoading={isPending}
          />
        </div>
      )}

      {/* Results */}
      <div className="mx-auto mt-6 max-w-5xl">
        <ResultsList
          data={data}
          isLoading={isPending}
          error={error}
          hasSearched={hasSearched}
          onSearch={handleSearch}
          loadingQuery={variables?.query}
        />
      </div>
    </main>
  );
}
