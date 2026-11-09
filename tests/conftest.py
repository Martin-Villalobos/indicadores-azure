"""Dobles de prueba: un contenedor de blob en memoria y una conexión MySQL falsa."""

from __future__ import annotations

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
            self.conn.control[self.lastrowid] = {"tipo": params[0], "sha": params[3], "estado": "PROCESANDO"}
        elif sql.startswith("UPDATE control_carga SET estado='PROCESANDO'"):
            self.conn.control[params[-1]]["estado"] = "PROCESANDO"
        elif sql.startswith("UPDATE control_carga SET estado='COMPLETADO'"):
            self.conn.control[params[-1]]["estado"] = "COMPLETADO"
        elif sql.startswith("UPDATE control_carga SET estado='ERROR'"):
            self.conn.control[params[-1]].update(estado="ERROR", mensaje=params[2])
        else:
            raise AssertionError(f"SQL no esperado: {sql}")

    def executemany(self, sql, filas):
        self.conn.pendientes.extend(filas)

    def fetchone(self):
        return self._resultado


class ConexionFalsa:
    def __init__(self):
        self.control: dict[int, dict] = {}
        self.siguiente = 0
        self.filas: list[tuple] = []
        self.pendientes: list[tuple] = []

    def cursor(self):
        return CursorFalso(self)

    def commit(self):
        self.filas.extend(self.pendientes)
        self.pendientes.clear()

    def rollback(self):
        self.pendientes.clear()


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
