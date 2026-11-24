"""Mantenedor de usuarios (/api/usuarios), permisos por rol (/api/yo) y web.exigir en las otras API.

Usa SQLite en memoria con el mismo esquema de portal_reportes (sólo cambia AUTO_INCREMENT),
para probar el SQL real de compartido/portal.py y de usuarios/__init__.py.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

func = pytest.importorskip("azure.functions")

RAIZ = Path(__file__).resolve().parents[1]
API = RAIZ / "web" / "api"


def _modulo(nombre: str):
    spec = importlib.util.spec_from_file_location(f"api_{nombre}_test_usuarios", API / nombre / "__init__.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


class Cursor:
    def __init__(self, cur):
        self._cur = cur

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    @property
    def lastrowid(self):
        return self._cur.lastrowid

    def execute(self, sql, params=()):
        try:
            params = tuple(str(v) if isinstance(v, datetime) else v for v in params)
            self._cur.execute(sql.replace("%s", "?"), params)
        except sqlite3.IntegrityError as exc:
            if "UNIQUE" in str(exc):
                raise RuntimeError(1062, str(exc)) from None  # como pymysql: args[0] = código MySQL
            raise

    def fetchall(self):
        return self._cur.fetchall()

    def fetchone(self):
        return self._cur.fetchone()


class Conexion:
    def __init__(self, db):
        self.db = db

    def cursor(self):
        return Cursor(self.db.cursor())

    def commit(self):
        self.db.commit()

    def rollback(self):
        self.db.rollback()

    def close(self):
        pass


@pytest.fixture
def db():
    esquema = (RAIZ / "web" / "sql" / "portal_reportes.sql").read_text(encoding="utf-8")
    esquema = re.sub(r"^(CREATE DATABASE|USE) .*$", "", esquema, flags=re.M)
    esquema = esquema.replace("INT AUTO_INCREMENT PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
    conn = sqlite3.connect(":memory:", isolation_level="DEFERRED")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(esquema)
    conn.executescript("""
        INSERT INTO menu (nombre, orden) VALUES ('Indicadores Operacionales', 1), ('ITE', 2);
        INSERT INTO rol (nombre, es_admin, puede_cargar, puede_maestros) VALUES
          ('Administrador', 1, 0, 0), ('Operaciones', 0, 1, 0), ('Gerencia', 0, 0, 0);
        INSERT INTO usuario (email, nombre) VALUES ('admin@empresa.cl', 'Admin'), ('ope@empresa.cl', 'Ope'),
                                                   ('ger@empresa.cl', NULL);
        INSERT INTO usuario (email, activo) VALUES ('baja@empresa.cl', 0);
        INSERT INTO usuario_rol VALUES (1, 1), (2, 2), (3, 3), (4, 1);
        INSERT INTO permiso (rol_id, menu_id) VALUES (1, 1), (1, 2), (2, 1);
    """)
    conn.commit()
    return conn


@pytest.fixture
def api(db, monkeypatch):
    mods = {n: _modulo(n) for n in ("usuarios", "yo", "maestros")}
    for m in mods.values():
        monkeypatch.setattr(m.web, "conexion_portal", lambda: Conexion(db))
    return mods


def _req(ruta: str, email: str, metodo: str = "GET", cuerpo=None, params=None) -> "func.HttpRequest":
    principal = base64.b64encode(json.dumps({"userDetails": email}).encode()).decode()
    return func.HttpRequest(method=metodo, url=f"http://localhost/api/{ruta}",
                            headers={"x-ms-client-principal": principal}, params=params or {},
                            body=json.dumps(cuerpo).encode() if cuerpo is not None else b"")


def _post(api, cuerpo, email="admin@empresa.cl"):
    r = api["usuarios"].main(_req("usuarios", email, "POST", cuerpo))
    return r.status_code, json.loads(r.get_body())


@pytest.mark.parametrize("email, esperado", [
    ("admin@empresa.cl", {"admin": True, "cargar": True, "maestros": True}),
    ("ope@empresa.cl", {"admin": False, "cargar": True, "maestros": False}),
    ("ger@empresa.cl", {"admin": False, "cargar": False, "maestros": False}),
    ("baja@empresa.cl", {"admin": False, "cargar": False, "maestros": False}),   # inactivo
    ("nadie@empresa.cl", {"admin": False, "cargar": False, "maestros": False}),  # no registrado
])
def test_yo_permisos_por_rol(api, db, email, esperado):
    r = api["yo"].main(_req("yo", email))
    assert r.status_code == 200 and r.headers["Cache-Control"] == "no-store"
    assert json.loads(r.get_body()) == {"email": email, **esperado}


def test_yo_anota_ultimo_acceso(api, db):
    api["yo"].main(_req("yo", "ope@empresa.cl"))
    assert db.execute("SELECT ultimo_acceso FROM usuario WHERE email = 'ope@empresa.cl'").fetchone()[0]


def test_exigir_bloquea_maestros_sin_permiso(api):
    r = api["maestros"].main(_req("maestros", "ope@empresa.cl"))
    assert r.status_code == 403 and "permiso" in json.loads(r.get_body())["mensaje"]
    assert api["maestros"].main(_req("maestros", "admin@empresa.cl")).status_code == 200


def test_exigir_sin_base_responde_500(api, monkeypatch):
    def falla():
        raise OSError("sin conexión")

    monkeypatch.setattr(api["maestros"].web, "conexion_portal", falla)
    assert api["maestros"].main(_req("maestros", "admin@empresa.cl")).status_code == 500


def test_solo_admin_usa_el_mantenedor(api):
    for email in ("ope@empresa.cl", "baja@empresa.cl", "nadie@empresa.cl"):
        assert api["usuarios"].main(_req("usuarios", email)).status_code == 403
    assert _post(api, {"accion": "borrar_usuario", "id": 1}, email="ope@empresa.cl")[0] == 403


def test_listar(api):
    r = api["usuarios"].main(_req("usuarios", "admin@empresa.cl"))
    d = json.loads(r.get_body())
    assert [u["email"] for u in d["usuarios"]] == ["admin@empresa.cl", "baja@empresa.cl", "ger@empresa.cl", "ope@empresa.cl"]
    ope = next(u for u in d["usuarios"] if u["email"] == "ope@empresa.cl")
    assert ope["roles"] == [2] and ope["activo"] is True and ope["nombre"] == "Ope"
    roles = {r["nombre"]: r for r in d["roles"]}
    assert roles["Administrador"]["menus"] == [1, 2] and roles["Administrador"]["usuarios"] == 2
    assert roles["Operaciones"]["puede_cargar"] is True and roles["Gerencia"]["menus"] == []
    assert [m["nombre"] for m in d["menus"]] == ["Indicadores Operacionales", "ITE"]


def test_agregar_usuario_normaliza_email_y_asigna_roles(api, db):
    estado, d = _post(api, {"accion": "guardar_usuario",
                            "usuario": {"email": "  Nueva.Persona@Empresa.cl ", "nombre": "Nueva", "roles": [2, 3]}})
    assert estado == 200, d
    fila = db.execute("SELECT id, email, nombre, activo FROM usuario WHERE email = 'nueva.persona@empresa.cl'").fetchone()
    assert fila[1:] == ("nueva.persona@empresa.cl", "Nueva", 1)
    assert sorted(r for (r,) in db.execute("SELECT rol_id FROM usuario_rol WHERE usuario_id = ?", (fila[0],))) == [2, 3]


@pytest.mark.parametrize("usuario, error", [
    ({"email": "sin-arroba"}, "Email inválido"),
    ({"email": "ope@empresa.cl"}, "Ya existe"),
    ({"email": "x@empresa.cl", "roles": [99]}, "No existe el rol 99"),
    ({"email": "x@empresa.cl", "roles": ["a"]}, "inválida"),
])
def test_agregar_usuario_valida(api, db, usuario, error):
    estado, d = _post(api, {"accion": "guardar_usuario", "usuario": usuario})
    assert estado == 400 and error in d["mensaje"]
    assert db.execute("SELECT COUNT(*) FROM usuario").fetchone()[0] == 4


def test_editar_usuario_cambia_roles_y_desactiva(api, db):
    estado, _ = _post(api, {"accion": "guardar_usuario", "usuario": {
        "id": 2, "email": "ope@empresa.cl", "nombre": "Operador", "activo": False, "roles": [3]}})
    assert estado == 200
    assert db.execute("SELECT nombre, activo FROM usuario WHERE id = 2").fetchone() == ("Operador", 0)
    assert db.execute("SELECT rol_id FROM usuario_rol WHERE usuario_id = 2").fetchall() == [(3,)]


def test_borrar_usuario(api, db):
    assert _post(api, {"accion": "borrar_usuario", "id": 3})[0] == 200
    assert db.execute("SELECT COUNT(*) FROM usuario WHERE id = 3").fetchone()[0] == 0
    assert _post(api, {"accion": "borrar_usuario", "id": 3})[0] == 400


@pytest.mark.parametrize("cuerpo", [
    {"accion": "borrar_usuario", "id": 1},
    {"accion": "guardar_usuario", "usuario": {"id": 1, "email": "admin@empresa.cl", "roles": [2]}},
    {"accion": "guardar_usuario", "usuario": {"id": 1, "email": "admin@empresa.cl", "activo": False, "roles": [1]}},
    {"accion": "guardar_rol", "rol": {"id": 1, "nombre": "Administrador", "es_admin": False}},
])
def test_no_puede_quitarse_el_admin(api, db, cuerpo):
    estado, d = _post(api, cuerpo)
    assert estado == 400 and "a ti mismo" in d["mensaje"]
    assert json.loads(api["yo"].main(_req("yo", "admin@empresa.cl")).get_body())["admin"] is True


def test_guardar_rol_con_menus_y_herramientas(api, db):
    estado, _ = _post(api, {"accion": "guardar_rol", "rol": {
        "id": 3, "nombre": "Gerencia", "puede_maestros": True, "menus": [2]}})
    assert estado == 200
    assert db.execute("SELECT es_admin, puede_cargar, puede_maestros FROM rol WHERE id = 3").fetchone() == (0, 0, 1)
    assert db.execute("SELECT menu_id FROM permiso WHERE rol_id = 3").fetchall() == [(2,)]
    assert json.loads(api["yo"].main(_req("yo", "ger@empresa.cl")).get_body())["maestros"] is True


def test_guardar_rol_no_toca_permisos_por_reporte(api, db):
    db.execute("INSERT INTO reporte (menu_id, nombre, url_powerbi) VALUES (2, 'IP', 'https://x')")
    db.execute("INSERT INTO permiso (rol_id, reporte_id) VALUES (2, 1)")
    db.commit()
    assert _post(api, {"accion": "guardar_rol", "rol": {"id": 2, "nombre": "Operaciones", "menus": []}})[0] == 200
    assert db.execute("SELECT menu_id, reporte_id FROM permiso WHERE rol_id = 2").fetchall() == [(None, 1)]


def test_agregar_rol_y_nombre_repetido(api, db):
    assert _post(api, {"accion": "guardar_rol", "rol": {"nombre": "Lectura"}})[0] == 200
    estado, d = _post(api, {"accion": "guardar_rol", "rol": {"nombre": "Lectura"}})
    assert estado == 400 and "Ya existe un rol" in d["mensaje"]


def test_borrar_rol_solo_sin_usuarios(api, db):
    estado, d = _post(api, {"accion": "borrar_rol", "id": 2})
    assert estado == 400 and "1 usuario" in d["mensaje"]
    _post(api, {"accion": "guardar_usuario", "usuario": {"id": 2, "email": "ope@empresa.cl", "roles": []}})
    assert _post(api, {"accion": "borrar_rol", "id": 2})[0] == 200
    assert db.execute("SELECT COUNT(*) FROM permiso WHERE rol_id = 2").fetchone()[0] == 0


def test_accion_invalida(api):
    assert _post(api, {"accion": "otra"})[0] == 400
