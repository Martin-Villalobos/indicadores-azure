"""/api/maestros: sólo deja editar las tablas de la lista y valida los valores."""

import importlib.util
import json
from pathlib import Path

import pytest

func = pytest.importorskip("azure.functions")
API = Path(__file__).resolve().parents[1] / "web" / "api" / "maestros" / "__init__.py"
spec = importlib.util.spec_from_file_location("api_maestros_test", API)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def _get(params):
    return m.main(func.HttpRequest(method="GET", url="http://x/api/maestros", headers={}, params=params, body=b""))


def test_lista_tablas_editables():
    tablas = json.loads(_get({}).get_body())
    assert [t["tabla"] for t in tablas] == ["dim_bus", "dim_servicio_terminal"]


def test_tabla_no_editable():
    r = _get({"tabla": "control_carga"})
    assert r.status_code == 400 and "no editable" in json.loads(r.get_body())["mensaje"]


class Cursor:
    def __init__(self):
        self.sql = []
        self.rowcount = 1

    def execute(self, sql, params=()):
        self.sql.append((" ".join(sql.split()), params))


def test_guardar_normaliza_patente_y_marca_manual():
    cur = Cursor()
    m._guardar(cur, "dim_bus", {"ppu": "ab-cd 12", "tipo_bus": "B1", "plazas": "90"}, "ana@x.cl", "guardar")
    sql, params = cur.sql[0]
    assert sql.startswith("INSERT INTO dim_bus") and params[:5] == ("ABCD12", "B1", 90, "MANUAL", None)
    assert params[5] == "ana@x.cl"


@pytest.mark.parametrize("fila, error", [({"ppu": ""}, "Falta Patente"), ({"ppu": "A", "plazas": "x"}, "entero"),
                                         ({"ppu": "A", "plazas": "0"}, "mayor que cero")])
def test_guardar_valida(fila, error):
    with pytest.raises(m.ErrorUsuario, match=error):
        m._guardar(Cursor(), "dim_bus", fila, "u", "guardar")
