"""
scrapers/zonaprop.py
────────────────────
Scraper para Zonaprop (zonaprop.com.ar).

Estrategia de extracción (por orden de prioridad):
  1. JSON embebido en <script id="__NEXT_DATA__"> (más robusto, menos frágil)
  2. Fallback a parsing HTML con múltiples selectores CSS alternativos

URL de búsqueda construida con filtros en el path (formato estándar de Zonaprop).

NOTA: Si el sitio cambia su estructura, ajustar los selectores en
      _CARD_SELECTORS y _parse_html_card(), o actualizar el path de JSON
      en _extract_postings_from_json().
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

PORTAL = "Zonaprop"
BASE_URL = "https://www.zonaprop.com.ar"
MAX_PAGES = 25  # límite de seguridad

# Selectores CSS de tarjetas de propiedad (varios como fallback)
_CARD_SELECTORS = [
    "div.postingCardLayout-module__posting-card-layout[data-id]",
    "[data-qa^='posting '][data-id]",
    '[data-qa="POSTING_CARD"]',
    "[data-id]",
    "article.postingCard",
    "div.postingCard",
    "div[class*='postingCard']",
    "section[class*='posting']",
    "[class*='CardContainer']",
    "[class*='postingCard']",
    "[class*='posting-card']",
]


# ══════════════════════════════════════════════════════════════════════════════
# SCRAPER
# ══════════════════════════════════════════════════════════════════════════════


class ZonapropScraper(BaseScraper):
    """Scraper de publicaciones de departamentos en venta de Zonaprop."""

    PORTAL = PORTAL

    # ── URL ───────────────────────────────────────────────────────────────────

    def build_url(self, filters: SearchFilters, page: int = 1) -> str:
        """Construye la URL de búsqueda dinámicamente desde SearchFilters."""
        barrios = filters.barrios
        barrios_str = "-".join(barrio_to_slug(b) for b in barrios) if barrios else "capital-federal"
        operacion = filters.operacion  # 'venta' o 'alquiler'
        m2_min = filters.m2_min or 0

        if operacion == "alquiler":
            # Alquiler: precios en pesos; omitir segmento de precio si no fue especificado
            currency = "pesos"
            if filters.precio_max:
                price_segment = f"-{filters.precio_max}-{currency}"
            elif filters.precio_min:
                price_segment = f"-{filters.precio_min}-{filters.precio_max or 999_999}-{currency}"
            else:
                price_segment = ""  # sin filtro de precio en URL
        else:
            # Venta: precios en dólares
            precio_max = filters.precio_max or 999_999
            if filters.precio_min:
                price_segment = f"-{filters.precio_min}-{precio_max}-dolar"
            else:
                price_segment = f"-{precio_max}-dolar"

        path = (
            f"/departamentos-{operacion}-{barrios_str}"
            f"-mas-de-{m2_min}-m2-cubiertos"
            f"{price_segment}"
        )
        if filters.balcon is True:
            path += "-con-balcon"
        if page > 1:
            path += f"-pagina-{page}"
        return BASE_URL + path + ".html"

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
            logger.info("[Zonaprop] Página %d → %s", page, url)

            html = self.get_page(url)
            if not html:
                logger.warning("[Zonaprop] No se pudo obtener página %d, deteniendo.", page)
                break

            pubs_pagina, hay_siguiente = self._parse_page(html, url)

            if not pubs_pagina:
                logger.info("[Zonaprop] Página %d sin resultados, deteniendo.", page)
                break

            pubs_nuevas = [p for p in pubs_pagina if p.id_publicacion and p.id_publicacion not in ids_vistos]
            if not pubs_nuevas:
                logger.info("[Zonaprop] Página %d repetida (sin IDs nuevos), deteniendo.", page)
                break

            publicaciones.extend(pubs_nuevas)
            ids_vistos.update(p.id_publicacion for p in pubs_nuevas)
            logger.info("[Zonaprop] Página %d: %d pubs encontradas (total: %d)",
                        page, len(pubs_nuevas), len(publicaciones))

            if not hay_siguiente:
                break

            page += 1
            time.sleep(config.DELAY_ENTRE_PAGINAS)

        logger.info("[Zonaprop] Scraping completo: %d publicaciones", len(publicaciones))
        return publicaciones

    # ── Parsing de página ─────────────────────────────────────────────────────

    def _parse_page(self, html: str, base_url: str) -> Tuple[List[Publicacion], bool]:
        """Retorna (publicaciones_de_la_pagina, hay_pagina_siguiente)."""
        soup = BeautifulSoup(html, "lxml")

        # Intento 1: JSON de Next.js
        pubs = self._parse_from_next_data(soup)
        if pubs is not None:
            has_next = self._has_next_page_json(soup) or len(pubs) >= 20
            return pubs, has_next

        # Intento 2: HTML
        pubs = self._parse_from_html(soup)
        has_next = self._has_next_page_html(soup)

        # DEBUG: guardar HTML para diagn\u00f3stico cuando no se encuentra nada
        if not pubs and logger.isEnabledFor(logging.DEBUG):
            from pathlib import Path as _Path
            dbg = _Path("logs/debug_zonaprop_page.html")
            dbg.parent.mkdir(exist_ok=True)
            dbg.write_text(base_url + "\n" + html, encoding="utf-8")
            logger.debug("[Zonaprop] HTML de diagn\u00f3stico guardado en %s", dbg)

        return pubs, has_next

    # ── Extracci\u00f3n desde __NEXT_DATA__ ────────────────────────────────────────

    def _parse_from_next_data(self, soup: BeautifulSoup) -> Optional[List[Publicacion]]:
        script = soup.find("script", {"id": "__NEXT_DATA__"})
        if not script or not script.string:
            return None

        try:
            data = json.loads(script.string)
        except json.JSONDecodeError as e:
            logger.debug("[Zonaprop] Error JSON __NEXT_DATA__: %s", e)
            return None

        postings = self._extract_postings_from_json(data)
        if postings is None:
            logger.debug("[Zonaprop] __NEXT_DATA__ presente pero sin postings en rutas conocidas.")
            return None

        result: List[Publicacion] = []
        for p in postings:
            pub = self._parse_next_data_item(p)
            if pub:
                result.append(pub)

        return result

    def _extract_postings_from_json(self, data: Dict[str, Any]) -> Optional[List[dict]]:
        """Intenta extraer la lista de postings desde varias rutas conocidas del JSON."""
        page_props = data.get("props", {}).get("pageProps", {})

        # Ruta 1: listPostings.listPostings (más común)
        postings = page_props.get("listPostings", {}).get("listPostings")
        if isinstance(postings, list):
            return postings

        # Ruta 2: postings directos
        postings = page_props.get("postings")
        if isinstance(postings, list):
            return postings

        # Ruta 3: searchResult.postings
        postings = page_props.get("searchResult", {}).get("postings")
        if isinstance(postings, list):
            return postings

        # Ruta 4: initialState (algunos sitios)
        initial = page_props.get("initialState", {})
        postings = initial.get("postings") or initial.get("listPostings", {}).get("listPostings")
        if isinstance(postings, list):
            return postings

        # Ruta 5: b\u00fasqueda profunda recursiva (estructura cambiada / desconocida)
        postings = self._deep_find_postings(data)
        if postings:
            logger.debug("[Zonaprop] Postings hallados por b\u00fasqueda profunda: %d", len(postings))
            return postings

        return None

    def _deep_find_postings(self, node: Any, _depth: int = 0) -> Optional[List[dict]]:
        """Recorre el \u00e1rbol JSON buscando el primer array con aspecto de listado de propiedades."""
        if _depth > 7:
            return None
        if isinstance(node, list) and len(node) >= 2:
            first = node[0]
            if isinstance(first, dict):
                posting_keys = {"postingId", "id", "propertyId", "url",
                                "price", "precio", "location", "address"}
                if len(posting_keys & first.keys()) >= 2:
                    return node
        if isinstance(node, dict):
            # Primero buscar en keys con nombres relacionados a listings
            priority = ("postings", "listings", "items", "results", "properties", "data", "list")
            for k in priority:
                if k in node:
                    found = self._deep_find_postings(node[k], _depth + 1)
                    if found:
                        return found
            # Luego el resto de keys
            for k, v in node.items():
                if k not in priority:
                    found = self._deep_find_postings(v, _depth + 1)
                    if found:
                        return found
        return None

    def _parse_next_data_item(self, posting: dict) -> Optional[Publicacion]:
        """Mapea un item del JSON de Next.js al modelo Publicacion."""
        try:
            id_pub = str(
                posting.get("postingId")
                or posting.get("id")
                or posting.get("propertyId")
                or ""
            ).strip()
            if not id_pub:
                return None

            # URL
            url_rel = posting.get("url") or posting.get("link") or ""
            url = BASE_URL + url_rel if url_rel.startswith("/") else url_rel
            if not url:
                url = BASE_URL

            # Imagen principal
            imagen_url = self._extract_image_url(posting)

            # Precio en USD
            precio_usd = self._extract_price_from_json(posting)

            # Ubicación
            location = posting.get("location") or posting.get("address") or {}
            if isinstance(location, str):
                direccion = location
                barrio = self._detect_barrio(location)
            else:
                direccion = (
                    location.get("address")
                    or location.get("postingAddress")
                    or location.get("street")
                    or ""
                )
                barrio = (
                    location.get("neighborhood", {}).get("name")
                    or location.get("barrio")
                    or self._detect_barrio(direccion)
                )

            # Features
            features = posting.get("mainFeatures") or posting.get("features") or {}
            ambientes = self._to_int(
                self._feature_val(features, ["CFT100", "rooms", "ambientes", "roomsTotal"])
            )
            m2_cub = self._to_float(
                self._feature_val(features, ["CFT102", "coveredArea", "m2Cubiertos",
                                             "coveredSurface", "totalArea"])
            )
            m2_desc = self._to_float(
                self._feature_val(features, ["CFT103", "uncoveredArea", "m2Descubiertos",
                                             "uncoveredSurface"])
            )
            m2_tot = self._to_float(
                self._feature_val(features, ["CFT101", "totalArea", "m2Totales", "surface"])
            )
            piso = self._to_int(
                self._feature_val(features, ["CFT104", "floor", "piso", "floorNumber"])
            )
            antiguedad = self._to_int(
                self._feature_val(features, ["CFT105", "propertyAge", "antiguedad",
                                             "constructionYear"])
            )

            # Si antigüedad viene como año de construcción, convertir a años
            if antiguedad and antiguedad > 1900:
                from datetime import date
                antiguedad = max(0, date.today().year - antiguedad)

            # Características generales
            gen_features = posting.get("generalFeatures") or {}
            all_text = json.dumps(posting, ensure_ascii=False).lower()

            disposicion = (
                gen_features.get("disposicion")
                or gen_features.get("disposition")
                or self._parse_disposicion(all_text)
            )
            orientacion = (
                gen_features.get("orientacion")
                or gen_features.get("orientation")
                or self._parse_orientacion(all_text)
            )

            descripcion = (
                posting.get("descriptionNormalized")
                or posting.get("description")
                or ""
            )

            balcon = self._detect_bool(descripcion + all_text,
                                       ["balcón", "balcon", "balcones", "terraza"])
            cochera = self._detect_bool(descripcion + all_text,
                                        ["cochera", "garage", "garaje", "estacionamiento"])
            amenities_list = self._extract_amenities(descripcion + all_text)

            expensas = self._to_float(
                posting.get("expenses", {}).get("amount")
                if isinstance(posting.get("expenses"), dict)
                else posting.get("expensas") or posting.get("expenses")
            )

            publisher = posting.get("publisher") or {}
            inmobiliaria = (
                publisher.get("name") or publisher.get("publisherName")
                if isinstance(publisher, dict) else str(publisher)
            ) or None

            fecha_pub = posting.get("createdAt") or posting.get("dateCreated") or None

            # Aplicar filtros
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
                direccion=str(direccion) if direccion else None,
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
                amenities=amenities_list and ", ".join(amenities_list),
                descripcion=descripcion[:2000] if descripcion else None,
                fecha_publicacion=fecha_pub,
                imagen_url=imagen_url,
            )

        except Exception as e:
            logger.debug("[Zonaprop] Error parseando item JSON id=%s: %s",
                         posting.get("postingId", "?"), e, exc_info=True)
            return None

    @staticmethod
    def _extract_image_url(posting: dict) -> Optional[str]:
        """Extrae la URL de la imagen principal del posting."""
        # Ruta 1: postingPictures (más común en Zonaprop)
        pics = posting.get("postingPictures") or []
        if pics and isinstance(pics, list):
            first = pics[0]
            if isinstance(first, dict):
                return first.get("url") or first.get("src") or first.get("picture")
            if isinstance(first, str):
                return first
        # Ruta 2: multimedia.pictures
        multimedia = posting.get("multimedia") or {}
        if isinstance(multimedia, dict):
            mpics = multimedia.get("pictures") or []
            if mpics:
                first = mpics[0]
                if isinstance(first, dict):
                    return first.get("url") or first.get("src")
                if isinstance(first, str):
                    return first
        # Ruta 3: photos / visuals / images
        for key in ("photos", "visuals", "images"):
            photos = posting.get(key) or []
            if photos:
                first = photos[0]
                if isinstance(first, dict):
                    return first.get("url") or first.get("src")
                if isinstance(first, str):
                    return first
        return None

    def _extract_price_from_json(self, posting: dict) -> Optional[float]:
        """Extrae el precio USD de las distintas estructuras de precio."""
        # Estructura "priceOperationTypes" → venta en USD
        price_ops = posting.get("priceOperationTypes") or []
        for op in price_ops:
            if not isinstance(op, dict):
                continue
            op_type = (op.get("priceOperationType") or "").lower()
            if "venta" in op_type or "sale" in op_type or "sell" in op_type:
                for p in (op.get("prices") or []):
                    currency = (p.get("currency") or "").upper()
                    if currency in ("USD", "U$S", "DOLAR", "DOLARES"):
                        try:
                            return float(p.get("amount") or 0) or None
                        except (ValueError, TypeError):
                            pass

        # Estructura "price" directa
        price_raw = posting.get("price") or posting.get("precio")
        if isinstance(price_raw, (int, float)):
            val = float(price_raw)
            return val if val > 1000 else None
        if isinstance(price_raw, str):
            return self._parse_precio(price_raw)
        if isinstance(price_raw, dict):
            currency = (price_raw.get("currency") or "").upper()
            if currency in ("USD", "U$S"):
                return self._to_float(price_raw.get("amount"))

        return None

    # ── Extracción desde HTML (fallback) ──────────────────────────────────────

    def _parse_from_html(self, soup: BeautifulSoup) -> List[Publicacion]:
        """Parsea tarjetas de propiedades directamente del HTML."""
        cards: List[Tag] = []
        for sel in _CARD_SELECTORS:
            cards = soup.select(sel)
            if cards:
                logger.debug("[Zonaprop HTML] Selector '%s' → %d cards", sel, len(cards))
                break

        if not cards:
            logger.warning("[Zonaprop HTML] No se encontraron cards con ningún selector.")
            return []

        result: List[Publicacion] = []
        ids_local: set[str] = set()
        for card in cards:
            pub = self._parse_html_card(card)
            if pub and self.apply_filters(
                precio_usd=pub.precio_usd,
                m2_totales=pub.m2_totales or pub.m2_cubiertos,
                piso=pub.piso,
                disposicion=pub.disposicion,
                antiguedad=pub.antiguedad,
                barrio=pub.barrio,
                balcon=pub.balcon,
            ):
                if pub.id_publicacion in ids_local:
                    continue
                ids_local.add(pub.id_publicacion)
                result.append(pub)
        return result

    def _parse_html_card(self, card: Tag) -> Optional[Publicacion]:
        """Extrae datos de una tarjeta HTML individual."""
        try:
            posting_type = str(card.get("data-posting-type") or "").strip().upper()
            if posting_type and posting_type != "PROPERTY":
                return None

            id_pub = (
                card.get("data-id")
                or card.get("data-posting-id")
                or card.get("id", "").replace("posting-", "")
            )
            if not id_pub:
                return None

            id_pub = str(id_pub).strip()

            # URL
            url_rel = card.get("data-to-posting") or ""
            if not url_rel:
                link = card.find("a", href=True)
                url_rel = link["href"] if link else ""
            url = BASE_URL + url_rel if str(url_rel).startswith("/") else str(url_rel)

            # Texto completo de la tarjeta para extracciones genéricas
            full_text = card.get_text(" ", strip=True)

            # Precio
            price_elem = card.select_one('[data-qa="POSTING_CARD_PRICE"]')
            if not price_elem:
                price_elem = card.find(
                    lambda t: t.name in ("span", "div", "p") and
                    re.search(r"USD|U\$[Ss]|\$|precio|price", t.get("class", [""])[0]
                              if t.get("class") else "", re.IGNORECASE)
                )
            precio_usd = self._parse_precio(
                price_elem.get_text(strip=True) if price_elem else full_text
            )

            # Dirección y barrio
            addr_elem = card.select_one('[data-qa="POSTING_CARD_LOCATION"]')
            if not addr_elem:
                addr_elem = card.find(
                    class_=lambda x: x and any(
                        a in str(x).lower() for a in ["address", "location", "direccion"]
                    )
                )
            direccion = addr_elem.get_text(strip=True) if addr_elem else ""
            barrio = self._detect_barrio(full_text)

            # Features desde el elemento específico (más preciso que full_text)
            feat_elem = card.select_one('[data-qa="POSTING_CARD_FEATURES"]')
            feat_text = feat_elem.get_text(" ", strip=True) if feat_elem else full_text

            m2_cub, m2_desc, m2_tot = self._parse_m2(feat_text)
            ambientes = self._parse_ambientes(feat_text)
            piso = self._parse_piso(feat_text)
            antiguedad = self._parse_antiguedad(feat_text)
            disposicion = self._parse_disposicion(full_text)
            orientacion = self._parse_orientacion(full_text)

            # Expensas: elemento data-qa="expensas" o fallback a full_text
            exp_elem = card.select_one('[data-qa="expensas"]')
            if exp_elem:
                # Zonaprop usa formato "$ 228.900 Expensas" → extraer número directamente
                exp_text = exp_elem.get_text(" ", strip=True)
                m_exp = re.search(r"([\d.,]+)", exp_text)
                expensas = self._to_float(self._clean_num(m_exp.group(1))) if m_exp else None
            else:
                expensas = self._parse_expensas(full_text)

            balcon = self._detect_bool(full_text, ["balcón", "balcon", "terraza"])
            cochera = self._detect_bool(full_text, ["cochera", "garage", "garaje"])
            amenities_list = self._extract_amenities(full_text)

            return Publicacion(
                id_publicacion=id_pub,
                portal=PORTAL,
                url=url,
                direccion=direccion or None,
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
            )

        except Exception as e:
            logger.debug("[Zonaprop HTML] Error parseando card: %s", e, exc_info=True)
            return None

    # ── Paginación ────────────────────────────────────────────────────────────

    def _has_next_page_json(self, soup: BeautifulSoup) -> bool:
        script = soup.find("script", {"id": "__NEXT_DATA__"})
        if not script or not script.string:
            return False
        try:
            data = json.loads(script.string)
            paging = (
                data.get("props", {})
                    .get("pageProps", {})
                    .get("listPostings", {})
                    .get("paging", {})
            )
            current = paging.get("currentPage", 1)
            total = paging.get("totalPages", 1)
            return current < total
        except Exception:
            return False

    def _has_next_page_html(self, soup: BeautifulSoup) -> bool:
        # Zonaprop no usa rel="next" — usa su propio pager con hrefs tipo "pagina-N"
        return bool(
            soup.find("a", {"rel": "next"})
            or soup.find("a", string=re.compile(r"siguiente|next|›|»", re.IGNORECASE))
            or soup.find("a", href=re.compile(r"pagina-\d+"))
        )

    # ── Utilidades internas ───────────────────────────────────────────────────

    @staticmethod
    def _feature_val(features: dict, keys: List[str]) -> Optional[Any]:
        """Intenta obtener un valor de `features` probando múltiples keys."""
        for k in keys:
            val = features.get(k)
            if val is None:
                continue
            if isinstance(val, dict):
                val = val.get("value") or val.get("amount") or val.get("name")
            if val is not None:
                return val
        return None
