"""Archivos que se cargan solos al crear una base nueva: ``datos_iniciales/<tipo>/``.

Para no subir uno a uno los anexos al pasar a otra instancia, se dejan en el repo:

    datos_iniciales/anexo1/Anexo 1 marzo 2026.xlsx
    datos_iniciales/anexo3/...
    datos_iniciales/exclusiones/...
    datos_iniciales/velocidades/...

Al partir, el job sube a ``<tipo>/entrada/`` los que la base todavía no tiene registrados en
``carga_inicial`` y los procesa en esa misma vuelta igual que si vinieran de la web (vigencias,
recálculo, aparecen en "Archivos cargados" como subidos por "carga inicial"). Se ordenan por
ruta, así que si dos archivos cubren las mismas fechas rige el de nombre mayor.

Cada archivo se sube una sola vez por base, aunque después se elimine su carga en la web. Un
archivo nuevo que se agregue a la carpeta más adelante también se sube en la próxima vuelta.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from urllib.parse import quote

from .lectores import LECTORES

log = logging.getLogger("indicadores_azure.datos_iniciales")

SUBIDO_POR = "carga inicial"
# Antes que cualquier archivo de la web (que empiezan con la fecha de subida, AAAAMMDD_HHMMSS).
PREFIJO = "00000000"


def carpeta() -> Path | None:
    from .migraciones import carpeta as buscar

    try:
        return buscar("datos_iniciales")
    except RuntimeError:
        return None


def archivos(raiz: Path) -> list[tuple[str, Path]]:
    """(tipo, archivo) de cada archivo con extensión válida para su tipo, ordenados por ruta."""

    encontrados = []
    for tipo, lector in LECTORES.items():
        if not (raiz / tipo).is_dir():
            continue
        for ruta in (raiz / tipo).rglob("*"):
            if ruta.is_file() and not ruta.name.startswith((".", "~$")) and ruta.suffix.lower() in lector.EXTENSIONES:
                encontrados.append((tipo, ruta))
    return sorted(encontrados, key=lambda t: (t[0], t[1].relative_to(raiz).as_posix()))


def subir_pendientes(conn, contenedor, raiz: Path | None = None) -> list[str]:
    """Sube a ``<tipo>/entrada/`` los archivos que la base no tiene. Devuelve los blobs subidos."""

    raiz = raiz or carpeta()
    if raiz is None:
        return []
    lista = archivos(raiz)
    if not lista:
        return []
    with conn.cursor() as cur:
        cur.execute("SELECT sha256, archivo, tamano FROM carga_inicial")
        registrados = cur.fetchall()
    hashes = {sha for sha, _, _ in registrados}
    vistos = {(archivo, int(tamano)) for _, archivo, tamano in registrados}

    subidos: list[str] = []
    for i, (tipo, ruta) in enumerate(lista, start=1):
        relativo = ruta.relative_to(raiz).as_posix()
        tamano = ruta.stat().st_size
        if (relativo, tamano) in vistos:  # no leer de nuevo lo que ya se subió
            continue
        contenido = ruta.read_bytes()
        sha = hashlib.sha256(contenido).hexdigest()
        if sha in hashes:  # mismo archivo con otro nombre o en otra carpeta
            continue
        blob = f"{tipo}/entrada/{PREFIJO}_{i:04d}_{ruta.name}"
        metadatos = {"subido_por": quote(SUBIDO_POR, safe=" @._-()"),
                     "nombre_original": quote(ruta.name, safe=" @._-()")}
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
