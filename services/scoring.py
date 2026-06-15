"""
services/scoring.py
────────────────────
Sistema de scoring configurable.
Calcula un puntaje numérico y una clasificación para cada publicación
basándose en los pesos definidos en config.py.

Puntuación máxima teórica: ~130 puntos
"""

from __future__ import annotations

import logging
from typing import Optional

import config
from database.models import Publicacion

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# SCORING SERVICE
# ══════════════════════════════════════════════════════════════════════════════


def calcular_score(pub: Publicacion) -> Publicacion:
    """Calcula y asigna score + clasificación a la publicación (in-place).

    Retorna la misma instancia modificada para facilitar encadenamiento.
    """
    score = 0.0
    detalle: list[str] = []

    # ── 1. Barrio ─────────────────────────────────────────────────────────────
    if pub.barrio:
        barrio_norm = pub.barrio.strip()
        pts = config.SCORE_BARRIOS.get(barrio_norm, 0)
        if pts:
            score += pts
            detalle.append(f"barrio:{barrio_norm}={pts}")

    # ── 2. Disposición ────────────────────────────────────────────────────────
    if pub.disposicion:
        disp_key = pub.disposicion.lower().strip()
        pts = config.SCORE_DISPOSICION.get(disp_key, 0)
        if pts:
            score += pts
            detalle.append(f"disposicion:{pub.disposicion}={pts}")

    # ── 3. Balcón ─────────────────────────────────────────────────────────────
    if pub.balcon:
        score += config.SCORE_BALCON
        detalle.append(f"balcon={config.SCORE_BALCON}")

    # ── 4. Metros cuadrados — scoring escalonado ──────────────────────────────
    m2_ref = pub.m2_totales or pub.m2_cubiertos
    if m2_ref:
        tiers = getattr(config, 'SCORE_M2_TIERS', [])
        if tiers:
            # Solo aplica el escalón más alto que califique
            for umbral, pts in sorted(tiers, key=lambda x: -x[0]):
                if m2_ref > umbral:
                    score += pts
                    detalle.append(f"m2>{umbral}={pts}")
                    break
        elif m2_ref >= 45:
            # Fallback al sistema anterior si no hay tiers configurados
            score += config.SCORE_METROS_45_MAS
            detalle.append(f"m2>=45={config.SCORE_METROS_45_MAS}")

    # ── 5. Antigüedad ≤ 10 años ───────────────────────────────────────────────
    if pub.antiguedad is not None and pub.antiguedad <= 10:
        score += config.SCORE_ANTIGUEDAD_10_MENOS
        detalle.append(f"antiguedad<={pub.antiguedad}a={config.SCORE_ANTIGUEDAD_10_MENOS}")

    # ── 6. Cochera ────────────────────────────────────────────────────────────
    if pub.cochera:
        score += config.SCORE_COCHERA
        detalle.append(f"cochera={config.SCORE_COCHERA}")

    # ── 7. Piso ≥ 5 ───────────────────────────────────────────────────────────
    if pub.piso is not None and pub.piso >= 5:
        score += config.SCORE_PISO_5_MAS
        detalle.append(f"piso{pub.piso}>={config.SCORE_PISO_5_MAS}")

    # ── 8. Amenities ─────────────────────────────────────────────────────────
    if pub.amenities:
        amenities_lower = pub.amenities.lower()
        for amenity, pts in config.SCORE_AMENITIES.items():
            if amenity in amenities_lower:
                score += pts
                detalle.append(f"{amenity}={pts}")

    # ── 9. Expensas — scoring escalonado ─────────────────────────────────────
    if pub.expensas is not None:
        exp_tiers = getattr(config, 'SCORE_EXPENSAS_TIERS', [])
        for (min_e, max_e, pts) in exp_tiers:
            if min_e <= pub.expensas <= max_e:
                if pts != 0:
                    score += pts
                    rango = f"{min_e//1000}k-{max_e//1000}k" if max_e < 9_999_999 else f">{min_e//1000}k"
                    detalle.append(f"expensas({rango})={pts:+}")
                break

    # ── 10. Relación precio / m² ──────────────────────────────────────────────
    if pub.usd_m2_efectivo:
        if pub.usd_m2_efectivo <= config.USD_M2_EXCELENTE:
            score += config.SCORE_USD_M2_EXCELENTE
            detalle.append(f"usdm2_excelente={config.SCORE_USD_M2_EXCELENTE}")
        elif pub.usd_m2_efectivo <= config.USD_M2_BUENO:
            score += config.SCORE_USD_M2_BUENO
            detalle.append(f"usdm2_bueno={config.SCORE_USD_M2_BUENO}")

    pub.score = round(score, 1)
    pub.clasificacion = clasificar(pub.score)

    logger.debug("[Score] %s/%s → %.1f (%s) | %s",
                 pub.portal, pub.id_publicacion, pub.score, pub.clasificacion,
                 ", ".join(detalle))

    return pub


def clasificar(score: float) -> str:
    """Retorna la clasificación textual según el score."""
    if score >= config.SCORE_EXCELENTE:
        return "Excelente"
    if score >= config.SCORE_MINIMO_ALERTA:
        return "Muy interesante"
    if score >= config.SCORE_MINIMO_EXPORTAR:
        return "Revisar"
    return "Ignorar"


def debe_exportar(pub: Publicacion) -> bool:
    """Retorna True si la publicación debe exportarse a Google Sheets."""
    return (pub.score or 0) >= config.SCORE_MINIMO_EXPORTAR


def debe_alertar(pub: Publicacion) -> bool:
    """Retorna True si se debe enviar alerta Telegram."""
    return (pub.score or 0) >= config.SCORE_MINIMO_ALERTA


def es_excelente(pub: Publicacion) -> bool:
    return (pub.score or 0) >= config.SCORE_EXCELENTE
