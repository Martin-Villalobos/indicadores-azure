"""Entrega la lista de dashboards (nombre y descripción) sólo a usuarios con login.

Los enlaces de "Publicar en la web" no van en el código ni en el repo: se guardan en la
variable de entorno DASHBOARDS de la Static Web App, como JSON:
    [{"nombre": "IP del mes", "descripcion": "...", "url": "https://app.powerbi.com/view?r=..."}]
Esta API no entrega las URL: cada dashboard sale con su número ("id"), y la página lo
abre con /api/reporte/<id>, que redirige al enlace. Así el enlace no queda en la página.
Static Web Apps sólo deja llegar aquí a usuarios con el rol "empleado".
"""

from __future__ import annotations

import json
import logging
import os

import azure.functions as func


def leer_dashboards() -> list[dict]:
    """Lee DASHBOARDS. Lanza ValueError si falta o no es un JSON válido."""

    crudo = os.getenv("DASHBOARDS", "").strip()
    if not crudo:
        raise ValueError("Falta la variable de entorno DASHBOARDS en la Static Web App.")
    try:
        return [
            {"nombre": str(d["nombre"]), "descripcion": str(d.get("descripcion", "")), "url": str(d.get("url", ""))}
            for d in json.loads(crudo)
        ]
    except (ValueError, TypeError, KeyError) as exc:
        raise ValueError(f"La variable DASHBOARDS no es un JSON válido: {exc}") from exc


def _respuesta(datos, status: int = 200) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(datos, ensure_ascii=False),
        status_code=status,
        mimetype="application/json",
        headers={"Cache-Control": "no-store"},
    )


def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        dashboards = leer_dashboards()
    except ValueError as exc:
        logging.exception("DASHBOARDS inválido")
        return _respuesta({"mensaje": str(exc)}, 500)
    return _respuesta([
        {"id": i, "nombre": d["nombre"], "descripcion": d["descripcion"]} for i, d in enumerate(dashboards)
    ])
