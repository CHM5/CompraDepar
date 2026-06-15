"""
main.py
────────
Orquestador principal de la aplicación.

Flujo de ejecución:
  1. Inicializar base de datos
  2. Conectar a Google Sheets
  3. Para cada portal (Zonaprop, Argenprop):
     a. Scrape de publicaciones
     b. Calcular score + análisis por cada pub
     c. Persistir en SQLite (detecta NUEVA / BAJA_PRECIO / SUBA_PRECIO)
     d. Marcar eliminadas (las que ya no aparecen)
  4. Exportar publicaciones relevantes (score ≥ umbral) a Google Sheets
  5. Enviar alertas Telegram para novedades destacadas
  6. Generar resumen de ejecución

Diseñado para correr cada 4 horas vía cron o GitHub Actions.
Cada portal falla de forma independiente (no interrumpe el otro).
"""

from __future__ import annotations

import logging
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Tuple
from urllib.parse import urlparse

import config
from database import db
from database.models import Publicacion
from scrapers.argenprop import ArgenpropScraper
from scrapers.mel import MelScraper
from scrapers.toribio import ToribioachavalScraper
from scrapers.zonaprop import ZonapropScraper
from services import analyzer, scoring
from services.sheets import SheetsService
from services.telegram import TelegramService
from shared.filters import SearchFilters


# ══════════════════════════════════════════════════════════════════════════════
# LOGGING
# ══════════════════════════════════════════════════════════════════════════════


def setup_logging() -> None:
    """Configura el sistema de logging con salida a archivo y consola."""
    log_file = Path(config.LOG_FILE)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    level = getattr(logging, config.LOG_LEVEL.upper(), logging.INFO)
    fmt = "%(asctime)s [%(levelname)s] %(name)s — %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    logging.basicConfig(
        level=level,
        format=fmt,
        datefmt=datefmt,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("gspread").setLevel(logging.WARNING)


logger = logging.getLogger(__name__)


def _normalizar_id_publicacion(id_publicacion: str, url: str) -> str:
    """Normaliza el ID de publicación y, si falta, intenta derivarlo desde la URL."""
    raw = str(id_publicacion or "").strip()
    if raw:
        return raw

    parsed = urlparse(url or "")
    path = (parsed.path or "").strip("/")

    m = re.search(r"(\d{5,})", path)
    if m:
        return m.group(1)

    return path.lower() or (url or "").strip().lower()


# ══════════════════════════════════════════════════════════════════════════════
# RESULTADO DE RUN
# ══════════════════════════════════════════════════════════════════════════════


@dataclass
class RunResult:
    portal: str
    total_scrapeadas: int = 0
    nuevas: int = 0
    bajas_precio: int = 0
    subas_precio: int = 0
    sin_cambios: int = 0
    eliminadas: int = 0
    exportadas: int = 0
    alertas_enviadas: int = 0
    errores: List[str] = field(default_factory=list)


# ══════════════════════════════════════════════════════════════════════════════
# PROCESAMIENTO DE UN PORTAL
# ══════════════════════════════════════════════════════════════════════════════


def procesar_portal(
    scraper,
    sheets: SheetsService,
    telegram: TelegramService,
    filters: SearchFilters,
) -> RunResult:
    """Ejecuta el ciclo completo para un portal. Retorna el resumen."""
    result = RunResult(portal=scraper.PORTAL)

    # ── Scraping ─────────────────────────────────────────────────────────────
    logger.info("═" * 60)
    logger.info("  Iniciando scraping: %s", scraper.PORTAL)
    logger.info("═" * 60)

    try:
        publicaciones_raw = scraper.scrape(filters)
    except Exception as e:
        logger.error("[%s] Error crítico durante el scraping: %s", scraper.PORTAL, e, exc_info=True)
        result.errores.append(f"Scraping fallido: {e}")
        return result

    result.total_scrapeadas = len(publicaciones_raw)
    logger.info("[%s] Scrapeadas: %d publicaciones", scraper.PORTAL, result.total_scrapeadas)

    if not publicaciones_raw:
        logger.warning("[%s] No se encontraron publicaciones. Verificar URL y selectores.", scraper.PORTAL)
        return result

    # ── Dedupe y normalización previa ─────────────────────────────────────────
    publicaciones_unicas: List[Publicacion] = []
    seen_keys = set()

    for pub in publicaciones_raw:
        pub.id_publicacion = _normalizar_id_publicacion(pub.id_publicacion, pub.url)
        dedupe_key = (pub.portal.lower().strip(), pub.id_publicacion.strip())
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        publicaciones_unicas.append(pub)

    if len(publicaciones_unicas) != len(publicaciones_raw):
        logger.info(
            "[%s] Dedupe aplicado: %d → %d publicaciones únicas",
            scraper.PORTAL,
            len(publicaciones_raw),
            len(publicaciones_unicas),
        )

    # ── Proceso individual ────────────────────────────────────────────────────
    ids_activos: List[str] = []
    pubs_para_exportar: List[Publicacion] = []
    pubs_nuevas_alertar: List[Publicacion] = []   # acumuladas para enviar en batch al final
    pubs_baja_alertar:   List[Publicacion] = []

    for pub in publicaciones_unicas:
        try:
            # Score + análisis
            scoring.calcular_score(pub)
            analyzer.analizar(pub)

            # Persistir en SQLite
            estado = db.upsert_publicacion(pub)

            ids_activos.append(pub.id_publicacion)

            # Contadores
            if estado == "NUEVA":
                result.nuevas += 1
            elif estado == "BAJA_PRECIO":
                result.bajas_precio += 1
            elif estado == "SUBA_PRECIO":
                result.subas_precio += 1
            else:
                result.sin_cambios += 1

            # Acumular para alertas batch (se envían al finalizar el portal)
            if estado == "NUEVA" and scoring.debe_alertar(pub):
                pubs_nuevas_alertar.append(pub)
                result.alertas_enviadas += 1

            elif estado == "BAJA_PRECIO":
                pubs_baja_alertar.append(pub)
                result.alertas_enviadas += 1

            # Acumular para exportación batch
            if scoring.debe_exportar(pub):
                pubs_para_exportar.append(pub)

        except Exception as e:
            msg = f"Error procesando {pub.id_publicacion}: {e}"
            logger.error("[%s] %s", scraper.PORTAL, msg, exc_info=True)
            result.errores.append(msg)
    # ── Alertas Telegram en batch ───────────────────────────────────────────────
    if pubs_nuevas_alertar:
        # Excelentes → mensaje individual; el resto agrupado
        excelentes = [p for p in pubs_nuevas_alertar if scoring.es_excelente(p)]
        normales   = [p for p in pubs_nuevas_alertar if not scoring.es_excelente(p)]
        for pub in excelentes:
            telegram.alerta_excelente(pub)
            time.sleep(1.0)
        if normales:
            telegram.alerta_batch_nuevas(normales)
    if pubs_baja_alertar:
        telegram.alerta_batch_bajas(pubs_baja_alertar)
    # ── Detectar eliminadas ───────────────────────────────────────────────────
    try:
        result.eliminadas = db.marcar_eliminadas(ids_activos, scraper.PORTAL)
    except Exception as e:
        logger.error("[%s] Error marcando eliminadas: %s", scraper.PORTAL, e)

    # ── Exportar a Sheets ─────────────────────────────────────────────────────
    if pubs_para_exportar:
        logger.info("[%s] Exportando %d publicaciones a Google Sheets…", scraper.PORTAL, len(pubs_para_exportar))
        result.exportadas = sheets.exportar_batch(pubs_para_exportar)
    else:
        logger.info("[%s] Ninguna publicación supera el umbral de exportación.", scraper.PORTAL)

    return result


# ══════════════════════════════════════════════════════════════════════════════
# ORQUESTADOR PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════


def run(config_overrides: dict | None = None) -> int:
    """Punto de entrada principal. Retorna 0 si OK, 1 si hubo errores.

    Args:
        config_overrides: dict opcional con overrides de config (e.g. desde bot.py).
                          Se aplican al módulo config antes de iniciar los scrapers.
    """
    # Aplicar overrides de config ANTES de crear scrapers (que leen config en __init__/scrape)
    if config_overrides:
        from services.user_config import apply_to_module
        apply_to_module(config_overrides)

    setup_logging()
    inicio = datetime.now()
    logger.info("▶ Iniciando scraper — %s", inicio.strftime("%Y-%m-%d %H:%M:%S"))
    logger.info("  Portales: Zonaprop, Argenprop, MEL, ToribiAchaval")
    logger.info("  Barrios : %s", ", ".join(config.BARRIOS_OBJETIVO))
    logger.info("  Precio  : USD %s – %s", f"{config.PRECIO_MIN_USD:,}", f"{config.PRECIO_MAX_USD:,}")

    # Construir SearchFilters a partir de la configuración global
    default_filters = SearchFilters(
        operacion="venta",
        tipo="departamento",
        barrios=list(config.BARRIOS_OBJETIVO),
        precio_min=config.PRECIO_MIN_USD,
        precio_max=config.PRECIO_MAX_USD,
        m2_min=int(config.M2_MINIMO),
        balcon=True if getattr(config, "MUST_HAVE_BALCON", False) else None,
        antiguedad_max=config.ANTIGUEDAD_MAXIMA,
    )

    # ── Inicializar infraestructura ───────────────────────────────────────────
    try:
        db.init_db()
    except Exception as e:
        logger.critical("No se pudo inicializar la base de datos: %s", e, exc_info=True)
        return 1

    sheets = SheetsService()
    sheets.connect()

    telegram = TelegramService()

    # ── Scrapers configurados ─────────────────────────────────────────────────
    scrapers = [
        ZonapropScraper(),
        ArgenpropScraper(),
        MelScraper(),
        ToribioachavalScraper(),
    ]

    resultados: List[RunResult] = []

    for scraper in scrapers:
        try:
            result = procesar_portal(scraper, sheets, telegram, default_filters)
            resultados.append(result)
        except Exception as e:
            logger.error("Error inesperado en portal %s: %s", scraper.PORTAL, e, exc_info=True)
            resultados.append(RunResult(portal=scraper.PORTAL, errores=[str(e)]))

    # ── Resumen final ─────────────────────────────────────────────────────────
    duracion = (datetime.now() - inicio).total_seconds()
    total_nuevas = sum(r.nuevas for r in resultados)
    total_bajas = sum(r.bajas_precio for r in resultados)
    total_procesadas = sum(r.total_scrapeadas for r in resultados)
    total_exportadas = sum(r.exportadas for r in resultados)
    total_alertas = sum(r.alertas_enviadas for r in resultados)

    logger.info("═" * 60)
    logger.info("  RESUMEN FINAL")
    logger.info("═" * 60)
    for r in resultados:
        logger.info(
            "  %-12s | scrapeadas: %3d | nuevas: %2d | bajas: %2d | "
            "subas: %2d | eliminadas: %2d | exportadas: %2d | alertas: %2d",
            r.portal, r.total_scrapeadas, r.nuevas, r.bajas_precio,
            r.subas_precio, r.eliminadas, r.exportadas, r.alertas_enviadas,
        )
        if r.errores:
            for err in r.errores:
                logger.warning("    ⚠ %s", err)

    logger.info("─" * 60)
    logger.info(
        "  TOTAL | procesadas: %d | nuevas: %d | bajas: %d | "
        "exportadas: %d | alertas: %d | %.1fs",
        total_procesadas, total_nuevas, total_bajas,
        total_exportadas, total_alertas, duracion,
    )
    logger.info("═" * 60)

    # Resumen por Telegram
    telegram.mensaje_resumen(total_nuevas, total_bajas, total_procesadas)

    hubo_errores = any(r.errores for r in resultados)
    return 1 if hubo_errores else 0


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════


if __name__ == "__main__":
    sys.exit(run())
