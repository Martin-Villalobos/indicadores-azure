"""Entrega la lista de dashboards (nombre, descripción y enlace) sólo a usuarios con login.

Los enlaces de "Publicar en la web" no van en el código ni en el repo: se guardan en la
variable de entorno DASHBOARDS de la Static Web App, como JSON:
    [{"nombre": "IP del mes", "descripcion": "...", "url": "https://app.powerbi.com/view?r=..."}]
Static Web Apps sólo deja llegar aquí a usuarios con el rol "empleado".
"""

from __future__ import annotations

import json
import logging
import os

import azure.functions as func


def _respuesta(datos, status: int = 200) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(datos, ensure_ascii=False),
        status_code=status,
        mimetype="application/json",
        headers={"Cache-Control": "no-store"},
    )


def main(req: func.HttpRequest) -> func.HttpResponse:
    crudo = os.getenv("DASHBOARDS", "").strip()
    if not crudo:
        return _respuesta({"mensaje": "Falta la variable de entorno DASHBOARDS en la Static Web App."}, 500)
    try:
        lista = json.loads(crudo)
        dashboards = [
            {"nombre": str(d["nombre"]), "descripcion": str(d.get("descripcion", "")), "url": str(d.get("url", ""))}
            for d in lista
        ]
    except (ValueError, TypeError, KeyError) as exc:
        logging.exception("DASHBOARDS inválido")
        return _respuesta({"mensaje": f"La variable DASHBOARDS no es un JSON válido: {exc}"}, 500)
    return _respuesta(dashboards)
