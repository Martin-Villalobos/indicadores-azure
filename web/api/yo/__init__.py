"""Qué puede hacer en la web el usuario que inició sesión.

GET /api/yo -> {"email", "admin", "cargar", "maestros"}

La página lo usa para mostrar sólo las herramientas permitidas (Cargar archivos, Datos maestros,
Usuarios). Cada API vuelve a revisar el permiso, así que esconderlas no es la única protección.
También anota usuario.ultimo_acceso, que se ve en el mantenedor de usuarios.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

import azure.functions as func

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # web/api, para "compartido"

from compartido import portal, web  # noqa: E402


def main(req: func.HttpRequest) -> func.HttpResponse:
    email = web.usuario(req)
    try:
        conn = web.conexion_portal()
        try:
            with conn.cursor() as cur:
                permisos = portal.permisos_cursor(cur, email)
                cur.execute("UPDATE usuario SET ultimo_acceso = %s WHERE email = %s", (datetime.now(), email))
            conn.commit()
        finally:
            conn.close()
    except Exception:  # noqa: BLE001
        logging.exception("No se pudieron leer los permisos de portal_reportes")
        resp = web.respuesta({"mensaje": "No se pudieron leer tus permisos."}, 500)
    else:
        resp = web.respuesta({"email": email, **permisos})
    resp.headers["Cache-Control"] = "no-store"
    return resp
