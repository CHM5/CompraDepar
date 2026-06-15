"""
bot.py
──────
Bot de Telegram interactivo para controlar el scraper de departamentos.

Ejecutar:
    .venv/bin/python bot.py

Para que arranque al iniciar el sistema (crontab -e):
    @reboot cd /home/hernie/Desktop/AutomatizacionCompraDepar && .venv/bin/python bot.py >> logs/bot.log 2>&1 &

Multi-usuario: agregá los chat_ids autorizados en .env como:
    TELEGRAM_AUTHORIZED_USERS=123456789,987654321
    (si está vacío, solo responde a TELEGRAM_CHAT_ID)
"""

from __future__ import annotations

import html as _html
import logging
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

sys.path.insert(0, str(Path(__file__).parent))

import config
from database import db
from services.user_config import (
    ALL_BARRIOS_CABA,
    apply_to_module,
    get_user_cfg,
    reset_cfg,
    set_val,
)

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"
SHEETS_URL = f"https://docs.google.com/spreadsheets/d/{config.GOOGLE_SHEETS_ID}"

# ── Usuarios autorizados ──────────────────────────────────────────────────────
def _load_authorized() -> set:
    """Lee TELEGRAM_AUTHORIZED_USERS del .env y agrega TELEGRAM_CHAT_ID."""
    raw = os.getenv("TELEGRAM_AUTHORIZED_USERS", "").strip()
    ids = {x.strip() for x in raw.split(",") if x.strip()}
    if config.TELEGRAM_CHAT_ID:
        ids.add(str(config.TELEGRAM_CHAT_ID))
    return ids

_AUTHORIZED: set = set()   # se inicializa en main()

# ── Estado global ─────────────────────────────────────────────────────────────
_scraping_en_curso = False
_ultimo_run: Optional[str] = None

_GREET_WORDS = {"hola", "hola!", "hola.", "hi", "hello", "buenas", "ola", "hey"}


# ══════════════════════════════════════════════════════════════════════════════
# MENÚ
# ══════════════════════════════════════════════════════════════════════════════

MENU = (
    "🤖 <b>Bot Scraper — Departamentos CABA</b>\n\n"
    "<b>📌 Consultas:</b>\n"
    "  /top [N] — Mejores N rankeados (def. 10, máx 25)\n"
    "  /barrio [nombre] — Top de un barrio\n"
    "  /nuevas — Últimas propiedades detectadas\n"
    "  /estado — Estadísticas de la base\n"
    "  /stats — Promedios por barrio (precio, m², expensas, score)\n"
    "  /sheets — Link al Google Sheets\n\n"
    "<b>🔍 Scraping:</b>\n"
    "  /scrape — Disparar scraping completo ahora\n"
    "  <i>Portales: Zonaprop · Argenprop · MEL · ToribiAchaval</i>\n\n"
    "<b>⚙️ Configuración:</b>\n"
    "  /config — Ver tu config actual\n"
    "  /set precio 80000 105000 — Rango de precio USD\n"
    "  /set m2 35 — m² mínimos\n"
    "  /set piso 2 — Piso mínimo (0 = sin filtro)\n"
    "  /set antiguedad 20 — Antigüedad máx. en años\n"
    "  /set umbral 70 — Score mínimo para exportar\n"
    "  /set must balcon si/no — Exigir balcón (MUST)\n"
    "  /set must barrio si/no — Exigir barrio en lista\n\n"
    "<b>🏙 Barrios:</b>\n"
    "  /barrios — Ver lista activa\n"
    "  /barrios + Palermo — Agregar barrio\n"
    "  /barrios - Palermo — Quitar barrio\n"
    "  /barrios lista — Todos los barrios de CABA\n\n"
    "<b>🏆 Ponderación (scoring):</b>\n"
    "  /scoring — Ver pesos actuales\n"
    "  /scoring balcon 15\n"
    "  /scoring cochera 5\n"
    "  /scoring m2 10 — Bonus por ≥45m²\n"
    "  /scoring piso 5 — Bonus por piso≥5\n"
    "  /scoring antiguedad 10 — Bonus por ≤10 años\n"
    "  /scoring barrio Palermo 50 — Score de barrio\n"
    "  /scoring amenity pileta 3\n"
    "  /scoring amenity quitar pileta\n\n"
    "  /reset — 🔄 Restablecer config por defecto\n\n"
    "<i>💬 Con OPENAI_API_KEY activa podés escribir en lenguaje natural.</i>\n"
    "Escribí <b>hola</b> para ver este menú."
)


# ══════════════════════════════════════════════════════════════════════════════
# TELEGRAM API
# ══════════════════════════════════════════════════════════════════════════════

def _api(method: str, **kwargs) -> Optional[dict]:
    url = TELEGRAM_API.format(token=config.TELEGRAM_BOT_TOKEN, method=method)
    try:
        resp = requests.post(url, json=kwargs, timeout=35)
        data = resp.json()
        if not data.get("ok"):
            logger.warning("[Bot] API error en %s: %s", method, data.get("description", ""))
            return None
        return data.get("result")
    except Exception as e:
        logger.error("[Bot] Excepción en %s: %s", method, e)
        return None


def _send(chat_id: str, text: str, disable_preview: bool = True) -> bool:
    return _api("sendMessage", chat_id=chat_id, text=text,
                parse_mode="HTML", disable_web_page_preview=disable_preview) is not None


def _get_updates(offset: int = 0, timeout: int = 30) -> list:
    return _api("getUpdates", offset=offset, timeout=timeout, allowed_updates=["message"]) or []


def _e(value) -> str:
    return _html.escape(str(value)) if value is not None else "N/D"


def _send_chunked(chat_id: str, lines: list) -> None:
    """Envía lista de líneas partiéndola si supera 4096 chars."""
    chunk = ""
    for line in lines:
        candidate = (chunk + "\n" + line) if chunk else line
        if len(candidate) > 4000:
            _send(chat_id, chunk, disable_preview=True)
            chunk = line
        else:
            chunk = candidate
    if chunk:
        _send(chat_id, chunk, disable_preview=True)


# ══════════════════════════════════════════════════════════════════════════════
# HANDLERS — CONSULTAS
# ══════════════════════════════════════════════════════════════════════════════

def _handle_scrape(chat_id: str) -> None:
    global _scraping_en_curso, _ultimo_run
    if _scraping_en_curso:
        _send(chat_id, "⏳ Ya hay un scraping en curso. Esperá a que termine.")
        return

    cfg_snapshot = get_user_cfg(chat_id)
    _send(
        chat_id,
        "🚀 <b>Iniciando scraping completo...</b>\n"
        f"⏱ Tarda ~3-5 min. Te aviso cuando termine.\n\n"
        f"📋 Config aplicada:\n"
        f"  💰 USD {cfg_snapshot['PRECIO_MIN_USD']:,} – {cfg_snapshot['PRECIO_MAX_USD']:,}\n"
        f"  📐 m² ≥ {cfg_snapshot['M2_MINIMO']:.0f} | Piso ≥ {cfg_snapshot['PISO_MINIMO']}\n"
        f"  🏙 {len(cfg_snapshot['BARRIOS_OBJETIVO'])} barrios",
    )

    def _run() -> None:
        global _scraping_en_curso, _ultimo_run
        _scraping_en_curso = True
        inicio = datetime.now()
        try:
            apply_to_module(cfg_snapshot)
            import main as _main
            exit_code = _main.run()
            duracion = (datetime.now() - inicio).total_seconds()
            _ultimo_run = datetime.now().strftime("%d/%m/%Y %H:%M")
            if exit_code == 0:
                stats = db.get_estadisticas()
                total = stats.get("total", "?")
                portal_str = " | ".join(f"{p}: {n}" for p, n in stats.get("por_portal", {}).items())
                _send(chat_id,
                      f"✅ <b>Scraping completado</b> en {duracion:.0f}s\n"
                      f"🏠 {total} propiedades activas ({portal_str})\n\n"
                      f"Usá /top para ver los mejores o /sheets para la planilla.")
            else:
                _send(chat_id, f"⚠️ Scraping terminó con errores ({duracion:.0f}s). Revisá /estado.")
        except Exception as e:
            logger.error("[Bot] Error scraping: %s", e, exc_info=True)
            _send(chat_id, f"❌ Error durante el scraping:\n<code>{_e(e)}</code>")
        finally:
            _scraping_en_curso = False

    threading.Thread(target=_run, daemon=True).start()


def _handle_top(chat_id: str, args: str) -> None:
    try:
        limit = int(args.strip()) if args.strip().isdigit() else 10
        limit = max(1, min(limit, 25))
    except (ValueError, AttributeError):
        limit = 10

    rows = db.get_top_publicaciones(limit)
    if not rows:
        _send(chat_id, "📭 No hay propiedades aún.\nUsá /scrape para obtener datos.")
        return

    lines = [f"🏆 <b>Top {len(rows)} rankeadas</b>\n"]
    for i, row in enumerate(rows, 1):
        score  = row["score"] or 0
        precio = f"USD {row['precio_usd']:,.0f}" if row["precio_usd"] else "N/D"
        m2_val = row["m2_totales"] or row["m2_cubiertos"]
        m2_str = f"{m2_val:.0f}m²" if m2_val else "N/D"
        extras = " · ".join(x for x in [
            f"{row['ambientes']}amb" if row["ambientes"] else "",
            f"P{row['piso']}" if row["piso"] else "",
        ] if x)
        lines.append(
            f"{i}. <b>{score:.0f}pts</b> — {_e(row['barrio'] or '?')} | {precio} | {m2_str}"
            + (f" | {extras}" if extras else "")
            + f"\n   <i>{_e(row['portal'])}</i> · <a href=\"{row['url']}\">Ver →</a>\n"
        )
    _send_chunked(chat_id, lines)


def _handle_sheets(chat_id: str) -> None:
    _send(
        chat_id,
        f"📊 <b>Google Sheets — Departamentos CABA</b>\n\n"
        f"🔗 <a href=\"{SHEETS_URL}\">Abrir planilla completa</a>\n\n"
        f"<i>Propiedades con score ≥ {config.SCORE_MINIMO_EXPORTAR}pts, ordenadas por ranking.</i>",
        disable_preview=False,
    )


def _handle_estado(chat_id: str) -> None:
    try:
        stats = db.get_estadisticas()
    except Exception as e:
        _send(chat_id, f"❌ Error DB: <code>{_e(e)}</code>")
        return

    por_portal = stats.get("por_portal", {})
    por_estado = stats.get("por_estado", {})
    score_max  = stats.get("score_max")
    score_avg  = stats.get("score_avg")
    ultima_act = (stats.get("ultima_actualizacion") or "N/D")[:16].replace("T", " ")
    portales_str = "\n".join(f"  • <b>{_e(p)}</b>: {n}" for p, n in por_portal.items()) or "  (vacía)"
    estados_str  = "\n".join(f"  • {_e(e)}: {n}" for e, n in sorted(por_estado.items(), key=lambda x: -x[1]))
    score_str = f"{score_max:.0f} (máx) · {score_avg:.1f} (prom)" if score_max else "N/D"
    _send(
        chat_id,
        f"📈 <b>Estado de la base de datos</b>\n\n"
        f"🏠 <b>Activas:</b> {stats['total']}\n\n"
        f"<b>Por portal:</b>\n{portales_str}\n\n"
        f"<b>Por estado:</b>\n{estados_str}\n\n"
        f"<b>Score:</b> {score_str}\n"
        f"🕐 <b>Última actualización:</b> {_e(ultima_act)}\n"
        f"🚀 <b>Último scraping:</b> {_e(_ultimo_run or 'N/D en esta sesión')}",
    )


def _handle_stats(chat_id: str) -> None:
    """Muestra estadísticas detalladas por barrio."""
    try:
        filas = db.get_stats_por_barrio()
    except Exception as e:
        _send(chat_id, f"❌ Error DB: <code>{_e(e)}</code>")
        return

    if not filas:
        _send(chat_id, "📭 Sin datos. Usá /scrape primero.")
        return

    lines = ["📊 <b>Estadísticas por barrio</b>\n"]
    for f in filas:
        barrio     = f.get("barrio") or "?"
        cant       = f.get("cantidad", 0)
        avg_m2     = f.get("avg_usd_m2")
        avg_exp    = f.get("avg_expensas")
        avg_score  = f.get("avg_score") or 0
        max_score  = f.get("max_score") or 0
        avg_precio = f.get("avg_precio")
        min_precio = f.get("min_precio")
        max_precio = f.get("max_precio")
        avg_m2_m2  = f.get("avg_m2")
        precio_str = f"USD {avg_precio:,.0f}" if avg_precio else "N/D"
        rango_str  = f"({min_precio:,.0f}–{max_precio:,.0f})" if (min_precio and max_precio) else ""
        m2_str     = f"{avg_m2_m2:.0f}m²" if avg_m2_m2 else ""
        usdm2_str  = f"${avg_m2:,.0f}/m²" if avg_m2 else ""
        exp_str    = f"exp${avg_exp/1000:.0f}k" if avg_exp else ""
        detalles   = " · ".join(x for x in [precio_str, rango_str, m2_str, usdm2_str, exp_str] if x)
        lines.append(
            f"🏙 <b>{_e(barrio)}</b> ({cant} props) | Score {avg_score:.0f} avg / {max_score:.0f} máx\n"
            f"   {detalles}"
        )

    # Stats globales
    try:
        stats = db.get_estadisticas()
        total = stats.get("total", 0)
        score_avg = stats.get("score_avg")
        score_max = stats.get("score_max")
        global_line = f"\n<b>📈 Global:</b> {total} activas"
        if score_avg and score_max:
            global_line += f" | Score avg {score_avg:.1f} / máx {score_max:.0f}"
        lines.append(global_line)
    except Exception:
        pass

    _send_chunked(chat_id, lines)


def _handle_barrio_query(chat_id: str, args: str) -> None:
    barrio = args.strip()
    if not barrio:
        cfg = get_user_cfg(chat_id)
        disponibles = "\n".join(f"  • {b}" for b in cfg["BARRIOS_OBJETIVO"])
        _send(chat_id, f"📍 Ej: /barrio Palermo\n\n<b>Tus barrios activos:</b>\n{disponibles}")
        return
    rows = db.get_top_publicaciones(limit=10, barrio=barrio)
    if not rows:
        _send(chat_id, f"📭 Sin resultados para <b>{_e(barrio)}</b>.\nUsá /barrios para ver tu lista activa.")
        return
    lines = [f"🏙 <b>Top en {_e(barrio.capitalize())}</b> ({len(rows)} props)\n"]
    for i, row in enumerate(rows, 1):
        precio = f"USD {row['precio_usd']:,.0f}" if row["precio_usd"] else "N/D"
        m2_val = row["m2_totales"] or row["m2_cubiertos"]
        m2_str = f"{m2_val:.0f}m²" if m2_val else "N/D"
        extras = " · ".join(x for x in [
            f"{row['ambientes']}amb" if row["ambientes"] else "",
            f"P{row['piso']}" if row["piso"] else "",
            _e(row["disposicion"] or ""),
        ] if x)
        lines.append(
            f"{i}. <b>{(row['score'] or 0):.0f}pts</b> | {precio} | {m2_str}"
            + (f" | {extras}" if extras else "")
            + f"\n   <i>{_e(row['portal'])}</i> · <a href=\"{row['url']}\">Ver →</a>\n"
        )
    _send_chunked(chat_id, lines)


def _handle_nuevas(chat_id: str) -> None:
    rows = db.get_recientes(limit=10)
    if not rows:
        _send(chat_id, "📭 No hay propiedades aún.\nUsá /scrape.")
        return
    lines = ["🆕 <b>Últimas 10 detectadas</b>\n"]
    for i, row in enumerate(rows, 1):
        precio = f"USD {row['precio_usd']:,.0f}" if row["precio_usd"] else "N/D"
        m2_val = row["m2_totales"] or row["m2_cubiertos"]
        m2_str = f"{m2_val:.0f}m²" if m2_val else "N/D"
        fecha  = (row["fecha_deteccion"] or "")[:10]
        lines.append(
            f"{i}. {_e(row['barrio'] or '?')} | {precio} | {m2_str} | <b>{(row['score'] or 0):.0f}pts</b>"
            + (f" | 📅{fecha}" if fecha else "")
            + f"\n   <i>{_e(row['portal'])}</i> · <a href=\"{row['url']}\">Ver →</a>\n"
        )
    _send_chunked(chat_id, lines)


# ══════════════════════════════════════════════════════════════════════════════
# HANDLERS — CONFIGURACIÓN
# ══════════════════════════════════════════════════════════════════════════════

def _handle_config(chat_id: str) -> None:
    cfg = get_user_cfg(chat_id)
    barrios_str = ", ".join(cfg["BARRIOS_OBJETIVO"]) or "(ninguno)"
    sb = cfg["SCORE_BARRIOS"]
    sb_str = "\n".join(f"    • {b}: {v}pts" for b, v in sorted(sb.items(), key=lambda x: -x[1])) or "    (sin ponderación)"
    am = cfg["SCORE_AMENITIES"]
    am_str = ", ".join(f"{k}={v}pts" for k, v in am.items()) if am else "(ninguno)"
    _send(
        chat_id,
        f"⚙️ <b>Tu configuración actual</b>\n\n"
        f"<b>🔍 Búsqueda:</b>\n"
        f"  💰 Precio: USD {cfg['PRECIO_MIN_USD']:,} – {cfg['PRECIO_MAX_USD']:,}\n"
        f"  📐 m² mín: {cfg['M2_MINIMO']:.0f}\n"
        f"  🏢 Piso mín: {cfg['PISO_MINIMO']} {'(sin filtro)' if cfg['PISO_MINIMO'] == 0 else ''}\n"
        f"  🗓 Antigüedad máx: {cfg['ANTIGUEDAD_MAXIMA']} años\n\n"
        f"<b>🏙 Barrios ({len(cfg['BARRIOS_OBJETIVO'])}):</b>\n  {barrios_str}\n\n"
        f"<b>🏆 Scoring:</b>\n"
        f"  Balcón: {cfg['SCORE_BALCON']}pts | Cochera: {cfg['SCORE_COCHERA']}pts\n"
        f"  ≥45m²: {cfg['SCORE_METROS_45_MAS']}pts | Piso≥5: {cfg['SCORE_PISO_5_MAS']}pts\n"
        f"  Antigüedad≤10a: {cfg['SCORE_ANTIGUEDAD_10_MENOS']}pts\n"
        f"  Amenities: {am_str}\n\n"
        f"<b>Por barrio:</b>\n{sb_str}\n\n"
        f"<b>📊 Umbrales:</b>\n"
        f"  Exportar: ≥{cfg['SCORE_MINIMO_EXPORTAR']}pts | Alertar: ≥{cfg['SCORE_MINIMO_ALERTA']}pts\n\n"
        f"<i>Usá /set, /barrios y /scoring para cambiar. /reset para defaults.</i>",
    )


def _handle_set(chat_id: str, args: str) -> None:
    parts = args.strip().split()
    if not parts:
        _send(
            chat_id,
            "⚙️ <b>/set — parámetros disponibles:</b>\n"
            "  <code>/set precio 80000 105000</code>\n"
            "  <code>/set m2 35</code>\n"
            "  <code>/set piso 2</code>  (0 = sin filtro)\n"
            "  <code>/set antiguedad 20</code>\n"
            "  <code>/set umbral 70</code>  (score mín. exportar)",
        )
        return
    param = parts[0].lower()
    try:
        if param == "precio":
            if len(parts) < 3:
                _send(chat_id, "Ej: <code>/set precio 80000 105000</code>")
                return
            min_p, max_p = int(parts[1]), int(parts[2])
            if min_p >= max_p or min_p < 1000:
                _send(chat_id, "❌ Precio inválido.")
                return
            set_val(chat_id, "PRECIO_MIN_USD", min_p)
            set_val(chat_id, "PRECIO_MAX_USD", max_p)
            _send(chat_id, f"✅ Precio → USD {min_p:,} – {max_p:,}")
        elif param == "m2":
            val = float(parts[1])
            if not (10 <= val <= 300):
                _send(chat_id, "❌ Rango válido: 10 – 300 m²")
                return
            set_val(chat_id, "M2_MINIMO", val)
            _send(chat_id, f"✅ m² mínimos → {val:.0f}m²")
        elif param == "piso":
            val = int(parts[1])
            if not (0 <= val <= 30):
                _send(chat_id, "❌ Rango válido: 0 (sin filtro) – 30")
                return
            set_val(chat_id, "PISO_MINIMO", val)
            _send(chat_id, f"✅ Piso mínimo → {val} {'(sin filtro)' if val == 0 else ''}")
        elif param == "antiguedad":
            val = int(parts[1])
            if not (0 <= val <= 100):
                _send(chat_id, "❌ Rango válido: 0 – 100 años")
                return
            set_val(chat_id, "ANTIGUEDAD_MAXIMA", val)
            _send(chat_id, f"✅ Antigüedad máx → {val} años {'(sin filtro)' if val == 0 else ''}")
        elif param in ("umbral", "score", "minimo"):
            val = int(parts[1])
            if not (0 <= val <= 130):
                _send(chat_id, "❌ Rango válido: 0 – 130")
                return
            set_val(chat_id, "SCORE_MINIMO_EXPORTAR", val)
            _send(chat_id, f"✅ Umbral de exportación → ≥{val}pts")
        elif param == "must":
            # /set must balcon si/no  |  /set must barrio si/no
            if len(parts) < 3:
                cfg = get_user_cfg(chat_id)
                mb = "✅" if cfg.get("MUST_HAVE_BALCON") else "❌"
                mbar = "✅" if cfg.get("MUST_HAVE_BARRIO") else "❌"
                _send(chat_id,
                      f"⚠️ <b>Filtros obligatorios (MUST):</b>\n"
                      f"  {mb} Balcón: <code>/set must balcon si/no</code>\n"
                      f"  {mbar} Barrio: <code>/set must barrio si/no</code>")
                return
            campo = parts[1].lower()
            valor_str = parts[2].lower()
            valor = valor_str in ("si", "sí", "1", "true", "yes")
            if campo in ("balcon", "balcón"):
                set_val(chat_id, "MUST_HAVE_BALCON", valor)
                _send(chat_id, f"✅ Balcón obligatorio → {'SÍ' if valor else 'NO'}")
            elif campo == "barrio":
                set_val(chat_id, "MUST_HAVE_BARRIO", valor)
                _send(chat_id, f"✅ Barrio obligatorio → {'SÍ' if valor else 'NO'}")
            else:
                _send(chat_id, f"❌ Campo desconocido: <code>{_e(campo)}</code>. Usá <code>balcon</code> o <code>barrio</code>")
        else:
            _send(chat_id,
                  f"❌ Parámetro desconocido: <code>{_e(param)}</code>\n"
                  "Disponibles: <code>precio</code>, <code>m2</code>, <code>piso</code>, "
                  "<code>antiguedad</code>, <code>umbral</code>, <code>must</code>")
    except (IndexError, ValueError):
        _send(chat_id, "❌ Valor inválido. Revisá el formato con /ayuda.")


def _handle_barrios(chat_id: str, args: str) -> None:
    cfg          = get_user_cfg(chat_id)
    lista_actual = list(cfg["BARRIOS_OBJETIVO"])
    args         = args.strip()

    if not args:
        barrios_str = "\n".join(f"  {i+1}. {b}" for i, b in enumerate(lista_actual))
        _send(
            chat_id,
            f"🏙 <b>Tus barrios activos ({len(lista_actual)}):</b>\n{barrios_str}\n\n"
            f"  <code>/barrios + Palermo</code> — agregar\n"
            f"  <code>/barrios - Palermo</code> — quitar\n"
            f"  <code>/barrios lista</code> — todos los de CABA",
        )
        return

    if args.lower() in ("lista", "todos", "disponibles", "caba"):
        activos_lower = {b.lower() for b in lista_actual}
        lines = ["📋 <b>Barrios de CABA disponibles (✅ = en tu lista):</b>\n"]
        for b in sorted(ALL_BARRIOS_CABA):
            marca = "✅" if b.lower() in activos_lower else "  "
            lines.append(f"{marca} {b}")
        lines.append("\nUsá <code>/barrios + NombreBarrio</code> para agregar.")
        _send_chunked(chat_id, lines)
        return

    if args.startswith("+") or args.lower().startswith(("add ", "agregar ")):
        nombre = args.lstrip("+").replace("add ", "", 1).replace("agregar ", "", 1).strip().title()
        if not nombre:
            _send(chat_id, "❌ Indicá el nombre. Ej: <code>/barrios + Palermo</code>")
            return
        if any(b.lower() == nombre.lower() for b in lista_actual):
            _send(chat_id, f"ℹ️ <b>{_e(nombre)}</b> ya está en tu lista.")
            return
        match = next((b for b in ALL_BARRIOS_CABA if b.lower() == nombre.lower()), nombre)
        lista_actual.append(match)
        set_val(chat_id, "BARRIOS_OBJETIVO", lista_actual)
        _send(chat_id, f"✅ <b>{_e(match)}</b> agregado. Total: {len(lista_actual)} barrios.")

    elif args.startswith("-") or args.lower().startswith(("quitar ", "sacar ")):
        nombre = args.lstrip("-").replace("quitar ", "", 1).replace("sacar ", "", 1).strip().title()
        if not nombre:
            _send(chat_id, "❌ Indicá el nombre. Ej: <code>/barrios - Palermo</code>")
            return
        nueva_lista = [b for b in lista_actual if b.lower() != nombre.lower()]
        if len(nueva_lista) == len(lista_actual):
            _send(chat_id, f"❌ <b>{_e(nombre)}</b> no estaba en tu lista.")
            return
        if not nueva_lista:
            _send(chat_id, "❌ No podés quedar sin barrios.")
            return
        set_val(chat_id, "BARRIOS_OBJETIVO", nueva_lista)
        _send(chat_id, f"✅ <b>{_e(nombre)}</b> quitado. Quedan {len(nueva_lista)} barrios.")
    else:
        _send(chat_id, f"❓ Usá:\n  <code>/barrios + Palermo</code>\n  <code>/barrios - Palermo</code>")


def _handle_scoring(chat_id: str, args: str) -> None:
    cfg   = get_user_cfg(chat_id)
    args  = args.strip()
    parts = args.split()

    if not args:
        sb = cfg["SCORE_BARRIOS"]
        sb_str = "\n".join(f"  • {b}: {v}pts" for b, v in sorted(sb.items(), key=lambda x: -x[1])) or "  (sin ponderación)"
        am = cfg["SCORE_AMENITIES"]
        am_str = "\n".join(f"  • {k}: {v}pts" for k, v in am.items()) if am else "  (ninguno)"
        tiers = cfg.get("SCORE_M2_TIERS", [])
        tiers_str = "\n".join(
            f"  • >{u}m² → {p}pts" for u, p in sorted(tiers, key=lambda x: x[0])
        ) if tiers else "  (desactivado)"
        exp_tiers = cfg.get("SCORE_EXPENSAS_TIERS", [])
        exp_tiers_str = "\n".join(
            f"  • ${mn//1000}k–${'∞' if mx >= 9_999_999 else str(mx//1000)+'k'} → {p:+}pts"
            for mn, mx, p in sorted(exp_tiers, key=lambda x: x[0])
        ) if exp_tiers else "  (desactivado)"
        must_balcon = "✅ Sí (obligatorio)" if cfg.get("MUST_HAVE_BALCON") else "❌ No obligatorio"
        _send(
            chat_id,
            f"🏆 <b>Tus pesos de scoring</b>\n\n"
            f"  Balcón:          {cfg['SCORE_BALCON']}pts {must_balcon}\n"
            f"  Cochera:         {cfg['SCORE_COCHERA']}pts\n"
            f"  Piso ≥ 5:        {cfg['SCORE_PISO_5_MAS']}pts\n"
            f"  Antigüedad ≤10a: {cfg['SCORE_ANTIGUEDAD_10_MENOS']}pts\n\n"
            f"<b>m² tiers (solo aplica el más alto):</b>\n{tiers_str}\n\n"
            f"<b>Expensas tiers (rango coincidente):</b>\n{exp_tiers_str}\n\n"
            f"<b>Por barrio:</b>\n{sb_str}\n\n"
            f"<b>Amenities:</b>\n{am_str}\n\n"
            f"<i>Ej: <code>/scoring balcon 20</code> · <code>/scoring barrio Palermo 55</code>\n"
            f"Filtros must: <code>/set must balcon si/no</code></i>",
        )
        return

    SIMPLE_MAP = {
        "balcon": "SCORE_BALCON", "balcón": "SCORE_BALCON",
        "cochera": "SCORE_COCHERA", "garage": "SCORE_COCHERA",
        "m2": "SCORE_METROS_45_MAS", "metros": "SCORE_METROS_45_MAS",
        "piso": "SCORE_PISO_5_MAS",
        "antiguedad": "SCORE_ANTIGUEDAD_10_MENOS", "antigüedad": "SCORE_ANTIGUEDAD_10_MENOS",
    }
    param = parts[0].lower()

    try:
        if param in SIMPLE_MAP:
            if len(parts) < 2:
                _send(chat_id, f"Ej: <code>/scoring {param} 15</code>")
                return
            val = int(parts[1])
            if not (0 <= val <= 100):
                _send(chat_id, "❌ Rango válido: 0 – 100")
                return
            set_val(chat_id, SIMPLE_MAP[param], val)
            _send(chat_id, f"✅ Scoring <b>{param}</b> → {val}pts")

        elif param == "barrio":
            if len(parts) < 3:
                _send(chat_id, "Ej: <code>/scoring barrio Palermo 50</code>")
                return
            try:
                pts = int(parts[-1])
                barrio_nombre = " ".join(parts[1:-1]).strip().title()
            except ValueError:
                _send(chat_id, "Ej: <code>/scoring barrio Villa Crespo 40</code>")
                return
            if not (0 <= pts <= 200):
                _send(chat_id, "❌ Rango válido: 0 – 200")
                return
            sb = dict(cfg["SCORE_BARRIOS"])
            if pts == 0:
                sb.pop(barrio_nombre, None)
                set_val(chat_id, "SCORE_BARRIOS", sb)
                _send(chat_id, f"✅ <b>{_e(barrio_nombre)}</b> eliminado de barrios ponderados.")
            else:
                sb[barrio_nombre] = pts
                set_val(chat_id, "SCORE_BARRIOS", sb)
                _send(chat_id, f"✅ Score de <b>{_e(barrio_nombre)}</b> → {pts}pts")

        elif param == "amenity":
            if len(parts) < 3:
                _send(chat_id, "Ej: <code>/scoring amenity pileta 3</code>\no: <code>/scoring amenity quitar pileta</code>")
                return
            am   = dict(cfg["SCORE_AMENITIES"])
            sub  = parts[1].lower()
            if sub in ("quitar", "eliminar", "borrar", "sacar"):
                nombre_am = " ".join(parts[2:]).lower()
                am.pop(nombre_am, None)
                set_val(chat_id, "SCORE_AMENITIES", am)
                _send(chat_id, f"✅ Amenity <b>{_e(nombre_am)}</b> eliminado.")
            else:
                try:
                    pts = int(parts[-1])
                    nombre_am = " ".join(parts[1:-1]).lower()
                except ValueError:
                    _send(chat_id, "Ej: <code>/scoring amenity pileta 3</code>")
                    return
                if not (0 <= pts <= 50):
                    _send(chat_id, "❌ Rango válido: 0 – 50")
                    return
                am[nombre_am] = pts
                set_val(chat_id, "SCORE_AMENITIES", am)
                _send(chat_id, f"✅ Amenity <b>{_e(nombre_am)}</b> → {pts}pts")
        else:
            _send(chat_id,
                  f"❌ Scoring desconocido: <code>{_e(param)}</code>\n"
                  "Opciones: <code>balcon</code>, <code>cochera</code>, <code>m2</code>, "
                  "<code>piso</code>, <code>antiguedad</code>, <code>barrio</code>, <code>amenity</code>")
    except (IndexError, ValueError):
        _send(chat_id, "❌ Formato incorrecto. Usá /ayuda para ver ejemplos.")


def _handle_reset(chat_id: str) -> None:
    reset_cfg(chat_id)
    _send(chat_id,
          "🔄 <b>Configuración restablecida.</b>\n\n"
          "Todos los parámetros volvieron a los valores originales.\n"
          "Usá /config para verificar.")


def _handle_nl(chat_id: str, text: str) -> None:
    """Maneja mensajes en lenguaje natural usando NLU (OpenAI)."""
    from services import nlp

    if not nlp.is_enabled():
        _send(
            chat_id,
            f"\U0001f916 No entendí «{_e(text[:40])}»\n\n"
            f"Escribi /ayuda para ver los comandos disponibles.\n"
            f"<i>Para activar lenguaje natural: agregá OPENAI_API_KEY en el .env</i>",
        )
        return

    cfg = get_user_cfg(chat_id)
    _send(chat_id, "\U0001f4ad Interpretando...")
    result = nlp.translate(text, user_cfg=cfg)
    intent = result.get("intent")

    if intent == "unsupported":
        msg = result.get("message", "Acción no disponible.")
        _send(chat_id, f"\u274c <b>No disponible:</b> {_e(msg)}\n\n<i>Escribi /ayuda para ver los comandos.</i>")

    elif intent == "clarify":
        missing = result.get("missing", [])
        missing_str = ", ".join(f"<b>{_e(m)}</b>" for m in missing) or "más información"
        _send(chat_id, f"\u2753 Necesito más info. Por favor indicá: {missing_str}")

    elif intent in ("error", None):
        msg = result.get("message", "No pude interpretar el mensaje.")
        _send(chat_id, f"\u26a0\ufe0f {_e(msg)}\n\nEscribi /ayuda para ver los comandos.")

    else:
        cmd = nlp.intent_to_command(result, user_cfg=cfg)
        if cmd:
            _send(chat_id, f"\U0001f916 Interpreté: <code>{_e(cmd)}</code>")
            _route_single(chat_id, cmd)
        else:
            _send(
                chat_id,
                f"\u274c No pude convertir el intent <b>{_e(intent)}</b> a un comando.\n"
                f"Usá /ayuda para ver los comandos disponibles.",
            )


# ══════════════════════════════════════════════════════════════════════════════

def _split_commands(text: str) -> list[str]:
    """Divide un mensaje con múltiples comandos en una lista de comandos individuales.

    Ej: "/scoring barrio Palermo 50 /scoring barrio Saavedra 35"
     → ["/scoring barrio Palermo 50", "/scoring barrio Saavedra 35"]

    Si el mensaje no empieza con '/', lo devuelve tal cual como un solo elemento.
    """
    import re as _re
    text = text.strip()
    # Buscar todas las posiciones donde empieza un nuevo comando (/ al inicio de palabra)
    positions = [m.start() for m in _re.finditer(r"(?<!\S)/\S", text)]
    if len(positions) <= 1:
        return [text]
    chunks = []
    for i, pos in enumerate(positions):
        end = positions[i + 1] if i + 1 < len(positions) else len(text)
        chunks.append(text[pos:end].strip())
    return [c for c in chunks if c]


def _route(chat_id: str, text: str) -> None:
    if str(chat_id) not in _AUTHORIZED:
        logger.warning("[Bot] Chat no autorizado: %s", chat_id)
        return

    text = (text or "").strip()

    # Soporte para múltiples comandos en un solo mensaje
    # Ej: "/scoring barrio Palermo 50 /scoring barrio Saavedra 35"
    cmds = _split_commands(text)
    if len(cmds) > 1:
        for cmd in cmds:
            _route_single(chat_id, cmd)
        return

    _route_single(chat_id, text)


def _route_single(chat_id: str, text: str) -> None:
    """Procesa un único comando."""
    text_lower = text.lower()

    if text_lower in _GREET_WORDS or text_lower in {"/start", "/ayuda", "/help", "/menu"}:
        _send(chat_id, MENU)
        return

    # Lenguaje natural: cualquier texto sin prefijo / que no sea saludo
    if not text.startswith("/"):
        _handle_nl(chat_id, text)
        return

    parts   = text.split(None, 1)
    raw_cmd = parts[0].lstrip("/").lower().split("@")[0]
    args    = parts[1].strip() if len(parts) > 1 else ""

    dispatch = {
        "scrape": lambda: _handle_scrape(chat_id),
        "scrapear": lambda: _handle_scrape(chat_id),
        "run": lambda: _handle_scrape(chat_id),
        "top": lambda: _handle_top(chat_id, args),
        "mejores": lambda: _handle_top(chat_id, args),
        "ranking": lambda: _handle_top(chat_id, args),
        "sheets": lambda: _handle_sheets(chat_id),
        "excel": lambda: _handle_sheets(chat_id),
        "planilla": lambda: _handle_sheets(chat_id),
        "estado": lambda: _handle_estado(chat_id),
        "stats": lambda: _handle_stats(chat_id),
        "estadisticas": lambda: _handle_stats(chat_id),
        "barrio": lambda: _handle_barrio_query(chat_id, args),
        "zona": lambda: _handle_barrio_query(chat_id, args),
        "nuevas": lambda: _handle_nuevas(chat_id),
        "recientes": lambda: _handle_nuevas(chat_id),
        "config": lambda: _handle_config(chat_id),
        "configuracion": lambda: _handle_config(chat_id),
        "set": lambda: _handle_set(chat_id, args),
        "barrios": lambda: _handle_barrios(chat_id, args),
        "scoring": lambda: _handle_scoring(chat_id, args),
        "score": lambda: _handle_scoring(chat_id, args),
        "ponderacion": lambda: _handle_scoring(chat_id, args),
        "reset": lambda: _handle_reset(chat_id),
        "resetear": lambda: _handle_reset(chat_id),
        "ayuda": lambda: _send(chat_id, MENU),
        "help": lambda: _send(chat_id, MENU),
        "comandos": lambda: _send(chat_id, MENU),
    }

    handler = dispatch.get(raw_cmd)
    if handler:
        handler()
    else:
        _send(chat_id, f"🤖 No entendí «{_e(text[:40])}»\n\nEscribí /ayuda para ver los comandos.")


# ══════════════════════════════════════════════════════════════════════════════
# LOOP PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    global _AUTHORIZED

    Path("logs").mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("logs/bot.log", encoding="utf-8"),
        ],
    )

    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        logger.critical("[Bot] Configurá TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID en el .env")
        sys.exit(1)

    _AUTHORIZED = _load_authorized()
    logger.info("[Bot] Usuarios autorizados: %s", _AUTHORIZED)

    db.init_db()
    logger.info("[Bot] Iniciando bot de Telegram (long polling)...")
    _send(
        config.TELEGRAM_CHAT_ID,
        "🤖 <b>Bot iniciado correctamente</b>\nEscribí /ayuda para ver los comandos.",
    )

    offset = 0
    while True:
        try:
            updates = _get_updates(offset=offset, timeout=30)
            for update in updates:
                offset = update["update_id"] + 1
                message = update.get("message") or {}
                chat_id = str(message.get("chat", {}).get("id", ""))
                text    = message.get("text", "")
                if not chat_id or not text:
                    continue
                logger.info("[Bot] [%s] → %s", chat_id, text[:80])
                _route(chat_id, text)

        except KeyboardInterrupt:
            logger.info("[Bot] Detenido (Ctrl+C).")
            break
        except Exception as e:
            logger.error("[Bot] Error en loop: %s", e, exc_info=True)
            time.sleep(5)


if __name__ == "__main__":
    main()
