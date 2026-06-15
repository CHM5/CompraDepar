-- schema.sql
-- Esquema completo de la base de datos SQLite.
-- Se ejecuta automáticamente en database/db.py al inicializar.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ─── Tabla principal de publicaciones ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS publicaciones (
    -- Identificadores
    id_publicacion      TEXT    NOT NULL,
    portal              TEXT    NOT NULL,
    url                 TEXT    NOT NULL,

    -- Información del inmueble
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
    balcon              INTEGER DEFAULT 0,   -- 0/1 → bool
    cochera             INTEGER DEFAULT 0,   -- 0/1 → bool
    amenities           TEXT,
    descripcion         TEXT,
    fecha_publicacion   TEXT,

    -- Scoring y análisis
    score               REAL,
    clasificacion       TEXT,
    pros                TEXT,
    contras             TEXT,
    usd_m2_efectivo     REAL,

    -- Estado y seguimiento
    operacion           TEXT    DEFAULT 'venta',   -- 'venta' | 'alquiler'
    estado              TEXT    DEFAULT 'NUEVA',
    precio_anterior     REAL,
    variacion_porcentual REAL,
    fecha_deteccion     TEXT,
    ultima_actualizacion TEXT,
    comentarios         TEXT,

    PRIMARY KEY (id_publicacion, portal)
);

-- ─── Caché de búsquedas dinámicas ────────────────────────────────────────────
-- Registra cuándo se realizó el último scraping para un conjunto de filtros.
-- Permite implementar TTL (time-to-live) sin repetir scraping innecesario.
CREATE TABLE IF NOT EXISTS search_cache (
    filters_hash  TEXT    PRIMARY KEY,
    barrios       TEXT,
    precio_max    INTEGER,
    m2_min        INTEGER,
    scraped_at    TEXT    NOT NULL
);

-- ─── Historial de precios ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS historial_precios (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    id_publicacion  TEXT    NOT NULL,
    portal          TEXT    NOT NULL,
    precio_usd      REAL    NOT NULL,
    fecha_registro  TEXT    NOT NULL,
    estado          TEXT
);

-- ─── Índices ──────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_pub_barrio    ON publicaciones (barrio);
CREATE INDEX IF NOT EXISTS idx_pub_score     ON publicaciones (score);
CREATE INDEX IF NOT EXISTS idx_pub_estado    ON publicaciones (estado);
CREATE INDEX IF NOT EXISTS idx_pub_precio    ON publicaciones (precio_usd);
CREATE INDEX IF NOT EXISTS idx_hist_pub      ON historial_precios (id_publicacion, portal);
