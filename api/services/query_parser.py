"""
api/services/query_parser.py
────────────────────────────
Convierte lenguaje natural a SearchFilters.

Responsabilidades:
  ✔ Extraer intención del usuario (barrio, precio, m², características)
  ✗ No consulta la base de datos
  ✗ No valida disponibilidad de barrios
  ✗ No conoce portales ni configuración interna

Interfaz pública:
    parse_query(text: str) -> SearchFilters
"""

from __future__ import annotations

import re
from typing import Optional

from shared.filters import SearchFilters

_OPERACION_KEYWORDS = {
    "venta":    ["comprar", "compra", "venta", "vender", "adquirir"],
    "alquiler": ["alquilar", "alquiler", "arrendar", "renta", "rentar", "alq"],
}

_BARRIO_ALIASES: dict[str, str] = {
    "agronomia": "Agronomía", "agronomía": "Agronomía",
    "almagro": "Almagro", "balvanera": "Balvanera", "barracas": "Barracas",
    "barrio norte": "Barrio Norte", "barrionorte": "Barrio Norte",
    "belgrano": "Belgrano", "boedo": "Boedo", "caballito": "Caballito",
    "chacarita": "Chacarita", "coghlan": "Coghlan", "colegiales": "Colegiales",
    "constitucion": "Constitución", "constitución": "Constitución",
    "devoto": "Villa Devoto", "floresta": "Floresta", "flores": "Flores",
    "la boca": "La Boca", "la paternal": "La Paternal", "liniers": "Liniers",
    "lugano": "Villa Lugano", "mataderos": "Mataderos", "monserrat": "Monserrat",
    "monte castro": "Monte Castro", "nueva pompeya": "Nueva Pompeya",
    "nunez": "Núñez", "nuñez": "Núñez", "palermo": "Palermo",
    "parque avellaneda": "Parque Avellaneda", "parque chacabuco": "Parque Chacabuco",
    "parque chas": "Parque Chas", "parque patricios": "Parque Patricios",
    "paternal": "La Paternal", "pompeya": "Nueva Pompeya",
    "puerto madero": "Puerto Madero", "recoleta": "Recoleta", "retiro": "Retiro",
    "saavedra": "Saavedra", "san cristobal": "San Cristóbal",
    "san nicolas": "San Nicolás", "san telmo": "San Telmo",
    "tribunales": "Tribunales", "velez": "Vélez Sársfield",
    "velez sarsfield": "Vélez Sársfield", "versalles": "Versalles",
    "villa crespo": "Villa Crespo", "villa del parque": "Villa del Parque",
    "villa devoto": "Villa Devoto", "villa general mitre": "Villa General Mitre",
    "villa lugano": "Villa Lugano", "villa luro": "Villa Luro",
    "villa ortuzar": "Villa Ortúzar", "villa pueyrredon": "Villa Pueyrredón",
    "villa real": "Villa Real", "villa riachuelo": "Villa Riachuelo",
    "villa santa rita": "Villa Santa Rita", "villa soldati": "Villa Soldati",
    "villa urquiza": "Villa Urquiza", "villacrespo": "Villa Crespo",
    "villaurquiza": "Villa Urquiza",
}

_ALL_CANONICAL = sorted(set(_BARRIO_ALIASES.values()), key=len, reverse=True)

# Calles principales de CABA y los barrios por los que pasan
_CALLES_A_BARRIOS: dict[str, list[str]] = {
    "callao":           ["Balvanera", "Tribunales", "Recoleta", "Barrio Norte"],
    "corrientes":       ["Balvanera", "Almagro", "Tribunales", "San Nicolás"],
    "santa fe":         ["Barrio Norte", "Recoleta", "Palermo"],
    "rivadavia":        ["Balvanera", "Almagro", "Caballito", "Flores"],
    "cordoba":          ["Balvanera", "Almagro", "Palermo", "San Nicolás"],
    "córdoba":          ["Balvanera", "Almagro", "Palermo", "San Nicolás"],
    "pueyrredon":       ["Almagro", "Recoleta", "Barrio Norte"],
    "cabildo":          ["Belgrano", "Núñez"],
    "scalabrini ortiz": ["Villa Crespo", "Palermo"],
    "thames":           ["Villa Crespo", "Palermo"],
    "malabia":          ["Palermo", "Villa Crespo"],
    "honduras":         ["Palermo"],
    "gorriti":          ["Palermo"],
    "el salvador":      ["Palermo"],
    "medrano":          ["Almagro"],
    "warnes":           ["Villa Crespo", "Chacarita"],
    "lerma":            ["Villa Crespo"],
    "niceto vega":      ["Palermo", "Villa Crespo"],
    "angel gallardo":   ["Almagro", "Parque Chas"],
    "donado":           ["Colegiales", "Belgrano"],
    "juramento":        ["Belgrano"],
    "vidal":            ["Belgrano"],
    "zapiola":          ["Colegiales", "Belgrano"],
    "julian alvarez":   ["Palermo", "Villa Crespo"],
    "humboldt":         ["Palermo"],
    "fitz roy":         ["Palermo", "Villa Crespo"],
    "serrano":          ["Palermo"],
    "uriarte":          ["Palermo"],
    "armenia":          ["Palermo"],
    "paraguay":         ["Palermo", "Recoleta"],
    "laprida":          ["Recoleta"],
    "beruti":           ["Barrio Norte", "Recoleta"],
    "juncal":           ["Barrio Norte", "Recoleta"],
    "libertad":         ["Barrio Norte", "Tribunales"],
    "talcahuano":       ["Tribunales", "San Nicolás"],
    "lavalle":          ["San Nicolás", "Tribunales"],
    "viamonte":         ["San Nicolás", "Tribunales"],
    "uruguay":          ["Balvanera", "Tribunales"],
    "sarmiento":        ["San Nicolás", "Almagro"],
    "entre rios":       ["Balvanera", "Constitución"],
    "entre ríos":       ["Balvanera", "Constitución"],
    "independencia":    ["San Cristóbal", "Balvanera"],
    "defensa":          ["San Telmo"],
    "florida":          ["San Nicolás"],
    "maipu":            ["San Nicolás", "Retiro"],
    "suipacha":         ["San Nicolás", "Retiro"],
}


def _parse_barrios_from_interseccion(t: str) -> list[str]:
    """Detecta calles CABA en el texto y las mapea a barrios.

    Soporta patrones como 'callao y corrientes', 'en callao', 'santa fe y pueyrredon'.
    """
    # Buscar dos calles: "X y Y" o "X e Y"
    # Ordenar por longitud desc para que coincidan las frases más largas primero
    calles_sorted = sorted(_CALLES_A_BARRIOS.keys(), key=len, reverse=True)
    calles_encontradas: list[str] = []
    for calle in calles_sorted:
        if re.search(rf"\b{re.escape(calle)}\b", t):
            calles_encontradas.append(calle)

    if not calles_encontradas:
        return []

    if len(calles_encontradas) >= 2:
        # Buscar barrios comunes entre las dos primeras calles
        b1 = set(_CALLES_A_BARRIOS[calles_encontradas[0]])
        b2 = set(_CALLES_A_BARRIOS[calles_encontradas[1]])
        comunes = list(b1 & b2)
        if comunes:
            return comunes[:2]  # max 2 barrios
        # Sin intersección: usar el primero de cada calle
        return [
            _CALLES_A_BARRIOS[calles_encontradas[0]][0],
            _CALLES_A_BARRIOS[calles_encontradas[1]][0],
        ]

    # Solo una calle encontrada: devolver el primer barrio
    return [_CALLES_A_BARRIOS[calles_encontradas[0]][0]]


def parse_query(text: str) -> SearchFilters:
    """Convierte una consulta en lenguaje natural a SearchFilters."""
    t = _normalize(text)
    ambientes_min = _parse_ambientes(t)
    # monoambiente = exactamente 1 ambiente (no 2, 3, 4...)
    ambientes_max = 1 if "monoambiente" in t else None
    return SearchFilters(
        operacion=_parse_operacion(t),
        tipo="departamento",
        barrios=_parse_barrios(t),
        precio_min=_parse_precio_min(t),
        precio_max=_parse_precio_max(t),
        m2_min=_parse_m2_min(t),
        m2_max=_parse_m2_max(t),
        ambientes_min=ambientes_min,
        ambientes_max=ambientes_max,
        balcon=_parse_balcon(t),
        terraza=_parse_terraza(t),
    )


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().strip())


def _parse_operacion(t: str) -> str:
    for op, keywords in _OPERACION_KEYWORDS.items():
        if any(kw in t for kw in keywords):
            return op
    return "venta"


def _parse_barrios(t: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for alias, canonical in sorted(_BARRIO_ALIASES.items(), key=lambda x: -len(x[0])):
        if alias in t and canonical not in seen:
            found.append(canonical)
            seen.add(canonical)
    for canonical in _ALL_CANONICAL:
        if canonical.lower() in t and canonical not in seen:
            found.append(canonical)
            seen.add(canonical)
    # Fallback: detectar calles / intersecciones cuando no se encontró ningún barrio
    if not found:
        found = _parse_barrios_from_interseccion(t)
    return found


def _parse_precio_min(t: str) -> Optional[int]:
    for pat in [
        r"desde\s+(?:usd\s*)?(\d[\d.,k]*)\s*(?:d[oó]lares?|usd)?",
        r"entre\s+(?:usd\s*)?(\d[\d.,k]*)\s*y",
        r"m[aá]s\s+de\s+(?:usd\s*)?(\d[\d.,k]*)",
        r"precio\s+m[ií]nimo[:\s]+(?:usd\s*)?(\d[\d.,k]*)",
        r"m[ií]nimo\s+(?:usd\s*)?(\d[\d.,k]*)",
    ]:
        m = re.search(pat, t)
        if m:
            return _to_int_price(m.group(1))
    return None


def _parse_precio_max(t: str) -> Optional[int]:
    for pat in [
        r"hasta\s+(?:usd\s*)?(\d[\d.,k]*)\s*(?:d[oó]lares?|usd)?",
        r"y\s+(?:usd\s*)?(\d[\d.,k]*)\s*(?:d[oó]lares?|usd)?",
        r"menos\s+de\s+(?:usd\s*)?(\d[\d.,k]*)",
        r"precio\s+m[aá]ximo[:\s]+(?:usd\s*)?(\d[\d.,k]*)",
        r"m[aá]ximo\s+(?:usd\s*)?(\d[\d.,k]*)",
        r"(?:usd\s*)?\d[\d.,k]+\s*[a\-–]\s*(?:usd\s*)?(\d[\d.,k]+)",
        r"tengo\s+(?:usd\s*)?(\d[\d.,k]*)\s*(?:d[oó]lares?|usd)?",
        r"(?:con\s+)?(?:un\s+)?presupuesto\s+(?:de\s+)?(?:usd\s*)?(\d[\d.,k]*)",
        r"dispongo\s+de\s+(?:usd\s*)?(\d[\d.,k]*)",
        r"cuento\s+con\s+(?:usd\s*)?(\d[\d.,k]*)",
    ]:
        m = re.search(pat, t)
        if m:
            return _to_int_price(m.group(1))
    return None


def _parse_m2_min(t: str) -> Optional[int]:
    for pat in [
        r"desde\s+(\d+(?:[.,]\d+)?)\s*m[²23]?",
        r"a\s+partir\s+de\s+(\d+(?:[.,]\d+)?)\s*m[²23]?",
        r"(?:m[ií]nimo|al\s+menos|por\s+lo\s+menos)\s+(\d+(?:[.,]\d+)?)\s*m[²23]?",
        r"m[aá]s\s+de\s+(\d+(?:[.,]\d+)?)\s*m[²23]?",
        r"mayor\s+de\s+(\d+(?:[.,]\d+)?)\s*m[²23]?",
        r"(\d+(?:[.,]\d+)?)\s*m[²23]\s*(?:m[ií]nimo|o\s+m[aá]s)",
        r"superficie\s+(?:de\s+)?(\d+(?:[.,]\d+)?)",
        r"(\d+(?:[.,]\d+)?)\s*m[²23]\s+(?:como\s+)?m[ií]nimo",
    ]:
        m = re.search(pat, t)
        if m:
            try:
                return int(float(m.group(1).replace(",", ".")))
            except ValueError:
                pass
    return None


def _parse_m2_max(t: str) -> Optional[int]:
    for pat in [
        r"hasta\s+(\d+(?:[.,]\d+)?)\s*m[²23]?",
        r"(\d+(?:[.,]\d+)?)\s*m[²23]\s*(?:como\s+)?m[aá]ximo",
        r"m[aá]ximo\s+(\d+(?:[.,]\d+)?)\s*m[²23]?",
    ]:
        m = re.search(pat, t)
        if m:
            try:
                return int(float(m.group(1).replace(",", ".")))
            except ValueError:
                pass
    return None


def _parse_ambientes(t: str) -> Optional[int]:
    m = re.search(r"(\d+)\s*(?:amb(?:iente)?s?)", t)
    if m:
        return int(m.group(1))
    if "monoambiente" in t:
        return 1
    return None


def _parse_balcon(t: str) -> Optional[bool]:
    if re.search(r"con\s+balc[oó]n|balc[oó]n", t):
        return True
    if re.search(r"sin\s+balc[oó]n", t):
        return False
    return None


def _parse_terraza(t: str) -> Optional[bool]:
    if re.search(r"con\s+terraza|terraza", t):
        return True
    if re.search(r"sin\s+terraza", t):
        return False
    return None


def _to_int_price(raw: str) -> Optional[int]:
    raw = raw.strip().lower()
    if raw.endswith("k"):
        try:
            return int(float(raw[:-1]) * 1000)
        except ValueError:
            return None
    raw = raw.replace(".", "").replace(",", "")
    try:
        v = int(raw)
        return v if v >= 1000 else None
    except ValueError:
        return None
