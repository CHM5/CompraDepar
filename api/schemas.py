"""
api/schemas.py
──────────────
Modelos Pydantic para request/response de la API.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class ExtraFilters(BaseModel):
    """Filtros adicionales enviados desde el panel de refinamiento del frontend.
    Cuando está presente, la búsqueda es solo contra la DB (sin scraping).
    """
    barrios: Optional[list[str]] = None
    operacion: Optional[str] = None
    precio_min: Optional[int] = None
    precio_max: Optional[int] = None
    m2_min: Optional[int] = None
    m2_max: Optional[int] = None
    ambientes_min: Optional[int] = None
    ambientes_max: Optional[int] = None
    balcon: Optional[bool] = None
    terraza: Optional[bool] = None
    cochera: Optional[bool] = None
    antiguedad_max: Optional[int] = None
    expensas_max: Optional[int] = None


class SearchRequest(BaseModel):
    query: str
    extra_filters: Optional[ExtraFilters] = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "query": "quiero comprar un departamento en Belgrano desde 40m2 entre 80000 y 130000 dólares"
                }
            ]
        }
    }


class PropertyResult(BaseModel):
    ranking: int
    portal: str
    barrio: Optional[str] = None
    direccion: Optional[str] = None
    precio_usd: Optional[float] = None
    expensas: Optional[float] = None
    m2_totales: Optional[float] = None
    m2_cubiertos: Optional[float] = None
    ambientes: Optional[int] = None
    score: Optional[float] = None
    clasificacion: Optional[str] = None
    balcon: bool = False
    cochera: bool = False
    url: str
    estado: str = "NUEVA"
    imagen_url: Optional[str] = None


class SearchResponse(BaseModel):
    success: bool
    plan: str
    total: int
    truncated: bool
    results: list[PropertyResult]
    filters_applied: dict
    intent: Optional[str] = None
    message: Optional[str] = None


class ChatRequest(BaseModel):
    query: str


class ChatResponse(BaseModel):
    message: str
