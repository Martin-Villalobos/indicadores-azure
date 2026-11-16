"""/api/archivos: listar, simular y aplicar eliminar / cambiar fechas."""

import importlib.util
import json
from datetime import date
from pathlib import Path

import pytest

func = pytest.importorskip("azure.functions")
RAIZ = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("api_archivos_test", RAIZ / "web" / "api" / "archivos" / "__init__.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_copia_de_vigencias_en_la_web_es_identica():
    original = (RAIZ / "src" / "indicadores_azure" / "vigencias.py").read_text(encoding="utf-8")
    copia = (RAIZ / "web" / "api" / "compartido" / "vigencias.py").read_text(encoding="utf-8")
    assert copia == original, "cp src/indicadores_azure/vigencias.py web/api/compartido/vigencias.py"


class Conn:
    def __init__(self):
        self.commits = self.rollbacks = 0

    def cursor(self):
        class Cur:
            def __enter__(s):
                return s

            def __exit__(s, *a):
                pass
        return Cur()

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        pass


def _post(cuerpo):
    return m.main(func.HttpRequest(method="POST", url="/api/archivos", body=json.dumps(cuerpo).encode()))


@pytest.fixture
def conn(monkeypatch):
    c = Conn()
    monkeypatch.setattr(m.web, "conexion", lambda: c)
    monkeypatch.setattr(m.web, "avisar_job", lambda motivo: None)
    return c


def test_tipo_no_soportado():
    r = m.main(func.HttpRequest(method="GET", url="/api/archivos", params={"tipo": "flota"}, body=b""))
    assert r.status_code == 400


def test_accion_invalida(conn):
    assert _post({"accion": "borrar", "carga_id": 1}).status_code == 400
    assert _post({"accion": "eliminar"}).status_code == 400


def test_simular_no_aplica_y_confirmar_si(conn, monkeypatch):
    llamadas = []

    def eliminar(cur, carga_id, *, usuario, aplicar):
        llamadas.append(aplicar)
        return m.vigencias.Resultado(
            tipo="anexo3", cambios=[m.vigencias.Cambio(date(2026, 9, 18), date(2026, 9, 19), 2, 1)],
            advertencias=["Del 18-09-2026 al 19-09-2026 pasa a regir otro."],
            recalculos=[("ICFP", date(2026, 9, 17), date(2026, 9, 20))])

    monkeypatch.setattr(m.vigencias, "eliminar_carga", eliminar)
    r = _post({"accion": "eliminar", "carga_id": 2})
    d = json.loads(r.get_body())
    assert r.status_code == 200 and d["estado"] == "SIMULACION" and d["cambios"][0]["despues"] == 1
    assert conn.rollbacks == 1 and conn.commits == 0

    r = _post({"accion": "eliminar", "carga_id": 2, "confirmar": True})
    d = json.loads(r.get_body())
    assert d["estado"] == "OK" and "recalculan" in d["mensaje"] and conn.commits == 1
    assert llamadas == [False, True]


def test_errores_no_aplican(conn, monkeypatch):
    monkeypatch.setattr(m.vigencias, "cambiar_fechas",
                        lambda cur, cid, d, h, *, usuario, aplicar: m.vigencias.Resultado(
                            tipo="anexo3", errores=["La fecha de fin es anterior a la de inicio."]))
    r = _post({"accion": "cambiar_fechas", "carga_id": 1, "desde": "2026-09-30", "hasta": "2026-09-01", "confirmar": True})
    assert r.status_code == 400 and conn.commits == 0 and conn.rollbacks == 1
    assert _post({"accion": "cambiar_fechas", "carga_id": 1, "desde": "30/09/2026"}).status_code == 400
