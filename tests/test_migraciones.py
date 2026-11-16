import pytest

from indicadores_azure import migraciones


class Cursor:
    def __init__(self, db):
        self.db = db
        self._res = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def execute(self, sql, params=()):
        self.db.ejecutadas.append(sql)
        if sql.startswith("SELECT GET_LOCK"):
            self._res = [(1 if self.db.candado_libre else 0,)]
        elif sql.startswith("SELECT archivo, sha256"):
            self._res = list(self.db.registro.items())
        elif sql.startswith("INSERT INTO migracion_aplicada"):
            self.db.registro[params[0]] = params[1]
        elif "FALLA" in sql:
            raise RuntimeError("error de SQL")
        else:
            self._res = []

    def fetchone(self):
        return self._res[0] if self._res else None

    def fetchall(self):
        return self._res


class Base:
    def __init__(self):
        self.registro, self.ejecutadas, self.candado_libre, self.commits = {}, [], True, 0

    def cursor(self):
        return Cursor(self)

    def commit(self):
        self.commits += 1


@pytest.fixture
def sql(tmp_path):
    (tmp_path / "01_a.sql").write_text("-- tabla a\nCREATE TABLE IF NOT EXISTS a (x INT);\n", encoding="utf-8")
    (tmp_path / "02_b.sql").write_text("CREATE TABLE IF NOT EXISTS b (y INT);\nINSERT IGNORE INTO b VALUES (1);\n")
    return tmp_path


def _de_usuario(base):
    return [s for s in base.ejecutadas if not s.startswith(("SELECT", "CREATE TABLE IF NOT EXISTS migracion", "INSERT INTO migracion"))]


def test_aplica_todo_en_orden_la_primera_vez(sql):
    base = Base()
    assert migraciones.aplicar(base, sql) == ["01_a.sql", "02_b.sql"]
    assert _de_usuario(base) == [
        "CREATE TABLE IF NOT EXISTS a (x INT)",
        "CREATE TABLE IF NOT EXISTS b (y INT)",
        "INSERT IGNORE INTO b VALUES (1)",
    ]
    assert set(base.registro) == {"01_a.sql", "02_b.sql"}
    assert base.ejecutadas[-1].startswith("SELECT RELEASE_LOCK")


def test_segunda_vez_no_hace_nada(sql):
    base = Base()
    migraciones.aplicar(base, sql)
    base.ejecutadas.clear()
    assert migraciones.aplicar(base, sql) == []
    assert _de_usuario(base) == []


def test_archivo_nuevo_o_modificado_se_aplica(sql):
    base = Base()
    migraciones.aplicar(base, sql)
    (sql / "02_b.sql").write_text("CREATE TABLE IF NOT EXISTS b (y INT);\nINSERT IGNORE INTO b VALUES (2);\n")
    (sql / "03_c.sql").write_text("CREATE OR REPLACE VIEW c AS SELECT 1;\n")
    assert migraciones.aplicar(base, sql) == ["02_b.sql", "03_c.sql"]


def test_falla_corta_no_registra_y_suelta_el_candado(sql):
    (sql / "02_b.sql").write_text("CREATE TABLE FALLA;\n")
    (sql / "03_c.sql").write_text("CREATE TABLE IF NOT EXISTS c (z INT);\n")
    base = Base()
    with pytest.raises(RuntimeError):
        migraciones.aplicar(base, sql)
    assert set(base.registro) == {"01_a.sql"}
    assert "CREATE TABLE IF NOT EXISTS c (z INT)" not in base.ejecutadas
    assert base.ejecutadas[-1].startswith("SELECT RELEASE_LOCK")


def test_sin_candado_no_migra(sql):
    base = Base()
    base.candado_libre = False
    with pytest.raises(RuntimeError, match="candado"):
        migraciones.aplicar(base, sql)
    assert base.registro == {}


def test_los_sql_del_repo_son_idempotentes():
    for archivo in sorted(migraciones.carpeta().glob("*.sql")):
        for s in migraciones.sentencias(archivo.read_text(encoding="utf-8")):
            primera = s.split(None, 3)[:3]
            assert (
                s.startswith(("CREATE TABLE IF NOT EXISTS", "INSERT IGNORE", "CREATE OR REPLACE VIEW", "ALTER TABLE"))
            ), f"{archivo.name}: sentencia no idempotente: {' '.join(primera)}"
