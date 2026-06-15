"use client";

import { useState, useRef, type FormEvent, type KeyboardEvent } from "react";
import { Search, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface SearchBoxProps {
  onSearch: (query: string) => void;
  isLoading?: boolean;
}

export function SearchBox({ onSearch, isLoading = false }: SearchBoxProps) {
  const [value, setValue] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const q = value.trim();
    if (!q || isLoading) return;
    onSearch(q);
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      const q = value.trim();
      if (!q || isLoading) return;
      onSearch(q);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="w-full">
      <div
        className={cn(
          "relative flex items-end gap-2 rounded-2xl border bg-white p-3 shadow-sm",
          "transition-shadow focus-within:shadow-md",
          "border-neutral-200 focus-within:border-blue-300",
        )}
      >
        <textarea
          ref={ref}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          rows={2}
          disabled={isLoading}
          placeholder="Ej: quiero comprar un departamento en Palermo entre 90.000 y 120.000 dólares con balcón…"
          className={cn(
            "flex-1 resize-none bg-transparent text-sm leading-relaxed text-neutral-800",
            "placeholder:text-neutral-400 focus:outline-none",
            "disabled:opacity-50",
          )}
        />
        <button
          type="submit"
          disabled={!value.trim() || isLoading}
          aria-label="Buscar"
          className={cn(
            "flex h-9 w-9 shrink-0 items-center justify-center rounded-xl",
            "bg-blue-600 text-white transition-colors",
            "hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-40",
          )}
        >
          {isLoading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Search className="h-4 w-4" />
          )}
        </button>
      </div>
      <p className="mt-1.5 text-center text-xs text-neutral-400">
        Enter para buscar · Shift+Enter para nueva línea
      </p>
    </form>
  );
}
