"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { SearchBox } from "@/components/SearchBox";
import { ResultsList } from "@/components/ResultsList";
import { searchProperties } from "@/lib/api";
import type { SearchApiResponse } from "@/types/property";

const EXAMPLES = [
  "Palermo, entre USD 90k y 120k, desde 40m²",
  "2 ambientes en Belgrano o Colegiales con balcón",
  "Monoambiente en Recoleta hasta USD 100k",
  "Villa Crespo o Almagro, 3 ambientes",
];

export default function HomePage() {
  const [hasSearched, setHasSearched] = useState(false);

  const { mutate, data, isPending, error, reset, variables } = useMutation<
    SearchApiResponse,
    Error,
    string
  >({
    mutationFn: (query: string) => searchProperties(query),
  });

  function handleSearch(query: string) {
    setHasSearched(true);
    reset();
    mutate(query);
  }

  return (
    <main className="mx-auto min-h-screen max-w-5xl px-4 pb-16 pt-12 sm:pt-16">
      {/* Hero */}
      <div
        className={`text-center transition-all duration-300 ${
          hasSearched ? "mb-6" : "mb-10"
        }`}
      >
        <h1 className="mb-2 text-3xl font-bold tracking-tight text-neutral-900 sm:text-4xl">
          Depar Finder
        </h1>
        {!hasSearched && (
          <p className="mx-auto mt-2 max-w-lg text-base text-neutral-500">
            Buscá tu próximo departamento en CABA usando lenguaje natural.
            Resultados de Zonaprop, Argenprop, MEL y Toribio Achaval.
          </p>
        )}
      </div>

      {/* Search */}
      <div
        className={`mx-auto transition-all duration-300 ${
          hasSearched ? "max-w-3xl" : "max-w-2xl"
        }`}
      >
        <SearchBox onSearch={handleSearch} isLoading={isPending} />

        {/* Example chips — only before first search */}
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

      {/* Results */}
      <div className="mx-auto mt-8 max-w-5xl">
        <ResultsList
          data={data}
          isLoading={isPending}
          error={error}
          hasSearched={hasSearched}
          onSearch={handleSearch}
          loadingQuery={variables}
        />
      </div>
    </main>
  );
}
