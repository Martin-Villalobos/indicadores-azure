"""Registro de cargas en control_carga y carga transaccional a tablas raw_."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from datetime import date
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
    blob_error: str | None = None,
    vigencia: Sequence[str] | None = None,
    vigencia_por_mes: bool = False,
) -> ResultadoCarga:
    """Carga las filas de un archivo en una sola transacción.

    - ``blob`` es la ruta donde queda el archivo si la carga resulta (``<tipo>/procesados/...``);
      si falla, control_carga.blob_nombre pasa a ``blob_error`` (``<tipo>/errores/...``).
    - Si el mismo contenido (tipo + SHA-256) ya se cargó, devuelve DUPLICADO.
    - ``vigencia`` = (columna desde, columna hasta): con el mínimo y el máximo de esas
      columnas se registra en vigencia_archivo qué fechas rige esta carga.
    - Si falla, no queda ninguna fila en la tabla raw ni en vigencia_archivo y
      control_carga queda en ERROR con el motivo.
    """

    from .vigencias import rango_mes, registrar_vigencia

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
    i_desde = columnas.index(vigencia[0]) if vigencia else None
    i_hasta = columnas.index(vigencia[1]) if vigencia else None
    desde: date | None = None
    hasta: date | None = None
    leidas = 0
    try:
        with conn.cursor() as cur:
            lote: list[tuple] = []
            for fila in filas:
                leidas += 1
                if vigencia:
                    d, h = fila[i_desde], fila[i_hasta]
                    desde = d if desde is None or d < desde else desde
                    hasta = h if hasta is None or h > hasta else hasta
                lote.append((carga_id, *fila))
                if len(lote) >= batch_size:
                    cur.executemany(sql, lote)
                    lote.clear()
            if lote:
                cur.executemany(sql, lote)
            if leidas == 0:
                raise ErrorDeCarga("El archivo no tiene filas de datos.")
            if vigencia:
                if vigencia_por_mes:
                    desde, hasta = rango_mes(desde, hasta)
                registrar_vigencia(cur, tipo=tipo, carga_id=carga_id, desde=desde, hasta=hasta, usuario=subido_por)
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
                   filas_cargadas=0, mensaje_error=%s, blob_nombre=%s WHERE carga_id=%s""",
                (datetime.now(), leidas, str(exc)[:4000], blob_error or blob, carga_id),
            )
        conn.commit()
        raise
    return ResultadoCarga(carga_id, "COMPLETADO", leidas, leidas)
