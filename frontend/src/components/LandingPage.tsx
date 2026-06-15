"use client";

import Image from "next/image";
import { useState } from "react";
import { Bell, Building2, TrendingDown, Sparkles } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { FIREBASE_CONFIGURED } from "@/lib/firebase";

export function LandingPage() {
  const { login } = useAuth();
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function handleLogin() {
    setLoading(true);
    setErr(null);
    try {
      await login();
    } catch (e: unknown) {
      setErr((e as Error).message ?? "Error al iniciar sesión. Intentá de nuevo.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col bg-gradient-to-br from-neutral-50 via-blue-50/30 to-indigo-50/30">
      {/* Top bar */}
      <header className="flex items-center gap-2 px-6 py-5">
        <Image
          src="/depar-finder-logo.svg"
          alt="Depar Finder"
          width={32}
          height={32}
          className="h-8 w-8 rounded-lg"
        />
        <span className="text-xl font-bold text-neutral-900">Depar Finder</span>
      </header>

      {/* Hero */}
      <main className="flex flex-1 flex-col items-center justify-center px-6 py-16 text-center">
        {/* Badge */}
        <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-blue-100 bg-blue-50 px-4 py-1.5 text-sm font-medium text-blue-700">
          <Sparkles className="h-4 w-4" />
          Búsqueda inteligente de departamentos en CABA
        </div>

        {/* Headline */}
        <h1 className="mb-4 max-w-2xl text-4xl font-extrabold tracking-tight text-neutral-900 sm:text-5xl">
          Encontrá oportunidades{" "}
          <span className="text-blue-600">antes que el resto</span>
        </h1>

        <p className="mb-10 max-w-lg text-lg text-neutral-500">
          Comparamos Zonaprop, Argenprop y más en tiempo real. Buscás en lenguaje
          natural y te mostramos lo mejor ordenado por puntuación.
        </p>

        {/* Value props */}
        <div className="mb-10 grid w-full max-w-2xl grid-cols-1 gap-4 text-left sm:grid-cols-3">
          {[
            {
              icon: Building2,
              title: "Compará todo en un lugar",
              desc: "Zonaprop, Argenprop, MEL y más sincronizados.",
              color: "bg-blue-50 text-blue-600",
            },
            {
              icon: TrendingDown,
              title: "Mejor relación precio/m²",
              desc: "Descubrí las propiedades más convenientes del mercado.",
              color: "bg-green-50 text-green-600",
            },
            {
              icon: Bell,
              title: "Alertas automáticas",
              desc: "Recibí notificaciones cuando baje el precio de lo que te interesa.",
              color: "bg-violet-50 text-violet-600",
            },
          ].map(({ icon: Icon, title, desc, color }) => (
            <div
              key={title}
              className="rounded-2xl border border-neutral-100 bg-white p-4 shadow-sm"
            >
              <div className={`mb-2 inline-flex rounded-xl p-2 ${color}`}>
                <Icon className="h-5 w-5" />
              </div>
              <p className="text-sm font-semibold text-neutral-900">{title}</p>
              <p className="mt-0.5 text-xs text-neutral-500">{desc}</p>
            </div>
          ))}
        </div>

        {/* CTA Button */}
        <button
          onClick={handleLogin}
          disabled={loading}
          className="flex items-center gap-3 rounded-xl bg-neutral-900 px-8 py-4 text-base font-semibold text-white shadow-lg transition-all hover:bg-neutral-700 hover:shadow-xl disabled:cursor-not-allowed disabled:opacity-60"
        >
          {/* Google G */}
          <svg className="h-5 w-5 shrink-0" viewBox="0 0 24 24" aria-hidden="true">
            <path fill="white" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
            <path fill="white" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
            <path fill="white" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
            <path fill="white" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
          </svg>
          {loading
            ? "Iniciando sesión…"
            : FIREBASE_CONFIGURED
            ? "Iniciar sesión con Google"
            : "Entrar (modo demo)"}
        </button>

        {err && (
          <p className="mt-3 max-w-xs text-sm text-red-500">{err}</p>
        )}

        {!FIREBASE_CONFIGURED && (
          <p className="mt-3 text-xs text-neutral-400">
            Firebase no configurado — modo demo con datos locales.
          </p>
        )}

        <p className="mt-4 text-xs text-neutral-400">
          Sin tarjeta de crédito · Plan Free permanentemente gratuito
        </p>
      </main>
    </div>
  );
}
