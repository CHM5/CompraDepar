"""
shared/filters.py
─────────────────
Modelo de filtros de búsqueda compartido entre parser, scrapers, API y caché.

No depende de config.py ni de ningún portal específico.
"""

from __future__ import annotations

import hashlib
import json
from typing import Optional


try:
    from pydantic import BaseModel
except ImportError:  # fallback minimal implementation without pydantic
    class BaseModel:  # type: ignore
        def __init__(self, **data):
            for k, v in data.items():
                setattr(self, k, v)


class SearchFilters(BaseModel):
    """
    Filtros de búsqueda derivados exclusivamente de la consulta del usuario.

    Reglas:
    - Sin listas de barrios válidos predefinidas.
    - Sin valores por defecto de config.py.
    - Cualquier barrio de CABA es aceptable.
    - Los scrapers construyen sus URLs a partir de esta estructura.
    """

    operacion: str = "venta"
    tipo: str = "departamento"

    # Ubicación — lista vacía = toda CABA
    barrios: list[str] = []

    # Rango de precio en USD
    precio_min: Optional[int] = None
    precio_max: Optional[int] = None

    # Superficie
    m2_min: Optional[int] = None
    m2_max: Optional[int] = None

    # Habitaciones
    ambientes_min: Optional[int] = None
    ambientes_max: Optional[int] = None

    # Características
    balcon: Optional[bool] = None
    cochera: Optional[bool] = None

    # Antigüedad máxima en años
    antiguedad_max: Optional[int] = None

    def has_meaningful_criteria(self) -> bool:
        """Retorna True si la búsqueda tiene al menos un criterio significativo.

        `operacion` y `tipo` siempre tienen valores por defecto y no cuentan.
        Se necesita al menos uno de: barrio, precio, superficie, ambientes o
        característica explícita para que la búsqueda sea válida.
        """
        return bool(
            self.barrios
            or self.precio_min is not None
            or self.precio_max is not None
            or self.m2_min is not None
            or self.m2_max is not None
            or self.ambientes_min is not None
            or self.balcon is not None
            or self.cochera is not None
        )

    def filters_hash(self) -> str:
        """Hash MD5 estable para uso como clave de caché."""
        key = {
            "op": self.operacion,
            "tipo": self.tipo,
            "barrios": sorted(self.barrios),
            "pmin": self.precio_min,
            "pmax": self.precio_max,
            "m2min": self.m2_min,
            "m2max": self.m2_max,
            "ambmin": self.ambientes_min,
            "ambmax": self.ambientes_max,
            "balcon": self.balcon,
        }
        return hashlib.md5(
            json.dumps(key, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()

    def __repr__(self) -> str:
        parts = [f"op={self.operacion}"]
        if self.barrios:
            parts.append(f"barrios={self.barrios}")
        if self.precio_max:
            parts.append(f"≤USD{self.precio_max:,}")
        if self.m2_min:
            parts.append(f"≥{self.m2_min}m²")
        if self.balcon:
            parts.append("balcon")
        return f"SearchFilters({', '.join(parts)})"
