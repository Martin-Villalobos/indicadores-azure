"""Job de carga: procesa los archivos que llegan a ``<contenedor>/<tipo>/entrada/``.

Lo ejecuta el Container Apps Job cuando llega un aviso a la cola (Event Grid
avisa de cada blob nuevo), o a mano con ``indicadores-azure-procesar``.

Por cada archivo:
  1. lo lee con el lector de su tipo (``lectores/``),
  2. lo carga en su tabla raw_ registrando ``control_carga``,
  3. lo mueve a ``<tipo>/procesados/`` (con estado y filas en los metadatos)
     o a ``<tipo>/errores/`` junto a un ``.error.txt`` con el motivo.

La web consulta esas carpetas para mostrar el resultado.
"""

from __future__ import annotations

import hashlib
import logging
import sys
from pathlib import Path
from urllib.parse import unquote

from .config import Config
from .control import ErrorDeCarga, cargar_archivo
from .db import conexion
from .lectores import LECTORES

log = logging.getLogger("indicadores_azure")


def _contenedor(config: Config):
    from azure.storage.blob import BlobServiceClient

    servicio = BlobServiceClient.from_connection_string(config.blob_connection_string)
    return servicio.get_container_client(config.blob_container)


def vaciar_cola(config: Config) -> None:
    """Los mensajes sólo avisan que llegó algo: el job revisa todo ``entrada/``."""

    if not config.queue_name:
        return
    from azure.storage.queue import QueueClient

    cola = QueueClient.from_connection_string(config.blob_connection_string, config.queue_name)
    while True:
        mensajes = list(cola.receive_messages(messages_per_page=32, max_messages=32))
        if not mensajes:
            return
        for mensaje in mensajes:
            cola.delete_message(mensaje)


def _mover(contenedor, origen: str, destino: str, contenido: bytes, metadatos: dict[str, str]) -> None:
    contenedor.get_blob_client(destino).upload_blob(contenido, overwrite=True, metadata=metadatos)
    contenedor.delete_blob(origen)


def procesar_blob(config: Config, contenedor, conn, tipo: str, blob_nombre: str, metadatos: dict[str, str]) -> str:
    """Procesa un archivo y devuelve el estado final (COMPLETADO, DUPLICADO o ERROR)."""

    lector = LECTORES[tipo]
    nombre = unquote(metadatos.get("nombre_original") or "") or Path(blob_nombre).name
    subido_por = unquote(metadatos.get("subido_por") or "") or "desconocido"
    archivo = blob_nombre.split("/entrada/", 1)[1]
    contenido = contenedor.download_blob(blob_nombre).readall()
    sha256 = hashlib.sha256(contenido).hexdigest()

    try:
        if Path(nombre).suffix.lower() not in lector.EXTENSIONES:
            raise ErrorDeCarga(
                f"Extensión no permitida para {tipo}: se espera {', '.join(sorted(lector.EXTENSIONES))}."
            )
        resultado = cargar_archivo(
            conn,
            tipo=tipo,
            nombre=nombre,
            blob=blob_nombre,
            sha256=sha256,
            subido_por=subido_por,
            tabla=lector.TABLA,
            columnas=lector.COLUMNAS,
            filas=lector.leer(contenido),
            batch_size=config.batch_size,
        )
    except Exception as exc:
        mensaje = str(exc) if isinstance(exc, ErrorDeCarga) else f"Error inesperado: {exc.__class__.__name__}: {exc}"
        log.error("ERROR %s: %s", blob_nombre, mensaje)
        destino = f"{tipo}/errores/{archivo}"
        _mover(contenedor, blob_nombre, destino, contenido, {**metadatos, "estado": "ERROR"})
        contenedor.get_blob_client(f"{destino}.error.txt").upload_blob(
            f"Archivo: {nombre}\nTipo: {tipo}\nSubido por: {subido_por}\n\n{mensaje}\n".encode("utf-8"),
            overwrite=True,
        )
        return "ERROR"

    _mover(
        contenedor,
        blob_nombre,
        f"{tipo}/procesados/{archivo}",
        contenido,
        {
            **metadatos,
            "estado": resultado.estado,
            "carga_id": str(resultado.carga_id),
            "filas": str(resultado.filas_cargadas),
        },
    )
    log.info("%s %s: %s filas (carga %s)", resultado.estado, blob_nombre, resultado.filas_cargadas, resultado.carga_id)
    return resultado.estado


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = Config.desde_entorno()
    contenedor = _contenedor(config)
    vaciar_cola(config)

    pendientes = [
        (tipo, blob.name, dict(blob.metadata or {}))
        for tipo in LECTORES
        for blob in contenedor.list_blobs(name_starts_with=f"{tipo}/entrada/", include=["metadata"])
    ]
    if not pendientes:
        log.info("No hay archivos nuevos.")
        return 0

    log.info("Archivos a procesar: %s", len(pendientes))
    errores = 0
    with conexion(config) as conn:
        for tipo, blob_nombre, metadatos in pendientes:
            if procesar_blob(config, contenedor, conn, tipo, blob_nombre, metadatos) == "ERROR":
                errores += 1
    log.info("Terminado: %s archivos, %s con error.", len(pendientes), errores)
    return 0


if __name__ == "__main__":
    sys.exit(main())
