"""Archivos que se cargan solos en una base nueva: ``datos_iniciales/<tipo>/``.

Para no subir uno a uno los anexos al pasar a otra instancia, se dejan en el repo:

    datos_iniciales/anexo1/Anexo 1 marzo 2026.xlsx
    datos_iniciales/anexo3/...
    datos_iniciales/exclusiones/...
    datos_iniciales/velocidades/...

1. ``publicar`` copia la carpeta al blob, en ``iniciales/<tipo>/...`` (sólo lo que falta o cambió de
   tamaño). En Azure lo hace el despliegue (``indicadores-azure-publicar-iniciales`` en el workflow
   job), así la imagen del job no carga con los archivos; en dev lo hace el job al partir, porque
   la carpeta está montada.
2. ``subir_pendientes`` (el job, al partir) pasa a ``<tipo>/entrada/`` los de ``iniciales/`` que la
   base todavía no tiene registrados en ``carga_inicial``, y se procesan como si vinieran de la
   web: vigencias, recálculo, y aparecen en "Archivos cargados" como subidos por "carga inicial".
   Se ordenan por ruta, así que si dos archivos cubren las mismas fechas con el mismo rango, rige
   el de nombre mayor.

Cada archivo se carga una sola vez por base, aunque después se elimine su carga en la web. Un
archivo nuevo que se agregue a la carpeta más adelante se carga en el próximo despliegue.
"""

from __future__ import annotations

import hashlib
import logging
import os
import sys
from pathlib import Path
from urllib.parse import quote

from .lectores import LECTORES

log = logging.getLogger("indicadores_azure.datos_iniciales")

SUBIDO_POR = "carga inicial"
BLOB = "iniciales/"
# Antes que cualquier archivo de la web (que empiezan con la fecha de subida, AAAAMMDD_HHMMSS).
PREFIJO = "00000000"


def carpeta() -> Path | None:
    from .migraciones import carpeta as buscar

    try:
        return buscar("datos_iniciales")
    except RuntimeError:
        return None


def _tipo_valido(relativo: str) -> str | None:
    """Tipo de ``anexo1/2026/x.xlsx`` si es un archivo que se carga; si no, None."""

    tipo, _, resto = relativo.partition("/")
    nombre = Path(resto).name
    if tipo not in LECTORES or not nombre or nombre.startswith((".", "~$")):
        return None
    return tipo if Path(nombre).suffix.lower() in LECTORES[tipo].EXTENSIONES else None


def archivos(raiz: Path) -> list[tuple[str, Path]]:
    """(relativo, archivo) de la carpeta local que se cargan, ordenados por ruta."""

    lista = []
    for ruta in raiz.rglob("*"):
        relativo = ruta.relative_to(raiz).as_posix()
        if ruta.is_file() and _tipo_valido(relativo):
            lista.append((relativo, ruta))
    return sorted(lista)


def publicar(contenedor, raiz: Path | None = None) -> list[str]:
    """Copia la carpeta local a ``iniciales/`` del blob. Devuelve los blobs subidos."""

    raiz = raiz or carpeta()
    if raiz is None or not raiz.is_dir():
        return []
    existentes = {b.name: b.size for b in contenedor.list_blobs(name_starts_with=BLOB)}
    subidos = []
    for relativo, ruta in archivos(raiz):
        nombre = BLOB + relativo
        if existentes.get(nombre) == ruta.stat().st_size:
            continue
        with ruta.open("rb") as datos:
            contenedor.get_blob_client(nombre).upload_blob(datos, overwrite=True)
        subidos.append(nombre)
        log.info("Publicado %s", nombre)
    return subidos


def subir_pendientes(conn, contenedor) -> list[str]:
    """Pasa a ``<tipo>/entrada/`` lo de ``iniciales/`` que la base no tiene. Devuelve los blobs."""

    blobs = sorted(
        (b.name[len(BLOB):], b.name, b.size)
        for b in contenedor.list_blobs(name_starts_with=BLOB)
        if _tipo_valido(b.name[len(BLOB):])
    )
    if not blobs:
        return []
    with conn.cursor() as cur:
        cur.execute("SELECT sha256, archivo, tamano FROM carga_inicial")
        registrados = cur.fetchall()
    hashes = {sha for sha, _, _ in registrados}
    vistos = {(archivo, int(tamano)) for _, archivo, tamano in registrados}

    subidos: list[str] = []
    for i, (relativo, origen, tamano) in enumerate(blobs, start=1):
        if (relativo, tamano) in vistos:  # no bajar de nuevo lo que ya se cargó
            continue
        contenido = contenedor.download_blob(origen).readall()
        sha = hashlib.sha256(contenido).hexdigest()
        if sha in hashes:  # mismo archivo con otro nombre o en otra carpeta
            continue
        tipo, nombre = _tipo_valido(relativo), Path(relativo).name
        blob = f"{tipo}/entrada/{PREFIJO}_{i:04d}_{nombre}"
        metadatos = {"subido_por": quote(SUBIDO_POR, safe=" @._-()"), "nombre_original": quote(nombre, safe=" @._-()")}
        # Primero el blob y después el registro: si se corta entre medio, la próxima vuelta lo sube
        # otra vez y el job lo marca DUPLICADO (mismo sha256), así que no se pierde ni se duplica.
        contenedor.get_blob_client(blob).upload_blob(contenido, overwrite=True, metadata=metadatos)
        with conn.cursor() as cur:
            cur.execute(
                "INSERT IGNORE INTO carga_inicial (sha256, archivo, tamano, blob_nombre) VALUES (%s, %s, %s, %s)",
                (sha, relativo, tamano, blob),
            )
        conn.commit()
        hashes.add(sha)
        subidos.append(blob)
        log.info("Carga inicial: %s -> %s", relativo, blob)
    return subidos


def main() -> int:
    """indicadores-azure-publicar-iniciales: copia datos_iniciales/ al blob (lo usa el despliegue).

    Necesita BLOB_CONNECTION_STRING y, si no es "cargas", BLOB_CONTAINER.
    """

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("azure").setLevel(logging.WARNING)
    from azure.storage.blob import BlobServiceClient

    servicio = BlobServiceClient.from_connection_string(os.environ["BLOB_CONNECTION_STRING"])
    contenedor = servicio.get_container_client(os.getenv("BLOB_CONTAINER") or "cargas")
    subidos = publicar(contenedor)
    log.info("Datos iniciales publicados: %s archivos nuevos.", len(subidos))
    return 0


if __name__ == "__main__":
    sys.exit(main())
