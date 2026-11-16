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
    assert [t["tabla"] for t in tablas] == ["dim_bus", "dim_terminal", "dim_servicio_terminal"]


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
    assert sql.startswith("INSERT INTO dim_bus") and params[:6] == ("ABCD12", "B1", 90, None, "MANUAL", None)
    assert params[6] == "ana@x.cl"


@pytest.mark.parametrize("fila, error", [({"ppu": ""}, "Falta Patente"), ({"ppu": "A", "plazas": "x"}, "entero"),
                                         ({"ppu": "A", "plazas": "0"}, "mayor que cero")])
def test_guardar_valida(fila, error):
    with pytest.raises(m.ErrorUsuario, match=error):
        m._guardar(Cursor(), "dim_bus", fila, "u", "guardar")


def test_terminal_inexistente_da_mensaje_claro(monkeypatch):
    class CursorFK(Cursor):
        def execute(self, sql, params=()):
            if sql.lstrip().startswith("INSERT INTO dim_bus"):
                raise RuntimeError(1452, "Cannot add or update a child row: a foreign key constraint fails")
            super().execute(sql, params)

        def fetchone(self):
            return (None, None)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    class Conn:
        def cursor(self):
            return CursorFK()

        def rollback(self):
            pass

        def commit(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(m, "_conexion", lambda: Conn())
    req = func.HttpRequest(method="POST", url="/api/maestros", params={"tabla": "dim_bus"},
                           body=json.dumps({"accion": "guardar", "fila": {"ppu": "AB12", "terminal": "Nada"}}).encode())
    r = m.main(req)
    assert r.status_code == 400 and "agrégala primero" in json.loads(r.get_body())["mensaje"]
