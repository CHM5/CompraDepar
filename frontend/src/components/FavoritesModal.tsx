"use client";

import { X, Heart, ExternalLink, SearchX } from "lucide-react";
import { PropertyCard } from "./PropertyCard";
import { useFavorites } from "@/hooks/useFavorites";
import { trackEvent } from "@/lib/analytics";

interface Props {
  email: string;
  onClose: () => void;
}

export function FavoritesModal({ email, onClose }: Props) {
  const { favs, toggleFav, isFav } = useFavorites(email);

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 backdrop-blur-sm sm:items-center"
      onClick={onClose}
    >
      <div
        className="relative max-h-[88vh] w-full overflow-y-auto rounded-t-2xl bg-white shadow-xl sm:max-w-2xl sm:rounded-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-neutral-100 bg-white px-5 py-4">
          <div className="flex items-center gap-2">
            <Heart className="h-5 w-5 text-rose-500" />
            <h2 className="text-base font-bold text-neutral-900">
              Mis favoritos
            </h2>
            {favs.length > 0 && (
              <span className="rounded-full bg-rose-100 px-2 py-0.5 text-xs font-semibold text-rose-600">
                {favs.length}
              </span>
            )}
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1 hover:bg-neutral-100"
          >
            <X className="h-5 w-5 text-neutral-400" />
          </button>
        </div>

        <div className="p-5">
          {favs.length === 0 ? (
            <div className="flex flex-col items-center gap-3 py-16 text-center">
              <SearchX className="h-10 w-10 text-neutral-200" />
              <p className="font-semibold text-neutral-600">
                No guardaste favoritos todavía
              </p>
              <p className="max-w-xs text-sm text-neutral-400">
                Hacé clic en el corazón de cualquier propiedad para guardarla
                aquí.
              </p>
            </div>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2">
              {favs.map((prop) => (
                <div key={`${prop.portal}-${prop.url}`} className="relative">
                  <PropertyCard
                    property={prop}
                    isFav={isFav(prop)}
                    onToggleFav={(_, p) => toggleFav(p)}
                  />
                </div>
              ))}
            </div>
          )}

          {favs.length > 0 && (
            <div className="mt-5 border-t border-neutral-100 pt-4 text-center">
              <a
                href={favs.length === 1 ? favs[0].url : "#"}
                onClick={(e) => {
                  if (favs.length > 1) e.preventDefault();
                  trackEvent("property_click");
                }}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 text-sm text-blue-600 hover:underline"
              >
                <ExternalLink className="h-3.5 w-3.5" />
                Ver en portal
              </a>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
