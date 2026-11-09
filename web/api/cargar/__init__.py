"""Recibe un archivo desde la web y lo deja en el blob para el job de carga.

La web no lee el archivo: lo guarda en ``<tipo>/entrada/`` y el Container
Apps Job (src/indicadores_azure/procesar.py) lo procesa. La web consulta después /api/estado.
Static Web Apps sólo deja llegar aquí a usuarios con el rol "empleado".
"""

from __future__ import annotations

import base64
import json
import os
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import azure.functions as func
from azure.storage.blob import BlobServiceClient


# Tipos que se pueden subir desde la web (deben existir en src/indicadores_azure/lectores).
TIPOS = {"anexo1": {".xlsx"}}
TAMANO_MAXIMO = 50 * 1024 * 1024


def _contenedor():
    servicio = BlobServiceClient.from_connection_string(os.environ["BLOB_CONNECTION_STRING"])
    contenedor = servicio.get_container_client(os.getenv("BLOB_CONTAINER", "cargas"))
    if not contenedor.exists():
        contenedor.create_container()
    return contenedor


def _usuario(req: func.HttpRequest) -> str:
    principal = req.headers.get("x-ms-client-principal")
    if not principal:
        return "desconocido"
    try:
        return str(json.loads(base64.b64decode(principal)).get("userDetails") or "desconocido")
    except (ValueError, TypeError):
        return "desconocido"


def _nombre_seguro(nombre: str) -> str:
    nombre = Path(nombre.replace("\\", "/")).name
    return re.sub(r"[^\w.\- ()]", "_", nombre, flags=re.UNICODE).strip() or "archivo"


def _ascii(texto: str) -> str:
    """Los metadatos de blob sólo aceptan ASCII: se guardan con %XX (el job los decodifica)."""

    return quote(texto, safe=" @._-()")


def _respuesta(datos: dict, status: int) -> func.HttpResponse:
    return func.HttpResponse(json.dumps(datos, ensure_ascii=False), status_code=status, mimetype="application/json")


def main(req: func.HttpRequest) -> func.HttpResponse:
    tipo = (req.params.get("tipo") or "").lower()
    if tipo not in TIPOS:
        return _respuesta({"estado": "ERROR", "mensaje": f"Tipo no soportado: {tipo or '(vacío)'}"}, 400)

    original = Path((req.params.get("nombre") or "").replace("\\", "/")).name
    nombre = _nombre_seguro(original)
    if Path(nombre).suffix.lower() not in TIPOS[tipo]:
        return _respuesta({"estado": "ERROR", "mensaje": "Extensión no permitida: " + ", ".join(sorted(TIPOS[tipo]))}, 400)

    contenido = req.get_body()
    if not contenido:
        return _respuesta({"estado": "ERROR", "mensaje": "El archivo llegó vacío"}, 400)
    if len(contenido) > TAMANO_MAXIMO:
        return _respuesta({"estado": "ERROR", "mensaje": "El archivo supera los 50 MB"}, 413)

    blob = f"{tipo}/entrada/{datetime.now().strftime('%Y%m%d_%H%M%S')}_{nombre}"
    _contenedor().get_blob_client(blob).upload_blob(
        contenido,
        overwrite=True,
        metadata={
            "subido_por": _ascii(_usuario(req)),
            "nombre_original": _ascii(original or nombre),
        },
    )
    return _respuesta({"estado": "RECIBIDO", "archivo": original or nombre, "blob": blob}, 202)
