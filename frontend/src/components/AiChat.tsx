"use client";

import { useState, useRef, useEffect } from "react";
import { useMutation } from "@tanstack/react-query";
import { Send, Bot, User, Loader2 } from "lucide-react";
import { chatWithAI } from "@/lib/api";
import type { ChatMessage } from "@/types/property";
import { cn } from "@/lib/utils";

const SUGGESTED = [
  "¿Cuál es el precio promedio por m² en Palermo?",
  "Comparame Almagro vs Villa Crespo",
  "¿Qué barrios tienen mejor relación precio/m²?",
  "¿Cuál es el promedio de expensas en Belgrano?",
  "¿Dónde conviene comprar con menos de USD 80k?",
];

function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === "user";
  return (
    <div className={cn("flex gap-2.5", isUser ? "flex-row-reverse" : "flex-row")}>
      {/* Avatar */}
      <div
        className={cn(
          "mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-white",
          isUser ? "bg-blue-600" : "bg-neutral-800",
        )}
      >
        {isUser ? (
          <User className="h-3.5 w-3.5" />
        ) : (
          <Bot className="h-3.5 w-3.5" />
        )}
      </div>

      {/* Bubble */}
      <div
        className={cn(
          "max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed",
          isUser
            ? "rounded-tr-sm bg-blue-600 text-white"
            : "rounded-tl-sm bg-neutral-100 text-neutral-800",
        )}
      >
        {/* Simple markdown-like rendering: bold and newlines */}
        {msg.content.split("\n").map((line, i) => {
          // Render **bold**
          const rendered = line.replace(/\*\*(.*?)\*\*/g, (_, t) => `<strong>${t}</strong>`);
          return (
            <p
              key={i}
              className={line === "" ? "h-2" : ""}
              dangerouslySetInnerHTML={{ __html: rendered }}
            />
          );
        })}
      </div>
    </div>
  );
}

function TypingBubble() {
  return (
    <div className="flex gap-2.5">
      <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-neutral-800 text-white">
        <Bot className="h-3.5 w-3.5" />
      </div>
      <div className="flex items-center gap-1 rounded-2xl rounded-tl-sm bg-neutral-100 px-4 py-3">
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-neutral-400 [animation-delay:-0.3s]" />
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-neutral-400 [animation-delay:-0.15s]" />
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-neutral-400" />
      </div>
    </div>
  );
}

export function AiChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: "assistant",
      content:
        "Hola 👋 Soy tu asistente de mercado inmobiliario en CABA.\n\nPuedo darte estadísticas de precios por barrio, comparar zonas, analizar la relación precio/m² y más — todo basado en datos reales de las publicaciones.\n\n¿Qué querés saber?",
    },
  ]);
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  const { mutate, isPending } = useMutation({
    mutationFn: (q: string) => chatWithAI(q),
    onSuccess: (data) => {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.message },
      ]);
    },
    onError: (err: Error) => {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `⚠️ Error al consultar la IA: ${err.message}`,
        },
      ]);
    },
  });

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isPending]);

  function send(text: string) {
    const trimmed = text.trim();
    if (!trimmed || isPending) return;
    setMessages((prev) => [...prev, { role: "user", content: trimmed }]);
    setInput("");
    mutate(trimmed);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send(input);
    }
  }

  const showSuggestions = messages.length === 1;

  return (
    <div className="mx-auto flex max-w-2xl flex-col" style={{ height: "calc(100vh - 280px)", minHeight: "420px" }}>
      {/* Message area */}
      <div className="flex-1 space-y-4 overflow-y-auto rounded-2xl border border-neutral-100 bg-white p-4 shadow-sm">
        {messages.map((msg, i) => (
          <MessageBubble key={i} msg={msg} />
        ))}
        {isPending && <TypingBubble />}
        <div ref={bottomRef} />
      </div>

      {/* Suggested questions */}
      {showSuggestions && (
        <div className="mt-3 flex flex-wrap gap-2">
          {SUGGESTED.map((q) => (
            <button
              key={q}
              onClick={() => send(q)}
              className="rounded-full border border-neutral-200 bg-white px-3 py-1.5 text-xs text-neutral-600 transition-colors hover:border-blue-200 hover:bg-blue-50 hover:text-blue-700"
            >
              {q}
            </button>
          ))}
        </div>
      )}

      {/* Input */}
      <div className="mt-3 flex gap-2">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Preguntá sobre precios, barrios, tendencias…"
          rows={1}
          className="flex-1 resize-none rounded-xl border border-neutral-200 bg-white px-4 py-3 text-sm text-neutral-900 shadow-sm outline-none transition-colors placeholder:text-neutral-400 focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
        />
        <button
          onClick={() => send(input)}
          disabled={isPending || !input.trim()}
          className={cn(
            "flex h-[46px] w-[46px] shrink-0 items-center justify-center rounded-xl transition-colors",
            isPending || !input.trim()
              ? "bg-neutral-100 text-neutral-400"
              : "bg-blue-600 text-white hover:bg-blue-700",
          )}
        >
          {isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Send className="h-4 w-4" />
          )}
        </button>
      </div>
    </div>
  );
}
