from conftest import ANEXO1_OK, excel
from indicadores_azure.config import Config
from indicadores_azure.procesar import procesar_blob

CONFIG = Config("h", 3306, "db", "u", "p", None, "conn", "cargas", None, 1)
META = {"nombre_original": "Anexo%201%20Se%C3%B1al.xlsx", "subido_por": "ana%40empresa.cl"}


def test_carga_ok_mueve_a_procesados(contenedor, conn):
    contenedor.subir("anexo1/entrada/20260101_a.xlsx", excel(ANEXO1_OK), META)
    estado = procesar_blob(CONFIG, contenedor, conn, "anexo1", "anexo1/entrada/20260101_a.xlsx", META)
    assert estado == "COMPLETADO"
    assert len(conn.filas) == 2
    _, meta = contenedor.blobs["anexo1/procesados/20260101_a.xlsx"]
    assert meta["estado"] == "COMPLETADO" and meta["filas"] == "2" and meta["carga_id"] == "1"
    assert not any(n.startswith("anexo1/entrada/") for n in contenedor.blobs)


def test_mismo_archivo_dos_veces_es_duplicado(contenedor, conn):
    for nombre in ("anexo1/entrada/1_a.xlsx", "anexo1/entrada/2_a.xlsx"):
        contenedor.subir(nombre, excel(ANEXO1_OK), META)
    procesar_blob(CONFIG, contenedor, conn, "anexo1", "anexo1/entrada/1_a.xlsx", META)
    estado = procesar_blob(CONFIG, contenedor, conn, "anexo1", "anexo1/entrada/2_a.xlsx", META)
    assert estado == "DUPLICADO"
    assert len(conn.filas) == 2


def test_error_deja_archivo_y_motivo_sin_filas(contenedor, conn):
    malo = ANEXO1_OK[:7] + [("T201 00R", "201", "REGRESO", "SÁBADO", 2, "xx", "07:29")]
    contenedor.subir("anexo1/entrada/1_b.xlsx", excel(malo), META)
    estado = procesar_blob(CONFIG, contenedor, conn, "anexo1", "anexo1/entrada/1_b.xlsx", META)
    assert estado == "ERROR"
    assert conn.filas == []  # la primera fila válida no quedó a medias
    assert "anexo1/errores/1_b.xlsx" in contenedor.blobs
    texto = contenedor.blobs["anexo1/errores/1_b.xlsx.error.txt"][0].decode()
    assert "Archivo: Anexo 1 Señal.xlsx" in texto and "Subido por: ana@empresa.cl" in texto
    assert texto.split("\n\n", 1)[1].startswith("Hoja 'Anexo 1', fila 8, columna HORA INICIO")
    assert conn.control[1]["estado"] == "ERROR"


def test_extension_no_permitida(contenedor, conn):
    meta = {"nombre_original": "anexo.csv"}
    contenedor.subir("anexo1/entrada/1_anexo.csv", b"a,b", meta)
    assert procesar_blob(CONFIG, contenedor, conn, "anexo1", "anexo1/entrada/1_anexo.csv", meta) == "ERROR"
    assert "Extensión no permitida" in contenedor.blobs["anexo1/errores/1_anexo.csv.error.txt"][0].decode()
