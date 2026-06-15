"""
services/analyzer.py
─────────────────────
Generador automático de PROS y CONTRAS.
Analiza los atributos de cada publicación y produce listas legibles
para mostrar en Google Sheets y alertas Telegram.
"""

from __future__ import annotations

import logging
from typing import List, Tuple

import config
from database.models import Publicacion

logger = logging.getLogger(__name__)

# ─── Umbrales para análisis ───────────────────────────────────────────────────
EXPENSAS_ALTA: float = 120_000     # ARS
USD_M2_ALTO: float = 2_800.0      # USD/m²


# ══════════════════════════════════════════════════════════════════════════════
# ANALIZADOR
# ══════════════════════════════════════════════════════════════════════════════


def analizar(pub: Publicacion) -> Publicacion:
    """Genera y asigna pros y contras a la publicación (in-place).

    Retorna la misma instancia para facilitar encadenamiento.
    """
    pros, contras = _generar_pros_contras(pub)
    pub.pros = "\n".join(f"• {p}" for p in pros) if pros else None
    pub.contras = "\n".join(f"• {c}" for c in contras) if contras else None

    logger.debug("[Analyzer] %s/%s → %d pros, %d contras",
                 pub.portal, pub.id_publicacion, len(pros), len(contras))
    return pub


def _generar_pros_contras(pub: Publicacion) -> Tuple[List[str], List[str]]:
    pros: List[str] = []
    contras: List[str] = []

    # ── Barrio ────────────────────────────────────────────────────────────────
    if pub.barrio:
        if pub.barrio in ("Palermo", "Belgrano"):
            pros.append(f"Barrio premium: {pub.barrio}")
        elif pub.barrio in config.BARRIOS_OBJETIVO:
            pros.append(f"Barrio objetivo: {pub.barrio}")
        else:
            contras.append(f"Barrio fuera de prioridad: {pub.barrio}")

    # ── Disposición ──────────────────────────────────────────────────────────
    if pub.disposicion:
        disp = pub.disposicion.lower()
        if "frente" in disp and "contra" not in disp:
            pros.append("Frente (máxima luminosidad)")
        elif "contrafrente" in disp:
            pros.append("Contrafrente (tranquilo y luminoso)")
        elif "interno" in disp:
            contras.append("Interno (poca luz natural)")
        elif "lateral" in disp:
            contras.append("Lateral")

    # ── Balcón ────────────────────────────────────────────────────────────────
    if pub.balcon:
        pros.append("Tiene balcón")
    # No agregar contra si no tiene balcón (es común)

    # ── Cochera ───────────────────────────────────────────────────────────────
    if pub.cochera:
        pros.append("Cochera incluida (+valor de reventa)")

    # ── Superficie ───────────────────────────────────────────────────────────
    m2_ref = pub.m2_totales or pub.m2_cubiertos
    if m2_ref:
        if m2_ref >= 55:
            pros.append(f"Amplio: {m2_ref:.0f} m²")
        elif m2_ref >= 45:
            pros.append(f"Buenos metros: {m2_ref:.0f} m²")
        elif m2_ref < 40:
            contras.append(f"Pocos metros: {m2_ref:.0f} m²")

    # ── Antigüedad ────────────────────────────────────────────────────────────
    if pub.antiguedad is not None:
        if pub.antiguedad == 0:
            pros.append("A estrenar")
        elif pub.antiguedad <= 5:
            pros.append(f"Edificio muy moderno ({pub.antiguedad} años)")
        elif pub.antiguedad <= 10:
            pros.append(f"Edificio moderno ({pub.antiguedad} años)")
        elif pub.antiguedad <= 15:
            pass  # neutro
        else:
            contras.append(f"Antigüedad elevada: {pub.antiguedad} años")

    # ── Piso ─────────────────────────────────────────────────────────────────
    if pub.piso is not None:
        if pub.piso >= 7:
            pros.append(f"Piso alto ({pub.piso}°) — vistas y luminosidad")
        elif pub.piso >= 5:
            pros.append(f"Buen piso ({pub.piso}°)")
        elif pub.piso == 2:
            contras.append(f"Piso bajo ({pub.piso}°)")

    # ── Orientación ───────────────────────────────────────────────────────────
    if pub.orientacion:
        ori = pub.orientacion.lower()
        if "norte" in ori or "noreste" in ori or "noroeste" in ori:
            pros.append(f"Orientación {pub.orientacion} (soleado)")
        elif "sur" in ori:
            contras.append(f"Orientación {pub.orientacion} (menos sol)")

    # ── Relación precio/m² ───────────────────────────────────────────────────
    if pub.usd_m2_efectivo:
        if pub.usd_m2_efectivo <= config.USD_M2_EXCELENTE:
            pros.append(f"Excelente relación USD/m² ({pub.usd_m2_efectivo:,.0f} USD/m²)")
        elif pub.usd_m2_efectivo <= config.USD_M2_BUENO:
            pros.append(f"Buena relación USD/m² ({pub.usd_m2_efectivo:,.0f} USD/m²)")
        elif pub.usd_m2_efectivo > USD_M2_ALTO:
            contras.append(f"USD/m² elevado: {pub.usd_m2_efectivo:,.0f}")

    # ── Amenities ─────────────────────────────────────────────────────────────
    if pub.amenities:
        amenities_lower = pub.amenities.lower()
        highlights = []
        if "pileta" in amenities_lower or "piscina" in amenities_lower:
            highlights.append("pileta")
        if "sum" in amenities_lower:
            highlights.append("SUM")
        if "gimnasio" in amenities_lower or "gym" in amenities_lower:
            highlights.append("gimnasio")
        if highlights:
            pros.append("Amenities: " + ", ".join(highlights))

    # ── Expensas ──────────────────────────────────────────────────────────────
    if pub.expensas:
        if pub.expensas > EXPENSAS_ALTA:
            contras.append(f"Expensas altas: ${pub.expensas:,.0f}")

    # ── Precio ────────────────────────────────────────────────────────────────
    if pub.precio_usd:
        if pub.precio_usd <= 85_000:
            pros.append(f"Precio en el límite inferior (USD {pub.precio_usd:,.0f})")
        elif pub.precio_usd >= 100_000:
            contras.append(f"Precio en el límite superior (USD {pub.precio_usd:,.0f})")

    # ── Cambio de precio ──────────────────────────────────────────────────────
    if pub.estado == "BAJA_PRECIO" and pub.variacion_porcentual:
        pros.append(f"Bajó de precio: {pub.variacion_porcentual:.1f}% "
                    f"(antes USD {pub.precio_anterior:,.0f})")
    elif pub.estado == "SUBA_PRECIO" and pub.variacion_porcentual:
        contras.append(f"Subió de precio: +{pub.variacion_porcentual:.1f}%")

    return pros, contras
