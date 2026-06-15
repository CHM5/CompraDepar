"""
services/user_config.py
────────────────────────
Configuración personalizada por usuario (chat_id de Telegram).

Almacena overrides sobre los defaults de config.py en data/user_configs.json.
Cada chat_id puede tener sus propios parámetros de búsqueda y scoring.

Uso:
    from services.user_config import get_user_cfg, set_val, reset_cfg, apply_to_module

    cfg = get_user_cfg(chat_id)          # config completa del usuario
    set_val(chat_id, "M2_MINIMO", 40)    # guardar un override
    apply_to_module(cfg)                 # aplicar al módulo config antes de scraping
    reset_cfg(chat_id)                   # volver a defaults
"""

from __future__ import annotations

import copy
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import config as _base

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path("data/user_configs.json")

# Claves editables por el usuario (subset seguro de config.py)
EDITABLE_KEYS = {
    "PRECIO_MIN_USD",
    "PRECIO_MAX_USD",
    "M2_MINIMO",
    "ANTIGUEDAD_MAXIMA",
    "PISO_MINIMO",
    "BARRIOS_OBJETIVO",
    "SCORE_MINIMO_EXPORTAR",
    "SCORE_MINIMO_ALERTA",
    "SCORE_BARRIOS",
    "SCORE_BALCON",
    "SCORE_COCHERA",
    "SCORE_METROS_45_MAS",
    "SCORE_PISO_5_MAS",
    "SCORE_ANTIGUEDAD_10_MENOS",
    "SCORE_AMENITIES",
    "DISPOSICION_EXCLUIR",
    "MUST_HAVE_BALCON",
    "MUST_HAVE_BARRIO",
    "SCORE_M2_TIERS",
    "SCORE_EXPENSAS_TIERS",
}

# Todos los barrios de CABA disponibles para agregar
ALL_BARRIOS_CABA: List[str] = [
    "Almagro", "Balvanera", "Barracas", "Barrio Norte", "Belgrano",
    "Boedo", "Caballito", "Chacarita", "Coghlan", "Colegiales",
    "Constitución", "Flores", "Floresta", "La Boca", "La Paternal",
    "Liniers", "Mataderos", "Monte Castro", "Montserrat", "Nueva Pompeya",
    "Núñez", "Palermo", "Parque Avellaneda", "Parque Chacabuco",
    "Parque Chas", "Parque Patricios", "Puerto Madero", "Recoleta",
    "Retiro", "Saavedra", "San Cristóbal", "San Nicolás", "San Telmo",
    "Vélez Sársfield", "Versalles", "Villa Crespo", "Villa del Parque",
    "Villa Devoto", "Villa General Mitre", "Villa Lugano", "Villa Luro",
    "Villa Ortúzar", "Villa Pueyrredón", "Villa Real", "Villa Riachuelo",
    "Villa Santa Rita", "Villa Soldati", "Villa Urquiza",
]


# ══════════════════════════════════════════════════════════════════════════════
# DEFAULTS
# ══════════════════════════════════════════════════════════════════════════════

def _defaults() -> dict:
    """Copia profunda de los valores por defecto de config.py."""
    return {
        "PRECIO_MIN_USD": _base.PRECIO_MIN_USD,
        "PRECIO_MAX_USD": _base.PRECIO_MAX_USD,
        "M2_MINIMO": float(_base.M2_MINIMO),
        "ANTIGUEDAD_MAXIMA": _base.ANTIGUEDAD_MAXIMA,
        "PISO_MINIMO": _base.PISO_MINIMO,
        "BARRIOS_OBJETIVO": list(_base.BARRIOS_OBJETIVO),
        "SCORE_MINIMO_EXPORTAR": _base.SCORE_MINIMO_EXPORTAR,
        "SCORE_MINIMO_ALERTA": _base.SCORE_MINIMO_ALERTA,
        "SCORE_BARRIOS": dict(_base.SCORE_BARRIOS),
        "SCORE_BALCON": _base.SCORE_BALCON,
        "SCORE_COCHERA": _base.SCORE_COCHERA,
        "SCORE_METROS_45_MAS": _base.SCORE_METROS_45_MAS,
        "SCORE_PISO_5_MAS": _base.SCORE_PISO_5_MAS,
        "SCORE_ANTIGUEDAD_10_MENOS": _base.SCORE_ANTIGUEDAD_10_MENOS,
        "SCORE_AMENITIES": dict(getattr(_base, 'SCORE_AMENITIES', {})),
        "DISPOSICION_EXCLUIR": list(_base.DISPOSICION_EXCLUIR),
        "MUST_HAVE_BALCON": getattr(_base, 'MUST_HAVE_BALCON', True),
        "MUST_HAVE_BARRIO": getattr(_base, 'MUST_HAVE_BARRIO', True),
        "SCORE_M2_TIERS": list(getattr(_base, 'SCORE_M2_TIERS', [(35, 10), (40, 20), (45, 30), (50, 40), (55, 50), (60, 60)])),
        "SCORE_EXPENSAS_TIERS": list(getattr(_base, 'SCORE_EXPENSAS_TIERS', [(10_000, 100_000, 15), (100_001, 130_000, 10), (130_001, 160_000, 5), (160_001, 200_000, 0), (200_001, 9_999_999, -5)])),
    }


# ══════════════════════════════════════════════════════════════════════════════
# PERSISTENCIA
# ══════════════════════════════════════════════════════════════════════════════

def _load_all() -> Dict[str, dict]:
    if _CONFIG_PATH.exists():
        try:
            return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("[UserConfig] Error leyendo %s: %s", _CONFIG_PATH, e)
    return {}


def _save_all(data: Dict[str, dict]) -> None:
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CONFIG_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ══════════════════════════════════════════════════════════════════════════════
# API PÚBLICA
# ══════════════════════════════════════════════════════════════════════════════

def get_user_cfg(chat_id: str) -> dict:
    """Retorna la config completa del usuario (defaults + sus overrides)."""
    all_cfgs = _load_all()
    overrides = all_cfgs.get(str(chat_id), {})
    merged = _defaults()
    for k, v in overrides.items():
        if k in EDITABLE_KEYS:
            merged[k] = copy.deepcopy(v)
    return merged


def set_val(chat_id: str, key: str, value: Any) -> None:
    """Guarda un valor de override para el usuario."""
    if key not in EDITABLE_KEYS:
        raise ValueError(f"Clave no editable: {key}")
    all_cfgs = _load_all()
    cid = str(chat_id)
    if cid not in all_cfgs:
        all_cfgs[cid] = {}
    all_cfgs[cid][key] = value
    _save_all(all_cfgs)
    logger.debug("[UserConfig] chat_id=%s → %s = %r", cid, key, value)


def reset_cfg(chat_id: str) -> None:
    """Elimina todos los overrides del usuario (vuelve a defaults de config.py)."""
    all_cfgs = _load_all()
    all_cfgs.pop(str(chat_id), None)
    _save_all(all_cfgs)


def apply_to_module(cfg: dict) -> None:
    """
    Aplica los valores de `cfg` al módulo config en tiempo de ejecución.
    Llamar ANTES de iniciar scrapers para que tomen los parámetros del usuario.
    Thread-safe siempre que no haya dos scrapes simultáneos (el bot ya lo previene).
    """
    import config as c
    for key, val in cfg.items():
        if hasattr(c, key):
            setattr(c, key, copy.deepcopy(val))
    logger.debug("[UserConfig] Config de módulo actualizada con %d parámetros.", len(cfg))


def get_all_users() -> List[str]:
    """Retorna lista de chat_ids que tienen config personalizada guardada."""
    return list(_load_all().keys())
