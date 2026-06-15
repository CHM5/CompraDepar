"""
shared/intent.py
────────────────
Clasificación de intención de usuario basada en reglas.

Sin IA, sin LLM, sin embeddings — solo regex/keywords.

Interfaz pública:
    detect_intent(text: str) -> Intent
"""

from __future__ import annotations

import re
from enum import Enum


class Intent(str, Enum):
    SEARCH   = "search"    # búsqueda inmobiliaria → ejecutar scrapers/DB
    COMMAND  = "command"   # comando de sistema (top, pondera, etc.)
    GREETING = "greeting"  # saludo
    HELP     = "help"      # pedido de ayuda / ejemplos
    UNKNOWN  = "unknown"   # no reconocido


# ── Respuestas estándar por intención ─────────────────────────────────────────

INTENT_MESSAGES: dict[Intent, str] = {
    Intent.GREETING: "¡Hola! Contame qué propiedad estás buscando.",
    Intent.HELP: (
        "Podés buscar propiedades usando lenguaje natural. "
        "Por ejemplo: 'Quiero comprar un departamento en Belgrano desde 40 m² hasta 120.000 dólares'."
    ),
    Intent.COMMAND: (
        "Ese comando no está disponible en la búsqueda web. "
        "Usá el bot de Telegram para comandos como /top, /stats, etc."
    ),
    Intent.UNKNOWN: "No entendí tu mensaje. Contame qué propiedad estás buscando o escribí 'ayuda'.",
}


# ── Patrones por categoría (orden de evaluación importa) ─────────────────────

_GREETING_PATTERNS = re.compile(
    r"""
    ^(                       # desde el principio (mensaje corto)
        hola | hey | hi |
        buen\s*d[ií]a | buenos\s*d[ií]as |
        buenas?\s*(tardes?|noches?)? |
        saludos? | greetings
    )[\s!.]*$                # nada más
    """,
    re.IGNORECASE | re.VERBOSE,
)

_HELP_PATTERNS = re.compile(
    r"""
    ayuda | help |
    qu[eé]\s+pod[eé]s?\s+hacer |
    c[oó]mo\s+funciona |
    ejemplos? |
    qu[eé]\s+hac[eé]s? |
    instrucciones? |
    manual |
    tutorial
    """,
    re.IGNORECASE | re.VERBOSE,
)

_COMMAND_PATTERNS = re.compile(
    r"""
    \btop\s*\d+ |
    /(top|stats|config|barrios|scoring|nueva|reciente|ayuda|start) |
    ponder[aá] | prioriz[aá] | orden[aá]\s+por |
    guard[aá]\s+esta | resetear? | limpiar\s+filtros? |
    exportar | sheet | telegram
    """,
    re.IGNORECASE | re.VERBOSE,
)

_SEARCH_PATTERNS = re.compile(
    r"""
    # Verbos de intención
    quiero?\s+(comprar|alquilar|buscar|encontrar|ver) |
    busco | necesito | estoy\s+buscando |
    me\s+interesa | me\s+gustaria | quisiera |

    # Tipos de propiedad
    \bdepartamento\b | \bdeptos?\b | \bcasa\b | \bph\b |
    \bpropiedad\b | \binmueble\b | \bmonoambiente\b |

    # Operaciones
    \bventa\b | \balquiler\b | \balquilar\b | \bcomprar\b |
    \bvender\b | \barrendar\b |

    # Precio — número largo o con sufijo k/mil
    \bdolares?\b | \busd\b | d[oó]lares? |
    \bpresupuesto\b | \bprecio\b |
    \d+k\b |                       # 110k, 90k
    \d{5,}\b |                     # 110000, 90000

    # Superficie — con o sin espacio antes de m2/m²
    \d+\s*m[²2] |                  # 40m2, 40 m2, 40m²
    metros?\s*cuadrados? | superficie |

    # Características
    \bbalc[oó]n\b | \bcochera\b | \bgarage\b | \bpileta\b |
    \bsum\b | \bgimn[ae]sio\b | \bpiso\s+\d | \bambientes?\b |

    # Barrios CABA (con o sin "en" delante)
    \b(palermo|belgrano|almagro|recoleta|caballito|colegiales|
       chacarita|saavedra|villa\s+crespo|villa\s+urquiza|n[uú][nñ]ez|
       coghlan|barrio\s+norte|la\s+paternal|floresta|flores|
       boedo|devoto|liniers|mataderos|monserrat|retiro|
       san\s+telmo|puerto\s+madero|la\s+boca|nueva\s+pompeya|
       parque\s+chas|parque\s+patricios|versalles|villa\s+luro|
       villa\s+del\s+parque|villa\s+devoto|villa\s+lugano|
       villa\s+ortuzar|villa\s+pueyrredon|villa\s+santa\s+rita|
       villa\s+soldati|monte\s+castro|agronomia|agronomi[aá]|
       villa\s+real|villa\s+riachuelo)\b
    """,
    re.IGNORECASE | re.VERBOSE,
)


def detect_intent(text: str) -> Intent:
    """Clasifica la intención del usuario sin usar IA.

    Orden de prioridad:
        1. GREETING  — saludos cortos
        2. HELP      — pedidos de ayuda/ejemplos
        3. COMMAND   — comandos de sistema
        4. SEARCH    — búsqueda inmobiliaria
        5. UNKNOWN   — no reconocido
    """
    t = text.strip()
    if not t:
        return Intent.UNKNOWN

    if _GREETING_PATTERNS.search(t):
        return Intent.GREETING

    if _HELP_PATTERNS.search(t):
        return Intent.HELP

    if _COMMAND_PATTERNS.search(t):
        return Intent.COMMAND

    if _SEARCH_PATTERNS.search(t):
        return Intent.SEARCH

    return Intent.UNKNOWN
