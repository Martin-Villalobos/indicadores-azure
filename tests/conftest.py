"""Dobles de prueba: un contenedor de blob en memoria y una conexión MySQL falsa."""

from __future__ import annotations

import copy
import io
from types import SimpleNamespace

import pytest


class ContenedorFalso:
    def __init__(self):
        self.blobs: dict[str, tuple[bytes, dict]] = {}

    def subir(self, nombre, contenido, metadata=None):
        self.blobs[nombre] = (contenido, dict(metadata or {}))

    def list_blobs(self, name_starts_with="", include=None):
        return [SimpleNamespace(name=n, metadata=m) for n, (_, m) in sorted(self.blobs.items()) if n.startswith(name_starts_with)]

    def download_blob(self, nombre):
        return SimpleNamespace(readall=lambda: self.blobs[nombre][0])

    def delete_blob(self, nombre):
        del self.blobs[nombre]

    def get_blob_client(self, nombre):
        contenedor = self

        class _Cliente:
            def upload_blob(self, contenido, overwrite=False, metadata=None):
                contenedor.subir(nombre, contenido, metadata)

        return _Cliente()


class CursorFalso:
    def __init__(self, conn):
        self.conn = conn
        self.lastrowid = None
        self._resultado = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=()):
        sql = " ".join(sql.split())
        if sql.startswith("SELECT carga_id, estado FROM control_carga"):
            tipo, sha = params
            fila = next(((i, c["estado"]) for i, c in self.conn.control.items() if c["tipo"] == tipo and c["sha"] == sha), None)
            self._resultado = fila
        elif sql.startswith("INSERT INTO control_carga"):
            self.conn.siguiente += 1
            self.lastrowid = self.conn.siguiente
            self.conn.control[self.lastrowid] = {
                "tipo": params[0], "sha": params[3], "blob": params[2], "estado": "PROCESANDO"
            }
        elif sql.startswith("UPDATE control_carga SET estado='PROCESANDO'"):
            self.conn.control[params[-1]].update(estado="PROCESANDO", blob=params[1])
        elif sql.startswith("UPDATE control_carga SET estado='COMPLETADO'"):
            self.conn.control[params[-1]]["estado"] = "COMPLETADO"
        elif sql.startswith("UPDATE control_carga SET estado='ERROR'"):
            self.conn.control[params[-1]].update(estado="ERROR", mensaje=params[2], blob=params[3])
        elif sql.startswith("SELECT vigencia_id, carga_id, fecha_inicio, fecha_termino, rango_desde, rango_hasta, origen FROM vigencia_archivo"):
            tipo, hasta, desde = params
            self._resultados = [
                (v["vigencia_id"], v["carga_id"], v["fecha_inicio"], v["fecha_termino"], v["rango_desde"], v["rango_hasta"], v["origen"])
                for v in sorted(self.conn.vigencias, key=lambda v: v["fecha_inicio"])
                if v["tipo"] == tipo and v["vigente"] and v["fecha_inicio"] <= hasta and v["fecha_termino"] >= desde
            ]
        elif sql.startswith("UPDATE vigencia_archivo SET vigente = 0"):
            self.conn.guardar_vigencias()
            carga, _, *ids = params
            for v in self.conn.vigencias:
                if v["vigencia_id"] in ids:
                    v.update(vigente=0, reemplazada_por=carga)
        else:
            raise AssertionError(f"SQL no esperado: {sql}")

    def executemany(self, sql, filas):
        if " ".join(sql.split()).startswith("INSERT INTO vigencia_archivo"):
            self.conn.guardar_vigencias()
            for tipo, carga, inicio, termino, desde, hasta, origen, *_ in filas:
                self.conn.vigencias.append({
                    "vigencia_id": len(self.conn.vigencias) + 1, "tipo": tipo, "carga_id": carga,
                    "fecha_inicio": inicio, "fecha_termino": termino, "rango_desde": desde,
                    "rango_hasta": hasta, "origen": origen, "vigente": 1, "reemplazada_por": None,
                })
            return
        self.conn.pendientes.extend(filas)

    def fetchone(self):
        return self._resultado

    def fetchall(self):
        return self._resultados


class ConexionFalsa:
    def __init__(self):
        self.control: dict[int, dict] = {}
        self.siguiente = 0
        self.filas: list[tuple] = []
        self.pendientes: list[tuple] = []
        self.vigencias: list[dict] = []
        self._vigencias_antes = None

    def cursor(self):
        return CursorFalso(self)

    def guardar_vigencias(self):
        if self._vigencias_antes is None:
            self._vigencias_antes = copy.deepcopy(self.vigencias)

    def vigentes(self, tipo):
        """[(carga_id, inicio, termino)] vigentes del tipo, ordenados por fecha."""
        return sorted(
            (v["carga_id"], v["fecha_inicio"], v["fecha_termino"])
            for v in self.vigencias if v["tipo"] == tipo and v["vigente"]
        )

    def commit(self):
        self.filas.extend(self.pendientes)
        self.pendientes.clear()
        self._vigencias_antes = None

    def rollback(self):
        self.pendientes.clear()
        if self._vigencias_antes is not None:
            self.vigencias = self._vigencias_antes
            self._vigencias_antes = None


@pytest.fixture
def contenedor():
    return ContenedorFalso()


@pytest.fixture
def conn():
    return ConexionFalsa()


def excel(filas) -> bytes:
    from openpyxl import Workbook

    libro = Workbook()
    hoja = libro.active
    hoja.title = "Anexo 1"
    for fila in filas:
        hoja.append(list(fila))
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


ANEXO1_OK = [
    ("UNIDAD DE SERVICIOS", "U1"),
    ("AÑO", 2026),
    ("FECHA INICIO", "01/03/2026"),
    ("FECHA TÉRMINO", "31/12/2026"),
    (),
    ("CÓDIGO TS SERVICIO", "CÓDIGO USUARIO SERVICIO", "SENTIDO", "TIPO DÍA", "TRAMO HORARIO", "HORA INICIO", "HORA TÉRMINO"),
    ("T201 00I", "201", "IDA", "LABORAL", 1, "05:30", "06:29"),
    (),
    ("T201 00R", "201", "REGRESO", "SÁBADO", 2, "06:30:00", "07:29:00"),
]
