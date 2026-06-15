"""
services/sheets.py
───────────────────
Integración con Google Sheets.
Actualiza (o crea) la hoja de cálculo con las publicaciones con score ≥ SCORE_MINIMO_EXPORTAR.

Estrategia:
  - Al inicializar busca o crea la hoja "Departamentos".
  - Escribe/actualiza el encabezado.
  - Por cada publicación: busca si ya existe (por id_publicacion + portal) y
    actualiza la fila, o agrega una fila nueva al final.

Requiere:
  - GOOGLE_SHEETS_ID: ID del spreadsheet
  - GOOGLE_SERVICE_ACCOUNT_JSON: JSON de service account (como string o path a archivo)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import gspread
from google.oauth2.service_account import Credentials

import config
from database.models import Publicacion

logger = logging.getLogger(__name__)

SHEET_NAME = "departamentos"
SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# ─── Definición de columnas ───────────────────────────────────────────────────
COLUMNAS: List[str] = [
    "fecha_deteccion",
    "dias_en_pagina",
    "estado",
    "score",
    "clasificacion",
    "portal",
    "inmobiliaria",
    "direccion",
    "barrio",
    "ambientes",
    "m2_cubiertos",
    "m2_descubiertos",
    "m2_totales",
    "precio_usd",
    "expensas",
    "usd_m2_efectivo",
    "antiguedad",
    "piso",
    "disposicion",
    "orientacion",
    "balcon",
    "cochera",
    "amenities",
    "pros",
    "contras",
    "comentarios",
    "url",
    "id_publicacion",
    "ultima_actualizacion",
]


# ══════════════════════════════════════════════════════════════════════════════
# SERVICIO
# ══════════════════════════════════════════════════════════════════════════════


class SheetsService:
    """Gestiona la sincronización de publicaciones con Google Sheets."""

    def __init__(self) -> None:
        self._client: Optional[gspread.Client] = None
        self._sheet: Optional[gspread.Worksheet] = None
        self._enabled = bool(config.GOOGLE_SHEETS_ID and config.GOOGLE_SERVICE_ACCOUNT_JSON)

        if not self._enabled:
            logger.warning(
                "[Sheets] GOOGLE_SHEETS_ID o GOOGLE_SERVICE_ACCOUNT_JSON no configurados. "
                "La exportación a Sheets estará desactivada."
            )

    # ── Inicialización ────────────────────────────────────────────────────────

    def connect(self) -> bool:
        """Establece conexión con Google Sheets. Retorna True si tuvo éxito."""
        if not self._enabled:
            return False
        try:
            creds = self._build_credentials()
            self._client = gspread.authorize(creds)
            spreadsheet = self._client.open_by_key(config.GOOGLE_SHEETS_ID)
            self._sheet = self._get_or_create_worksheet(spreadsheet)
            self._ensure_header()
            logger.info("[Sheets] Conectado a '%s' (hoja: %s)",
                        config.GOOGLE_SHEETS_ID, SHEET_NAME)
            return True
        except Exception as e:
            logger.error("[Sheets] Error al conectar: %s", e, exc_info=True)
            return False

    # ── Exportación ───────────────────────────────────────────────────────────

    def exportar_publicacion(self, pub: Publicacion) -> bool:
        """Inserta o actualiza una publicación en la hoja.

        Busca la fila existente por (id_publicacion + portal) y actualiza,
        o agrega al final si no existe.
        Retorna True si la operación fue exitosa.
        """
        if not self._sheet:
            return False

        try:
            row_data = self._pub_to_row(pub)
            row_num = self._find_row(pub.id_publicacion, pub.portal)

            if row_num:
                # Actualizar fila existente (preservar columna "comentarios")
                comentarios_col = COLUMNAS.index("comentarios") + 1
                try:
                    comentarios_actual = self._sheet.cell(row_num, comentarios_col).value
                    if comentarios_actual:
                        row_data[comentarios_col - 1] = comentarios_actual
                except Exception:
                    pass
                self._sheet.update(f"A{row_num}", [row_data])
                logger.debug("[Sheets] Actualizada fila %d: %s/%s", row_num, pub.portal, pub.id_publicacion)
            else:
                self._sheet.append_row(row_data, value_input_option="USER_ENTERED")
                logger.debug("[Sheets] Nueva fila: %s/%s", pub.portal, pub.id_publicacion)

            return True

        except gspread.exceptions.APIError as e:
            logger.error("[Sheets] APIError al exportar %s/%s: %s",
                         pub.portal, pub.id_publicacion, e)
            return False
        except Exception as e:
            logger.error("[Sheets] Error inesperado al exportar %s/%s: %s",
                         pub.portal, pub.id_publicacion, e, exc_info=True)
            return False

    def exportar_batch(self, publicaciones: List[Publicacion]) -> int:
        """Exporta una lista de publicaciones. Retorna la cantidad de éxitos."""
        if not self._sheet:
            return 0
        ok = sum(1 for pub in publicaciones if self.exportar_publicacion(pub))
        logger.info("[Sheets] Exportadas %d/%d publicaciones", ok, len(publicaciones))
        return ok

    # ── Helpers internos ──────────────────────────────────────────────────────

    def _build_credentials(self) -> Credentials:
        """Construye credenciales desde JSON string o archivo."""
        sa_json = config.GOOGLE_SERVICE_ACCOUNT_JSON

        # Intentar como JSON string directo
        try:
            service_account_info = json.loads(sa_json)
            return Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
        except (json.JSONDecodeError, ValueError):
            pass

        # Intentar como ruta a archivo JSON
        if os.path.isfile(sa_json):
            return Credentials.from_service_account_file(sa_json, scopes=SCOPES)

        # Variable de entorno alternativa: GOOGLE_SERVICE_ACCOUNT_FILE
        file_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "")
        if file_path and os.path.isfile(file_path):
            return Credentials.from_service_account_file(file_path, scopes=SCOPES)

        raise ValueError(
            "No se pudo construir credenciales de Google. "
            "Verificar GOOGLE_SERVICE_ACCOUNT_JSON o GOOGLE_SERVICE_ACCOUNT_FILE."
        )

    def _get_or_create_worksheet(self, spreadsheet: gspread.Spreadsheet) -> gspread.Worksheet:
        """Obtiene la hoja existente o la crea si no existe."""
        try:
            return spreadsheet.worksheet(SHEET_NAME)
        except gspread.exceptions.WorksheetNotFound:
            logger.info("[Sheets] Hoja '%s' no encontrada, creando...", SHEET_NAME)
            ws = spreadsheet.add_worksheet(title=SHEET_NAME, rows=1000, cols=len(COLUMNAS) + 5)
            return ws

    def _ensure_header(self) -> None:
        """Escribe el encabezado si la hoja está vacía o el encabezado es incorrecto."""
        if not self._sheet:
            return
        try:
            first_row = self._sheet.row_values(1)
            if first_row != COLUMNAS:
                self._sheet.update("A1", [COLUMNAS])
                # Formatear encabezado en negrita
                self._sheet.format("1:1", {
                    "textFormat": {"bold": True},
                    "backgroundColor": {"red": 0.2, "green": 0.4, "blue": 0.8},
                })
                logger.info("[Sheets] Encabezado actualizado.")
        except Exception as e:
            logger.warning("[Sheets] No se pudo verificar/escribir encabezado: %s", e)

    def _find_row(self, id_publicacion: str, portal: str) -> Optional[int]:
        """Busca el número de fila de una publicación por ID y portal.

        Retorna None si no se encuentra.
        """
        try:
            id_col = COLUMNAS.index("id_publicacion") + 1
            portal_col = COLUMNAS.index("portal") + 1

            id_target = str(id_publicacion or "").strip()
            portal_target = str(portal or "").strip().lower()

            ids = self._sheet.col_values(id_col)
            portales = self._sheet.col_values(portal_col)

            for i, (id_val, portal_val) in enumerate(zip(ids, portales), start=1):
                if str(id_val).strip() == id_target and str(portal_val).strip().lower() == portal_target:
                    return i
        except Exception as e:
            logger.debug("[Sheets] Error buscando fila: %s", e)
        return None

    @staticmethod
    def _pub_to_row(pub: Publicacion) -> List[Any]:
        """Convierte una Publicacion en una fila de valores para Sheets."""
        def fmt_bool(val: bool) -> str:
            return "Sí" if val else "No"

        def fmt_float(val: Optional[float], decimals: int = 2) -> str:
            return f"{val:.{decimals}f}" if val is not None else ""

        return [
            pub.fecha_deteccion or "",
            pub.dias_en_pagina,
            pub.estado or "",
            fmt_float(pub.score, 1),
            pub.clasificacion or "",
            pub.portal,
            pub.inmobiliaria or "",
            pub.direccion or "",
            pub.barrio or "",
            pub.ambientes if pub.ambientes is not None else "",
            fmt_float(pub.m2_cubiertos, 1),
            fmt_float(pub.m2_descubiertos, 1),
            fmt_float(pub.m2_totales, 1),
            fmt_float(pub.precio_usd, 0),
            fmt_float(pub.expensas, 0),
            fmt_float(pub.usd_m2_efectivo, 0),
            pub.antiguedad if pub.antiguedad is not None else "",
            pub.piso if pub.piso is not None else "",
            pub.disposicion or "",
            pub.orientacion or "",
            fmt_bool(pub.balcon),
            fmt_bool(pub.cochera),
            pub.amenities or "",
            pub.pros or "",
            pub.contras or "",
            pub.comentarios or "",
            pub.url,
            pub.id_publicacion,
            pub.ultima_actualizacion or "",
        ]
