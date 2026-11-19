"""Menú lateral de la web: los menús y reportes de Power BI que puede ver el usuario.

GET /api/dashboards -> [{"id", "nombre", "icono", "reportes": [{"id", "nombre", "descripcion"}]}]

Se lee de la base portal_reportes (tablas menu, reporte, usuario, rol, usuario_rol, permiso;
ver web/sql/portal_reportes.sql) según el email con que el usuario inició sesión en Entra ID.
No entrega las URL: la página abre cada reporte con /api/reporte/<id>, que redirige al enlace.
Static Web Apps sólo deja llegar aquí a usuarios con el rol "empleado".
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import azure.functions as func

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # web/api, para "compartido"

from compartido import portal, web  # noqa: E402


def main(req: func.HttpRequest) -> func.HttpResponse:
    email = web.usuario(req)
    try:
        conn = web.conexion_portal()
        try:
            menus = portal.menu_usuario(conn, email)
        finally:
            conn.close()
    except Exception:  # noqa: BLE001
        logging.exception("No se pudo leer el menú de portal_reportes")
        resp = web.respuesta({"mensaje": "No se pudo leer el menú de reportes."}, 500)
    else:
        resp = web.respuesta(menus)
    resp.headers["Cache-Control"] = "no-store"
    return resp
