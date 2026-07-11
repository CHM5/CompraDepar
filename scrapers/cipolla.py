"""
scrapers/cipolla.py
────────────────────
Scraper para David Cipolla Inmobiliaria (davidcipolla.com.ar).

Plataforma: Brokian (PHP, SSR)
Cards en HTML con estructura:
  h5 > a  →  "VENTA • BARRIO • TIPO • X AMBIENTES..."
  párrafo  →  dirección
  h6       →  "USD 1.800.000"
  texto    →  "4 Dormitorios", "Sup. Total 216 m2"

URL de búsqueda:
  https://davidcipolla.com.ar/propiedades?operacion=venta&tipo=departamento&zona=caba&page=N

ID: extraído del final de la URL de la publicación (--4661177)
"""

from __future__ import annotations

import logging
import re
from typing import List, Optional, Tuple
from urllib.parse import urlencode

from bs4 import BeautifulSoup, Tag

import config
from database.models import Publicacion
from scrapers.base import BaseScraper
from shared.filters import SearchFilters

logger = logging.getLogger(__name__)

PORTAL = "Cipolla"
BASE_URL = "https://davidcipolla.com.ar"
MAX_PAGES = 10

_RE_ID       = re.compile(r"--(\d+)$")
_RE_USD      = re.compile(r"USD[\s\xa0]*([\d.,]+)", re.IGNORECASE)
_RE_M2       = re.compile(r"Sup\.\s*Total\s*([\d.,]+)\s*m2", re.IGNORECASE)
_RE_DORM     = re.compile(r"(\d+)\s*Dormitorio", re.IGNORECASE)
_RE_AMB      = re.compile(r"(\d+)\s*[Aa]mbiente", re.IGNORECASE)
_RE_PISO_TITLE = re.compile(r"\bPISO\b", re.IGNORECASE)


class CipollaScraper(BaseScraper):
    """Scraper de publicaciones de departamentos en venta de David Cipolla."""

    PORTAL = PORTAL

    def build_url(self, filters: SearchFilters, page: int = 1) -> str:
        params: dict = {
            "operacion": "venta",
            "tipo": "departamento",
            "zona": "caba",
        }
        if page > 1:
            params["page"] = page
        return BASE_URL + "/propiedades?" + urlencode(params)

    def scrape(self, filters: SearchFilters) -> List[Publicacion]:
        if filters.operacion != "venta":
            logger.info("[Cipolla] Solo venta — saltando %s.", filters.operacion)
            return []
        self._filters = filters
        self.warm_up(BASE_URL)
        publicaciones: List[Publicacion] = []
        ids_vistos: set = set()
        page = 1

        while page <= self._max_pages:
            url = self.build_url(filters, page)
            logger.info("[Cipolla] Página %d → %s", page, url)
            html = self.get_page(url, extra_headers={"Referer": BASE_URL + "/"})
            if not html:
                logger.warning("[Cipolla] No se pudo obtener página %d.", page)
                break

            pubs_pagina, has_next = self._parse_page(html)
            if not pubs_pagina:
                logger.info("[Cipolla] Página %d sin resultados.", page)
                break

            pubs_nuevas = [p for p in pubs_pagina
                           if p.id_publicacion and p.id_publicacion not in ids_vistos]
            if not pubs_nuevas:
                break

            for p in pubs_nuevas:
                ids_vistos.add(p.id_publicacion)
                publicaciones.append(p)

            if not has_next:
                break
            page += 1

        logger.info("[Cipolla] Total: %d publicaciones", len(publicaciones))
        return publicaciones

    # ── Parseo de una página ──────────────────────────────────────────────────

    def _parse_page(self, html: str) -> Tuple[List[Publicacion], bool]:
        soup = BeautifulSoup(html, "lxml")
        pubs: List[Publicacion] = []

        # Cada propiedad tiene un <h5> con un <a> al detalle
        cards = soup.find_all("h5")
        for h5 in cards:
            link_tag = h5.find("a", href=re.compile(r"/propiedad/"))
            if not link_tag:
                continue
            try:
                pub = self._parse_card(h5, link_tag)
                if pub:
                    pubs.append(pub)
            except Exception as e:
                logger.debug("[Cipolla] Error parseando card: %s", e)

        # Paginación: buscar link "Siguiente" o última página numerada
        has_next = bool(soup.find("a", href=re.compile(r"[?&]page=\d+")))
        return pubs, has_next

    def _parse_card(self, h5: Tag, link_tag: Tag) -> Optional[Publicacion]:
        href = link_tag.get("href", "")
        if not href.startswith("http"):
            href = BASE_URL + href

        # ID numérico al final de la URL: /propiedad/slug--4661177
        id_match = _RE_ID.search(href)
        if not id_match:
            return None
        pub_id = id_match.group(1)

        # Título: "VENTA • BARRIO • TIPO • X AMBIENTES..."
        titulo = link_tag.get_text(strip=True)
        partes = [p.strip() for p in titulo.split("•")]
        barrio = partes[1].title() if len(partes) > 1 else None

        # Filtro: solo departamentos (excluir terrenos, locales, casas, etc.)
        tipo_str = titulo.upper()
        TIPOS_EXCLUIR = ("TERRENO", "LOTE", "LOCAL", "COCHERA", "CAMPO", "GALPÓN", "HOTEL")
        if any(t in tipo_str for t in TIPOS_EXCLUIR):
            return None

        # Cochera y balcón desde el título
        cochera = int("COCHERA" in tipo_str)
        balcon  = int(any(k in tipo_str for k in ("BALCÓN", "BALCON")))

        # Ambientes desde título
        amb_m = _RE_AMB.search(titulo)
        ambientes = int(amb_m.group(1)) if amb_m else None

        # Piso desde título
        piso_m = re.search(r"\bPISO\b.*?(\d+)", titulo, re.IGNORECASE)
        piso = int(piso_m.group(1)) if piso_m else None

        # El contenedor padre del h5 tiene los detalles
        card_div = h5.parent
        full_text = card_div.get_text(" ", strip=True) if card_div else ""

        # Dirección: primer párrafo después del h5 (texto que no es precio ni m2)
        direccion = None
        next_sib = h5.find_next_sibling()
        while next_sib:
            txt = next_sib.get_text(strip=True)
            if txt and not _RE_USD.search(txt) and not _RE_M2.search(txt) \
                    and "Dormitorio" not in txt and "Baño" not in txt:
                direccion = txt
                break
            next_sib = next_sib.find_next_sibling()

        # Precio USD
        precio = None
        h6 = card_div.find("h6") if card_div else None
        if h6:
            precio_txt = h6.get_text(strip=True)
            m = _RE_USD.search(precio_txt)
            if m:
                precio = self._parse_price(m.group(1))

        # m² total
        m2_match = _RE_M2.search(full_text)
        m2 = float(m2_match.group(1).replace(",", ".")) if m2_match else None

        # Dormitorios
        dorm_m = _RE_DORM.search(full_text)
        dormitorios = int(dorm_m.group(1)) if dorm_m else None
        # Aproximar ambientes si no estaba en el título
        if ambientes is None and dormitorios:
            ambientes = dormitorios + 1

        # Imagen (primera img o background-image en el card)
        imagen_url = None
        img_tag = (card_div or h5).find_previous("img") if card_div else None
        if img_tag and img_tag.get("src"):
            imagen_url = img_tag["src"]

        return Publicacion(
            id_publicacion=pub_id,
            portal=PORTAL,
            url=href,
            inmobiliaria="David Cipolla",
            direccion=direccion,
            barrio=barrio,
            ambientes=ambientes,
            m2_totales=m2,
            m2_cubiertos=m2,
            precio_usd=precio,
            piso=piso,
            balcon=balcon,
            cochera=cochera,
            imagen_url=imagen_url,
        )

    def _parse_price(self, raw: str) -> Optional[float]:
        """Convierte '1.800.000' o '1,800,000' → 1800000.0"""
        cleaned = re.sub(r"[^\d]", "", raw)
        return float(cleaned) if cleaned else None
