"""
database/db.py
──────────────
Capa de acceso a datos sobre SQLite.
Gestiona inserción, actualización, historial de precios y marcado de bajas.
"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Generator, List, Optional, Sequence

import config
from database.models import Publicacion

logger = logging.getLogger(__name__)

CACHE_TTL_HOURS: int = 2   # horas antes de repetir scraping para los mismos filtros


# ══════════════════════════════════════════════════════════════════════════════
# INICIALIZACIÓN
# ══════════════════════════════════════════════════════════════════════════════


def init_db() -> None:
    """Crea la base de datos y las tablas si no existen."""
    db_path = Path(config.DATABASE_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    schema_path = Path(__file__).parent.parent / "schema.sql"

    with get_connection() as conn:
        if schema_path.exists():
            conn.executescript(schema_path.read_text(encoding="utf-8"))
        else:
            _create_schema_inline(conn)
        _run_migrations(conn)

    logger.info("Base de datos inicializada: %s", config.DATABASE_PATH)


def _run_migrations(conn: sqlite3.Connection) -> None:
    """Aplica migraciones de columnas nuevas de forma idempotente."""
    pending = [
        "ALTER TABLE publicaciones ADD COLUMN operacion TEXT DEFAULT 'venta'",
        "ALTER TABLE publicaciones ADD COLUMN imagen_url TEXT",
    ]
    for stmt in pending:
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError:
            pass  # columna ya existe


def _create_schema_inline(conn: sqlite3.Connection) -> None:
    """Fallback: crea el esquema directamente sin leer schema.sql."""
    conn.executescript("""
        PRAGMA journal_mode = WAL;
        PRAGMA foreign_keys = ON;

        CREATE TABLE IF NOT EXISTS publicaciones (
            id_publicacion      TEXT NOT NULL,
            portal              TEXT NOT NULL,
            url                 TEXT NOT NULL,
            inmobiliaria        TEXT,
            direccion           TEXT,
            barrio              TEXT,
            ambientes           INTEGER,
            m2_cubiertos        REAL,
            m2_descubiertos     REAL,
            m2_totales          REAL,
            precio_usd          REAL,
            expensas            REAL,
            antiguedad          INTEGER,
            piso                INTEGER,
            disposicion         TEXT,
            orientacion         TEXT,
            balcon              INTEGER DEFAULT 0,
            cochera             INTEGER DEFAULT 0,
            amenities           TEXT,
            descripcion         TEXT,
            fecha_publicacion   TEXT,
            score               REAL,
            clasificacion       TEXT,
            pros                TEXT,
            contras             TEXT,
            usd_m2_efectivo     REAL,
            estado              TEXT DEFAULT 'NUEVA',
            operacion           TEXT DEFAULT 'venta',
            precio_anterior     REAL,
            variacion_porcentual REAL,
            fecha_deteccion     TEXT,
            ultima_actualizacion TEXT,
            comentarios         TEXT,
            PRIMARY KEY (id_publicacion, portal)
        );

        CREATE TABLE IF NOT EXISTS historial_precios (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            id_publicacion  TEXT NOT NULL,
            portal          TEXT NOT NULL,
            precio_usd      REAL NOT NULL,
            fecha_registro  TEXT NOT NULL,
            estado          TEXT
        );

        CREATE TABLE IF NOT EXISTS search_cache (
            filters_hash  TEXT PRIMARY KEY,
            barrios       TEXT,
            precio_max    INTEGER,
            m2_min        INTEGER,
            scraped_at    TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_pub_barrio ON publicaciones (barrio);
        CREATE INDEX IF NOT EXISTS idx_pub_score  ON publicaciones (score);
        CREATE INDEX IF NOT EXISTS idx_pub_estado ON publicaciones (estado);
        CREATE INDEX IF NOT EXISTS idx_hist_pub   ON historial_precios (id_publicacion, portal);
    """)


# ══════════════════════════════════════════════════════════════════════════════
# CONEXIÓN
# ══════════════════════════════════════════════════════════════════════════════


@contextmanager
def get_connection() -> Generator[sqlite3.Connection, None, None]:
    """Context manager que entrega una conexión SQLite con autocommit/rollback."""
    conn = sqlite3.connect(config.DATABASE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# OPERACIONES PRINCIPALES
# ══════════════════════════════════════════════════════════════════════════════


def upsert_publicacion(pub: Publicacion) -> str:
    """Inserta o actualiza una publicación y registra historial de precios.

    Retorna el estado resultante:
        'NUEVA'       → ID no existía
        'BAJA_PRECIO' → precio bajó
        'SUBA_PRECIO' → precio subió
        'SIN_CAMBIOS' → sin variación de precio
    """
    existing = get_publicacion(pub.id_publicacion, pub.portal)
    estado = "NUEVA"

    if existing:
        precio_anterior = existing["precio_usd"]
        pub.fecha_deteccion = existing["fecha_deteccion"]  # preservar fecha original

        if pub.precio_usd is not None and precio_anterior is not None:
            if pub.precio_usd < precio_anterior:
                estado = "BAJA_PRECIO"
                variacion = ((pub.precio_usd - precio_anterior) / precio_anterior) * 100
                pub.precio_anterior = precio_anterior
                pub.variacion_porcentual = round(variacion, 2)
            elif pub.precio_usd > precio_anterior:
                estado = "SUBA_PRECIO"
                variacion = ((pub.precio_usd - precio_anterior) / precio_anterior) * 100
                pub.precio_anterior = precio_anterior
                pub.variacion_porcentual = round(variacion, 2)
            else:
                estado = "SIN_CAMBIOS"
        else:
            estado = "SIN_CAMBIOS"

    pub.estado = estado
    pub.ultima_actualizacion = datetime.now().isoformat(timespec="seconds")

    _save_publicacion(pub)

    if pub.precio_usd:
        _save_historial(pub.id_publicacion, pub.portal, pub.precio_usd, pub.ultima_actualizacion, estado)

    logger.debug("[DB] %s %s/%s → %s", estado, pub.portal, pub.id_publicacion, pub.barrio)
    return estado


def get_publicacion(id_publicacion: str, portal: str) -> Optional[sqlite3.Row]:
    """Retorna la fila de la publicación o None si no existe."""
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM publicaciones WHERE id_publicacion = ? AND portal = ?",
            (id_publicacion, portal),
        ).fetchone()


def get_publicaciones_para_exportar() -> List[sqlite3.Row]:
    """Retorna publicaciones con score ≥ SCORE_MINIMO_EXPORTAR, ordenadas por score desc."""
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM publicaciones WHERE score >= ? ORDER BY score DESC",
            (config.SCORE_MINIMO_EXPORTAR,),
        ).fetchall()


def get_ids_activos(portal: str) -> set:
    """Retorna el conjunto de IDs activos (no ELIMINADOS) para un portal."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id_publicacion FROM publicaciones WHERE portal = ? AND estado != 'ELIMINADA'",
            (portal,),
        ).fetchall()
    return {row["id_publicacion"] for row in rows}


def get_top_publicaciones(limit: int = 10, barrio: Optional[str] = None) -> List[sqlite3.Row]:
    """Retorna las top N publicaciones por score (no eliminadas)."""
    with get_connection() as conn:
        if barrio:
            return conn.execute(
                """SELECT * FROM publicaciones
                   WHERE score IS NOT NULL AND estado != 'ELIMINADA'
                   AND LOWER(barrio) LIKE LOWER(?)
                   ORDER BY score DESC LIMIT ?""",
                (f"%{barrio}%", limit),
            ).fetchall()
        return conn.execute(
            """SELECT * FROM publicaciones
               WHERE score IS NOT NULL AND estado != 'ELIMINADA'
               ORDER BY score DESC LIMIT ?""",
            (limit,),
        ).fetchall()


def get_recientes(limit: int = 10) -> List[sqlite3.Row]:
    """Retorna las N publicaciones detectadas más recientemente."""
    with get_connection() as conn:
        return conn.execute(
            """SELECT * FROM publicaciones
               WHERE score IS NOT NULL AND estado != 'ELIMINADA'
               ORDER BY fecha_deteccion DESC LIMIT ?""",
            (limit,),
        ).fetchall()


def get_estadisticas() -> dict:
    """Retorna estadísticas generales de la base de datos."""
    with get_connection() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM publicaciones WHERE estado != 'ELIMINADA'"
        ).fetchone()[0]
        por_portal = {
            r[0]: r[1]
            for r in conn.execute(
                "SELECT portal, COUNT(*) FROM publicaciones WHERE estado != 'ELIMINADA' GROUP BY portal"
            ).fetchall()
        }
        por_estado = {
            r[0]: r[1]
            for r in conn.execute(
                "SELECT estado, COUNT(*) FROM publicaciones GROUP BY estado ORDER BY COUNT(*) DESC"
            ).fetchall()
        }
        agg = conn.execute(
            "SELECT MAX(score), AVG(score) FROM publicaciones "
            "WHERE estado != 'ELIMINADA' AND score IS NOT NULL"
        ).fetchone()
        ultima_act = conn.execute(
            "SELECT MAX(ultima_actualizacion) FROM publicaciones"
        ).fetchone()[0]
    return {
        "total": total,
        "por_portal": por_portal,
        "por_estado": por_estado,
        "score_max": agg[0] if agg else None,
        "score_avg": agg[1] if agg else None,
        "ultima_actualizacion": ultima_act,
    }


def get_stats_por_barrio() -> List[dict]:
    """Estadísticas agrupadas por barrio: precio promedio, USD/m², expensas y score."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                barrio,
                COUNT(*)                                              AS cantidad,
                AVG(usd_m2_efectivo)                                  AS avg_usd_m2,
                MIN(usd_m2_efectivo)                                  AS min_usd_m2,
                MAX(usd_m2_efectivo)                                  AS max_usd_m2,
                AVG(CASE WHEN expensas > 0 THEN expensas END)         AS avg_expensas,
                MIN(CASE WHEN expensas > 0 THEN expensas END)         AS min_expensas,
                MAX(CASE WHEN expensas > 0 THEN expensas END)         AS max_expensas,
                AVG(score)                                            AS avg_score,
                MAX(score)                                            AS max_score,
                AVG(precio_usd)                                       AS avg_precio,
                MIN(precio_usd)                                       AS min_precio,
                MAX(precio_usd)                                       AS max_precio,
                AVG(COALESCE(m2_totales, m2_cubiertos))               AS avg_m2
            FROM publicaciones
            WHERE estado != 'ELIMINADA' AND barrio IS NOT NULL
            GROUP BY barrio
            ORDER BY avg_score DESC
            """,
        ).fetchall()
    return [dict(r) for r in rows]


def marcar_eliminadas(ids_activos_scrape: Sequence[str], portal: str) -> int:
    """Marca como ELIMINADA toda publicación del portal que ya no apareció en el scrape.

    No borra registros: preserva el historial completo.
    Retorna la cantidad de publicaciones marcadas.
    """
    ids_db = get_ids_activos(portal)
    ids_activos_set = set(str(i) for i in ids_activos_scrape)
    eliminadas = ids_db - ids_activos_set
    now = datetime.now().isoformat(timespec="seconds")

    with get_connection() as conn:
        for id_pub in eliminadas:
            conn.execute(
                "UPDATE publicaciones SET estado = 'ELIMINADA', ultima_actualizacion = ? "
                "WHERE id_publicacion = ? AND portal = ?",
                (now, id_pub, portal),
            )

    if eliminadas:
        logger.info("[DB] %d publicaciones marcadas como ELIMINADAS en %s", len(eliminadas), portal)

    return len(eliminadas)


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS PRIVADOS
# ══════════════════════════════════════════════════════════════════════════════


def _save_publicacion(pub: Publicacion) -> None:
    """Ejecuta el INSERT OR REPLACE para guardar la publicación."""
    params = {
        "id_publicacion": pub.id_publicacion,
        "portal": pub.portal,
        "url": pub.url,
        "inmobiliaria": pub.inmobiliaria,
        "direccion": pub.direccion,
        "barrio": pub.barrio,
        "ambientes": pub.ambientes,
        "m2_cubiertos": pub.m2_cubiertos,
        "m2_descubiertos": pub.m2_descubiertos,
        "m2_totales": pub.m2_totales,
        "precio_usd": pub.precio_usd,
        "expensas": pub.expensas,
        "antiguedad": pub.antiguedad,
        "piso": pub.piso,
        "disposicion": pub.disposicion,
        "orientacion": pub.orientacion,
        "balcon": int(pub.balcon),
        "cochera": int(pub.cochera),
        "amenities": pub.amenities,
        "descripcion": pub.descripcion,
        "fecha_publicacion": pub.fecha_publicacion,
        "score": pub.score,
        "clasificacion": pub.clasificacion,
        "pros": pub.pros,
        "contras": pub.contras,
        "usd_m2_efectivo": pub.usd_m2_efectivo,
        "estado": pub.estado,
        "operacion": getattr(pub, 'operacion', 'venta'),
        "imagen_url": getattr(pub, 'imagen_url', None),
        "precio_anterior": pub.precio_anterior,
        "variacion_porcentual": pub.variacion_porcentual,
        "fecha_deteccion": pub.fecha_deteccion,
        "ultima_actualizacion": pub.ultima_actualizacion,
        "comentarios": pub.comentarios,
    }

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO publicaciones (
                id_publicacion, portal, url, inmobiliaria, direccion, barrio,
                ambientes, m2_cubiertos, m2_descubiertos, m2_totales,
                precio_usd, expensas, antiguedad, piso, disposicion, orientacion,
                balcon, cochera, amenities, descripcion, fecha_publicacion,
                score, clasificacion, pros, contras, usd_m2_efectivo,
                estado, precio_anterior, variacion_porcentual,
                fecha_deteccion, ultima_actualizacion, comentarios, operacion, imagen_url
            ) VALUES (
                :id_publicacion, :portal, :url, :inmobiliaria, :direccion, :barrio,
                :ambientes, :m2_cubiertos, :m2_descubiertos, :m2_totales,
                :precio_usd, :expensas, :antiguedad, :piso, :disposicion, :orientacion,
                :balcon, :cochera, :amenities, :descripcion, :fecha_publicacion,
                :score, :clasificacion, :pros, :contras, :usd_m2_efectivo,
                :estado, :precio_anterior, :variacion_porcentual,
                :fecha_deteccion, :ultima_actualizacion, :comentarios, :operacion, :imagen_url
            )
            ON CONFLICT(id_publicacion, portal) DO UPDATE SET
                url                  = excluded.url,
                inmobiliaria         = excluded.inmobiliaria,
                direccion            = excluded.direccion,
                barrio               = excluded.barrio,
                ambientes            = excluded.ambientes,
                m2_cubiertos         = excluded.m2_cubiertos,
                m2_descubiertos      = excluded.m2_descubiertos,
                m2_totales           = excluded.m2_totales,
                precio_usd           = excluded.precio_usd,
                expensas             = excluded.expensas,
                antiguedad           = excluded.antiguedad,
                piso                 = excluded.piso,
                disposicion          = excluded.disposicion,
                orientacion          = excluded.orientacion,
                balcon               = excluded.balcon,
                cochera              = excluded.cochera,
                amenities            = excluded.amenities,
                descripcion          = excluded.descripcion,
                fecha_publicacion    = excluded.fecha_publicacion,
                score                = excluded.score,
                clasificacion        = excluded.clasificacion,
                pros                 = excluded.pros,
                contras              = excluded.contras,
                usd_m2_efectivo      = excluded.usd_m2_efectivo,
                estado               = excluded.estado,
                precio_anterior      = excluded.precio_anterior,
                variacion_porcentual = excluded.variacion_porcentual,
                ultima_actualizacion = excluded.ultima_actualizacion,
                operacion            = excluded.operacion,
                imagen_url           = excluded.imagen_url
            """,
            params,
        )


def _save_historial(
    id_publicacion: str, portal: str, precio: float, fecha: str, estado: str
) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO historial_precios (id_publicacion, portal, precio_usd, fecha_registro, estado) "
            "VALUES (?, ?, ?, ?, ?)",
            (id_publicacion, portal, precio, fecha, estado),
        )


# ══════════════════════════════════════════════════════════════════════════════
# CACHÉ DE BÚSQUEDAS DINÁMICAS
# ══════════════════════════════════════════════════════════════════════════════


def has_fresh_results(filters_hash: str) -> bool:
    """Retorna True si existe un scraping reciente (< CACHE_TTL_HOURS) para este hash."""
    with get_connection() as conn:
        # Ensure table exists (for DBs created before this migration)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS search_cache (
                filters_hash TEXT PRIMARY KEY,
                barrios TEXT,
                precio_max INTEGER,
                m2_min INTEGER,
                scraped_at TEXT NOT NULL
            )
        """)
        row = conn.execute(
            "SELECT scraped_at FROM search_cache WHERE filters_hash = ?",
            (filters_hash,),
        ).fetchone()
    if not row:
        return False
    try:
        scraped = datetime.fromisoformat(row["scraped_at"])
        age_hours = (datetime.now() - scraped).total_seconds() / 3600
        return age_hours < CACHE_TTL_HOURS
    except (ValueError, TypeError):
        return False


def mark_search_done(filters_hash: str, barrios: str = "", precio_max: Optional[int] = None, m2_min: Optional[int] = None) -> None:
    """Registra que se acaba de completar un scraping para este hash."""
    now = datetime.now().isoformat(timespec="seconds")
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS search_cache (
                filters_hash TEXT PRIMARY KEY,
                barrios TEXT,
                precio_max INTEGER,
                m2_min INTEGER,
                scraped_at TEXT NOT NULL
            )
        """)
        conn.execute(
            """INSERT INTO search_cache (filters_hash, barrios, precio_max, m2_min, scraped_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(filters_hash) DO UPDATE SET scraped_at = excluded.scraped_at""",
            (filters_hash, barrios, precio_max, m2_min, now),
        )
    logger.debug("[DB] search_cache actualizado: hash=%s barrios=%s", filters_hash[:8], barrios)


def get_cache_timestamp(filters_hash: str) -> Optional[str]:
    """Retorna el ISO timestamp del último scraping para este hash, o None si no existe."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT scraped_at FROM search_cache WHERE filters_hash = ? LIMIT 1",
            (filters_hash,),
        ).fetchone()
    return row["scraped_at"] if row else None
