"""
services/telegram.py
─────────────────────
Integración con el Bot de Telegram.
Envía alertas formateadas para:
  - Nueva publicación con score >= SCORE_MINIMO_ALERTA
  - Baja de precio en cualquier publicación
  - Publicación con score >= SCORE_EXCELENTE (alerta urgente)

Usa la API HTTP del Bot de Telegram directamente (sin dependencias extra).
"""

from __future__ import annotations

import logging
from typing import Optional

import time

import requests

import config
from database.models import Publicacion

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"
PARSE_MODE = "HTML"


# ══════════════════════════════════════════════════════════════════════════════
# CLIENTE
# ══════════════════════════════════════════════════════════════════════════════


class TelegramService:
    """Cliente para enviar mensajes al bot de Telegram."""

    def __init__(self) -> None:
        self.token = config.TELEGRAM_BOT_TOKEN
        self.chat_id = config.TELEGRAM_CHAT_ID
        self._enabled = bool(self.token and self.chat_id)

        if not self._enabled:
            logger.warning(
                "[Telegram] TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID no configurados. "
                "Las alertas estarán desactivadas."
            )

    # ── Mensajes de alto nivel ────────────────────────────────────────────────

    def alerta_nueva(self, pub: Publicacion) -> bool:
        """Envía alerta de nueva publicación con score relevante."""
        if not self._enabled:
            return False
        msg = self._formato_nueva(pub)
        return self._send(msg)

    def alerta_baja_precio(self, pub: Publicacion) -> bool:
        """Envía alerta de baja de precio."""
        if not self._enabled:
            return False
        msg = self._formato_baja_precio(pub)
        return self._send(msg)

    def alerta_excelente(self, pub: Publicacion) -> bool:
        """Envía alerta urgente cuando el score supera SCORE_EXCELENTE."""
        if not self._enabled:
            return False
        msg = self._formato_excelente(pub)
        return self._send(msg)

    def alerta_batch_nuevas(self, pubs: list) -> int:
        """Envía nuevas publicaciones agrupadas de a 10 en un mensaje por bloque."""
        if not self._enabled or not pubs:
            return 0
        count = 0
        for i in range(0, len(pubs), 10):
            chunk = pubs[i:i+10]
            total_str = f" ({i+1}\u2013{i+len(chunk)} de {len(pubs)})" if len(pubs) > 10 else ""
            encabezado = f"\U0001f3e0 <b>Nuevas propiedades detectadas{total_str}</b>"
            lines = [encabezado, ""]
            for pub in chunk:
                lines.append(self._formato_compacto(pub))
            self._send("\n".join(lines))
            count += len(chunk)
            if i + 10 < len(pubs):
                time.sleep(1.5)
        return count

    def alerta_batch_bajas(self, pubs: list) -> int:
        """Env\u00eda bajas de precio agrupadas de a 10 en un mensaje por bloque."""
        if not self._enabled or not pubs:
            return 0
        count = 0
        for i in range(0, len(pubs), 10):
            chunk = pubs[i:i+10]
            total_str = f" ({i+1}\u2013{i+len(chunk)} de {len(pubs)})" if len(pubs) > 10 else ""
            encabezado = f"\U0001f4c9 <b>Bajas de precio{total_str}</b>"
            lines = [encabezado, ""]
            for pub in chunk:
                var_str = f" ({pub.variacion_porcentual:.1f}%)" if pub.variacion_porcentual else ""
                ant_str = f"USD {pub.precio_anterior:,.0f} \u2192 " if pub.precio_anterior else ""
                precio  = f"USD {pub.precio_usd:,.0f}" if pub.precio_usd else "N/D"
                m2_val  = pub.m2_totales or pub.m2_cubiertos
                m2      = f"{m2_val:.0f}m\u00b2" if m2_val else "?m\u00b2"
                lines.append(
                    f"\U0001f4c9 <b>{pub.barrio or '?'}</b> | {ant_str}{precio}{var_str} | "
                    f"{m2} | Score <b>{pub.score:.0f}</b> \u00b7 <a href=\"{pub.url}\">ver</a>"
                )
            self._send("\n".join(lines))
            count += len(chunk)
            if i + 10 < len(pubs):
                time.sleep(1.5)
        return count

    def mensaje_resumen(self, total_nuevas: int, total_bajas: int, total_procesadas: int) -> bool:
        """Envía resumen del run del scraper."""
        if not self._enabled:
            return False
        msg = (
            f"📊 <b>Resumen del scraping</b>\n\n"
            f"✅ Procesadas: {total_procesadas}\n"
            f"🆕 Nuevas relevantes: {total_nuevas}\n"
            f"📉 Bajas de precio: {total_bajas}"
        )
        return self._send(msg)

    # ── Formatos de mensajes ──────────────────────────────────────────────────

    @staticmethod
    def _formato_nueva(pub: Publicacion) -> str:
        emoji = "🏆" if (pub.score or 0) >= config.SCORE_EXCELENTE else "🏠"
        precio_str = f"USD {pub.precio_usd:,.0f}" if pub.precio_usd else "N/D"
        m2_str = f"{pub.m2_totales or pub.m2_cubiertos:.0f} m²" if (pub.m2_totales or pub.m2_cubiertos) else "N/D"
        usd_m2_str = f"{pub.usd_m2_efectivo:,.0f}" if pub.usd_m2_efectivo else "N/D"

        pros_lines = ""
        if pub.pros:
            pros_lines = "\n<b>✅ Pros:</b>\n" + pub.pros

        contras_lines = ""
        if pub.contras:
            contras_lines = "\n<b>⚠️ Contras:</b>\n" + pub.contras

        return (
            f"{emoji} <b>OPORTUNIDAD DETECTADA</b>\n"
            f"<i>{pub.portal}</i>\n\n"
            f"🏷 <b>Score:</b> {pub.score:.0f} — {pub.clasificacion}\n"
            f"📍 <b>Barrio:</b> {pub.barrio or 'N/D'}\n"
            f"💰 <b>Precio:</b> {precio_str}\n"
            f"📐 <b>m²:</b> {m2_str}\n"
            f"📊 <b>USD/m²:</b> {usd_m2_str}\n"
            f"🏢 <b>Piso:</b> {pub.piso or 'N/D'} | "
            f"<b>Disp.:</b> {pub.disposicion or 'N/D'}"
            f"{pros_lines}"
            f"{contras_lines}\n\n"
            f"🔗 <a href=\"{pub.url}\">Ver publicación</a>"
        )

    @staticmethod
    def _formato_baja_precio(pub: Publicacion) -> str:
        var_str = f"{pub.variacion_porcentual:.1f}%" if pub.variacion_porcentual else "?"
        anterior_str = f"USD {pub.precio_anterior:,.0f}" if pub.precio_anterior else "N/D"
        actual_str = f"USD {pub.precio_usd:,.0f}" if pub.precio_usd else "N/D"
        return (
            f"📉 <b>BAJA DE PRECIO</b>\n"
            f"<i>{pub.portal}</i>\n\n"
            f"📍 <b>Barrio:</b> {pub.barrio or 'N/D'}\n"
            f"💰 Antes: {anterior_str} → Ahora: {actual_str} ({var_str})\n"
            f"🏷 <b>Score:</b> {pub.score:.0f} — {pub.clasificacion}\n\n"
            f"🔗 <a href=\"{pub.url}\">Ver publicación</a>"
        )

    @staticmethod
    def _formato_excelente(pub: Publicacion) -> str:
        precio_str = f"USD {pub.precio_usd:,.0f}" if pub.precio_usd else "N/D"
        m2_str = f"{pub.m2_totales or pub.m2_cubiertos:.0f} m²" if (pub.m2_totales or pub.m2_cubiertos) else "N/D"
        usd_m2_str = f"{pub.usd_m2_efectivo:,.0f}" if pub.usd_m2_efectivo else "N/D"

        pros_lines = ""
        if pub.pros:
            pros_lines = "\n<b>✅ Pros:</b>\n" + pub.pros

        return (
            f"🚨🏆 <b>OPORTUNIDAD EXCELENTE — SCORE {pub.score:.0f}</b> 🏆🚨\n"
            f"<i>{pub.portal}</i>\n\n"
            f"📍 <b>Barrio:</b> {pub.barrio or 'N/D'}\n"
            f"💰 <b>Precio:</b> {precio_str}\n"
            f"📐 <b>m²:</b> {m2_str}\n"
            f"📊 <b>USD/m²:</b> {usd_m2_str}\n"
            f"🏢 <b>Piso:</b> {pub.piso or 'N/D'} | "
            f"<b>Disp.:</b> {pub.disposicion or 'N/D'}"
            f"{pros_lines}\n\n"
            f"🔗 <a href=\"{pub.url}\">Ver publicación</a>"
        )

    @staticmethod
    def _formato_compacto(pub: "Publicacion") -> str:
        """Formato de una l\u00ednea para alertas batch."""
        emoji  = "\U0001f3c6" if (pub.score or 0) >= config.SCORE_EXCELENTE else "\U0001f3e0"
        precio = f"USD {pub.precio_usd:,.0f}" if pub.precio_usd else "N/D"
        m2_val = pub.m2_totales or pub.m2_cubiertos
        m2     = f"{m2_val:.0f}m\u00b2" if m2_val else "?m\u00b2"
        exp    = f"exp${pub.expensas/1000:.0f}k" if pub.expensas else ""
        extras = " \u00b7 ".join(x for x in [
            f"P{pub.piso}" if pub.piso else "",
            pub.disposicion or "",
            exp,
        ] if x)
        return (
            f"{emoji} <b>{pub.barrio or '?'}</b> | {precio} | {m2}"
            f" | Score <b>{pub.score:.0f}</b>"
            + (f" | {extras}" if extras else "")
            + f" \u00b7 <a href=\"{pub.url}\">ver</a>"
        )

    # \u2500\u2500 HTTP \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

    def _send(self, text: str) -> bool:
        """Envía un mensaje de texto al chat configurado."""
        url = TELEGRAM_API.format(token=self.token, method="sendMessage")
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": PARSE_MODE,
            "disable_web_page_preview": False,
        }
        try:
            resp = requests.post(url, json=payload, timeout=15)
            if resp.status_code == 200:
                logger.info("[Telegram] Mensaje enviado correctamente.")
                return True
            else:
                logger.error("[Telegram] Error %d: %s", resp.status_code, resp.text[:200])
                return False
        except requests.exceptions.RequestException as e:
            logger.error("[Telegram] Excepción al enviar mensaje: %s", e)
            return False
