"""
scrapers/argenprop.py
─────────────────────
Scraper para Argenprop (argenprop.com).

Estrategia de extracción (por orden de prioridad):
  1. JSON embebido en <script id="__NEXT_DATA__"> o window.__STORE__
  2. Fallback a parsing HTML con múltiples selectores CSS

URL construida con filtros en el path (formato estándar de Argenprop).

NOTA: Si el sitio cambia estructura, ajustar _CARD_SELECTORS y
      _extract_postings_from_json().
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from bs4 import BeautifulSoup, Tag

import config
from database.models import Publicacion
from scrapers.base import BaseScraper, barrio_to_slug
from shared.filters import SearchFilters

logger = logging.getLogger(__name__)

PORTAL = "Argenprop"
BASE_URL = "https://www.argenprop.com"
MAX_PAGES = 25

# Selectores CSS de tarjetas (en orden de confianza)
_CARD_SELECTORS = [
    "div.listing-item",
    "article.listing-item",
    "div.listing__item",
    "div.card",
    "article.card",
    "[class*='listing-item']",
    "[class*='listing__item']",
    "[class*='property-card']",
    "[class*='posting-card']",
    "[data-id]",
    ".listing__item",
    "[id][class*='listing__item']",
]


# ══════════════════════════════════════════════════════════════════════════════
# SCRAPER
# ══════════════════════════════════════════════════════════════════════════════


class ArgenpropScraper(BaseScraper):
    """Scraper de publicaciones de departamentos en venta de Argenprop."""

    PORTAL = PORTAL

    # ── URL ───────────────────────────────────────────────────────────────────

    def build_url(self, filters: SearchFilters, page: int = 1) -> str:
        """Construye la URL dinámicamente desde SearchFilters."""
        barrios = filters.barrios
        barrios_str = "-o-".join(barrio_to_slug(b) for b in barrios) if barrios else "capital-federal"
        operacion = filters.operacion  # 'venta' o 'alquiler'
        m2_min = filters.m2_min or 0

        if operacion == "alquiler":
            # Alquiler: precios en pesos
            if filters.precio_max:
                price_part = f"pesos-{filters.precio_max}"
            else:
                price_part = ""  # sin filtro de precio
        else:
            # Venta: precios en dólares
            precio_max = filters.precio_max or 999_999
            if filters.precio_min:
                price_part = f"dolares-{filters.precio_min}-{precio_max}"
            else:
                price_part = f"dolares-{precio_max}"

        path = f"/departamentos/{operacion}/{barrios_str}"
        if price_part:
            path += f"/{price_part}"
        params = f"?desde-{m2_min}-m2-cubiertos"
        if filters.balcon is True:
            params += "&con-ambiente-balcon"
        if page > 1:
            params += f"&pagina={page}"
        return BASE_URL + path + params

    # ── Entrada principal ─────────────────────────────────────────────────────

    def scrape(self, filters: SearchFilters) -> List[Publicacion]:
        """Itera páginas y retorna publicaciones según los filtros dados."""
        self._filters = filters
        self.warm_up(BASE_URL)
        publicaciones: List[Publicacion] = []
        ids_vistos: set[str] = set()
        page = 1

        while page <= self._max_pages:
            url = self.build_url(filters, page)
            logger.info("[Argenprop] Página %d → %s", page, url)

            html = self.get_page(url)
            if not html:
                logger.warning("[Argenprop] No se pudo obtener página %d, deteniendo.", page)
                break

            pubs_pagina, hay_siguiente = self._parse_page(html, url)
            logger.info("HTML size: %s bytes", len(html))
            if not pubs_pagina:
                logger.info("[Argenprop] Página %d sin resultados, deteniendo.", page)
                break

            pubs_nuevas = [p for p in pubs_pagina if p.id_publicacion and p.id_publicacion not in ids_vistos]
            if not pubs_nuevas:
                logger.info("[Argenprop] Página %d repetida (sin IDs nuevos), deteniendo.", page)
                break

            publicaciones.extend(pubs_nuevas)
            ids_vistos.update(p.id_publicacion for p in pubs_nuevas)
            logger.info("[Argenprop] Página %d: %d pubs encontradas (total: %d)",
                        page, len(pubs_nuevas), len(publicaciones))

            if not hay_siguiente:
                break

            page += 1
            time.sleep(config.DELAY_ENTRE_PAGINAS)

        logger.info("[Argenprop] Scraping completo: %d publicaciones", len(publicaciones))
        return publicaciones

    # ── Parsing de página ─────────────────────────────────────────────────────

    def _parse_page(self, html: str, base_url: str) -> Tuple[List[Publicacion], bool]:
        soup = BeautifulSoup(html, "lxml")

        # Intento 1: JSON de Next.js / window.__STORE__
        pubs = self._parse_from_next_data(soup)
        logger.debug(
            "[Argenprop] NEXT_DATA resultado: %s",
            "None" if pubs is None else len(pubs)
        )
        if pubs is not None:
            has_next = self._has_next_page_json(soup) or len(pubs) >= 20
            return pubs, has_next

        # Intento 2: HTML
        pubs = self._parse_from_html(soup)
        logger.debug(
            "[Argenprop] HTML resultado: %s publicaciones",
            len(pubs)
        )
        has_next = self._has_next_page_html(soup)
        return pubs, has_next

    # ── JSON de Next.js ───────────────────────────────────────────────────────

    def _parse_from_next_data(self, soup: BeautifulSoup) -> Optional[List[Publicacion]]:
        script = soup.find("script", {"id": "__NEXT_DATA__"})
        if not script or not script.string:
            # Buscar window.__STORE__ en scripts inline
            return self._parse_from_inline_store(soup)

        try:
            data = json.loads(script.string)
        except json.JSONDecodeError as e:
            logger.debug("[Argenprop] Error JSON __NEXT_DATA__: %s", e)
            return None

        postings = self._extract_postings_from_json(data)
        if postings is None:
            return None

        result: List[Publicacion] = []
        for p in postings:
            pub = self._parse_json_item(p)
            if pub:
                result.append(pub)
        return result

    def _parse_from_inline_store(self, soup: BeautifulSoup) -> Optional[List[Publicacion]]:
        """Intenta encontrar datos en scripts inline (window.__STORE__, window.DATA, etc.)."""
        for script in soup.find_all("script"):
            text = script.string or ""
            if not text:
                continue
            # Buscar patrones de datos JSON en scripts inline
            m = re.search(r'window\.__(?:STORE|DATA|STATE)__\s*=\s*(\{.+?\});', text, re.DOTALL)
            if m:
                try:
                    data = json.loads(m.group(1))
                    postings = self._extract_postings_from_json(data)
                    if postings:
                        result = [self._parse_json_item(p) for p in postings]
                        return [p for p in result if p]
                except (json.JSONDecodeError, Exception):
                    pass
        return None

    def _extract_postings_from_json(self, data: dict) -> Optional[List[dict]]:
        """Extrae la lista de postings desde varias rutas conocidas."""
        # Ruta 1: props.pageProps (Next.js estándar)
        page_props = data.get("props", {}).get("pageProps", {})

        for key in ("listings", "properties", "postings", "results", "items"):
            val = page_props.get(key)
            if isinstance(val, list):
                return val

        # Ruta 2: data.listings / data.properties
        for key in ("listings", "properties", "postings", "results"):
            val = data.get(key)
            if isinstance(val, list):
                return val

        # Ruta 3: anidado en searchResults / listingResults
        for outer in ("searchResults", "listingResults", "propertyList"):
            outer_val = page_props.get(outer) or data.get(outer) or {}
            if isinstance(outer_val, dict):
                for inner in ("listings", "items", "postings", "properties", "results"):
                    val = outer_val.get(inner)
                    if isinstance(val, list):
                        return val

        return None

    def _parse_json_item(self, item: dict) -> Optional[Publicacion]:
        """Mapea un item del JSON al modelo Publicacion."""
        try:
            id_pub = str(
                item.get("id")
                or item.get("propertyId")
                or item.get("postingId")
                or item.get("listingId")
                or ""
            ).strip()
            if not id_pub:
                return None

            # URL
            url_rel = item.get("url") or item.get("link") or item.get("slug") or ""
            url = BASE_URL + url_rel if str(url_rel).startswith("/") else str(url_rel)
            if not url or url == BASE_URL:
                logger.warning("No pude obtener URL para %s", id_pub)
                url = f"{BASE_URL}/propiedades/{id_pub}"

            # Precio
            precio_usd = self._extract_price(item)

            # Ubicación
            loc = item.get("location") or item.get("address") or {}
            if isinstance(loc, str):
                direccion = loc
                barrio = self._detect_barrio(loc)
            else:
                direccion = (
                    loc.get("address") or loc.get("street") or loc.get("streetAddress") or ""
                )
                barrio = (
                    loc.get("neighborhood") or loc.get("barrio")
                    or (loc.get("neighborhood", {}) or {}).get("name")
                    or self._detect_barrio(str(loc))
                )

            # Atributos del inmueble
            attrs = item.get("mainAttributes") or item.get("attributes") or item.get("features") or {}

            ambientes = self._to_int(self._attr_val(attrs, item, ["rooms", "ambientes", "roomsTotal", "bedrooms"]))
            m2_cub = self._to_float(self._attr_val(attrs, item, ["coveredArea", "m2_cubiertos", "superficie_cubierta", "coveredSurface"]))
            m2_desc = self._to_float(self._attr_val(attrs, item, ["uncoveredArea", "m2_descubiertos", "uncoveredSurface", "balconyArea"]))
            m2_tot = self._to_float(self._attr_val(attrs, item, ["totalArea", "m2_totales", "superficie_total", "surface", "totalSurface"]))
            piso = self._to_int(self._attr_val(attrs, item, ["floor", "piso", "floorNumber"]))
            antiguedad = self._to_int(self._attr_val(attrs, item, ["propertyAge", "antiguedad", "age", "constructionYear"]))
            expensas = self._to_float(self._attr_val(attrs, item, ["expenses", "expensas", "commonExpenses"]))

            if antiguedad and antiguedad > 1900:
                from datetime import date
                antiguedad = max(0, date.today().year - antiguedad)

            all_text = json.dumps(item, ensure_ascii=False).lower()

            disposicion = self._parse_disposicion(all_text) or self._attr_val_str(attrs, ["disposition", "disposicion"])
            orientacion = self._parse_orientacion(all_text) or self._attr_val_str(attrs, ["orientation", "orientacion"])

            descripcion = item.get("description") or item.get("descriptionNormalized") or ""
            search_text = descripcion.lower() + " " + all_text

            balcon = self._detect_bool(search_text, ["balcón", "balcon", "terraza"])
            cochera = self._detect_bool(search_text, ["cochera", "garage", "garaje"])
            amenities_list = self._extract_amenities(search_text)

            # Imagen principal
            imagen_url = self._extract_image_url_from_item(item)

            publisher = item.get("publisher") or item.get("agency") or {}
            inmobiliaria = (
                publisher.get("name") or publisher.get("realEstateName")
                if isinstance(publisher, dict) else str(publisher)
            ) or None

            fecha_pub = item.get("createdAt") or item.get("publishedAt") or None

            if not self.apply_filters(
                precio_usd=precio_usd,
                m2_totales=m2_tot or m2_cub,
                piso=piso,
                disposicion=disposicion,
                antiguedad=antiguedad,
                barrio=str(barrio).strip() if barrio else None,
                balcon=balcon,
            ):
                return None

            return Publicacion(
                id_publicacion=id_pub,
                portal=PORTAL,
                url=url,
                inmobiliaria=inmobiliaria,
                direccion=str(direccion).strip() if direccion else None,
                barrio=str(barrio).strip() if barrio else None,
                ambientes=ambientes,
                m2_cubiertos=m2_cub,
                m2_descubiertos=m2_desc,
                m2_totales=m2_tot,
                precio_usd=precio_usd,
                expensas=expensas,
                antiguedad=antiguedad,
                piso=piso,
                disposicion=str(disposicion).capitalize() if disposicion else None,
                orientacion=str(orientacion).capitalize() if orientacion else None,
                balcon=balcon,
                cochera=cochera,
                amenities=", ".join(amenities_list) if amenities_list else None,
                descripcion=descripcion[:2000] if descripcion else None,
                fecha_publicacion=fecha_pub,
                imagen_url=imagen_url,
            )

        except Exception as e:
            logger.debug("[Argenprop] Error parseando item JSON id=%s: %s",
                         item.get("id", "?"), e, exc_info=True)
            return None

    @staticmethod
    def _extract_image_url_from_item(item: dict) -> Optional[str]:
        """Extrae la URL de la imagen principal del item JSON de Argenprop."""
        for key in ("photos", "pictures", "images"):
            val = item.get(key)
            if isinstance(val, list) and val:
                first = val[0]
                if isinstance(first, dict):
                    return first.get("url") or first.get("src") or first.get("localUrl")
                if isinstance(first, str):
                    return first
        multimedia = item.get("multimedia") or {}
        if isinstance(multimedia, dict):
            pics = multimedia.get("pictures") or []
            if pics:
                first = pics[0]
                return first.get("url") or first.get("src") if isinstance(first, dict) else first
        return None
        """Extrae el precio USD de las distintas estructuras posibles."""
        # Estructura con operaciones
        for key in ("operationTypes", "operations", "priceOperationTypes"):
            ops = item.get(key) or []
            for op in ops:
                if not isinstance(op, dict):
                    continue
                op_type = str(op.get("type") or op.get("priceOperationType") or "").lower()
                if "venta" in op_type or "sale" in op_type:
                    for p in (op.get("prices") or []):
                        currency = str(p.get("currency") or "").upper()
                        if currency in ("USD", "U$S", "DOLAR", "DOLARES", "US$"):
                            try:
                                return float(p.get("amount") or 0) or None
                            except (ValueError, TypeError):
                                pass

        # Precio directo
        for key in ("price", "precio", "salePrice"):
            val = item.get(key)
            if isinstance(val, (int, float)):
                v = float(val)
                return v if v > 1000 else None
            if isinstance(val, dict):
                cur = str(val.get("currency") or "").upper()
                if cur in ("USD", "U$S"):
                    return self._to_float(val.get("amount"))
            if isinstance(val, str):
                return self._parse_precio(val)

        return None

    # ── HTML Fallback ─────────────────────────────────────────────────────────

    def _parse_from_html(self, soup: BeautifulSoup) -> List[Publicacion]:
        cards: List[Tag] = []
        for sel in _CARD_SELECTORS:
            found = soup.select(sel)
            # Filtrar cards sin contenido útil (menús, footers)
            cards = [c for c in found if len(c.get_text(strip=True)) > 50]
            if cards:
                logger.debug("[Argenprop HTML] Selector '%s' → %d cards", sel, len(cards))
                break

        if not cards:
            logger.warning("[Argenprop HTML] No se encontraron cards con ningún selector.")
            return []

        result: List[Publicacion] = []
        for card in cards:
            pub = self._parse_html_card(card)
            if pub and self.apply_filters(
                precio_usd=pub.precio_usd,
                m2_totales=pub.m2_totales,
                piso=pub.piso,
                disposicion=pub.disposicion,
                antiguedad=pub.antiguedad,
                barrio=pub.barrio,
                balcon=pub.balcon,
            ):
                result.append(pub)
        
        logger.debug("[Argenprop] Cards encontradas: %s", len(cards))
        logger.debug("[Argenprop] Publicaciones parseadas: %s", len(result))

        return result

    def _parse_html_card(self, card: Tag) -> Optional[Publicacion]:
        try:
            logger.debug("[Argenprop] ID card: %s", card.get("id"))
            link = card.find("a", href=True)
            if link:
                logger.debug("[Argenprop] LINK: %s", link["href"])

            # ID desde atributos data-* o link
            id_pub = (
                card.get("id")
                or card.get("data-id")
                or card.get("data-listing-id")
                or card.get("data-property-id")
                or ""
            )

            # Si no hay data-id, extraer del link
            if not id_pub:
                link = card.find("a", href=True)
                if link:
                    m = re.search(r"/(\d+)(?:/|\?|$)", str(link["href"]))
                    if m:
                        id_pub = m.group(1)

            if not id_pub:
                logger.warning("No pude obtener ID de la card")
                return None

            id_pub = str(id_pub).strip()

            link = card.find("a", href=True)
            url_rel = str(link["href"]) if link else ""
            url = BASE_URL + url_rel if url_rel.startswith("/") else url_rel

            full_text = card.get_text(" ", strip=True)

            # Precio
            price_elem = card.find(
                class_=lambda x: x and any(
                    p in str(x).lower() for p in ["price", "precio", "valor"]
                )
            )
            precio_usd = self._parse_precio(
                price_elem.get_text(strip=True) if price_elem else full_text
            )

            barrio = self._detect_barrio(full_text)
            addr_elem = card.find(class_=lambda x: x and "address" in str(x).lower())
            direccion = addr_elem.get_text(strip=True) if addr_elem else None

            m2_cub, m2_desc, m2_tot = self._parse_m2(full_text)
            ambientes = self._parse_ambientes(full_text)
            piso = self._parse_piso(full_text)
            antiguedad = self._parse_antiguedad(full_text)
            disposicion = self._parse_disposicion(full_text)
            orientacion = self._parse_orientacion(full_text)
            expensas = self._parse_expensas(full_text)
            balcon = self._detect_bool(full_text, ["balcón", "balcon", "terraza"])
            cochera = self._detect_bool(full_text, ["cochera", "garage"])
            amenities_list = self._extract_amenities(full_text)

            # Imagen desde HTML
            img_el = card.select_one("img[src]:not([src=''])")
            imagen_url = img_el.get("src") if img_el else None

            return Publicacion(
                id_publicacion=id_pub,
                portal=PORTAL,
                url=url,
                direccion=direccion,
                barrio=barrio,
                ambientes=ambientes,
                m2_cubiertos=m2_cub,
                m2_descubiertos=m2_desc,
                m2_totales=m2_tot,
                precio_usd=precio_usd,
                expensas=expensas,
                antiguedad=antiguedad,
                piso=piso,
                disposicion=str(disposicion).capitalize() if disposicion else None,
                orientacion=str(orientacion).capitalize() if orientacion else None,
                balcon=balcon,
                cochera=cochera,
                amenities=", ".join(amenities_list) if amenities_list else None,
                descripcion=full_text[:2000],
                imagen_url=imagen_url,
            )

        except Exception as e:
            logger.error(
                "[Argenprop HTML] Error parseando card:\n%s",
                card.prettify()[:2000],
                exc_info=True
            )
            return None

    # ── Paginación ────────────────────────────────────────────────────────────

    def _has_next_page_json(self, soup: BeautifulSoup) -> bool:
        script = soup.find("script", {"id": "__NEXT_DATA__"})
        if not script or not script.string:
            return False
        try:
            data = json.loads(script.string)
            page_props = data.get("props", {}).get("pageProps", {})
            for key in ("pagination", "paging", "paginator"):
                p = page_props.get(key) or {}
                current = p.get("current") or p.get("currentPage") or p.get("page")
                total = p.get("total") or p.get("totalPages") or p.get("pages")
                if current and total:
                    return int(current) < int(total)
        except Exception:
            pass
        return False

    def _has_next_page_html(self, soup: BeautifulSoup) -> bool:
        next_link = (
            soup.find("a", {"rel": "next"})
            or soup.find("a", string=re.compile(r"siguiente|next|›|»", re.IGNORECASE))
            or soup.find(class_=lambda x: x and "next" in str(x).lower())
        )
        return next_link is not None

    # ── Utilidades ────────────────────────────────────────────────────────────

    @staticmethod
    def _attr_val(attrs: dict, item: dict, keys: List[str]) -> Optional[Any]:
        """Busca un valor probando varias keys en attrs y luego en item raíz."""
        for source in (attrs, item):
            for k in keys:
                val = source.get(k)
                if val is None:
                    continue
                if isinstance(val, dict):
                    val = val.get("value") or val.get("amount") or val.get("name")
                if val is not None:
                    return val
        return None

    @staticmethod
    def _attr_val_str(attrs: dict, keys: List[str]) -> Optional[str]:
        for k in keys:
            val = attrs.get(k)
            if val is not None:
                return str(val)
        return None
