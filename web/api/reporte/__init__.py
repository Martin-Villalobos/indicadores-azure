"""Abre un reporte de Power BI en el iframe sin que su enlace esté en la página.

GET /api/reporte/<id> redirige (302) a reporte.url_powerbi de la base portal_reportes,
sólo si el usuario que inició sesión tiene permiso sobre ese reporte o su menú.
Static Web Apps sólo deja llegar aquí a usuarios con el rol "empleado".

El navegador sigue la redirección, así que el enlace real todavía se ve en la pestaña
Red de las herramientas del navegador (F12). Esto lo saca del código de la página;
no lo vuelve privado.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import azure.functions as func

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # web/api, para "compartido"

from compartido import portal, web  # noqa: E402


def _texto(mensaje: str, status: int) -> func.HttpResponse:
    return func.HttpResponse(mensaje, status_code=status, mimetype="text/plain", charset="utf-8",
                             headers={"Cache-Control": "no-store"})


def main(req: func.HttpRequest) -> func.HttpResponse:
    crudo = req.route_params.get("id", "")
    if not crudo.isdigit():
        return _texto("Reporte no encontrado.", 404)
    try:
        conn = web.conexion_portal()
        try:
            url = portal.url_reporte(conn, web.usuario(req), int(crudo))
        finally:
            conn.close()
    except Exception:  # noqa: BLE001
        logging.exception("No se pudo leer el reporte de portal_reportes")
        return _texto("No se pudo leer el reporte.", 500)

    if url is None:
        return _texto("Reporte no encontrado.", 404)
    if not url.startswith("https://"):
        return _texto("Este reporte todavía no tiene enlace configurado.", 404)
    return func.HttpResponse(
        status_code=302,
        headers={"Location": url, "Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )
