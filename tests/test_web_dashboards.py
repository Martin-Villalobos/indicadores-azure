"""/api/dashboards no entrega los enlaces y /api/reporte/<id> redirige a ellos."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

func = pytest.importorskip("azure.functions")

API = Path(__file__).resolve().parents[1] / "web" / "api"
DASHBOARDS = json.dumps([
    {"nombre": "IP del mes", "descripcion": "Puntualidad", "url": "https://app.powerbi.com/view?r=abc"},
    {"nombre": "IE", "descripcion": "Sin enlace", "url": ""},
])


def _main(nombre: str):
    spec = importlib.util.spec_from_file_location(f"api_{nombre}_test", API / nombre / "__init__.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo.main


def _req(ruta: str, **route_params) -> "func.HttpRequest":
    return func.HttpRequest(method="GET", url=f"http://localhost/api/{ruta}", headers={}, params={},
                            route_params=route_params, body=b"")


@pytest.fixture(autouse=True)
def _dashboards(monkeypatch):
    monkeypatch.setenv("DASHBOARDS", DASHBOARDS)


def test_lista_sin_enlaces():
    resp = _main("dashboards")(_req("dashboards"))
    assert resp.status_code == 200
    datos = json.loads(resp.get_body())
    assert datos == [
        {"id": 0, "nombre": "IP del mes", "descripcion": "Puntualidad"},
        {"id": 1, "nombre": "IE", "descripcion": "Sin enlace"},
    ]
    assert b"powerbi" not in resp.get_body()


def test_reporte_redirige():
    resp = _main("reporte")(_req("reporte/0", id="0"))
    assert resp.status_code == 302
    assert resp.headers["Location"] == "https://app.powerbi.com/view?r=abc"
    assert resp.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("id_", ["1", "2", "-1", "x", ""])
def test_reporte_sin_enlace_o_inexistente(id_):
    resp = _main("reporte")(_req(f"reporte/{id_}", id=id_))
    assert resp.status_code == 404
    assert "Location" not in resp.headers


def test_sin_variable(monkeypatch):
    monkeypatch.delenv("DASHBOARDS")
    assert _main("dashboards")(_req("dashboards")).status_code == 500
    assert _main("reporte")(_req("reporte/0", id="0")).status_code == 500
