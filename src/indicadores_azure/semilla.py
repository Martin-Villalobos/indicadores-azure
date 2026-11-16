"""Seeder del entorno dev: crea las tablas, carga datos de ejemplo y prepara el almacenamiento local.

    indicadores-azure-semilla              crea lo que falte; los datos se cargan sólo si la base está vacía
    indicadores-azure-semilla --reiniciar  borra las tablas y vuelve a cargar todo

Ejecuta ``sql/*.sql`` (tablas) y luego ``seeds/*.sql`` (datos), en orden alfabético, y crea el
contenedor y la cola en Azurite. Se niega a correr si el entorno activo no es ``dev``.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

from .config import RAIZ_REPO, Config, entorno_activo
from .db import conexion

log = logging.getLogger("indicadores_azure.semilla")


def _carpeta(nombre: str) -> Path:
    for base in (Path.cwd(), RAIZ_REPO):
        if (base / nombre).is_dir():
            return base / nombre
    raise RuntimeError(f"No se encontró la carpeta {nombre}/ (correr desde la raíz del repo).")


def sentencias(texto: str) -> list[str]:
    """Separa un archivo .sql en sentencias (los ``;`` de fin de línea), sin comentarios ``--``."""

    sin_comentarios = "\n".join(l for l in texto.splitlines() if not l.lstrip().startswith("--"))
    return [s.strip() for s in re.split(r";\s*(?:\n|$)", sin_comentarios) if s.strip()]


def _tablas(cur, tipo: str = "BASE TABLE") -> list[str]:
    cur.execute("SHOW FULL TABLES WHERE Table_type = %s", (tipo,))
    return [fila[0] for fila in cur.fetchall()]


def sembrar_base(conn, reiniciar: bool = False) -> None:
    with conn.cursor() as cur:
        if reiniciar:
            for vista in _tablas(cur, "VIEW"):
                cur.execute(f"DROP VIEW `{vista}`")
            cur.execute("SET FOREIGN_KEY_CHECKS = 0")
            for tabla in _tablas(cur):
                cur.execute(f"DROP TABLE `{tabla}`")
            cur.execute("SET FOREIGN_KEY_CHECKS = 1")
            log.info("Tablas borradas.")

        for archivo in sorted(_carpeta("sql").glob("*.sql")):
            for sql in sentencias(archivo.read_text(encoding="utf-8")):
                cur.execute(sql)
            log.info("Tablas: %s", archivo.name)

        cur.execute("SELECT COUNT(*) FROM control_carga")
        if cur.fetchone()[0]:
            log.info("La base ya tiene datos: no se cargan semillas (usa --reiniciar para partir de cero).")
        else:
            for archivo in sorted(_carpeta("seeds").glob("*.sql")):
                for sql in sentencias(archivo.read_text(encoding="utf-8")):
                    cur.execute(sql)
                log.info("Semilla: %s", archivo.name)
    conn.commit()


def preparar_almacenamiento(config: Config) -> None:
    """Crea el contenedor (y la cola, si hay) en Azurite."""

    from azure.core.exceptions import ResourceExistsError
    from azure.storage.blob import BlobServiceClient

    contenedor = BlobServiceClient.from_connection_string(config.blob_connection_string).get_container_client(
        config.blob_container
    )
    try:
        contenedor.create_container()
        log.info("Contenedor %s creado.", config.blob_container)
    except ResourceExistsError:
        pass
    if config.queue_name:
        from azure.storage.queue import QueueClient

        try:
            QueueClient.from_connection_string(config.blob_connection_string, config.queue_name).create_queue()
        except ResourceExistsError:
            pass


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("azure").setLevel(logging.WARNING)  # el SDK registra cada petición HTTP
    args = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    args.add_argument("--reiniciar", action="store_true", help="borra las tablas y carga todo de nuevo")
    args.add_argument("--sin-almacenamiento", action="store_true", help="no toca Azurite")
    opciones = args.parse_args(argv)

    entorno = entorno_activo()
    if entorno != "dev":
        log.error("El seeder sólo corre con ENTORNO=dev (entorno activo: %s).", entorno)
        return 2
    config = Config.desde_entorno()
    with conexion(config) as conn:
        sembrar_base(conn, reiniciar=opciones.reiniciar)
    if not opciones.sin_almacenamiento:
        preparar_almacenamiento(config)
    log.info("Entorno dev listo (base %s en %s:%s).", config.db_name, config.db_host, config.db_port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
