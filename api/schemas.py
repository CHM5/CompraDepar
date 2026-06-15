"""
api/schemas.py
──────────────
Modelos Pydantic para request/response de la API.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class SearchRequest(BaseModel):
    query: str

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
