"""
scrapers/toribio.py
────────────────────
Scraper para Toribio Achával (toribioachaval.com).

Estrategia de extracción:
  HTML puro con warm-up de sesión (WordPress + custom theme).
  Cards en:  section.grilla > div.item
  Link:      a.imagen-content[href]  → extrae ID numérico del slug
  Precio:    .content-valor span.precio
  M²:        .content-detalle span.superficie span.top (primero)
  Barrio:    .content-descripcion span.ubicacion
  Dirección: .content-descripcion div.desc p

URL de búsqueda:
  https://www.toribioachaval.com/listado/departamentos/capital-federal
    /{barrios_o_separados}/precio_{min}-{max}-USD-/superficie_{m2}-100
    [/pagina-{N}/]    (si existe paginación)
"""

from __future__ import annotations

import logging
import re
import time
from typing import List, Optional, Tuple

from bs4 import BeautifulSoup, Tag

import config
from database.models import Publicacion
from scrapers.base import BaseScraper, barrio_to_slug
from shared.filters import SearchFilters

logger = logging.getLogger(__name__)

PORTAL = "ToribiAchaval"
BASE_URL = "https://www.toribioachaval.com"
MAX_PAGES = 10


class ToribioachavalScraper(BaseScraper):
    """Scraper de publicaciones de departamentos en venta de Toribio Achával."""

    PORTAL = PORTAL

    # ── URL ───────────────────────────────────────────────────────────────────

    def build_url(self, filters: SearchFilters, page: int = 1) -> str:
        """Construye la URL dinámicamente desde SearchFilters."""
        if filters.barrios:
            barrios_str = "_o_".join(barrio_to_slug(b) for b in filters.barrios)
        else:
            barrios_str = "capital-federal"
        precio_max = filters.precio_max or 999_999
        m2_min = filters.m2_min or 0

        # Omitir precio_min cuando no está definido
        precio_min_val = filters.precio_min or 0
        path = (
            f"/listado/departamentos/capital-federal"
            f"/{barrios_str}"
            f"/precio_{precio_min_val}-{precio_max}-USD-"
            f"/superficie_{m2_min}-200"
        )
        if page > 1:
            path += f"/pagina-{page}/"
        return BASE_URL + path

    # ── Entrada principal ─────────────────────────────────────────────────────

    def scrape(self, filters: SearchFilters) -> List[Publicacion]:
        """Itera páginas y retorna publicaciones según los filtros dados."""
        if filters.operacion != "venta":
            logger.info("[ToribiAchaval] Solo indexa venta — saltando búsqueda de %s.", filters.operacion)
            return []
        self._filters = filters
        self.warm_up(BASE_URL)
        publicaciones: List[Publicacion] = []
        ids_vistos: set = set()
        page = 1

        while page <= self._max_pages:
            url = self.build_url(filters, page)
            logger.info("[ToribiAchaval] Página %d → %s", page, url)

            html = self.get_page(url, extra_headers={"Referer": BASE_URL + "/"})
            if not html:
                logger.warning("[ToribiAchaval] No se pudo obtener página %d, deteniendo.", page)
                break

            pubs_pagina, has_next = self._parse_page(html)

            if not pubs_pagina:
                logger.info("[ToribiAchaval] Página %d sin resultados, deteniendo.", page)
                break

            pubs_nuevas = [p for p in pubs_pagina
                           if p.id_publicacion and p.id_publicacion not in ids_vistos]
            if not pubs_nuevas:
                logger.info("[ToribiAchaval] Página %d sin IDs nuevos, deteniendo.", page)
                break

            publicaciones.extend(pubs_nuevas)
            ids_vistos.update(p.id_publicacion for p in pubs_nuevas)
            logger.info("[ToribiAchaval] Página %d: %d pubs (total: %d)",
                        page, len(pubs_nuevas), len(publicaciones))

            if not has_next:
                break

            page += 1
            time.sleep(config.DELAY_ENTRE_PAGINAS)

        logger.info("[ToribiAchaval] Scraping completo: %d publicaciones", len(publicaciones))
        return publicaciones

    # ── Parsing de página ─────────────────────────────────────────────────────

    def _parse_page(self, html: str) -> Tuple[List[Publicacion], bool]:
        soup = BeautifulSoup(html, "lxml")
        items = soup.select("section.grilla div.item")
        if not items:
            # Fallback selector
            items = soup.select("div.item")

        result: List[Publicacion] = []
        for item in items:
            pub = self._parse_card(item)
            if pub:
                result.append(pub)

        has_next = self._has_next_page(soup)
        return result, has_next

    def _parse_card(self, item: Tag) -> Optional[Publicacion]:
        try:
            # Link e ID
            link_el = item.select_one("a.imagen-content, a[href*='/propiedades/']")
            if not link_el:
                return None
            href = link_el.get("href", "")
            # ID = último número en el slug (e.g. ".../colegiales-capital-federal-69285")
            m = re.search(r"-(\d{4,})/?$", href)
            pub_id = m.group(1) if m else re.sub(r"[^a-z0-9]", "", href.lower())[-20:]
            if not pub_id:
                return None

            url = BASE_URL + href if href.startswith("/") else href

            # Precio
            precio_el = item.select_one(".content-valor span.precio, .precio")
            precio_usd = self._parse_precio(precio_el.get_text(strip=True)) if precio_el else None

            # M² y otros datos del content-detalle
            detalle = item.select_one(".content-detalle")
            m2_cubiertos: Optional[float] = None
            if detalle:
                tops = detalle.select("span.top")
                if tops:
                    # First 'top' span is usually m²
                    try:
                        m2_cubiertos = float(tops[0].get_text(strip=True).replace(",", "."))
                    except ValueError:
                        pass

            # Barrio y dirección
            desc_el = item.select_one(".content-descripcion")
            barrio_raw: Optional[str] = None
            direccion: Optional[str] = None
            if desc_el:
                ub = desc_el.select_one("span.ubicacion")
                if ub:
                    barrio_raw = ub.get_text(strip=True)
                desc_p = desc_el.select_one("div.desc p")
                if desc_p:
                    direccion = desc_p.get_text(strip=True)

            # Normalizar barrio
            barrio = self._normalizar_barrio(barrio_raw)

            # Calcular USD/m²
            m2_ref = m2_cubiertos
            usd_m2: Optional[float] = None
            if precio_usd and m2_ref and m2_ref > 0:
                usd_m2 = round(precio_usd / m2_ref, 2)

            # Filtros
            if not self.apply_filters(
                precio_usd=precio_usd,
                m2_totales=m2_cubiertos,
                piso=None,
                disposicion=None,
                antiguedad=None,
                barrio=barrio,
            ):
                return None

            return Publicacion(
                id_publicacion=pub_id,
                portal=PORTAL,
                url=url,
                barrio=barrio,
                direccion=direccion,
                m2_cubiertos=m2_cubiertos,
                m2_totales=m2_cubiertos,   # solo disponemos de m² cubiertos en la tarjeta
                precio_usd=precio_usd,
                usd_m2_efectivo=usd_m2,
            )

        except Exception as e:
            logger.debug("[ToribiAchaval] Error parseando card: %s", e)
            return None

    def _has_next_page(self, soup: BeautifulSoup) -> bool:
        """Detecta si hay página siguiente."""
        # Paginación via links con /pagina-N/
        pag_links = soup.select("a[href*='/pagina-']")
        if not pag_links:
            # También puede haber un botón .next o rel="next"
            return bool(soup.select_one("a[rel='next'], .pagination .next, .paginacion a.next"))
        # Verificar si el número de página más alto supera el actual
        current = 1
        max_page = 1
        for a in pag_links:
            m = re.search(r"/pagina-(\d+)/?", a.get("href", ""))
            if m:
                p = int(m.group(1))
                if p > max_page:
                    max_page = p
                # Active/current page
                if "active" in " ".join(a.get("class", [])):
                    current = p
        return max_page > current

    def _normalizar_barrio(self, raw: Optional[str]) -> Optional[str]:
        """Mapea el barrio desde la URL/tarjeta al nombre canónico."""
        if not raw:
            return None
        raw_lower = raw.lower().strip()
        # Equivalencias directas
        equivalencias = {
            "barrio norte": "Barrio Norte",
            "villa crespo": "Villa Crespo",
            "villa urquiza": "Villa Urquiza",
            "nunez": "Núñez",
            "nuñez": "Núñez",
            "las cañitas": "Palermo",  # subbarrio de Palermo
            "palermo chico": "Palermo",
            "palermo soho": "Palermo",
            "palermo hollywood": "Palermo",
        }
        if raw_lower in equivalencias:
            return equivalencias[raw_lower]
        for b in config.BARRIOS_OBJETIVO:
            if b.lower() == raw_lower or b.lower().replace("ú", "u") == raw_lower:
                return b
        return raw.strip().title()
