"""Registro de cargas en control_carga y carga transaccional a tablas raw_."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Sequence


@dataclass(frozen=True)
class ResultadoCarga:
    carga_id: int
    estado: str  # COMPLETADO | DUPLICADO
    filas_leidas: int
    filas_cargadas: int


class ErrorDeCarga(Exception):
    """Error con mensaje pensado para quien corrige el archivo."""


def cargar_archivo(
    conn,
    *,
    tipo: str,
    nombre: str,
    blob: str,
    sha256: str,
    subido_por: str,
    tabla: str,
    columnas: Sequence[str],
    filas: Iterable[tuple],
    batch_size: int = 5000,
) -> ResultadoCarga:
    """Carga las filas de un archivo en una sola transacción.

    - Si el mismo contenido (tipo + SHA-256) ya se cargó, devuelve DUPLICADO.
    - Si falla, no queda ninguna fila en la tabla raw y control_carga queda
      en ERROR con el motivo.
    """

    with conn.cursor() as cur:
        cur.execute(
            "SELECT carga_id, estado FROM control_carga WHERE tipo_archivo = %s AND hash_sha256 = %s",
            (tipo, sha256),
        )
        previa = cur.fetchone()
        if previa and previa[1] == "COMPLETADO":
            return ResultadoCarga(int(previa[0]), "DUPLICADO", 0, 0)
        if previa and previa[1] == "PROCESANDO":
            raise ErrorDeCarga(f"El archivo ya se está procesando (carga {previa[0]}).")
        if previa:  # ERROR anterior: se reintenta con el mismo registro
            carga_id = int(previa[0])
            cur.execute(
                """UPDATE control_carga SET estado='PROCESANDO', nombre_archivo=%s, blob_nombre=%s,
                   subido_por=%s, inicio_at=%s, fin_at=NULL, filas_leidas=NULL, filas_cargadas=NULL,
                   mensaje_error=NULL WHERE carga_id=%s""",
                (nombre, blob, subido_por, datetime.now(), carga_id),
            )
        else:
            cur.execute(
                """INSERT INTO control_carga (tipo_archivo, nombre_archivo, blob_nombre, hash_sha256,
                   estado, subido_por, inicio_at) VALUES (%s, %s, %s, %s, 'PROCESANDO', %s, %s)""",
                (tipo, nombre, blob, sha256, subido_por, datetime.now()),
            )
            carga_id = int(cur.lastrowid)
    conn.commit()

    sql = (
        f"INSERT INTO `{tabla}` (`carga_id`, "
        + ", ".join(f"`{c}`" for c in columnas)
        + ") VALUES ("
        + ", ".join(["%s"] * (len(columnas) + 1))
        + ")"
    )
    leidas = 0
    try:
        with conn.cursor() as cur:
            lote: list[tuple] = []
            for fila in filas:
                leidas += 1
                lote.append((carga_id, *fila))
                if len(lote) >= batch_size:
                    cur.executemany(sql, lote)
                    lote.clear()
            if lote:
                cur.executemany(sql, lote)
            if leidas == 0:
                raise ErrorDeCarga("El archivo no tiene filas de datos.")
            cur.execute(
                """UPDATE control_carga SET estado='COMPLETADO', fin_at=%s, filas_leidas=%s,
                   filas_cargadas=%s WHERE carga_id=%s""",
                (datetime.now(), leidas, leidas, carga_id),
            )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE control_carga SET estado='ERROR', fin_at=%s, filas_leidas=%s,
                   filas_cargadas=0, mensaje_error=%s WHERE carga_id=%s""",
                (datetime.now(), leidas, str(exc)[:4000], carga_id),
            )
        conn.commit()
        raise
    return ResultadoCarga(carga_id, "COMPLETADO", leidas, leidas)
