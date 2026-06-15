import type { SearchApiResponse, ChatApiResponse } from "@/types/property";

// Bakeado en build time: true solo cuando NEXT_PUBLIC_API_URL está configurado.
// En GitHub Pages sin secret configurado este valor es false.
export const HAS_BACKEND = !!(process.env.NEXT_PUBLIC_API_URL);

// || en vez de ?? para que string vacío también active el fallback
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function searchProperties(
  query: string,
  plan: "free" | "premium" = "free",
): Promise<SearchApiResponse> {
  const res = await fetch(`${API_URL}/api/v1/search`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-User-Plan": plan,
    },
    body: JSON.stringify({ query }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(
      (err as { detail?: string }).detail ?? `Error del servidor: ${res.status}`,
    );
  }

  return res.json() as Promise<SearchApiResponse>;
}

export async function chatWithAI(query: string): Promise<ChatApiResponse> {
  const res = await fetch(`${API_URL}/api/v1/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(
      (err as { detail?: string }).detail ?? `Error del servidor: ${res.status}`,
    );
  }

  return res.json() as Promise<ChatApiResponse>;
}
