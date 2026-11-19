"""/api/dashboards arma el menú del usuario sin enlaces y /api/reporte/<id> redirige sólo si tiene permiso."""

from __future__ import annotations

import base64
import importlib.util
import json
from pathlib import Path

import pytest

func = pytest.importorskip("azure.functions")

API = Path(__file__).resolve().parents[1] / "web" / "api"

# Filas como las devuelve la consulta de compartido/portal.py, por email.
MENU = {
    "ana@empresa.cl": [
        (1, "Indicadores Operacionales", None, 1, 10, "ICFP", "Frecuencia y plazas", 1, 1280, 2000),
        (1, "Indicadores Operacionales", None, 1, 11, "ICB", None, 2, 1280, 720),
        (2, "ITE", "reloj", 2, 20, "IP", "Puntualidad", 1, 1280, 720),
    ],
}
URLS = {("ana@empresa.cl", 10): "https://app.powerbi.com/view?r=abc", ("ana@empresa.cl", 11): ""}


class Cursor:
    def __init__(self):
        self.filas = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params):
        if "url_powerbi" in sql:
            url = URLS.get(params)
            self.filas = [] if url is None else [(url,)]
        else:
            self.filas = MENU.get(params[0], [])

    def fetchall(self):
        return self.filas

    def fetchone(self):
        return self.filas[0] if self.filas else None


class Conexion:
    cerrada = False

    def cursor(self):
        return Cursor()

    def close(self):
        self.cerrada = True


def _modulo(nombre: str):
    spec = importlib.util.spec_from_file_location(f"api_{nombre}_test", API / nombre / "__init__.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.fixture
def api(monkeypatch):
    conexiones = []

    def conectar():
        conexiones.append(Conexion())
        return conexiones[-1]

    mods = {n: _modulo(n) for n in ("dashboards", "reporte")}
    for m in mods.values():
        monkeypatch.setattr(m.web, "conexion_portal", conectar)
    mods["conexiones"] = conexiones
    return mods


def _req(ruta: str, email: str = "ana@empresa.cl", **route_params) -> "func.HttpRequest":
    principal = base64.b64encode(json.dumps({"userDetails": email}).encode()).decode()
    return func.HttpRequest(method="GET", url=f"http://localhost/api/{ruta}",
                            headers={"x-ms-client-principal": principal}, params={},
                            route_params=route_params, body=b"")


def test_menu_agrupado_sin_enlaces(api):
    resp = api["dashboards"].main(_req("dashboards"))
    assert resp.status_code == 200
    assert resp.headers["Cache-Control"] == "no-store"
    assert json.loads(resp.get_body()) == [
        {"id": 1, "nombre": "Indicadores Operacionales", "icono": None, "reportes": [
            {"id": 10, "nombre": "ICFP", "descripcion": "Frecuencia y plazas", "ancho": 1280, "alto": 2000},
            {"id": 11, "nombre": "ICB", "descripcion": "", "ancho": 1280, "alto": 720},
        ]},
        {"id": 2, "nombre": "ITE", "icono": "reloj", "reportes": [
            {"id": 20, "nombre": "IP", "descripcion": "Puntualidad", "ancho": 1280, "alto": 720},
        ]},
    ]
    assert b"powerbi" not in resp.get_body()
    assert all(c.cerrada for c in api["conexiones"])


def test_usuario_sin_permisos_ve_menu_vacio(api):
    resp = api["dashboards"].main(_req("dashboards", email="otro@empresa.cl"))
    assert resp.status_code == 200 and json.loads(resp.get_body()) == []


def test_reporte_redirige(api):
    resp = api["reporte"].main(_req("reporte/10", id="10"))
    assert resp.status_code == 302
    assert resp.headers["Location"] == "https://app.powerbi.com/view?r=abc"
    assert resp.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("id_,email", [("11", "ana@empresa.cl"), ("20", "ana@empresa.cl"), ("10", "otro@empresa.cl"),
                                       ("-1", "ana@empresa.cl"), ("x", "ana@empresa.cl"), ("", "ana@empresa.cl")])
def test_reporte_sin_enlace_sin_permiso_o_inexistente(api, id_, email):
    resp = api["reporte"].main(_req(f"reporte/{id_}", email=email, id=id_))
    assert resp.status_code == 404
    assert "Location" not in resp.headers


def test_sin_base(api, monkeypatch):
    def falla():
        raise OSError("sin conexión")

    for nombre in ("dashboards", "reporte"):
        monkeypatch.setattr(api[nombre].web, "conexion_portal", falla)
    assert api["dashboards"].main(_req("dashboards")).status_code == 500
    assert api["reporte"].main(_req("reporte/10", id="10")).status_code == 500
