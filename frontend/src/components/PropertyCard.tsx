import { ExternalLink, MapPin, Building2, Maximize2, Banknote } from "lucide-react";
import type { PropertyResult } from "@/types/property";
import { cn } from "@/lib/utils";

const PORTAL_COLORS: Record<string, string> = {
  Zonaprop: "bg-blue-100 text-blue-700",
  Argenprop: "bg-emerald-100 text-emerald-700",
  MEL: "bg-purple-100 text-purple-700",
  ToribiAchaval: "bg-amber-100 text-amber-700",
};

function formatUSD(value: number | null): string {
  if (!value) return "—";
  return new Intl.NumberFormat("es-AR", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value);
}

function formatExpensas(value: number | null): string | null {
  if (!value) return null;
  const k = value / 1000;
  return `exp $${k.toFixed(0)}k`;
}

function ScoreBadge({ score }: { score: number | null }) {
  if (!score) return null;
  const color =
    score >= 90
      ? "bg-green-100 text-green-700"
      : score >= 80
        ? "bg-yellow-100 text-yellow-700"
        : "bg-neutral-100 text-neutral-500";
  return (
    <span className={cn("rounded-lg px-2 py-0.5 text-xs font-semibold", color)}>
      {score.toFixed(0)} pts
    </span>
  );
}

function Chip({ icon, label }: { icon?: React.ReactNode; label: string }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-neutral-100 px-2.5 py-0.5 text-xs text-neutral-600">
      {icon}
      {label}
    </span>
  );
}

interface PropertyCardProps {
  property: PropertyResult;
}

export function PropertyCard({ property }: PropertyCardProps) {
  const {
    ranking,
    portal,
    barrio,
    direccion,
    precio_usd,
    expensas,
    m2_totales,
    m2_cubiertos,
    ambientes,
    score,
    balcon,
    cochera,
    url,
  } = property;

  const m2 = m2_totales ?? m2_cubiertos;
  const portalColor = PORTAL_COLORS[portal] ?? "bg-neutral-100 text-neutral-600";
  const exp = formatExpensas(expensas);

  return (
    <article
      className={cn(
        "flex flex-col rounded-2xl border border-neutral-100 bg-white p-5",
        "shadow-sm transition-shadow hover:shadow-md",
      )}
    >
      {/* Header */}
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-neutral-900 text-xs font-bold text-white">
            {ranking}
          </span>
          <span
            className={cn(
              "rounded-full px-2.5 py-0.5 text-xs font-medium",
              portalColor,
            )}
          >
            {portal}
          </span>
        </div>
        <ScoreBadge score={score} />
      </div>

      {/* Barrio */}
      {barrio && (
        <div className="mb-0.5 flex items-center gap-1.5">
          <MapPin className="h-3.5 w-3.5 shrink-0 text-neutral-400" />
          <span className="text-sm font-semibold text-neutral-800">{barrio}</span>
        </div>
      )}

      {/* Dirección */}
      {direccion && (
        <p className="mb-3 truncate text-xs text-neutral-400">{direccion}</p>
      )}
      {!direccion && <div className="mb-3" />}

      {/* Precio */}
      <div className="mb-3 flex flex-wrap items-baseline gap-1.5">
        <Banknote className="h-4 w-4 shrink-0 text-neutral-400" />
        <span className="text-2xl font-bold text-neutral-900">
          {formatUSD(precio_usd)}
        </span>
        {exp && <span className="text-xs text-neutral-400">· {exp}</span>}
      </div>

      {/* Chips */}
      <div className="mb-4 flex flex-wrap gap-1.5">
        {m2 && (
          <Chip
            icon={<Maximize2 className="h-3 w-3" />}
            label={`${m2.toFixed(0)} m²`}
          />
        )}
        {ambientes && (
          <Chip
            icon={<Building2 className="h-3 w-3" />}
            label={`${ambientes} amb`}
          />
        )}
        {balcon && <Chip label="Balcón" />}
        {cochera && <Chip label="Cochera" />}
      </div>

      {/* CTA */}
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        className={cn(
          "mt-auto flex items-center justify-center gap-1.5 rounded-xl",
          "border border-neutral-200 px-4 py-2.5 text-sm font-medium text-neutral-700",
          "transition-colors hover:border-blue-200 hover:bg-blue-50 hover:text-blue-700",
        )}
      >
        Ver publicación
        <ExternalLink className="h-3.5 w-3.5" />
      </a>
    </article>
  );
}
