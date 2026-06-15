import { ExternalLink, Heart, MapPin, Building2, Maximize2, Banknote, ImageOff } from "lucide-react";
import type { PropertyResult } from "@/types/property";
import { cn } from "@/lib/utils";
import { trackEvent } from "@/lib/analytics";

const PORTAL_COLORS: Record<string, string> = {
  Zonaprop: "bg-blue-600 text-white",
  Argenprop: "bg-emerald-600 text-white",
  MEL: "bg-purple-600 text-white",
  ToribiAchaval: "bg-amber-500 text-white",
};

const PORTAL_BG: Record<string, string> = {
  Zonaprop: "from-blue-100 to-blue-50",
  Argenprop: "from-emerald-100 to-emerald-50",
  MEL: "from-purple-100 to-purple-50",
  ToribiAchaval: "from-amber-100 to-amber-50",
};

function formatUSD(value: number | null): string {
  if (!value) return "—";
  if (value >= 1000) return `USD ${(value / 1000).toFixed(0)}k`;
  return new Intl.NumberFormat("es-AR", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value);
}

function formatExpensas(value: number | null): string | null {
  if (!value) return null;
  return `exp $${(value / 1000).toFixed(0)}k`;
}

function ScoreBadge({ score }: { score: number | null }) {
  if (!score) return null;
  const color =
    score >= 90
      ? "bg-green-500 text-white"
      : score >= 80
        ? "bg-yellow-400 text-yellow-900"
        : "bg-white/80 text-neutral-600";
  return (
    <span className={cn("rounded-full px-2 py-0.5 text-xs font-bold shadow-sm", color)}>
      {score.toFixed(0)} pts
    </span>
  );
}

interface PropertyCardProps {
  property: PropertyResult;
  isFav?: boolean;
  onToggleFav?: (e: React.MouseEvent, property: PropertyResult) => void;
}

export function PropertyCard({ property, isFav = false, onToggleFav }: PropertyCardProps) {
  const { ranking, portal, barrio, direccion, precio_usd, expensas,
    m2_totales, m2_cubiertos, ambientes, score, balcon, cochera, url, imagen_url } = property;

  const m2 = m2_totales ?? m2_cubiertos;
  const portalColor = PORTAL_COLORS[portal] ?? "bg-neutral-700 text-white";
  const portalBg = PORTAL_BG[portal] ?? "from-neutral-100 to-neutral-50";
  const exp = formatExpensas(expensas);

  function handleCardClick() {
    if (!url || url === "#") return;
    trackEvent("property_click");
    window.open(url, "_blank", "noopener,noreferrer");
  }

  function handleFavClick(e: React.MouseEvent) {
    e.stopPropagation();
    onToggleFav?.(e, property);
  }

  return (
    <article
      onClick={handleCardClick}
      className={cn(
        "flex flex-col rounded-2xl border border-neutral-100 bg-white overflow-hidden shadow-sm transition-all hover:shadow-md hover:-translate-y-0.5",
        url && url !== "#" ? "cursor-pointer" : "",
      )}
    >
      {/* Imagen */}
      <div className={cn("relative h-44 overflow-hidden bg-gradient-to-br", imagen_url ? "bg-neutral-100" : portalBg)}>
        {imagen_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={imagen_url}
            alt={barrio ?? portal}
            className="h-full w-full object-cover"
            referrerPolicy="no-referrer"
            onError={(e) => {
              const target = e.currentTarget;
              target.onerror = null;
              target.src = "/depar-finder-logo.svg";
              target.className = "h-full w-full object-contain p-6 bg-neutral-50";
            }}
          />
        ) : (
          <div className="flex h-full items-center justify-center">
            <ImageOff className="h-10 w-10 text-neutral-300" />
          </div>
        )}
        <div className="absolute inset-0 bg-gradient-to-t from-black/30 to-transparent pointer-events-none" />
        <span className={cn("absolute left-3 top-3 rounded-full px-2.5 py-0.5 text-xs font-semibold shadow-sm", portalColor)}>
          {portal}
        </span>
        <div className="absolute right-3 top-3 flex items-center gap-1.5">
          <ScoreBadge score={score} />
          {/* Favorite button */}
          <button
            onClick={handleFavClick}
            className="flex h-7 w-7 items-center justify-center rounded-full bg-black/40 backdrop-blur-sm transition-colors hover:bg-black/60"
            title={isFav ? "Quitar de favoritos" : "Guardar en favoritos"}
          >
            <Heart
              className={cn(
                "h-3.5 w-3.5 transition-colors",
                isFav ? "fill-rose-400 text-rose-400" : "text-white",
              )}
            />
          </button>
        </div>
        <span className="absolute bottom-3 left-3 flex h-6 w-6 items-center justify-center rounded-full bg-white/90 text-xs font-bold text-neutral-900 shadow">
          {ranking}
        </span>
        {imagen_url && precio_usd && (
          <span className="absolute bottom-3 right-3 rounded-lg bg-black/60 px-2.5 py-1 text-sm font-bold text-white backdrop-blur-sm">
            {formatUSD(precio_usd)}
          </span>
        )}
      </div>

      {/* Contenido */}
      <div className="flex flex-1 flex-col p-4">
        <div className="mb-3">
          {barrio && (
            <div className="flex items-center gap-1.5">
              <MapPin className="h-3.5 w-3.5 shrink-0 text-neutral-400" />
              <span className="text-sm font-semibold text-neutral-900">{barrio}</span>
            </div>
          )}
          {direccion && <p className="mt-0.5 truncate text-xs text-neutral-400">{direccion}</p>}
        </div>

        {!imagen_url && (
          <div className="mb-3 flex flex-wrap items-baseline gap-1.5">
            <Banknote className="h-4 w-4 shrink-0 text-neutral-400" />
            <span className="text-xl font-bold text-neutral-900">{formatUSD(precio_usd)}</span>
            {exp && <span className="text-xs text-neutral-400">· {exp}</span>}
          </div>
        )}
        {imagen_url && exp && <p className="mb-3 text-xs text-neutral-400">{exp}</p>}

        <div className="mb-4 flex flex-wrap gap-1.5">
          {m2 && (
            <span className="inline-flex items-center gap-1 rounded-full bg-neutral-100 px-2.5 py-0.5 text-xs font-medium text-neutral-700">
              <Maximize2 className="h-3 w-3" />{m2.toFixed(0)} m²
            </span>
          )}
          {ambientes && (
            <span className="inline-flex items-center gap-1 rounded-full bg-neutral-100 px-2.5 py-0.5 text-xs font-medium text-neutral-700">
              <Building2 className="h-3 w-3" />{ambientes} amb
            </span>
          )}
          {balcon && <span className="rounded-full border border-sky-100 bg-sky-50 px-2.5 py-0.5 text-xs font-medium text-sky-700">Balcón</span>}
          {cochera && <span className="rounded-full border border-amber-100 bg-amber-50 px-2.5 py-0.5 text-xs font-medium text-amber-700">Cochera</span>}
        </div>

        {/* Click hint */}
        {url && url !== "#" && (
          <div className="mt-auto flex items-center gap-1 text-xs text-neutral-400">
            <ExternalLink className="h-3 w-3" />
            <span>Hacé clic para abrir en el portal</span>
          </div>
        )}
      </div>
    </article>
  );
}
