"""
api/services/chat_service.py
────────────────────────────
Chat con IA sobre el mercado inmobiliario usando GPT-4o-mini.
Inyecta estadísticas en tiempo real de la DB como contexto.
"""

from __future__ import annotations

import json
import logging

import config
from database import db

logger = logging.getLogger(__name__)


def get_market_stats() -> dict:
    """Obtiene estadísticas del mercado desde la DB para pasarle a GPT como contexto."""
    try:
        with db.get_connection() as conn:
            rows_venta = conn.execute("""
                SELECT
                    barrio,
                    COUNT(*) as total,
                    ROUND(AVG(precio_usd), 0) as precio_promedio_usd,
                    ROUND(MIN(precio_usd), 0) as precio_min_usd,
                    ROUND(MAX(precio_usd), 0) as precio_max_usd,
                    ROUND(AVG(COALESCE(m2_totales, m2_cubiertos)), 0) as m2_promedio,
                    ROUND(AVG(usd_m2_efectivo), 0) as usd_por_m2_promedio,
                    ROUND(AVG(expensas), 0) as expensas_promedio_ars,
                    ROUND(AVG(ambientes), 1) as ambientes_promedio
                FROM publicaciones
                WHERE
                    estado != 'ELIMINADA'
                    AND barrio IS NOT NULL
                    AND precio_usd IS NOT NULL
                    AND COALESCE(operacion, 'venta') = 'venta'
                GROUP BY barrio
                HAVING total >= 2
                ORDER BY total DESC
                LIMIT 40
            """).fetchall()

            rows_alq = conn.execute("""
                SELECT
                    barrio,
                    COUNT(*) as total,
                    ROUND(AVG(precio_usd), 0) as precio_promedio_ars
                FROM publicaciones
                WHERE
                    estado != 'ELIMINADA'
                    AND barrio IS NOT NULL
                    AND precio_usd IS NOT NULL
                    AND operacion = 'alquiler'
                GROUP BY barrio
                HAVING total >= 2
                ORDER BY total DESC
                LIMIT 20
            """).fetchall()

            totals = conn.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN operacion = 'alquiler' THEN 1 ELSE 0 END) as alquileres,
                    MAX(ultima_actualizacion) as ultima_actualizacion
                FROM publicaciones WHERE estado != 'ELIMINADA'
            """).fetchone()

        return {
            "venta_por_barrio": [dict(r) for r in rows_venta],
            "alquiler_por_barrio": [dict(r) for r in rows_alq],
            "total_publicaciones": totals["total"] if totals else 0,
            "total_alquileres": totals["alquileres"] if totals else 0,
            "ultima_actualizacion": totals["ultima_actualizacion"] if totals else None,
        }
    except Exception as e:
        logger.error("[chat_service] Error obteniendo stats: %s", e)
        return {"venta_por_barrio": [], "alquiler_por_barrio": [], "total_publicaciones": 0}


def chat(query: str) -> str:
    """Responde una pregunta sobre el mercado inmobiliario de CABA usando GPT-4o-mini."""
    if not config.OPENAI_API_KEY:
        return (
            "⚙️ Para usar el chat con IA configurá `OPENAI_API_KEY` en el archivo `.env`.\n\n"
            "Mientras tanto podés buscar propiedades con el buscador de la izquierda."
        )

    try:
        from openai import OpenAI
    except ImportError:
        return "⚠️ Instalá el paquete: `pip install openai`"

    client = OpenAI(api_key=config.OPENAI_API_KEY)
    stats = get_market_stats()
    stats_json = json.dumps(stats, ensure_ascii=False, indent=2)

    system_prompt = f"""Sos un asistente especializado en el mercado inmobiliario de Capital Federal (CABA), Buenos Aires, Argentina.

Tenés acceso a datos en tiempo real de publicaciones de departamentos scrapeados de Zonaprop, Argenprop, MEL y Toribio Achával.

Estadísticas actuales del mercado:
{stats_json}

Instrucciones:
- Respondé preguntas sobre precios por barrio, promedios de m², comparativas, expensas, tendencias, etc.
- Usá los datos del contexto. Si no hay datos de un barrio mencionado, decilo y sugerí barrios similares.
- Sé conciso pero informativo. Usá listas o tablas markdown cuando ayude a la claridad.
- Precios de venta en USD, alquileres y expensas en ARS.
- Si la pregunta no es sobre inmuebles, redirigí amablemente al tema de propiedades en CABA.
- No inventes datos que no estén en el contexto."""

    try:
        resp = client.chat.completions.create(
            model=config.NLU_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query},
            ],
            max_tokens=700,
            temperature=0.3,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.error("[chat_service] Error OpenAI: %s", e)
        return f"⚠️ Error al consultar la IA: {e}"
