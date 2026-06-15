export interface PropertyResult {
  ranking: number;
  portal: string;
  barrio: string | null;
  direccion: string | null;
  precio_usd: number | null;
  expensas: number | null;
  m2_totales: number | null;
  m2_cubiertos: number | null;
  ambientes: number | null;
  score: number | null;
  clasificacion: string | null;
  balcon: boolean;
  cochera: boolean;
  url: string;
  estado: string;
  imagen_url: string | null;
}

export interface ExtraFilters {
  operacion?: string | null;
  precio_min?: number | null;
  precio_max?: number | null;
  m2_min?: number | null;
  m2_max?: number | null;
  ambientes_min?: number | null;
  ambientes_max?: number | null;
  balcon?: boolean | null;
  cochera?: boolean | null;
  antiguedad_max?: number | null;
  expensas_max?: number | null;
}

export interface FiltersApplied {
  operacion: string;
  tipo: string | null;
  barrios: string[];
  m2_min: number | null;
  m2_max: number | null;
  precio_min: number | null;
  precio_max: number | null;
  ambientes_min: number | null;
  ambientes_max: number | null;
  balcon: boolean | null;
  cochera: boolean | null;
  antiguedad_max: number | null;
  expensas_max: number | null;
}

export interface SearchApiRequest {
  query: string;
}

export interface SearchApiResponse {
  success: boolean;
  plan: string;
  total: number;
  truncated: boolean;
  results: PropertyResult[];
  filters_applied: FiltersApplied;
  intent?: string;
  message?: string;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ChatApiResponse {
  message: string;
}
