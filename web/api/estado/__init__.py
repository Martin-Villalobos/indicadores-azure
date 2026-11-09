"""Dice en qué quedó un archivo subido: procesando, cargado o con error.

Sólo mira en qué carpeta del blob está el archivo; no lo lee.
GET /api/estado?blob=<tipo>/entrada/<nombre>
"""

from __future__ import annotations

import json
import os
import re

import azure.functions as func
from azure.core.exceptions import ResourceNotFoundError
from azure.storage.blob import BlobServiceClient


PATRON = re.compile(r"^(?P<tipo>[a-z0-9_]+)/entrada/(?P<nombre>[^/]+)$")


def _respuesta(datos: dict, status: int = 200) -> func.HttpResponse:
    return func.HttpResponse(json.dumps(datos, ensure_ascii=False), status_code=status, mimetype="application/json")


def main(req: func.HttpRequest) -> func.HttpResponse:
    coincide = PATRON.match(req.params.get("blob") or "")
    if not coincide:
        return _respuesta({"estado": "ERROR", "mensaje": "Parámetro blob inválido"}, 400)
    tipo, nombre = coincide["tipo"], coincide["nombre"]

    contenedor = BlobServiceClient.from_connection_string(
        os.environ["BLOB_CONNECTION_STRING"]
    ).get_container_client(os.getenv("BLOB_CONTAINER", "cargas"))

    def propiedades(ruta: str):
        try:
            return contenedor.get_blob_client(ruta).get_blob_properties()
        except ResourceNotFoundError:
            return None

    procesado = propiedades(f"{tipo}/procesados/{nombre}")
    if procesado is not None:
        meta = procesado.metadata or {}
        return _respuesta({
            "estado": meta.get("estado", "COMPLETADO"),
            "carga_id": meta.get("carga_id"),
            "filas_cargadas": meta.get("filas"),
        })

    if propiedades(f"{tipo}/errores/{nombre}") is not None:
        try:
            detalle = contenedor.download_blob(f"{tipo}/errores/{nombre}.error.txt").readall().decode("utf-8")
            mensaje = detalle.split("\n\n", 1)[-1].strip()
        except ResourceNotFoundError:
            mensaje = "Error sin detalle."
        return _respuesta({"estado": "ERROR", "mensaje": mensaje})

    if propiedades(f"{tipo}/entrada/{nombre}") is not None:
        return _respuesta({"estado": "PROCESANDO"})

    return _respuesta({"estado": "DESCONOCIDO", "mensaje": "No se encontró el archivo en el blob."}, 404)
