"""
scrapers/base.py
────────────────
Clase base para todos los scrapers.
Provee:
  - Sesión HTTP con reintentos automáticos y backoff exponencial
  - Rotación de User-Agent
  - Helpers de parsing comunes (precios, m², pisos, barrios, etc.)
  - Filtros de pre-selección
"""

from __future__ import annotations

import logging
import random
import re
import time
from abc import ABC, abstractmethod
from typing import List, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import config
from database.models import Publicacion
from shared.filters import SearchFilters

logger = logging.getLogger(__name__)

# ─── Expresiones regulares de extracción ──────────────────────────────────────
_RE_USD = re.compile(
    r"(?:USD|U\$[Ss]|US\$|Dólares?)\s*[:\.]?\s*([\d.,]+)", re.IGNORECASE
)
_RE_PRECIO_SOLO = re.compile(r"([\d]{2,3}(?:[.,]\d{3})+|\d{5,7})")
_RE_AMBIENTES = re.compile(
    r"(\d+)\s*(?:amb(?:iente)?s?\.?|ambientes?|env\.?)", re.IGNORECASE
)
_RE_M2_CUB = re.compile(
    r"([\d]+(?:[.,]\d+)?)\s*m[²2]\s*(?:cub\.?|cubiertos?)", re.IGNORECASE
)
_RE_M2_DESC = re.compile(
    r"([\d]+(?:[.,]\d+)?)\s*m[²2]\s*(?:desc\.?|descubiertos?|tot\.?|totales?|semi)", re.IGNORECASE
)
_RE_M2_TOT = re.compile(
    r"([\d]+(?:[.,]\d+)?)\s*m[²2]\s*(?:tot(?:ales?)?\.?)", re.IGNORECASE
)
_RE_M2_GENERIC = re.compile(r"([\d]+(?:[.,]\d+)?)\s*m[²2]", re.IGNORECASE)
_RE_PISO = re.compile(
    r"(?:piso|p\.?|planta)\s*(\d+)|(\d+)[°º]\s*(?:piso|p\.?)", re.IGNORECASE
)
_RE_ANTIGUEDAD = re.compile(
    r"(?:antigüedad|antiguedad|construido|años?)\s*[:\s]*(\d+)\s*a[ñn]os?", re.IGNORECASE
)
_RE_EXPENSAS = re.compile(
    r"(?:expensas?|gastos?\s*comunes?)\s*[:\$]?\s*(?:ARS|AR\$|\$)?\s*([\d.,]+)", re.IGNORECASE
)


# ── Barrios de CABA (lista exhaustiva para detección en texto) ─────────────────
_CABA_BARRIOS: List[str] = [
    "Agronomía", "Almagro", "Balvanera", "Barracas", "Barrio Norte",
    "Belgrano", "Boedo", "Caballito", "Chacarita", "Coghlan", "Colegiales",
    "Constitución", "Flores", "Floresta", "La Boca", "La Paternal",
    "Liniers", "Mataderos", "Monserrat", "Monte Castro",
    "Nueva Pompeya", "Núñez", "Palermo", "Parque Avellaneda",
    "Parque Chacabuco", "Parque Chas", "Parque Patricios", "Puerto Madero",
    "Recoleta", "Retiro", "Saavedra", "San Cristóbal", "San Nicolás",
    "San Telmo", "Tribunales", "Vélez Sársfield", "Versalles",
    "Villa Crespo", "Villa del Parque", "Villa Devoto",
    "Villa General Mitre", "Villa Lugano", "Villa Luro",
    "Villa Ortúzar", "Villa Pueyrredón", "Villa Real", "Villa Riachuelo",
    "Villa Santa Rita", "Villa Soldati", "Villa Urquiza",
]

# pre-computar versión normalizada (sin tildes, minúsculas) → canónico
_BARRIO_NORM_MAP: dict = {}
for _b in _CABA_BARRIOS:
    _n = _b.lower()
    for _from, _to in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"), ("ü", "u")):
        _n = _n.replace(_from, _to)
    _BARRIO_NORM_MAP[_n] = _b
    _BARRIO_NORM_MAP[_b.lower()] = _b


def barrio_to_slug(barrio: str) -> str:
    """Convierte un nombre de barrio a slug apto para URLs.
    Ej: 'La Paternal' → 'la-paternal', 'Núñez' → 'nunez'
    """
    s = barrio.lower()
    for _from, _to in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"), ("ü", "u"), ("ñ", "n")):
        s = s.replace(_from, _to)
    s = re.sub(r"\s+", "-", s.strip())
    s = re.sub(r"[^a-z0-9-]", "", s)
    return s


# ══════════════════════════════════════════════════════════════════════════════
# BASE SCRAPER
# ══════════════════════════════════════════════════════════════════════════════


class BaseScraper(ABC):
    """Clase base abstracta para los scrapers de portales inmobiliarios."""

    PORTAL: str = "Base"

    def __init__(self) -> None:
        self.session = self._build_session()
        self._filters: Optional[SearchFilters] = None  # set by scrape(filters)
        self._max_pages: int = 9999  # override to limit pagination (e.g. 1 for free plan)

    # ── Método principal a implementar en subclases ────────────────────────────

    @abstractmethod
    def scrape(self, filters: SearchFilters) -> List[Publicacion]:
        """Realiza el scraping con los filtros dados y retorna publicaciones."""
        ...

    # ── Sesión HTTP ───────────────────────────────────────────────────────────

    def _build_session(self) -> requests.Session:
        try:
            import cloudscraper as _cs
            session = _cs.create_scraper(
                browser={"browser": "chrome", "platform": "linux", "mobile": False},
                delay=10,
            )
            logger.debug("[%s] Session: cloudscraper activo (bypass anti-bot)", self.PORTAL)
            return session
        except ImportError:
            logger.warning(
                "[%s] cloudscraper no instalado — usando requests est\u00e1ndar. "
                "Instalar con: pip install cloudscraper",
                self.PORTAL,
            )
        session = requests.Session()
        retry_strategy = Retry(
            total=config.REQUEST_RETRIES,
            backoff_factor=config.REQUEST_RETRY_DELAY,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "HEAD"],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def warm_up(self, base_url: str) -> None:
        """Visita la homepage del portal para obtener cookies de sesión."""
        try:
            headers = {
                "User-Agent": random.choice(config.USER_AGENTS),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
            }
            resp = self.session.get(base_url, headers=headers, timeout=config.REQUEST_TIMEOUT)
            logger.debug("[%s] Warm-up %s → HTTP %d", self.PORTAL, base_url, resp.status_code)
            time.sleep(random.uniform(2.0, 4.0))
        except Exception as e:
            logger.debug("[%s] Warm-up falló (continúa de todas formas): %s", self.PORTAL, e)

    def get_page(self, url: str, extra_headers: Optional[dict] = None) -> Optional[str]:
        """Descarga una página HTML con reintentos y pausa anti-ban.

        Retorna el HTML como string, o None si falla definitivamente.
        """
        headers = {
            "User-Agent": random.choice(config.USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Cache-Control": "max-age=0",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
        }
        if extra_headers:
            headers.update(extra_headers)

        for attempt in range(1, config.REQUEST_RETRIES + 1):
            try:
                time.sleep(random.uniform(config.DELAY_ENTRE_REQUESTS * 0.8,
                                          config.DELAY_ENTRE_REQUESTS * 1.2))
                response = self.session.get(
                    url,
                    headers=headers,
                    timeout=config.REQUEST_TIMEOUT,
                    allow_redirects=True,
                )
                status = response.status_code
                if status >= 400:
                    logger.warning("[%s] HTTP %d en %s (intento %d/%d)",
                                   self.PORTAL, status, url, attempt, config.REQUEST_RETRIES)
                    if status in (403, 404, 410):
                        logger.warning("[%s] Error %d — deteniendo reintentos (anti-bot o no encontrado).", self.PORTAL, status)
                        return None
                elif "text/html" not in response.headers.get("Content-Type", "text/html"):
                    logger.warning("[%s] Content-Type inesperado '%s': %s",
                                   self.PORTAL, response.headers.get("Content-Type"), url)
                    return None
                elif self._is_blocked(response.text):
                    logger.warning("[%s] CAPTCHA/bloqueo detectado (intento %d/%d)",
                                   self.PORTAL, attempt, config.REQUEST_RETRIES)
                else:
                    return response.text

            except requests.exceptions.ConnectionError as e:
                logger.warning("[%s] Error de conexión en %s: %s", self.PORTAL, url, e)
            except requests.exceptions.Timeout:
                logger.warning("[%s] Timeout en %s (intento %d/%d)",
                               self.PORTAL, url, attempt, config.REQUEST_RETRIES)
            except requests.exceptions.RequestException as e:
                logger.error("[%s] Error inesperado en %s: %s", self.PORTAL, url, e)
                return None

            if attempt < config.REQUEST_RETRIES:
                delay = config.REQUEST_RETRY_DELAY * (2 ** (attempt - 1))
                logger.info("[%s] Reintentando en %.1fs…", self.PORTAL, delay)
                time.sleep(delay)

        logger.error("[%s] No se pudo obtener %s tras %d intentos",
                     self.PORTAL, url, config.REQUEST_RETRIES)
        return None

    @staticmethod
    def _is_blocked(html: str) -> bool:
        """Detecta si la respuesta es una p\u00e1gina de bloqueo de Cloudflare/DDoS-Guard.

        Evita falsos positivos: muchas p\u00e1ginas leg\u00edtimas incluyen la palabra
        'captcha' en scripts de analytics o reCAPTCHA embebido.
        """
        if not html or len(html) < 300:
            return True
        lower = html.lower()
        # Cloudflare JS challenge: ambos patrones juntos = challenge real
        if "just a moment" in lower and "checking your browser" in lower:
            return True
        # P\u00e1gina de error de Cloudflare
        if "cf-error-code" in lower:
            return True
        # DDoS-Guard sin contenido inmobiliario
        if "ddos-guard" in lower and "departamento" not in lower:
            return True
        # Cloudflare gen\u00e9rico + p\u00e1gina muy corta sin contenido real
        if "cloudflare" in lower and len(html) < 10_000 and "departamento" not in lower:
            return True
        # JS + cookies requeridos expl\u00edcitamente (p\u00e1gina de bloqueo pura)
        if "please enable javascript" in lower and "enable cookies" in lower:
            return True
        return False

    # ── Filtros de pre-selección ──────────────────────────────────────────────

    def apply_filters(
        self,
        precio_usd: Optional[float],
        m2_totales: Optional[float],
        piso: Optional[int],
        disposicion: Optional[str],
        antiguedad: Optional[int],
        barrio: Optional[str] = None,
        balcon: Optional[bool] = None,
    ) -> bool:
        """Retorna True si la publicación pasa todos los filtros configurados.

        Cuando self._filters está definido (búsqueda dinámica), se usan sus valores.
        De lo contrario se usan los valores de config.py (modo bot/configuración fija).
        """
        f = self._filters  # búsqueda dinámica si está definida

        # ── MUST: Balcón requerido ─────────────────────────────────────────────
        # Solo rechazar si el dato es explícitamente False (no None/desconocido)
        if f is not None:
            if f.balcon is True and balcon is False:
                return False
        elif getattr(config, 'MUST_HAVE_BALCON', False) and balcon is False:
            return False

        # ── MUST: Barrio objetivo ─────────────────────────────────────────────
        barrios_objetivo = f.barrios if f is not None else config.BARRIOS_OBJETIVO
        if barrio is not None and barrios_objetivo:
            barrio_lower = barrio.lower().strip()
            en_lista = any(
                obj.lower() in barrio_lower or barrio_lower in obj.lower()
                for obj in barrios_objetivo
            )
            if not en_lista:
                # En búsqueda dinámica siempre rechazar barrio incorrecto
                # En modo config, respetar MUST_HAVE_BARRIO
                if f is not None or getattr(config, 'MUST_HAVE_BARRIO', True):
                    return False

        # Piso mínimo: solo aplica en modo config (no para búsqueda dinámica)
        if f is None and piso is not None and config.PISO_MINIMO > 0 and piso < config.PISO_MINIMO:
            return False

        # Disposición excluida: siempre aplica
        if disposicion:
            disp_lower = disposicion.lower().strip()
            for excl in config.DISPOSICION_EXCLUIR:
                if excl in disp_lower:
                    return False

        # Precio (los portales ya filtran en URL, esto es verificación extra)
        if precio_usd is not None:
            precio_min = f.precio_min if f is not None else config.PRECIO_MIN_USD
            precio_max = f.precio_max if f is not None else config.PRECIO_MAX_USD
            if precio_min is not None and precio_usd < precio_min:
                return False
            if precio_max is not None and precio_usd > precio_max:
                return False

        # Superficie mínima
        if m2_totales is not None:
            m2_min = f.m2_min if f is not None else config.M2_MINIMO
            if m2_min is not None and m2_totales < m2_min:
                return False

        # Antigüedad máxima
        if antiguedad is not None:
            if f is not None:
                if f.antiguedad_max is not None and antiguedad > f.antiguedad_max:
                    return False
            elif antiguedad > config.ANTIGUEDAD_MAXIMA:
                return False

        return True

    # ── Helpers de parsing ────────────────────────────────────────────────────

    @staticmethod
    def _clean_num(text: str) -> str:
        """Normaliza separadores numéricos argentinos a formato float."""
        text = text.strip().replace("\xa0", "").replace(" ", "")
        # Caso 1.234.567 o 1.234 (miles con punto) → quitar puntos
        # Caso 1.234,56 (miles con punto, decimal con coma) → punto decimal
        if "," in text and "." in text:
            # 1.234,56  → 1234.56
            text = text.replace(".", "").replace(",", ".")
        elif "," in text:
            # 1234,56 o 1.234 con coma como decimal
            text = text.replace(",", ".")
        elif "." in text:
            # Puede ser miles (1.234) o decimal (1.5)
            parts = text.split(".")
            if len(parts[-1]) == 3 and len(parts) > 1:
                text = text.replace(".", "")  # miles
        return text

    def _parse_precio(self, text: str) -> Optional[float]:
        """Extrae el precio en USD de un texto."""
        if not text:
            return None

        m = _RE_USD.search(text)
        if m:
            try:
                return float(self._clean_num(m.group(1)))
            except ValueError:
                pass

        # Fallback: buscar número grande que parezca precio
        m = _RE_PRECIO_SOLO.search(text)
        if m:
            try:
                val = float(self._clean_num(m.group(1)))
                if 50_000 <= val <= 500_000:
                    return val
            except ValueError:
                pass

        return None

    def _parse_m2(self, text: str) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """Retorna (m2_cubiertos, m2_descubiertos, m2_totales) del texto dado."""
        cub = desc = tot = None

        m = _RE_M2_CUB.search(text)
        if m:
            try:
                cub = float(self._clean_num(m.group(1)))
            except ValueError:
                pass

        m = _RE_M2_DESC.search(text)
        if m:
            try:
                desc = float(self._clean_num(m.group(1)))
            except ValueError:
                pass

        m = _RE_M2_TOT.search(text)
        if m:
            try:
                tot = float(self._clean_num(m.group(1)))
            except ValueError:
                pass

        # Fallback genérico si sólo hay un número con m²
        if cub is None and tot is None:
            m = _RE_M2_GENERIC.search(text)
            if m:
                try:
                    val = float(self._clean_num(m.group(1)))
                    if val >= 10:
                        cub = val
                except ValueError:
                    pass

        return cub, desc, tot

    def _parse_ambientes(self, text: str) -> Optional[int]:
        m = _RE_AMBIENTES.search(text)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                pass
        # Detectar "monoambiente"
        if re.search(r"monoambiente|1\s*amb", text, re.IGNORECASE):
            return 1
        return None

    def _parse_piso(self, text: str) -> Optional[int]:
        m = _RE_PISO.search(text)
        if m:
            val = m.group(1) or m.group(2)
            try:
                return int(val)
            except (ValueError, TypeError):
                pass
        return None

    def _parse_antiguedad(self, text: str) -> Optional[int]:
        m = _RE_ANTIGUEDAD.search(text)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                pass
        # Detectar "a estrenar"
        if re.search(r"a\s+estrenar|estrenar|estreno", text, re.IGNORECASE):
            return 0
        return None

    def _parse_expensas(self, text: str) -> Optional[float]:
        m = _RE_EXPENSAS.search(text)
        if m:
            try:
                return float(self._clean_num(m.group(1)))
            except ValueError:
                pass
        return None

    def _parse_disposicion(self, text: str) -> Optional[str]:
        text_lower = text.lower()
        for disp in ("frente", "contrafrente", "lateral", "interno"):
            if disp in text_lower:
                return disp.capitalize()
        return None

    def _parse_orientacion(self, text: str) -> Optional[str]:
        orientaciones = ["norte", "sur", "este", "oeste", "noreste", "noroeste", "sureste", "suroeste"]
        text_lower = text.lower()
        for ori in orientaciones:
            if ori in text_lower:
                return ori.capitalize()
        return None

    def _detect_bool(self, text: str, keywords: List[str]) -> bool:
        text_lower = text.lower()
        return any(kw.lower() in text_lower for kw in keywords)

    def _extract_amenities(self, text: str) -> List[str]:
        """Detecta amenities en el texto."""
        detectados: List[str] = []
        text_lower = text.lower()
        checks = {
            "Pileta": ["pileta", "piscina", "natación", "pool"],
            "SUM": ["sum", "salón de usos múltiples", "salón de fiestas", "salon usos"],
            "Gimnasio": ["gimnasio", "gym", "fitness"],
            "Solarium": ["solarium", "solario"],
            "Laundry": ["laundry", "lavandería"],
            "Quincho": ["quincho", "parrilla"],
            "Coworking": ["coworking"],
        }
        for nombre, keywords in checks.items():
            if any(kw in text_lower for kw in keywords):
                detectados.append(nombre)
        return detectados

    def _detect_barrio(self, text: str) -> Optional[str]:
        """Detecta el barrio más probable en el texto.

        Prioridad:
        1. Barrios pedidos en self._filters (búsqueda dinámica)
        2. Lista exhaustiva de barrios de CABA
        """
        text_lower = text.lower()
        # 1. Barrios solicitados en la búsqueda actual (alta prioridad)
        if self._filters and self._filters.barrios:
            for barrio in self._filters.barrios:
                b_norm = barrio.lower()
                for _f, _t in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u")):
                    b_norm = b_norm.replace(_f, _t)
                if b_norm in text_lower or barrio.lower() in text_lower:
                    return barrio
        # 2. Lista exhaustiva de CABA
        for norm, canonical in _BARRIO_NORM_MAP.items():
            if norm in text_lower:
                return canonical
        return None

    @staticmethod
    def _to_int(val) -> Optional[int]:
        if val is None:
            return None
        try:
            return int(str(val).strip().split(".")[0])
        except (ValueError, AttributeError):
            return None

    @staticmethod
    def _to_float(val) -> Optional[float]:
        if val is None:
            return None
        try:
            s = str(val).strip().replace(",", ".").replace("\xa0", "")
            return float(s)
        except (ValueError, AttributeError):
            return None
