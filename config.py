"""
config.py
─────────
Configuración central de la aplicación.
Todos los parámetros de búsqueda, scoring y entorno se gestionan aquí.
Modificar este archivo para ajustar los criterios sin tocar la lógica.
"""

from __future__ import annotations

import os
from typing import Dict, List

from dotenv import load_dotenv

load_dotenv()


# ══════════════════════════════════════════════════════════════════════════════
# CRITERIOS DE BÚSQUEDA
# ══════════════════════════════════════════════════════════════════════════════

PRECIO_MIN_USD: int = 80_000
PRECIO_MAX_USD: int = 105_000

M2_MINIMO: float = 35.0           # m² totales mínimos
ANTIGUEDAD_MAXIMA: int = 20       # años máximos de antigüedad
PISO_MINIMO: int = 2              # piso mínimo (inclusive)

BARRIOS_OBJETIVO: List[str] = [
    "Palermo",
    "Belgrano",
    "Villa Crespo",
    "Almagro",
    "Núñez",
    "Saavedra",
    "Caballito",
    "Recoleta",
    "Barrio Norte",
    "Chacarita",
    "Coghlan",
    "Villa Urquiza",
    "Colegiales",
]

DISPOSICION_EXCLUIR: List[str] = ["interno", "lateral"]
DISPOSICION_PRIORIZAR: List[str] = ["frente", "contrafrente"]


# ══════════════════════════════════════════════════════════════════════════════
# SCORING — valores configurables
# ══════════════════════════════════════════════════════════════════════════════

SCORE_BARRIOS: Dict[str, int] = {
    "Palermo": 50,
    "Belgrano": 45,
    "Villa Crespo": 40,
    "Almagro": 35,
    "Núñez": 30,
    "Saavedra": 25,
}

SCORE_DISPOSICION: Dict[str, int] = {
    "frente": 20,
    "contrafrente": 15,
}

SCORE_BALCON: int = 15
SCORE_METROS_45_MAS: int = 10      # ← mantenido por compatibilidad (no se usa si SCORE_M2_TIERS está definido)
SCORE_ANTIGUEDAD_10_MENOS: int = 10 # ≤ 10 años
SCORE_COCHERA: int = 5
SCORE_PISO_5_MAS: int = 5          # piso ≥ 5

SCORE_AMENITIES: Dict[str, int] = {
    "pileta": 3,
    "sum": 2,
    "gimnasio": 2,
}

# Scoring por m² en escalones (solo se aplica el escalón más alto que aplique)
# Formato: lista de (umbral_m2, puntos) ordenada de mayor a menor
SCORE_M2_TIERS: list = [
    (60, 60),   # > 60m² → 60pts
    (55, 50),   # > 55m² → 50pts
    (50, 40),   # > 50m² → 40pts
    (45, 30),   # > 45m² → 30pts
    (40, 20),   # > 40m² → 20pts
    (35, 10),   # > 35m² → 10pts
]

# Scoring por expensas en escalones (solo aplica el rango que coincide)
# Formato: (rango_min_ars, rango_max_ars, puntos)  — ARS mensuales; negativo = penalización
SCORE_EXPENSAS_TIERS: list = [
    (10_000,         100_000,  15),   # muy bajas           → +15 pts
    (100_001,   130_000,  10),   # normales             → +10 pts
    (130_001,   160_000,   5),   # algo altas           →  +5 pts
    (160_001,   200_000,   0),   # altas (neutro)       →   0 pts
    (200_001, 9_999_999,  -5),   # muy altas (penaliza) →  −5 pts
]

# Filtros obligatorios (hard filters — si no se cumplen, la pub NO se guarda)
MUST_HAVE_BALCON: bool = True      # rechazar si se detecta explícitamente que no tiene
MUST_HAVE_BARRIO: bool = True      # rechazar si el barrio es conocido y no está en la lista

# Relación precio / m² (USD efectivo por m²)
USD_M2_EXCELENTE: float = 1_800.0   # por debajo → bonus máximo
USD_M2_BUENO: float = 2_200.0       # por debajo → bonus medio
SCORE_USD_M2_EXCELENTE: int = 10
SCORE_USD_M2_BUENO: int = 5


# ══════════════════════════════════════════════════════════════════════════════
# UMBRALES DE CLASIFICACIÓN
# ══════════════════════════════════════════════════════════════════════════════

SCORE_MINIMO_EXPORTAR: int = 70     # < 70 → se ignora
SCORE_MINIMO_ALERTA: int = 80       # ≥ 80 → alerta Telegram
SCORE_EXCELENTE: int = 90           # ≥ 90 → alerta urgente Telegram

CLASIFICACIONES: Dict[str, str] = {
    "Excelente": f"≥ {SCORE_EXCELENTE}",
    "Muy interesante": "80 – 89",
    "Revisar": "70 – 79",
    "Ignorar": "< 70",
}


# ══════════════════════════════════════════════════════════════════════════════
# VARIABLES DE ENTORNO
# ══════════════════════════════════════════════════════════════════════════════

GOOGLE_SHEETS_ID: str = os.getenv("GOOGLE_SHEETS_ID", "1FxQJU8iR_31B8b5Y0bdP0PAxbw7AEObVbengyEQ5Gfk")
GOOGLE_SERVICE_ACCOUNT_JSON: str = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")
DATABASE_PATH: str = os.getenv("DATABASE_PATH", "data/departamentos.db")


# ══════════════════════════════════════════════════════════════════════════════
# NLU — Lenguaje Natural  (requiere: pip install openai)
# ══════════════════════════════════════════════════════════════════════════════

OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")  # https://platform.openai.com/api-keys
NLU_MODEL: str = os.getenv("NLU_MODEL", "gpt-4o-mini")  # gpt-4o-mini es el más barato


# ══════════════════════════════════════════════════════════════════════════════
# HTTP / SCRAPING
# ══════════════════════════════════════════════════════════════════════════════

REQUEST_TIMEOUT: int = 30
REQUEST_RETRIES: int = 3
REQUEST_RETRY_DELAY: float = 5.0     # segundos entre reintentos (base)
DELAY_ENTRE_REQUESTS: float = 2.5    # pausa entre páginas al mismo dominio
DELAY_ENTRE_PAGINAS: float = 4.0

USER_AGENTS: List[str] = [
    (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
]


# ══════════════════════════════════════════════════════════════════════════════
# LOGGING
# ══════════════════════════════════════════════════════════════════════════════

LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE: str = os.getenv("LOG_FILE", "logs/scraper.log")
