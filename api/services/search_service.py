"""
api/services/search_service.py
───────────────────────────────
Capa de búsqueda con flujo cache-first + scraping dinámico.

Flujo:
  1. parse_query()  →  SearchFilters
  2. cache lookup  (TTL = 24 h)
  3. ¿datos frescos?
     ├── Sí  →  consultar DB
     └── No  →  ejecutar scrapers + guardar + marcar caché
  4. devolver resultados

Reglas:
  - Sin fallback automático de barrio.
  - Sin substitución de intención.
  - Sin resultados = respuesta válida (total=0, results=[]).
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from database import db
from services import scoring, analyzer
from shared.filters import SearchFilters

logger = logging.getLogger(__name__)

# TTL re-exportado para conveniencia (el valor real vive en db.py)
CACHE_TTL_HOURS = db.CACHE_TTL_HOURS


def search(
    filters: SearchFilters,
    early_exit: Optional[int] = None,
    skip_scraping: bool = False,
) -> list[dict]:
    """Punto de entrada principal.

    Retorna lista de dicts ordenados por score DESC.
    early_exit: si se indica (plan free), scraping de 1 página por portal en paralelo.
    skip_scraping: cuando el frontend envía extra_filters, solo consulta la DB.
    """
    if skip_scraping:
        logger.info("[search_service] Refinamiento: DB-only, sin scraping.")
        return _query_db(filters)

    fhash = filters.filters_hash()
    barrios_str = ",".join(filters.barrios)

    if early_exit is not None:
        # Plan free: si ya existe caché completa (premium), la reutilizamos
        if db.has_fresh_results(fhash):
            logger.info("[search_service] Free plan: caché completa disponible, sin scraping.")
            return _query_db(filters)
        # Clave separada para scraping parcial
        partial_key = fhash + "_partial"
        if not db.has_fresh_results(partial_key):
            logger.info("[search_service] Free plan: scraping parcial (todos los portales, 1 página).")
            saved = _run_scrapers(filters, early_exit=early_exit)
            if saved > 0:
                db.mark_search_done(partial_key, barrios=barrios_str,
                                    precio_max=filters.precio_max, m2_min=filters.m2_min)
        else:
            logger.info("[search_service] Free plan: caché parcial vigente — usando DB.")
    else:
        # Plan premium: scraping completo si no hay caché fresca
        if not db.has_fresh_results(fhash):
            logger.info("[search_service] Premium: caché expirada — scraping completo. %r", filters)
            _run_scrapers(filters)
            db.mark_search_done(fhash, barrios=barrios_str,
                                precio_max=filters.precio_max, m2_min=filters.m2_min)
        else:
            logger.info("[search_service] Premium: caché vigente — usando DB. %r", filters)

    return _query_db(filters)


def _collect_from_scraper(scraper_class, filters: SearchFilters, max_pages: int) -> list:
    """Ejecuta un scraper en su propio hilo y retorna la lista de publicaciones."""
    try:
        s = scraper_class()
        s._max_pages = max_pages
        return s.scrape(filters)
    except Exception as e:
        logger.error("[search_service] Error en scraper %s: %s", scraper_class.__name__, e, exc_info=True)
        return []


def _run_scrapers(filters: SearchFilters, early_exit: Optional[int] = None) -> int:
    """Ejecuta los scrapers en paralelo, upsertea en DB y retorna total.

    early_exit (plan free): todos los portales, 1 página cada uno.
    None (plan premium): paginación completa.
    """
    from scrapers.zonaprop import ZonapropScraper
    from scrapers.argenprop import ArgenpropScraper
    from scrapers.mel import MelScraper
    from scrapers.toribio import ToribioachavalScraper

    max_pages = 1 if early_exit is not None else 9999
    scraper_classes = [ZonapropScraper, ArgenpropScraper, MelScraper, ToribioachavalScraper]
    logger.info("[search_service] Scraping en paralelo: %d scrapers, max_pages=%d",
                len(scraper_classes), max_pages)

    # HTTP en paralelo
    all_pubs: list = []
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(_collect_from_scraper, cls, filters, max_pages)
                   for cls in scraper_classes]
        for future in as_completed(futures):
            all_pubs.extend(future.result())

    # Escritura en DB en serie (SQLite WAL serializa escrituras)
    total = 0
    for pub in all_pubs:
        pub.operacion = filters.operacion
        try:
            scoring.calcular_score(pub)
            analyzer.analizar(pub)
            db.upsert_publicacion(pub)
            total += 1
        except Exception as e:
            logger.warning("[search_service] Error procesando pub %s: %s",
                           getattr(pub, 'id_publicacion', '?'), e)

    logger.info("[search_service] Scraping completado: %d publicaciones guardadas.", total)
    return total


def _query_db(filters: SearchFilters) -> list[dict]:
    """Consulta la DB con los filtros dados y retorna lista de dicts."""
    conditions: list[str] = [
        "estado != 'ELIMINADA'",
        "score IS NOT NULL",
        "COALESCE(operacion, 'venta') = ?",
    ]
    params: list = [filters.operacion]

    if filters.barrios:
        placeholders = ",".join("?" * len(filters.barrios))
        conditions.append(f"barrio IN ({placeholders})")
        params.extend(filters.barrios)

    if filters.precio_min is not None:
        conditions.append("precio_usd >= ?")
        params.append(filters.precio_min)

    if filters.precio_max is not None:
        conditions.append("precio_usd <= ?")
        params.append(filters.precio_max)

    if filters.m2_min is not None:
        conditions.append("COALESCE(m2_totales, m2_cubiertos) >= ?")
        params.append(filters.m2_min)

    if filters.m2_max is not None:
        conditions.append("COALESCE(m2_totales, m2_cubiertos) <= ?")
        params.append(filters.m2_max)

    if filters.ambientes_min is not None:
        conditions.append("ambientes >= ?")
        params.append(filters.ambientes_min)

    if filters.ambientes_max is not None:
        conditions.append("ambientes <= ?")
        params.append(filters.ambientes_max)

    if filters.balcon is True:
        conditions.append("balcon = 1")

    if filters.terraza is True:
        conditions.append("(balcon = 1 OR LOWER(COALESCE(descripcion, '')) LIKE '%terraza%' OR LOWER(COALESCE(amenities, '')) LIKE '%terraza%')")

    if filters.cochera is True:
        conditions.append("cochera = 1")

    if filters.antiguedad_max is not None:
        conditions.append("(antiguedad IS NULL OR antiguedad <= ?)")
        params.append(filters.antiguedad_max)

    if filters.expensas_max is not None:
        conditions.append("(expensas IS NULL OR expensas <= ?)")
        params.append(filters.expensas_max)

    where = " AND ".join(conditions)
    sql = (
        f"SELECT * FROM publicaciones WHERE {where} "
        "ORDER BY (imagen_url IS NOT NULL AND TRIM(imagen_url) != '') DESC, score DESC"
    )

    logger.debug("[search_service] SQL: %s | params: %s", sql, params)

    with db.get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()

    return [dict(r) for r in rows]
