"""
services/nlp.py
───────────────
Capa de Lenguaje Natural (NLU) para el bot de Telegram.

Traduce mensajes de texto libre a intents estructurados (JSON)
mediante una llamada a la API de OpenAI (gpt-4o-mini por defecto).

Activar: agregar OPENAI_API_KEY en el .env
Modelo configurable: NLU_MODEL=gpt-4o-mini (default)

Si OPENAI_API_KEY no está configurada, is_enabled() devuelve False
y el bot continúa en modo solo-comandos sin error alguno.

Arquitectura del flujo:
  texto_usuario → translate() → intent_json
  intent_json   → intent_to_command(user_cfg) → "/comando args"
  "/comando"    → bot._route_single() → handler existente
"""

from __future__ import annotations

import json
import logging
from typing import Optional

import config

logger = logging.getLogger(__name__)

try:
    from openai import OpenAI as _OpenAI
    _OPENAI_AVAILABLE = True
except ImportError:
    _OPENAI_AVAILABLE = False
    logger.debug("[NLU] openai no instalado — NLU desactivado. "
                 "Activar con: pip install openai")


# ══════════════════════════════════════════════════════════════════════════════
# SYSTEM PROMPT
# ══════════════════════════════════════════════════════════════════════════════

_SYSTEM_PROMPT = """\
Sos un asistente que traduce mensajes de usuarios argentinos a intents JSON
para un sistema de búsqueda de departamentos en CABA (Buenos Aires).

REGLAS ESTRICTAS:
1. Respondé ÚNICAMENTE con JSON válido. Sin texto adicional, sin markdown.
2. Siempre incluir los campos "intent" y "params".
3. Si la solicitud no se puede mapear a ningún intent → {"intent":"unsupported","message":"<razón breve en español>"}
4. Si faltan parámetros obligatorios → {"intent":"clarify","missing":["campo_faltante"]}
5. Nunca inventar comandos fuera de la lista.
6. Nunca asumir valores numéricos no mencionados explícitamente; pedí aclaración.
7. Para "más que el resto" / "el mejor barrio" → mode = "max_plus".
8. Para "sin filtro" en un campo numérico → value = 0.
9. Usá los nombres de barrio con tildes correctas cuando corresponda.
10. "k" = miles (80k = 80000). "m²" o "metros" = metros cuadrados.

═══════════════════════════════════════════════════════════════
INTENTS DISPONIBLES
═══════════════════════════════════════════════════════════════

── CONSULTAS ──────────────────────────────────────────────────

{"intent":"top","params":{"count":<int 1-25>}}
  Ejemplos: "dame el top 10", "mostrame las 5 mejores", "las top 8"

{"intent":"barrio","params":{"nombre":"<barrio CABA>"}}
  Ejemplos: "qué hay en Palermo", "top de Belgrano", "lo mejor de Recoleta"

{"intent":"nuevas","params":{}}
  Ejemplos: "las más nuevas", "últimas detectadas", "recién entradas"

{"intent":"estado","params":{}}
  Ejemplos: "cómo está la base", "cuántas propiedades hay", "estado del sistema"

{"intent":"stats","params":{}}
  Ejemplos: "estadísticas por barrio", "promedios de precio/m²", "análisis por zona"

{"intent":"sheets","params":{}}
  Ejemplos: "la planilla", "link al excel", "abrir el Google Sheets"

{"intent":"config","params":{}}
  Ejemplos: "ver mi configuración", "qué filtros tengo activos"

── SCRAPING ───────────────────────────────────────────────────

{"intent":"scrape","params":{}}
  Ejemplos: "scrapear ahora", "actualizar datos", "buscar nuevas propiedades", "corré el bot"

── CONFIGURACIÓN DE BÚSQUEDA ──────────────────────────────────

{"intent":"set_precio","params":{"min":<int USD>,"max":<int USD>}}
  Ejemplos: "buscar entre 80k y 100k", "precio de 85000 a 105000 dólares"

{"intent":"set_m2","params":{"value":<float>}}
  Ejemplos: "mínimo 40m²", "departamentos de más de 45 metros", "al menos 35m²"

{"intent":"set_piso","params":{"value":<int>}}
  Ejemplos: "piso 3 o más", "desde el cuarto piso", "sin filtro de piso" → value=0

{"intent":"set_antiguedad","params":{"value":<int años>}}
  Ejemplos: "máximo 15 años de antigüedad", "hasta 10 años", "sin filtro antigüedad" → value=0

{"intent":"set_umbral","params":{"value":<int 0-130>}}
  Ejemplos: "exportar los de más de 75 puntos", "umbral en 80", "score mínimo 65"

{"intent":"set_must_balcon","params":{"value":<bool>}}
  Ejemplos: "siempre con balcón" → true, "no me importa el balcón" → false

{"intent":"set_must_barrio","params":{"value":<bool>}}
  Ejemplos: "solo en mis barrios" → true, "cualquier barrio" → false

{"intent":"reset","params":{}}
  Ejemplos: "volver a los defaults", "resetear todo", "configuración original"

── BARRIOS ────────────────────────────────────────────────────

{"intent":"barrios_add","params":{"nombre":"<barrio CABA>"}}
  Ejemplos: "agregar Flores", "incluir Boedo", "también quiero ver Recoleta"

{"intent":"barrios_remove","params":{"nombre":"<barrio CABA>"}}
  Ejemplos: "sacar Saavedra", "quitar Coghlan de la lista"

{"intent":"remove_filter","params":{"field":"<antiguedad|piso>"}}
  Ejemplos: "sacar el filtro de antigüedad", "quitar la restricción de piso"

── SCORING / PONDERACIÓN ──────────────────────────────────────

{"intent":"scoring_barrio","params":{"barrio":"<barrio>","value":<int 0-200>}}
  Ejemplos: "que Palermo valga 60 puntos", "Belgrano = 55pts"

{"intent":"set_weight","params":{"barrio":"<barrio>","mode":"<absolute|max_plus>","value":<int>}}
  Ejemplos: "ponderame Belgrano más que el resto" → mode=max_plus, value=<delta sobre el max>
            "que Palermo valga 70 puntos" → mode=absolute, value=70
  NOTA: si el usuario no especifica un número de delta con mode=max_plus → clarify "delta"

{"intent":"scoring_simple","params":{"field":"<balcon|cochera|piso|antiguedad>","value":<int 0-100>}}
  Ejemplos: "que el balcón valga 20 puntos", "cochera suma 10", "dale 15 al balcón"

{"intent":"scoring_amenity","params":{"amenity":"<pileta|sum|gimnasio|...>","value":<int 0-50>}}
  Ejemplos: "que la pileta valga 5 puntos", "SUM suma 3 pts", "ponele 4 al gimnasio"

{"intent":"scoring_amenity_remove","params":{"amenity":"<amenity>"}}
  Ejemplos: "sacar pileta del scoring", "quitar gimnasio de la ponderación"

═══════════════════════════════════════════════════════════════
REFERENCIAS
═══════════════════════════════════════════════════════════════

BARRIOS CABA: Palermo, Belgrano, Villa Crespo, Almagro, Núñez, Saavedra, Caballito,
Recoleta, Barrio Norte, Chacarita, Coghlan, Villa Urquiza, Colegiales, Flores, Boedo,
San Telmo, Puerto Madero, y demás barrios de CABA.

CAMPOS SCORING: balcon, cochera, piso, antiguedad
AMENITIES COMUNES: pileta, sum, gimnasio, solarium, laundry, quincho, coworking
"""


# ══════════════════════════════════════════════════════════════════════════════
# API PÚBLICA
# ══════════════════════════════════════════════════════════════════════════════

def is_enabled() -> bool:
    """Retorna True si NLU está activo (openai instalado + API key configurada)."""
    return _OPENAI_AVAILABLE and bool(getattr(config, "OPENAI_API_KEY", ""))


def translate(message: str, user_cfg: dict | None = None) -> dict:
    """Traduce un mensaje de texto libre a un intent JSON.

    Retorna dict con:
      {"intent": "...", "params": {...}}           → comando a ejecutar
      {"intent": "clarify", "missing": [...]}      → faltan datos
      {"intent": "unsupported", "message": "..."}  → no disponible
      {"intent": "error", "message": "..."}        → fallo técnico
    """
    if not is_enabled():
        return {"intent": "error", "message": "NLU no configurado (falta OPENAI_API_KEY)."}

    try:
        client = _OpenAI(api_key=config.OPENAI_API_KEY)
        model = getattr(config, "NLU_MODEL", "gpt-4o-mini")

        # Contexto del usuario para ayudar al modelo a resolver referencias relativas
        context_parts: list[str] = []
        if user_cfg:
            barrios = user_cfg.get("BARRIOS_OBJETIVO", [])
            if barrios:
                context_parts.append(f"Barrios activos: {', '.join(barrios)}")
            sb = user_cfg.get("SCORE_BARRIOS", {})
            if sb:
                max_barrio = max(sb, key=lambda k: sb[k])
                context_parts.append(
                    f"Barrio con mayor peso actual: {max_barrio} ({sb[max_barrio]} pts)"
                )
            context_parts.append(
                f"Precio activo: USD {user_cfg.get('PRECIO_MIN_USD', 80000):,} – "
                f"{user_cfg.get('PRECIO_MAX_USD', 105000):,}"
            )

        user_content = message
        if context_parts:
            user_content = (
                f"[Contexto del usuario: {' | '.join(context_parts)}]\n\n"
                f"Mensaje: {message}"
            )

        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": user_content},
            ],
            temperature=0,
            max_tokens=256,
            response_format={"type": "json_object"},
        )

        raw = resp.choices[0].message.content or ""
        result = json.loads(raw)

        if "intent" not in result:
            logger.warning("[NLU] Respuesta sin campo 'intent': %s", raw[:200])
            return {"intent": "error", "message": "Respuesta inesperada del modelo."}

        logger.info("[NLU] «%s» → intent=%s params=%s",
                    message[:60], result.get("intent"), result.get("params", {}))
        return result

    except json.JSONDecodeError as e:
        logger.error("[NLU] JSON inválido del modelo: %s", e)
        return {"intent": "error", "message": "Respuesta del modelo no era JSON válido."}
    except Exception as e:
        logger.error("[NLU] Error en llamada al LLM: %s", e)
        return {"intent": "error", "message": str(e)[:120]}


def intent_to_command(result: dict, user_cfg: dict | None = None) -> Optional[str]:
    """Convierte un intent JSON al string de /comando correspondiente.

    Retorna el string listo para pasarle a _route_single(), o None si no hay mapeo.
    """
    intent = result.get("intent", "")
    params: dict = result.get("params") or {}

    try:
        # ── Consultas simples ─────────────────────────────────────────────────
        if intent == "top":
            count = max(1, min(int(params.get("count", 10)), 25))
            return f"/top {count}"

        if intent == "barrio":
            nombre = str(params.get("nombre", "")).strip()
            return f"/barrio {nombre}" if nombre else None

        if intent in ("nuevas", "estado", "stats", "sheets", "scrape", "config", "reset"):
            return f"/{intent}"

        # ── Config de búsqueda ────────────────────────────────────────────────
        if intent == "set_precio":
            min_p = int(params["min"])
            max_p = int(params["max"])
            return f"/set precio {min_p} {max_p}"

        if intent == "set_m2":
            return f"/set m2 {float(params['value']):.0f}"

        if intent == "set_piso":
            return f"/set piso {int(params['value'])}"

        if intent == "set_antiguedad":
            return f"/set antiguedad {int(params['value'])}"

        if intent == "set_umbral":
            return f"/set umbral {int(params['value'])}"

        if intent == "set_must_balcon":
            v = "si" if params.get("value") else "no"
            return f"/set must balcon {v}"

        if intent == "set_must_barrio":
            v = "si" if params.get("value") else "no"
            return f"/set must barrio {v}"

        # ── Barrios ───────────────────────────────────────────────────────────
        if intent == "barrios_add":
            nombre = str(params.get("nombre", "")).strip()
            return f"/barrios + {nombre}" if nombre else None

        if intent == "barrios_remove":
            nombre = str(params.get("nombre", "")).strip()
            return f"/barrios - {nombre}" if nombre else None

        if intent == "remove_filter":
            field = str(params.get("field", "")).strip().lower()
            if field in ("antiguedad", "antigüedad"):
                return "/set antiguedad 0"
            if field == "piso":
                return "/set piso 0"
            return None

        # ── Scoring / Ponderación ─────────────────────────────────────────────
        if intent == "scoring_barrio":
            barrio = str(params.get("barrio", "")).strip()
            value  = int(params.get("value", 0))
            return f"/scoring barrio {barrio} {value}" if barrio else None

        if intent == "set_weight":
            barrio = str(params.get("barrio", "")).strip()
            value  = params.get("value")
            mode   = str(params.get("mode", "absolute")).lower()
            if mode == "max_plus":
                sb      = (user_cfg or {}).get("SCORE_BARRIOS", {})
                max_val = max(sb.values()) if sb else 50
                value   = max_val + int(value or 10)
            if barrio and value is not None:
                return f"/scoring barrio {barrio} {int(value)}"
            return None

        if intent == "scoring_simple":
            field = str(params.get("field", "")).strip().lower()
            value = int(params.get("value", 0))
            return f"/scoring {field} {value}" if field else None

        if intent == "scoring_amenity":
            amenity = str(params.get("amenity", "")).strip().lower()
            value   = int(params.get("value", 0))
            return f"/scoring amenity {amenity} {value}" if amenity else None

        if intent == "scoring_amenity_remove":
            amenity = str(params.get("amenity", "")).strip().lower()
            return f"/scoring amenity quitar {amenity}" if amenity else None

    except (KeyError, ValueError, TypeError) as e:
        logger.warning("[NLU] intent_to_command error en '%s': %s", intent, e)

    return None
