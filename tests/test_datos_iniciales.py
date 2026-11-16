from indicadores_azure import datos_iniciales


class Cursor:
    def __init__(self, db):
        self.db = db
        self._res = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def execute(self, sql, params=()):
        if sql.startswith("SELECT sha256, archivo, tamano FROM carga_inicial"):
            self._res = [(sha, a, t) for sha, (a, t, _) in self.db.registro.items()]
        elif sql.startswith("INSERT IGNORE INTO carga_inicial"):
            self.db.registro.setdefault(params[0], params[1:])

    def fetchall(self):
        return self._res


class Conexion:
    def __init__(self):
        self.registro = {}
        self.commits = 0

    def cursor(self):
        return Cursor(self)

    def commit(self):
        self.commits += 1


def _raiz(tmp_path):
    (tmp_path / "anexo1" / "2026").mkdir(parents=True)
    (tmp_path / "anexo3").mkdir()
    (tmp_path / "anexo1" / "b.xlsx").write_bytes(b"b")
    (tmp_path / "anexo1" / "2026" / "a.xlsx").write_bytes(b"a")
    (tmp_path / "anexo1" / "notas.txt").write_bytes(b"no")
    (tmp_path / "anexo1" / "~$b.xlsx").write_bytes(b"temporal de excel")
    (tmp_path / "anexo3" / "c.xlsx").write_bytes(b"c")
    (tmp_path / "anexo4").mkdir()
    (tmp_path / "anexo4" / "d.xlsx").write_bytes(b"d")  # tipo sin lector: se ignora
    return tmp_path


def test_sube_en_orden_con_metadatos(tmp_path, contenedor):
    conn = Conexion()
    subidos = datos_iniciales.subir_pendientes(conn, contenedor, _raiz(tmp_path))
    assert subidos == [
        "anexo1/entrada/00000000_0001_a.xlsx",
        "anexo1/entrada/00000000_0002_b.xlsx",
        "anexo3/entrada/00000000_0003_c.xlsx",
    ]
    contenido, meta = contenedor.blobs["anexo1/entrada/00000000_0002_b.xlsx"]
    assert contenido == b"b"
    assert meta == {"subido_por": "carga inicial", "nombre_original": "b.xlsx"}
    assert {a for a, _, _ in conn.registro.values()} == {"anexo1/2026/a.xlsx", "anexo1/b.xlsx", "anexo3/c.xlsx"}


def test_no_sube_dos_veces_aunque_se_haya_procesado(tmp_path, contenedor):
    conn = Conexion()
    raiz = _raiz(tmp_path)
    datos_iniciales.subir_pendientes(conn, contenedor, raiz)
    contenedor.blobs.clear()  # el job ya los movió a procesados (o se eliminaron en la web)
    assert datos_iniciales.subir_pendientes(conn, contenedor, raiz) == []
    assert contenedor.blobs == {}


def test_archivo_nuevo_o_renombrado(tmp_path, contenedor):
    conn = Conexion()
    raiz = _raiz(tmp_path)
    datos_iniciales.subir_pendientes(conn, contenedor, raiz)
    (raiz / "anexo1" / "b.xlsx").rename(raiz / "anexo1" / "b2.xlsx")  # mismo contenido: no se sube
    (raiz / "anexo3" / "nuevo.xlsx").write_bytes(b"nuevo")
    assert datos_iniciales.subir_pendientes(conn, contenedor, raiz) == ["anexo3/entrada/00000000_0004_nuevo.xlsx"]


def test_sin_carpeta_no_hace_nada(tmp_path, contenedor):
    assert datos_iniciales.subir_pendientes(Conexion(), contenedor, tmp_path / "no_existe") == []
