"""Aplica automáticamente los ``sql/*.sql`` que falten en la base (dev y Azure).

    indicadores-azure-migrar     aplica lo pendiente y termina

El job de carga lo llama al partir, así que basta con desplegar la imagen nueva (y el workflow
lanza una ejecución del job después de actualizarlo) para que la base quede al día; ya no hay que
correr los SQL a mano.

Cada archivo aplicado queda en ``migracion_aplicada`` con su hash. Se aplica un archivo si no está
registrado o si su contenido cambió. Los archivos son idempotentes (``CREATE TABLE IF NOT EXISTS``,
``INSERT IGNORE``, ``CREATE OR REPLACE VIEW``, y ``ALTER TABLE`` cuyo error de "ya existe" se
salta), así que volver a correrlos es seguro. Un ``CREATE TABLE IF NOT EXISTS`` no agrega columnas
a una tabla que ya existe: un cambio de columnas va en un archivo nuevo con su ``ALTER TABLE``.
"""

from __future__ import annotations

import hashlib
import logging
import re
import sys
from pathlib import Path

from .config import RAIZ_REPO, Config

log = logging.getLogger("indicadores_azure.migraciones")

TABLA = """CREATE TABLE IF NOT EXISTS migracion_aplicada (
    archivo     VARCHAR(255) NOT NULL PRIMARY KEY,
    sha256      CHAR(64)     NOT NULL,
    aplicada_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
)"""
CANDADO = "indicadores_azure_migraciones"
# Errores de un ALTER TABLE que ya estaba hecho: columna, índice o FK que ya existe. Así un archivo
# con ALTER se puede volver a correr (MySQL no tiene ADD COLUMN IF NOT EXISTS).
YA_EXISTE = {1060, 1061, 1022, 1826}


def _ejecutar(cur, sql: str) -> None:
    try:
        cur.execute(sql)
    except Exception as exc:  # pymysql.err.OperationalError / InternalError, según el código
        codigo = exc.args[0] if exc.args else None
        if sql.lstrip().upper().startswith("ALTER TABLE") and codigo in YA_EXISTE:
            log.info("Ya aplicado, se salta: %s", sql.split("\n", 1)[0])
            return
        raise


def carpeta(nombre: str = "sql") -> Path:
    for base in (Path.cwd(), RAIZ_REPO):
        if (base / nombre).is_dir():
            return base / nombre
    raise RuntimeError(f"No se encontró la carpeta {nombre}/ (correr desde la raíz del repo).")


def sentencias(texto: str) -> list[str]:
    """Separa un archivo .sql en sentencias (los ``;`` de fin de línea), sin comentarios ``--``."""

    sin_comentarios = "\n".join(l for l in texto.splitlines() if not l.lstrip().startswith("--"))
    return [s.strip() for s in re.split(r";\s*(?:\n|$)", sin_comentarios) if s.strip()]


def aplicar(conn, directorio: Path | None = None) -> list[str]:
    """Aplica los archivos nuevos o modificados, en orden alfabético. Devuelve los aplicados.

    Un candado de MySQL evita que dos ejecuciones del job migren a la vez. Si un archivo falla se
    corta ahí (y se relanza la excepción): no se registra, así que se reintenta en la próxima vuelta.
    """

    archivos = sorted((directorio or carpeta()).glob("*.sql"))
    aplicados: list[str] = []
    with conn.cursor() as cur:
        cur.execute("SELECT GET_LOCK(%s, 120)", (CANDADO,))
        if (cur.fetchone() or [0])[0] != 1:
            raise RuntimeError("Otra ejecución está aplicando migraciones (no se obtuvo el candado).")
        try:
            cur.execute(TABLA)
            cur.execute("SELECT archivo, sha256 FROM migracion_aplicada")
            registrados = {archivo: sha for archivo, sha in cur.fetchall()}
            for archivo in archivos:
                texto = archivo.read_text(encoding="utf-8")
                sha = hashlib.sha256(texto.encode("utf-8")).hexdigest()
                if registrados.get(archivo.name) == sha:
                    continue
                if archivo.name in registrados:
                    log.warning(
                        "%s cambió desde que se aplicó: se vuelve a correr (si agrega columnas a una tabla "
                        "existente, eso necesita un ALTER TABLE en un archivo nuevo).",
                        archivo.name,
                    )
                for sql in sentencias(texto):
                    _ejecutar(cur, sql)
                cur.execute(
                    "INSERT INTO migracion_aplicada (archivo, sha256) VALUES (%s, %s) "
                    "ON DUPLICATE KEY UPDATE sha256 = VALUES(sha256)",
                    (archivo.name, sha),
                )
                conn.commit()
                aplicados.append(archivo.name)
                log.info("Migración aplicada: %s", archivo.name)
        finally:
            cur.execute("SELECT RELEASE_LOCK(%s)", (CANDADO,))
            cur.fetchall()
    if not aplicados:
        log.info("Base al día: no hay migraciones pendientes.")
    return aplicados


def main(argv: list[str] | None = None) -> int:
    from .db import conexion

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = Config.desde_entorno()
    with conexion(config) as conn:
        aplicar(conn)
    return 0


if __name__ == "__main__":
    sys.exit(main())
