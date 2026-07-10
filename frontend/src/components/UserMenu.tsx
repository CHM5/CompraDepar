"use client";

import { useState, useRef, useEffect } from "react";
import Image from "next/image";
import { Crown, History, Heart, LogOut, ChevronDown, Shield, Zap, TableProperties } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { trackEvent } from "@/lib/analytics";

interface Props {
  onShowFavorites: () => void;
  onShowHistory: () => void;
}

export function UserMenu({ onShowFavorites, onShowHistory }: Props) {
  const { user, plan, isAdmin, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  if (!user) return null;

  const firstName = user.displayName.split(" ")[0];

  async function handleLogout() {
    setOpen(false);
    await logout();
  }

  return (
    <div ref={ref} className="relative flex items-center gap-2.5">
      {/* Greeting */}
      <span className="hidden text-sm font-medium text-neutral-700 sm:block">
        Hola, {firstName} 👋
      </span>

      {/* Avatar button */}
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1.5 rounded-xl border border-neutral-200 bg-white px-2 py-1.5 shadow-sm transition-colors hover:border-neutral-300 hover:bg-neutral-50"
        aria-label="Menú de usuario"
      >
        {user.photoURL ? (
          <Image
            src={user.photoURL}
            alt={user.displayName}
            width={28}
            height={28}
            className="h-7 w-7 rounded-full"
            referrerPolicy="no-referrer"
          />
        ) : (
          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-blue-600 text-xs font-bold text-white">
            {user.displayName[0].toUpperCase()}
          </div>
        )}
        <ChevronDown
          className={`h-3.5 w-3.5 text-neutral-400 transition-transform ${
            open ? "rotate-180" : ""
          }`}
        />
      </button>

      {/* Dropdown */}
      {open && (
        <div className="absolute right-0 top-full z-50 mt-2 w-64 rounded-2xl border border-neutral-100 bg-white py-1 shadow-xl">
          {/* User info */}
          <div className="border-b border-neutral-100 px-4 py-3">
            <p className="truncate text-sm font-semibold text-neutral-900">
              {user.displayName}
            </p>
            <p className="truncate text-xs text-neutral-400">{user.email}</p>
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              {plan === "premium" || isAdmin ? (
                <span className="flex items-center gap-1 rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-semibold text-amber-700">
                  <Crown className="h-3 w-3" />
                  Premium
                </span>
              ) : (
                <span className="rounded-full bg-neutral-100 px-2.5 py-0.5 text-xs font-semibold text-neutral-600">
                  Plan Free
                </span>
              )}
              {isAdmin && (
                <span className="flex items-center gap-1 rounded-full bg-violet-100 px-2.5 py-0.5 text-xs font-semibold text-violet-700">
                  <Shield className="h-3 w-3" />
                  Admin
                </span>
              )}
            </div>
          </div>

          {/* Menu items */}
          <button
            onClick={() => {
              setOpen(false);
              onShowFavorites();
            }}
            className="flex w-full items-center gap-2.5 px-4 py-2.5 text-sm text-neutral-700 transition-colors hover:bg-neutral-50"
          >
            <Heart className="h-4 w-4 text-rose-400" />
            Mis favoritos
          </button>

          <button
            onClick={() => {
              setOpen(false);
              onShowHistory();
            }}
            className="flex w-full items-center gap-2.5 px-4 py-2.5 text-sm text-neutral-700 transition-colors hover:bg-neutral-50"
          >
            <History className="h-4 w-4 text-blue-400" />
            Historial de búsquedas
          </button>

          <a
            href={`https://docs.google.com/spreadsheets/d/${process.env.NEXT_PUBLIC_SHEETS_ID || "1FxQJU8iR_31B8b5Y0bdP0PAxbw7AEObVbengyEQ5Gfk"}`}
            target="_blank"
            rel="noopener noreferrer"
            onClick={() => setOpen(false)}
            className="flex w-full items-center gap-2.5 px-4 py-2.5 text-sm text-neutral-700 transition-colors hover:bg-neutral-50"
          >
            <TableProperties className="h-4 w-4 text-emerald-500" />
            Ver en Google Sheets
          </a>

          {/* Upgrade CTA (free plan only) */}
          {plan === "free" && !isAdmin && (
            <button
              onClick={() => {
                setOpen(false);
                trackEvent("upgrade_click");
              }}
              className="mx-3 my-2 flex w-[calc(100%-1.5rem)] items-center gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2.5 text-left transition-colors hover:bg-amber-100"
            >
              <Zap className="h-4 w-4 shrink-0 text-amber-500" />
              <div>
                <p className="text-xs font-semibold text-amber-800">
                  Actualizar a Premium
                </p>
                <p className="text-[11px] text-amber-600">
                  Resultados ilimitados, alertas y más.
                </p>
              </div>
            </button>
          )}

          {/* Logout */}
          <div className="mt-1 border-t border-neutral-100">
            <button
              onClick={handleLogout}
              className="flex w-full items-center gap-2.5 px-4 py-2.5 text-sm text-neutral-500 transition-colors hover:bg-neutral-50 hover:text-neutral-700"
            >
              <LogOut className="h-4 w-4" />
              Cerrar sesión
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
