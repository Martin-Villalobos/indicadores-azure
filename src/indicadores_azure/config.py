"""Configuración por variables de entorno (en Azure, secretos del job)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _cargar_env_local() -> None:
    """Carga un .env en la raíz del repo para pruebas locales, sin pisar variables."""

    archivo = Path(__file__).resolve().parents[2] / ".env"
    if not archivo.exists():
        return
    for linea in archivo.read_text(encoding="utf-8-sig").splitlines():
        linea = linea.strip()
        if linea and not linea.startswith("#") and "=" in linea:
            nombre, valor = linea.split("=", 1)
            os.environ.setdefault(nombre.strip(), valor.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Config:
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str
    db_ssl_ca: str | None
    blob_connection_string: str
    blob_container: str
    queue_name: str | None
    batch_size: int

    @classmethod
    def desde_entorno(cls) -> "Config":
        _cargar_env_local()
        faltan = [n for n in ("DB_HOST", "DB_USER", "DB_PASSWORD", "BLOB_CONNECTION_STRING") if not os.getenv(n)]
        if faltan:
            raise RuntimeError("Faltan variables de entorno: " + ", ".join(faltan))
        return cls(
            db_host=os.environ["DB_HOST"],
            db_port=int(os.getenv("DB_PORT", "3306")),
            db_name=os.getenv("DB_NAME", "indicadores_bi"),
            db_user=os.environ["DB_USER"],
            db_password=os.environ["DB_PASSWORD"],
            db_ssl_ca=os.getenv("DB_SSL_CA") or None,
            blob_connection_string=os.environ["BLOB_CONNECTION_STRING"],
            blob_container=os.getenv("BLOB_CONTAINER", "cargas"),
            queue_name=os.getenv("QUEUE_NAME") or None,
            batch_size=int(os.getenv("BATCH_SIZE", "5000")),
        )
