"""Recibe un archivo desde la web y lo deja en el blob para el job de carga.

La web no lee el archivo: lo guarda en ``<tipo>/entrada/`` y el Container
Apps Job (src/indicadores_azure/procesar.py) lo procesa. La web consulta después /api/estado.
Static Web Apps sólo deja llegar aquí a usuarios con el rol "empleado".
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import azure.functions as func


# Tipos que se pueden subir desde la web (deben existir en src/indicadores_azure/lectores).
TIPOS = {"anexo1": {".xlsx"}}
TAMANO_MAXIMO = 50 * 1024 * 1024


def _contenedor():
    from azure.storage.blob import BlobServiceClient

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


def _main(req: func.HttpRequest) -> func.HttpResponse:
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


def main(req: func.HttpRequest) -> func.HttpResponse:
    # Un error no controlado haría que Azure responda 500 vacío; así la web muestra el motivo.
    try:
        return _main(req)
    except KeyError as exc:
        return _respuesta({"estado": "ERROR", "mensaje": f"Falta la variable de entorno {exc} en la Static Web App."}, 500)
    except Exception as exc:  # noqa: BLE001
        logging.exception("Error en la API")
        return _respuesta({"estado": "ERROR", "mensaje": f"Error del servidor: {exc.__class__.__name__}: {exc}"}, 500)
