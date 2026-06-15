"""
database/models.py
──────────────────
Modelo de datos central para publicaciones inmobiliarias.
Usa dataclasses puras para mantener independencia del ORM.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Publicacion:
    """Representa una publicación inmobiliaria con todos sus atributos."""

    # ── Identificadores obligatorios ──────────────────────────────────────────
    id_publicacion: str
    portal: str          # "Zonaprop" | "Argenprop"
    url: str
    operacion: str = "venta"  # "venta" | "alquiler"

    # ── Datos del inmueble ────────────────────────────────────────────────────
    inmobiliaria: Optional[str] = None
    direccion: Optional[str] = None
    barrio: Optional[str] = None
    ambientes: Optional[int] = None
    m2_cubiertos: Optional[float] = None
    m2_descubiertos: Optional[float] = None
    m2_totales: Optional[float] = None
    precio_usd: Optional[float] = None
    expensas: Optional[float] = None
    antiguedad: Optional[int] = None
    piso: Optional[int] = None
    disposicion: Optional[str] = None
    orientacion: Optional[str] = None
    balcon: bool = False
    cochera: bool = False
    amenities: Optional[str] = None
    descripcion: Optional[str] = None
    fecha_publicacion: Optional[str] = None

    # ── Scoring y análisis (calculados en services/) ──────────────────────────
    score: Optional[float] = None
    clasificacion: Optional[str] = None
    pros: Optional[str] = None
    contras: Optional[str] = None
    usd_m2_efectivo: Optional[float] = None

    # ── Estado y tracking ─────────────────────────────────────────────────────
    estado: str = "NUEVA"
    precio_anterior: Optional[float] = None
    variacion_porcentual: Optional[float] = None
    fecha_deteccion: Optional[str] = None
    ultima_actualizacion: Optional[str] = None
    comentarios: Optional[str] = None

    def __post_init__(self) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        if not self.fecha_deteccion:
            self.fecha_deteccion = now
        if not self.ultima_actualizacion:
            self.ultima_actualizacion = now

        self._calcular_m2_totales()
        self._calcular_usd_m2()

    # ── Helpers internos ──────────────────────────────────────────────────────

    def _calcular_m2_totales(self) -> None:
        """Si m2_totales no viene informado lo calcula sumando cubiertos + descubiertos."""
        if self.m2_totales is None and self.m2_cubiertos:
            descubiertos = self.m2_descubiertos or 0.0
            self.m2_totales = round(self.m2_cubiertos + descubiertos, 2)

    def _calcular_usd_m2(self) -> None:
        """Calcula USD efectivo por m² ponderando descubiertos al 50%.

        Fórmula: precio_usd / (m2_cubiertos + m2_descubiertos / 2)
        """
        if self.precio_usd and self.m2_cubiertos:
            descubiertos = self.m2_descubiertos or 0.0
            denominador = self.m2_cubiertos + (descubiertos / 2.0)
            if denominador > 0:
                self.usd_m2_efectivo = round(self.precio_usd / denominador, 2)

    # ── Representación ────────────────────────────────────────────────────────

    @property
    def dias_en_pagina(self) -> int:
        """Días que lleva la publicación siendo seguida desde su primera detección."""
        if not self.fecha_deteccion:
            return 0
        try:
            from datetime import date as _date
            detected = datetime.fromisoformat(self.fecha_deteccion).date()
            return max(0, (_date.today() - detected).days)
        except (ValueError, TypeError):
            return 0

    def resumen(self) -> str:
        partes = [
            f"[{self.portal}] {self.barrio or 'Barrio desconocido'}",
            f"  Precio : USD {self.precio_usd:,.0f}" if self.precio_usd else "",
            f"  m²     : {self.m2_totales} (cub. {self.m2_cubiertos})",
            f"  Piso   : {self.piso} | Disp.: {self.disposicion}",
            f"  Score  : {self.score} ({self.clasificacion})",
            f"  URL    : {self.url}",
        ]
        return "\n".join(p for p in partes if p)
