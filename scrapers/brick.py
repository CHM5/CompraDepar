"""
scrapers/brick.py
──────────────────
Scraper para BRICK Propiedades (brick.com.ar).

Plataforma: Next.js / SSR — cards en HTML
Cards tienen un <a> con alt/title en formato estructurado:
  "Departamento en Venta en BARRIO / C.A.B.A. DIRECCION Piso N X amb Y dorm Z baños W m²"

Precio:  texto "U$S 74.500.-"
ID:      primer segmento numérico de la URL: /propiedades/1033786-slug
URL:     https://brick.com.ar/propiedades-en-venta?tipo=departamento&pagina=N
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

PORTAL = "Brick"
BASE_URL = "https://brick.com.ar"
MAX_PAGES = 15

_RE_ID        = re.compile(r"/propiedades/(\d+)-")
_RE_PRECIO    = re.compile(r"U\$S\s*([\d.,]+)", re.IGNORECASE)
_RE_M2        = re.compile(r"(\d+)\s*m[²2]", re.IGNORECASE)
_RE_AMB       = re.compile(r"(\d+)\s*amb", re.IGNORECASE)
_RE_DORM      = re.compile(r"(\d+)\s*dorm", re.IGNORECASE)
_RE_PISO      = re.compile(r"Piso\s+(\d+|PB)", re.IGNORECASE)
_RE_BARRIO    = re.compile(r"en\s+([A-ZÁÉÍÓÚÑÜ ,.\-]+?)\s*/\s*C\.A\.B\.A\.", re.IGNORECASE)
_RE_DIR       = re.compile(
    r"C\.A\.B\.A\.\s+(.+?)(?:\s+\d+\s+amb|\s+Piso\s+\d|\s+Piso\s+PB|$)",
    re.IGNORECASE,
)


class BrickScraper(BaseScraper):
    """Scraper de publicaciones de departamentos en venta de BRICK Propiedades."""

    PORTAL = PORTAL

    def build_url(self, filters: SearchFilters, page: int = 1) -> str:
        params: dict = {"tipo": "departamento"}
        if filters.precio_min:
            params["precio_desde"] = filters.precio_min
        if filters.precio_max:
            params["precio_hasta"] = filters.precio_max
        if filters.m2_min:
            params["superficie_desde"] = filters.m2_min
        if page > 1:
            params["pagina"] = page
        return BASE_URL + "/propiedades-en-venta?" + urlencode(params)

    def scrape(self, filters: SearchFilters) -> List[Publicacion]:
        if filters.operacion != "venta":
            logger.info("[Brick] Solo venta — saltando %s.", filters.operacion)
            return []
        self._filters = filters
        self.warm_up(BASE_URL)
        publicaciones: List[Publicacion] = []
        ids_vistos: set = set()
        page = 1

        while page <= self._max_pages:
            url = self.build_url(filters, page)
            logger.info("[Brick] Página %d → %s", page, url)
            html = self.get_page(url, extra_headers={"Referer": BASE_URL + "/"})
            if not html:
                logger.warning("[Brick] No se pudo obtener página %d.", page)
                break

            pubs_pagina, has_next = self._parse_page(html)
            if not pubs_pagina:
                logger.info("[Brick] Página %d sin resultados.", page)
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

        logger.info("[Brick] Total: %d publicaciones", len(publicaciones))
        return publicaciones

    # ── Parseo de página ──────────────────────────────────────────────────────

    def _parse_page(self, html: str) -> Tuple[List[Publicacion], bool]:
        soup = BeautifulSoup(html, "lxml")
        pubs: List[Publicacion] = []
        seen_ids: set = set()

        # Cada card tiene un <a href="/propiedades/{id}-..."> con el texto descriptivo
        for a_tag in soup.find_all("a", href=_RE_ID):
            href = a_tag.get("href", "")
            id_match = _RE_ID.search(href)
            if not id_match:
                continue
            pub_id = id_match.group(1)
            if pub_id in seen_ids:
                continue
            seen_ids.add(pub_id)

            # El texto completo del link contiene todos los datos
            texto = a_tag.get_text(" ", strip=True)
            if not texto or len(texto) < 20:
                continue

            # Filtrar: solo departamentos de CABA
            if "departamento" not in texto.lower():
                continue
            if "C.A.B.A." not in texto and "CABA" not in texto.upper():
                continue

            try:
                pub = self._parse_card(href, texto, a_tag, soup)
                if pub:
                    pubs.append(pub)
            except Exception as e:
                logger.debug("[Brick] Error parseando card %s: %s", pub_id, e)

        # Paginación: si hay algún link con pagina=N+1 en el HTML
        has_next = bool(soup.find("a", href=re.compile(r"pagina=\d+")))
        return pubs, has_next

    def _parse_card(self, href: str, texto: str, a_tag: Tag, soup: BeautifulSoup) -> Optional[Publicacion]:
        id_match = _RE_ID.search(href)
        if not id_match:
            return None
        pub_id = id_match.group(1)
        url = BASE_URL + href if href.startswith("/") else href

        # Barrio
        barrio_m = _RE_BARRIO.search(texto)
        barrio = barrio_m.group(1).strip().title() if barrio_m else None

        # Dirección
        dir_m = _RE_DIR.search(texto)
        direccion = dir_m.group(1).strip().title() if dir_m else None

        # Piso
        piso_m = _RE_PISO.search(texto)
        piso_raw = piso_m.group(1) if piso_m else None
        piso = 0 if piso_raw == "PB" else (int(piso_raw) if piso_raw else None)

        # Ambientes
        amb_m = _RE_AMB.search(texto)
        ambientes = int(amb_m.group(1)) if amb_m else None

        # Dormitorios
        dorm_m = _RE_DORM.search(texto)
        dormitorios = int(dorm_m.group(1)) if dorm_m else None

        # m² (último número antes de "m²" en el texto)
        m2_matches = _RE_M2.findall(texto)
        m2 = float(m2_matches[-1]) if m2_matches else None

        # Precio: buscar "U$S X" en el texto del contenedor padre
        precio = None
        parent = a_tag.parent
        for _ in range(4):   # subir hasta 4 niveles
            if parent is None:
                break
            parent_text = parent.get_text(" ", strip=True)
            precio_m = _RE_PRECIO.search(parent_text)
            if precio_m:
                raw = precio_m.group(1).replace(".", "").replace(",", ".")
                try:
                    precio = float(raw)
                except ValueError:
                    pass
                break
            parent = parent.parent

        # Imagen: primera img en el container
        imagen_url = None
        if a_tag.parent:
            img = a_tag.parent.find("img")
            if img and img.get("src"):
                src = img["src"]
                if not src.startswith("data:"):
                    imagen_url = src

        # Cochera: si el slug/texto lo menciona
        cochera = int("cochera" in href.lower() or "c/dep" in texto.lower())
        # Balcón: si está en el texto
        balcon = int(any(k in texto.lower() for k in ("balcón", "balcon", "balc.")))

        return Publicacion(
            id_publicacion=pub_id,
            portal=PORTAL,
            url=url,
            inmobiliaria="Brick",
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
