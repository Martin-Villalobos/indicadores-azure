"""Utilidades de las funciones HTTP: respuesta JSON, usuario, conexión a MySQL y aviso al job."""

from __future__ import annotations

import base64
import json
import os
from datetime import date, datetime
from decimal import Decimal

import azure.functions as func


def respuesta(datos, status: int = 200) -> func.HttpResponse:
    def conv(v):
        if isinstance(v, datetime):
            return v.isoformat(sep=" ")
        if isinstance(v, date):
            return v.isoformat()
        if isinstance(v, Decimal):
            return float(v)
        raise TypeError(type(v))

    return func.HttpResponse(json.dumps(datos, ensure_ascii=False, default=conv), status_code=status,
                             mimetype="application/json")


def usuario(req: func.HttpRequest) -> str:
    try:
        principal = json.loads(base64.b64decode(req.headers.get("x-ms-client-principal", "")))
        return principal.get("userDetails") or "desconocido"
    except (ValueError, TypeError):
        return "desconocido"


def conexion():
    import pymysql

    host = os.environ["DB_HOST"]
    ca = os.getenv("DB_SSL_CA")
    if ca:
        ssl = {"ca": ca}
    elif host in ("localhost", "127.0.0.1", "mysql"):
        ssl = None  # MySQL local de docker compose
    else:
        import certifi  # Azure Database for MySQL exige TLS

        ssl = {"ca": certifi.where()}
    return pymysql.connect(host=host, port=int(os.getenv("DB_PORT", "3306")), user=os.environ["DB_USER"],
                           password=os.environ["DB_PASSWORD"], database=os.getenv("DB_NAME", "indicadores_bi"),
                           charset="utf8mb4", autocommit=False, connect_timeout=15, ssl=ssl)


def contenedor():
    from azure.storage.blob import BlobServiceClient

    return BlobServiceClient.from_connection_string(
        os.environ["BLOB_CONNECTION_STRING"], retry_total=0, connection_timeout=5).get_container_client(
        os.getenv("BLOB_CONTAINER", "cargas"))


def avisar_job(motivo: str) -> None:
    """Deja un aviso en recalculo/entrada/ para que el job resuelva los recálculos pendientes."""

    nombre = f"recalculo/entrada/{datetime.now():%Y%m%d_%H%M%S_%f}.txt"
    contenedor().get_blob_client(nombre).upload_blob(f"{motivo}\n".encode(), overwrite=True)
