"""Abre un dashboard en el iframe sin que su enlace esté en la página.

GET /api/reporte/<id> redirige (302) al enlace de "Publicar en la web" número <id>
de la variable DASHBOARDS (el mismo orden que entrega /api/dashboards).
Static Web Apps sólo deja llegar aquí a usuarios con el rol "empleado".

El navegador sigue la redirección, así que el enlace real todavía se ve en la pestaña
Red de las herramientas del navegador (F12). Esto lo saca del código de la página;
no lo vuelve privado.
"""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path

import azure.functions as func

# Reutiliza la lectura de DASHBOARDS de la función vecina (cada función es una carpeta suelta).
_spec = importlib.util.spec_from_file_location(
    "api_dashboards_comun", Path(__file__).resolve().parents[1] / "dashboards" / "__init__.py"
)
_dashboards = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_dashboards)


def _texto(mensaje: str, status: int) -> func.HttpResponse:
    return func.HttpResponse(mensaje, status_code=status, mimetype="text/plain", charset="utf-8",
                             headers={"Cache-Control": "no-store"})


def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        dashboards = _dashboards.leer_dashboards()
    except ValueError as exc:
        logging.exception("DASHBOARDS inválido")
        return _texto(str(exc), 500)

    crudo = req.route_params.get("id", "")
    if not crudo.isdigit() or int(crudo) >= len(dashboards):
        return _texto("Dashboard no encontrado.", 404)
    url = dashboards[int(crudo)]["url"]
    if not url.startswith("https://"):
        return _texto("Este dashboard todavía no tiene enlace configurado.", 404)

    return func.HttpResponse(
        status_code=302,
        headers={"Location": url, "Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )
