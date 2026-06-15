import type { SearchApiResponse } from "@/types/property";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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
