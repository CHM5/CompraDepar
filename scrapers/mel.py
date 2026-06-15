"""
scrapers/mel.py
───────────────
Scraper para MEL Propiedades (melpropiedades.com.ar).

Estrategia de extracción:
  JSON embebido en <script id="__NEXT_DATA__">
  → data.props.pageProps.dataProps.objects → lista de propiedades

URL de búsqueda:
  https://melpropiedades.com.ar/resultados?properties=departamento
    &locations={barrios_csv}&currency=dolares
    &min_price={min}&max_price={max}&page={N}

Campos disponibles en JSON:
  id, slug, name, address, address_floor, neighborhood,
  price, covered_m2, uncovered_m2, total_m2, rooms, bathrooms,
  parking_lots, description, status
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

from bs4 import BeautifulSoup

import config
from database.models import Publicacion
from scrapers.base import BaseScraper, barrio_to_slug
from shared.filters import SearchFilters

logger = logging.getLogger(__name__)

PORTAL = "MEL"
BASE_URL = "https://melpropiedades.com.ar"
MAX_PAGES = 10


class MelScraper(BaseScraper):
    """Scraper de publicaciones de departamentos en venta de MEL Propiedades."""

    PORTAL = PORTAL

    # ── URL ───────────────────────────────────────────────────────────────────

    def build_url(self, filters: SearchFilters, page: int = 1) -> str:
        """Construye la URL dinámicamente desde SearchFilters."""
        # MEL usa nombres de barrio en minúsculas separados por coma
        if filters.barrios:
            locations = ",".join(b.lower() for b in filters.barrios)
        else:
            locations = "capital federal"

        params: dict = {
            "properties": "departamento",
            "locations": locations,
            "currency": "dolares",
            "page": page,
        }
        if filters.precio_min:
            params["min_price"] = filters.precio_min
        if filters.precio_max:
            params["max_price"] = filters.precio_max
        return BASE_URL + "/resultados?" + urlencode(params)

    # ── Entrada principal ─────────────────────────────────────────────────────

    def scrape(self, filters: SearchFilters) -> List[Publicacion]:
        """Itera páginas y retorna publicaciones según los filtros dados."""
        if filters.operacion != "venta":
            logger.info("[MEL] Solo indexa venta — saltando búsqueda de %s.", filters.operacion)
            return []
        self._filters = filters
        self.warm_up(BASE_URL)
        publicaciones: List[Publicacion] = []
        ids_vistos: set = set()
        page = 1

        while page <= self._max_pages:
            url = self.build_url(filters, page)
            logger.info("[MEL] Página %d → %s", page, url)

            html = self.get_page(url)
            if not html:
                logger.warning("[MEL] No se pudo obtener página %d, deteniendo.", page)
                break

            pubs_pagina, total_pages = self._parse_page(html)

            if not pubs_pagina:
                logger.info("[MEL] Página %d sin resultados, deteniendo.", page)
                break

            pubs_nuevas = [p for p in pubs_pagina
                           if p.id_publicacion and p.id_publicacion not in ids_vistos]
            if not pubs_nuevas:
                logger.info("[MEL] Página %d sin IDs nuevos, deteniendo.", page)
                break

            publicaciones.extend(pubs_nuevas)
            ids_vistos.update(p.id_publicacion for p in pubs_nuevas)
            logger.info("[MEL] Página %d: %d pubs (total: %d)",
                        page, len(pubs_nuevas), len(publicaciones))

            if page >= total_pages:
                break

            page += 1
            time.sleep(config.DELAY_ENTRE_PAGINAS)

        logger.info("[MEL] Scraping completo: %d publicaciones", len(publicaciones))
        return publicaciones

    # ── Parsing ───────────────────────────────────────────────────────────────

    def _parse_page(self, html: str) -> Tuple[List[Publicacion], int]:
        """Extrae publicaciones del JSON embebido. Retorna (pubs, total_pages)."""
        soup = BeautifulSoup(html, "lxml")
        nd = soup.find("script", {"id": "__NEXT_DATA__"})
        if not nd or not nd.string:
            logger.warning("[MEL] No se encontró __NEXT_DATA__")
            return [], 1

        try:
            data = json.loads(nd.string)
        except json.JSONDecodeError as e:
            logger.error("[MEL] Error JSON: %s", e)
            return [], 1

        try:
            dp = data["props"]["pageProps"]["dataProps"]
            items: List[dict] = dp.get("objects", [])
            count: int = dp.get("count", 0)
            limit: int = dp.get("limit", 16) or 16
            total_pages = max(1, (count + limit - 1) // limit)
        except (KeyError, TypeError) as e:
            logger.error("[MEL] Estructura JSON inesperada: %s", e)
            return [], 1

        result: List[Publicacion] = []
        for item in items:
            pub = self._parse_item(item)
            if pub:
                result.append(pub)

        return result, total_pages

    def _parse_item(self, item: dict) -> Optional[Publicacion]:
        """Convierte un dict del JSON de MEL en un objeto Publicacion."""
        try:
            pub_id = str(item.get("id", "")).strip()
            slug = item.get("slug", "")
            if not pub_id:
                return None

            # URL canónica de la propiedad
            url = f"{BASE_URL}/propiedades/{slug}" if slug else BASE_URL

            # Precio
            precio_raw = item.get("price")
            precio_usd: Optional[float] = None
            if precio_raw is not None:
                try:
                    precio_usd = float(str(precio_raw).replace(",", "."))
                except ValueError:
                    pass

            # M²
            m2_cubiertos = self._to_float(item.get("covered_m2"))
            m2_descubiertos = self._to_float(item.get("uncovered_m2"))
            m2_totales = self._to_float(item.get("total_m2"))
            # Normalizar
            if m2_totales is None and m2_cubiertos is not None:
                m2_totales = m2_cubiertos + (m2_descubiertos or 0.0)

            # Dirección / barrio
            address = item.get("address", "") or ""
            floor_raw = item.get("address_floor", "")
            direccion = f"{address} {floor_raw}".strip() if floor_raw else address
            barrio_raw = item.get("neighborhood", "")
            barrio = self._normalizar_barrio(barrio_raw)

            # Ambientes / baños / cochera
            ambientes = self._to_int(item.get("rooms"))
            parking_raw = self._to_int(item.get("parking_lots"))
            cochera: bool = bool(parking_raw and parking_raw > 0)

            # Descripción
            desc = item.get("description", "") or ""
            nombre = item.get("name", "") or ""
            descripcion = f"{nombre}. {desc}".strip(". ")

            # Piso (extraído del text "floor_raw")
            piso: Optional[int] = None
            if floor_raw:
                piso = self._parse_piso(str(floor_raw))

            # Detectar amenities y otras features desde descripción
            desc_full = descripcion.lower()
            balcon = self._detect_bool(desc_full, ["balcón", "balcon", "terraza"])
            amenities_list = self._extract_amenities(desc_full)
            amenities = ", ".join(amenities_list) if amenities_list else None

            # Cálculo USD/m²
            m2_ref = m2_totales or m2_cubiertos
            usd_m2: Optional[float] = None
            if precio_usd and m2_ref and m2_ref > 0:
                usd_m2 = round(precio_usd / m2_ref, 2)

            # Filtros
            if not self.apply_filters(
                precio_usd=precio_usd,
                m2_totales=m2_totales or m2_cubiertos,
                piso=piso,
                disposicion=None,
                antiguedad=None,
                barrio=barrio,
                balcon=balcon if balcon else None,
            ):
                return None

            return Publicacion(
                id_publicacion=pub_id,
                portal=PORTAL,
                url=url,
                direccion=direccion,
                barrio=barrio,
                ambientes=ambientes,
                m2_cubiertos=m2_cubiertos,
                m2_descubiertos=m2_descubiertos,
                m2_totales=m2_totales,
                precio_usd=precio_usd,
                piso=piso,
                cochera=cochera,
                balcon=balcon,
                amenities=amenities,
                descripcion=descripcion,
                usd_m2_efectivo=usd_m2,
            )

        except Exception as e:
            logger.debug("[MEL] Error parseando item %s: %s", item.get("id"), e)
            return None

    def _normalizar_barrio(self, raw: str) -> Optional[str]:
        """Mapea el nombre de barrio de MEL al nombre canónico del config."""
        if not raw:
            return None
        raw_lower = raw.lower().strip()
        # Mapa de equivalencias conocidas de MEL
        equivalencias = {
            "barrio norte": "Barrio Norte",
            "villa crespo": "Villa Crespo",
            "villa urquiza": "Villa Urquiza",
            "nunez": "Núñez",
            "nuñez": "Núñez",
        }
        if raw_lower in equivalencias:
            return equivalencias[raw_lower]
        # Buscar coincidencia con barrios objetivo
        for b in config.BARRIOS_OBJETIVO:
            if b.lower() == raw_lower or b.lower().replace("ú", "u") == raw_lower:
                return b
        return raw.strip().title()
