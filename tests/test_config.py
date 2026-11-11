import pytest

from indicadores_azure import config as cfg
from indicadores_azure.config import Config
from indicadores_azure.semilla import sentencias

VARIABLES = ("ENTORNO", "DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "BLOB_CONNECTION_STRING", "QUEUE_NAME")


@pytest.fixture(autouse=True)
def entorno_limpio(monkeypatch, tmp_path):
    for nombre in VARIABLES:
        monkeypatch.delenv(nombre, raising=False)
    monkeypatch.setattr(cfg, "_cargar_env_local", lambda: None)
    archivo = tmp_path / "entornos.toml"
    archivo.write_text(
        '[dev]\ndb_host = "localhost"\ndb_user = "u"\ndb_password = "p"\nblob_connection_string = "azurite"\n'
        '[prod]\ndb_host = "azure"\nqueue_name = "cola"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("CONFIG_ENTORNOS", str(archivo))


def test_dev_toma_conexiones_del_archivo(monkeypatch):
    monkeypatch.setenv("ENTORNO", "dev")
    c = Config.desde_entorno()
    assert (c.entorno, c.db_host, c.db_user, c.blob_connection_string, c.queue_name) == ("dev", "localhost", "u", "azurite", None)
    assert c.es_dev


def test_sin_entorno_es_prod_y_exige_secretos():
    with pytest.raises(RuntimeError, match="prod: DB_USER, DB_PASSWORD, BLOB_CONNECTION_STRING"):
        Config.desde_entorno()


def test_variable_de_entorno_gana_al_archivo(monkeypatch):
    for nombre, valor in {"DB_HOST": "otro", "DB_USER": "x", "DB_PASSWORD": "y", "BLOB_CONNECTION_STRING": "z"}.items():
        monkeypatch.setenv(nombre, valor)
    c = Config.desde_entorno()
    assert (c.entorno, c.db_host, c.queue_name) == ("prod", "otro", "cola")


def test_entorno_invalido(monkeypatch):
    monkeypatch.setenv("ENTORNO", "qa")
    with pytest.raises(RuntimeError, match="no es válido"):
        Config.desde_entorno()


def test_sentencias_separa_y_quita_comentarios():
    texto = "-- comentario\nCREATE TABLE a (x INT);\nINSERT INTO a VALUES (1),\n  (2);\n"
    assert sentencias(texto) == ["CREATE TABLE a (x INT)", "INSERT INTO a VALUES (1),\n  (2)"]
