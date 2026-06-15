"""
api/main.py
───────────
Punto de entrada de la API REST.

Ejecutar (dev):
    cd /home/hernie/Desktop/AutomatizacionCompraDepar
    .venv/bin/uvicorn api.main:app --reload --port 8000

Endpoints:
    GET  /health
    POST /api/v1/search    Headers: X-User-Plan: free | premium

Documentación interactiva: http://localhost:8000/docs
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# ── Asegura que el root del proyecto esté en el path ─────────────────────────
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.schemas import PropertyResult, SearchRequest, SearchResponse, ChatRequest, ChatResponse, ExtraFilters
from api.services.query_parser import parse_query
from api.services import search_service
from api.services import chat_service
from shared.filters import SearchFilters
from shared.intent import Intent, INTENT_MESSAGES, detect_intent

logger = logging.getLogger(__name__)

FREE_LIMIT = 20


def _non_search_response(plan: str, intent: Intent) -> SearchResponse:
    """Retorna una respuesta válida con 0 resultados para intenciones no-SEARCH."""
    return SearchResponse(
        success=False,
        plan=plan,
        total=0,
        truncated=False,
        results=[],
        filters_applied={},
        intent=intent.value,
        message=INTENT_MESSAGES[intent],
    )

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Depar API",
    description=(
        "API de búsqueda de departamentos en Buenos Aires.\n\n"
        "Enviar el header **X-User-Plan: free** (máx 5 resultados) "
        "o **X-User-Plan: premium** (sin límite)."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Endpoints ─────────────────────────────────────────────────────────────────


@app.get("/health", tags=["meta"])
def health() -> dict:
    """Verificación de vida del servicio."""
    return {"status": "ok"}


@app.post(
    "/api/v1/search",
    response_model=SearchResponse,
    tags=["búsqueda"],
    summary="Buscar departamentos por lenguaje natural",
)
def search(
    body: SearchRequest,
    x_user_plan: Optional[str] = Header(
        default=None,
        description="Plan del usuario: **free** (máx 5) o **premium** (ilimitado)",
    ),
) -> SearchResponse:
    """
    Recibe una query en lenguaje natural, la parsea con regex y devuelve
    los departamentos que coinciden ordenados por score descendente.

    Ejemplos de query:
    - `"quiero comprar en Belgrano, máximo 105000 dólares, al menos 40m2"`
    - `"departamento 2 ambientes en Palermo o Colegiales hasta 130k"`
    - `"busco en Almagro desde 35m2 entre 80000 y 100000 usd"`
    """
    # ── Validar plan ──────────────────────────────────────────────────────────
    if not x_user_plan:
        raise HTTPException(
            status_code=401,
            detail="Header X-User-Plan requerido. Valores aceptados: free | premium",
        )

    plan = x_user_plan.strip().lower()
    if plan not in ("free", "premium"):
        raise HTTPException(
            status_code=400,
            detail=f"Plan '{plan}' inválido. Valores aceptados: free | premium",
        )

    # ── Clasificar intención ──────────────────────────────────────────────
    intent = detect_intent(body.query)
    logger.info("[API] intent=%s | plan=%s | query=%r", intent.value, plan, body.query)

    # Pregunta analítica sobre el mercado → GPT-4o-mini con stats de la DB
    if intent == Intent.AI_CHAT:
        ai_message = chat_service.chat(body.query)
        return SearchResponse(
            success=True, plan=plan, total=0, truncated=False,
            results=[], filters_applied={},
            intent=intent.value, message=ai_message,
        )

    if intent != Intent.SEARCH:
        return _non_search_response(plan, intent)

    # ── Parsear query ──────────────────────────────────────────────────
    filters: SearchFilters = parse_query(body.query)

    # Cuando el frontend envía extra_filters, fusionarlos y omitir el scraping
    skip_scraping = False
    if body.extra_filters:
        skip_scraping = True
        ef: ExtraFilters = body.extra_filters
        for fname in (
            "operacion", "precio_min", "precio_max",
            "m2_min", "m2_max", "ambientes_min", "ambientes_max",
            "balcon", "cochera", "antiguedad_max", "expensas_max",
        ):
            val = getattr(ef, fname, None)
            if val is not None:
                setattr(filters, fname, val)

    if not filters.has_meaningful_criteria():
        logger.info("[API] Sin criterios significativos — no ejecutar búsqueda.")
        return SearchResponse(
            success=False,
            plan=plan,
            total=0,
            truncated=False,
            results=[],
            filters_applied=filters.model_dump(),
            intent=Intent.SEARCH.value,
            message="Necesito más información para buscar propiedades. Indicá barrio, precio o superficie.",
        )

    logger.info("[API] filters=%r", filters)

    # ── Buscar (cache-first + scraping dinámico si cache expirada) ───────────
    all_results = search_service.search(
        filters,
        early_exit=FREE_LIMIT if plan == "free" else None,
        skip_scraping=skip_scraping,
    )

    # ── Aplicar límite según plan ─────────────────────────────────────────────
    limit = FREE_LIMIT if plan == "free" else None
    truncated = limit is not None and len(all_results) > limit
    page = all_results[:limit] if limit is not None else all_results

    # ── Construir respuesta ───────────────────────────────────────────────────
    results = [
        PropertyResult(
            ranking=i + 1,
            portal=r.get("portal", ""),
            barrio=r.get("barrio"),
            direccion=r.get("direccion"),
            precio_usd=r.get("precio_usd"),
            expensas=r.get("expensas"),
            m2_totales=r.get("m2_totales"),
            m2_cubiertos=r.get("m2_cubiertos"),
            ambientes=r.get("ambientes"),
            score=r.get("score"),
            clasificacion=r.get("clasificacion"),
            balcon=bool(r.get("balcon", 0)),
            cochera=bool(r.get("cochera", 0)),
            url=r.get("url", ""),
            estado=r.get("estado", "NUEVA"),
            imagen_url=r.get("imagen_url"),
        )
        for i, r in enumerate(page)
    ]

    return SearchResponse(
        success=True,
        plan=plan,
        total=len(all_results),
        truncated=truncated,
        results=results,
        filters_applied=filters.model_dump(),
        intent=Intent.SEARCH.value,
    )


@app.post(
    "/api/v1/chat",
    response_model=ChatResponse,
    tags=["chat"],
    summary="Chat con IA sobre el mercado inmobiliario",
)
def chat(
    body: ChatRequest,
    x_user_plan: Optional[str] = Header(default=None),
) -> ChatResponse:
    """
    Responde preguntas en lenguaje natural sobre el mercado inmobiliario
    de CABA usando GPT-4o-mini con datos en tiempo real de la base de datos.
    """
    message = chat_service.chat(body.query)
    return ChatResponse(message=message)
