"""Utilidades de las funciones HTTP: respuesta JSON, usuario, conexión a MySQL y aviso al job."""

from __future__ import annotations

import base64
import json
import logging
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


def conexion(database: str | None = None):
    """Conexión a MySQL; por defecto a DB_NAME (indicadores_bi)."""

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
                           password=os.environ["DB_PASSWORD"], database=database or os.getenv("DB_NAME", "indicadores_bi"),
                           charset="utf8mb4", autocommit=False, connect_timeout=15, ssl=ssl)


def conexion_portal():
    """Conexión a la base del menú de Power BI (PORTAL_DB_NAME, por defecto portal_reportes)."""

    return conexion(os.getenv("PORTAL_DB_NAME", "portal_reportes"))


def exigir(req: func.HttpRequest, herramienta: str) -> func.HttpResponse | None:
    """None si el usuario puede usar la herramienta ("cargar", "maestros" o "admin"); si no, la respuesta 403.

    Los permisos salen de los roles del usuario en portal_reportes (rol.es_admin, puede_cargar,
    puede_maestros). La página esconde lo que el usuario no puede usar; esto lo hace cumplir en la API.
    """

    from . import portal

    try:
        conn = conexion_portal()
        try:
            permitido = portal.permisos(conn, usuario(req)).get(herramienta, False)
        finally:
            conn.close()
    except Exception:  # noqa: BLE001
        logging.exception("No se pudieron leer los permisos de portal_reportes")
        return respuesta({"estado": "ERROR", "mensaje": "No se pudieron leer tus permisos."}, 500)
    if permitido:
        return None
    return respuesta({"estado": "ERROR", "mensaje": "No tienes permiso para esta sección. Pide acceso al administrador."}, 403)


def contenedor():
    from azure.storage.blob import BlobServiceClient

    return BlobServiceClient.from_connection_string(
        os.environ["BLOB_CONNECTION_STRING"], retry_total=0, connection_timeout=5).get_container_client(
        os.getenv("BLOB_CONTAINER", "cargas"))


def avisar_job(motivo: str) -> None:
    """Deja un aviso en recalculo/entrada/ para que el job resuelva los recálculos pendientes."""

    nombre = f"recalculo/entrada/{datetime.now():%Y%m%d_%H%M%S_%f}.txt"
    contenedor().get_blob_client(nombre).upload_blob(f"{motivo}\n".encode(), overwrite=True)
