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


def parse_query(text: str) -> SearchFilters:
    """Convierte una consulta en lenguaje natural a SearchFilters."""
    t = _normalize(text)
    return SearchFilters(
        operacion=_parse_operacion(t),
        tipo="departamento",
        barrios=_parse_barrios(t),
        precio_min=_parse_precio_min(t),
        precio_max=_parse_precio_max(t),
        m2_min=_parse_m2_min(t),
        m2_max=_parse_m2_max(t),
        ambientes_min=_parse_ambientes(t),
        balcon=_parse_balcon(t),
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
        r"desde\s+(\d+(?:[.,]\d+)?)\s*m[²2]?",
        r"a\s+partir\s+de\s+(\d+(?:[.,]\d+)?)\s*m[²2]?",
        r"(?:m[ií]nimo|al\s+menos|por\s+lo\s+menos)\s+(\d+(?:[.,]\d+)?)\s*m[²2]?",
        r"m[aá]s\s+de\s+(\d+(?:[.,]\d+)?)\s*m[²2]?",
        r"(\d+(?:[.,]\d+)?)\s*m[²2]\s*(?:m[ií]nimo|o\s+m[aá]s)",
        r"superficie\s+(?:de\s+)?(\d+(?:[.,]\d+)?)",
        r"(\d+(?:[.,]\d+)?)\s*m[²2]\s+(?:como\s+)?m[ií]nimo",
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
        r"hasta\s+(\d+(?:[.,]\d+)?)\s*m[²2]?",
        r"(\d+(?:[.,]\d+)?)\s*m[²2]\s*(?:como\s+)?m[aá]ximo",
        r"m[aá]ximo\s+(\d+(?:[.,]\d+)?)\s*m[²2]?",
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
