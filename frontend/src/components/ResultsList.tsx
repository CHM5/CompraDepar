import { AlertCircle, Bot, Loader2, MapPin, SearchX, Sparkles } from "lucide-react";
import { PropertyCard } from "./PropertyCard";
import type { SearchApiResponse, FiltersApplied } from "@/types/property";

/** Formatea un precio según la operación (USD para venta, $ para alquiler) */
function fmtPrice(value: number, operacion: string): string {
  if (operacion === "alquiler") {
    return `$${(value / 1000).toFixed(0)}k`;
  }
  return `USD ${(value / 1000).toFixed(0)}k`;
}

/** Chips de filtros activos encima de los resultados */
function FiltersPanel({ filters }: { filters: FiltersApplied }) {
  const { operacion, barrios, precio_min, precio_max, m2_min, ambientes_min, balcon } = filters;

  type Chip = { label: string; cls: string };
  const chips: Chip[] = [];

  chips.push(
    operacion === "alquiler"
      ? { label: "Alquiler", cls: "bg-violet-100 text-violet-700" }
      : { label: "Venta", cls: "bg-blue-100 text-blue-700" },
  );

  if (barrios?.length) {
    for (const b of barrios)
      chips.push({ label: `📍 ${b}`, cls: "bg-neutral-100 text-neutral-700" });
  }

  if (precio_min != null && precio_max != null) {
    chips.push({ label: `${fmtPrice(precio_min, operacion)} – ${fmtPrice(precio_max, operacion)}`, cls: "bg-green-50 text-green-700" });
  } else if (precio_max != null) {
    chips.push({ label: `Hasta ${fmtPrice(precio_max, operacion)}`, cls: "bg-green-50 text-green-700" });
  } else if (precio_min != null) {
    chips.push({ label: `Desde ${fmtPrice(precio_min, operacion)}`, cls: "bg-green-50 text-green-700" });
  }

  if (m2_min != null)
    chips.push({ label: `≥ ${m2_min} m²`, cls: "bg-orange-50 text-orange-700" });

  if (ambientes_min != null)
    chips.push({ label: `${ambientes_min}+ amb`, cls: "bg-yellow-50 text-yellow-700" });

  if (balcon === true)
    chips.push({ label: "Balcón", cls: "bg-sky-50 text-sky-700" });

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-xl border border-neutral-100 bg-white px-4 py-2.5 shadow-sm">
      <MapPin className="h-3.5 w-3.5 shrink-0 text-neutral-400" />
      <span className="text-xs text-neutral-400">Búsqueda:</span>
      {chips.map((c, i) => (
        <span key={i} className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${c.cls}`}>
          {c.label}
        </span>
      ))}
    </div>
  );
}

const SUGGESTED_PROMPTS = [
  "Estoy buscando comprar un departamento en Palermo",
  "2 ambientes en Belgrano hasta USD 120k",
  "¿Cuánto sale el m² en Recoleta?",
  "Villa Crespo o Almagro, 3 ambientes hasta 110k",
];

const SUGGESTED_SEARCH_AFTER_AI = [
  "Quiero comprar en Palermo hasta 120k USD",
  "2 ambientes en Almagro desde 40 m²",
  "Monoambiente en Recoleta con balcón",
  "Departamento en Villa Crespo hasta 90k",
];

/** Burbuja violeta para respuestas analíticas de IA */
function AiChatReply({
  message,
  onSearch,
}: {
  message: string;
  onSearch: (q: string) => void;
}) {
  return (
    <div className="mx-auto max-w-xl space-y-5">
      <div className="flex items-start gap-3">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-violet-600 text-white shadow-sm">
          <Sparkles className="h-4 w-4" />
        </div>
        <div className="rounded-2xl rounded-tl-sm bg-gradient-to-br from-violet-50 to-indigo-50 px-4 py-3 shadow-sm border border-violet-100">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-violet-500">
            Análisis IA
          </p>
          <div className="text-sm text-neutral-800 leading-relaxed space-y-1">
            {message.split("\n").filter(Boolean).map((line, i) => {
              const parts = line.split(/(\*\*[^*]+\*\*)/);
              return (
                <p key={i}>
                  {parts.map((p, j) =>
                    p.startsWith("**") && p.endsWith("**") ? (
                      <strong key={j} className="font-semibold text-neutral-900">{p.slice(2, -2)}</strong>
                    ) : (
                      <span key={j}>{p}</span>
                    )
                  )}
                </p>
              );
            })}
          </div>
        </div>
      </div>
      <div className="pl-11 space-y-2">
        <p className="text-xs text-neutral-400 font-medium uppercase tracking-wide">Buscar propiedades</p>
        <div className="flex flex-wrap gap-2">
          {SUGGESTED_SEARCH_AFTER_AI.map((q) => (
            <button
              key={q}
              onClick={() => onSearch(q)}
              className="rounded-full border border-violet-100 bg-violet-50 px-3.5 py-1.5 text-xs text-violet-700 transition-colors hover:bg-violet-100 hover:border-violet-200"
            >
              {q}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function SkeletonCard() {
  return (
    <div className="animate-pulse rounded-2xl border border-neutral-100 bg-white p-5 shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="h-6 w-6 rounded-full bg-neutral-200" />
          <div className="h-5 w-20 rounded-full bg-neutral-200" />
        </div>
        <div className="h-5 w-14 rounded-lg bg-neutral-200" />
      </div>
      <div className="mb-0.5 h-4 w-28 rounded bg-neutral-200" />
      <div className="mb-3 h-3 w-44 rounded bg-neutral-100" />
      <div className="mb-3 h-8 w-32 rounded bg-neutral-200" />
      <div className="mb-4 flex gap-1.5">
        <div className="h-5 w-16 rounded-full bg-neutral-100" />
        <div className="h-5 w-12 rounded-full bg-neutral-100" />
        <div className="h-5 w-14 rounded-full bg-neutral-100" />
      </div>
      <div className="h-10 w-full rounded-xl bg-neutral-100" />
    </div>
  );
}

/** Respuesta tipo chat para intenciones no-SEARCH (saludo, ayuda, desconocido) */
function ConversationalReply({
  message,
  onSearch,
}: {
  message: string;
  onSearch: (q: string) => void;
}) {
  return (
    <div className="mx-auto max-w-xl space-y-5">
      {/* Burbuja del asistente */}
      <div className="flex items-start gap-3">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-blue-600 text-white shadow-sm">
          <Bot className="h-4 w-4" />
        </div>
        <div className="rounded-2xl rounded-tl-sm bg-white px-4 py-3 shadow-sm border border-neutral-100">
          <p className="text-sm text-neutral-800 leading-relaxed">{message}</p>
        </div>
      </div>

      {/* Sugerencias */}
      <div className="pl-11 space-y-2">
        <p className="text-xs text-neutral-400 font-medium uppercase tracking-wide">
          Podés probar con
        </p>
        <div className="flex flex-wrap gap-2">
          {SUGGESTED_PROMPTS.map((q) => (
            <button
              key={q}
              onClick={() => onSearch(q)}
              className="rounded-full border border-blue-100 bg-blue-50 px-3.5 py-1.5 text-xs text-blue-700 transition-colors hover:bg-blue-100 hover:border-blue-200"
            >
              {q}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

interface ResultsListProps {
  data: SearchApiResponse | undefined;
  isLoading: boolean;
  error: Error | null;
  hasSearched: boolean;
  onSearch: (q: string) => void;
  loadingQuery?: string;
}

export function ResultsList({
  data,
  isLoading,
  error,
  hasSearched,
  onSearch,
  loadingQuery,
}: ResultsListProps) {
  if (!hasSearched) return null;

  if (isLoading) {
    return (
      <div className="space-y-5">
        {/* Loading banner */}
        <div className="flex items-center gap-3 rounded-2xl border border-blue-100 bg-blue-50/70 px-5 py-4">
          <Loader2 className="h-5 w-5 shrink-0 animate-spin text-blue-500" />
          <div>
            <p className="text-sm font-semibold text-blue-800">
              {loadingQuery
                ? `Buscando: "${loadingQuery}"`
                : "Buscando departamentos…"}
            </p>
            <p className="mt-0.5 text-xs text-blue-500">
              Consultando portales inmobiliarios · puede tardar unos segundos
            </p>
          </div>
        </div>
        {/* Skeleton grid */}
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center gap-3 py-20 text-center">
        <AlertCircle className="h-10 w-10 text-red-400" />
        <p className="font-semibold text-neutral-700">Algo salió mal</p>
        <p className="max-w-sm text-sm text-neutral-500">{error.message}</p>
        <p className="text-xs text-neutral-400">
          Verificá que el backend esté corriendo en{" "}
          <code className="rounded bg-neutral-100 px-1 py-0.5 font-mono">
            {process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}
          </code>
        </p>
      </div>
    );
  }

  // Respuesta conversacional: el backend respondió con mensaje (no es una búsqueda con resultados)
  if (data && data.message && data.intent !== "search") {
    if (data.intent === "ai_chat") {
      return (
        <div className="py-8">
          <AiChatReply message={data.message} onSearch={onSearch} />
        </div>
      );
    }
    return (
      <div className="py-8">
        <ConversationalReply message={data.message} onSearch={onSearch} />
      </div>
    );
  }

  // Búsqueda real sin resultados
  if (!data || data.results.length === 0) {
    return (
      <div className="flex flex-col items-center gap-3 py-20 text-center">
        <SearchX className="h-10 w-10 text-neutral-300" />
        <p className="font-semibold text-neutral-700">Sin resultados</p>
        <p className="max-w-sm text-sm text-neutral-500">
          No encontramos propiedades para esa búsqueda en los portales disponibles.
          Probá con otro barrio, rango de precio o reducí los filtros.
        </p>
        <div className="mt-2 flex flex-wrap justify-center gap-2">
          {SUGGESTED_PROMPTS.map((q) => (
            <button
              key={q}
              onClick={() => onSearch(q)}
              className="rounded-full border border-neutral-200 bg-white px-3.5 py-1.5 text-xs text-neutral-600 transition-colors hover:border-blue-200 hover:bg-blue-50 hover:text-blue-700"
            >
              {q}
            </button>
          ))}
        </div>
      </div>
    );
  }

  const { results, total, truncated, plan, filters_applied } = data;

    return (
    <div className="space-y-4">
      {/* Filtros activos */}
      <FiltersPanel filters={filters_applied} />

      {/* Stats bar */}
      <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-neutral-500">
        <span>
          <span className="font-semibold text-neutral-800">{total}</span>{" "}
          propiedad{total !== 1 ? "es" : ""} encontrada{total !== 1 ? "s" : ""}
          {filters_applied.barrios?.length > 0 && (
            <> · {filters_applied.barrios.join(", ")}</>
          )}
        </span>
        <span className="rounded-full bg-neutral-100 px-2.5 py-0.5 text-xs capitalize">
          Plan {plan}
        </span>
      </div>

      {/* Truncated banner */}
      {truncated && (
        <div className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3">
          <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
          <p className="text-sm text-amber-800">
            Mostrando los primeros {results.length} resultados.{" "}
            <span className="font-semibold">
              Actualizá a Premium para ver los {total} resultados.
            </span>
          </p>
        </div>
      )}

      {/* Grid */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {results.map((prop) => (
          <PropertyCard key={`${prop.portal}-${prop.ranking}`} property={prop} />
        ))}
      </div>
    </div>
  );
}
