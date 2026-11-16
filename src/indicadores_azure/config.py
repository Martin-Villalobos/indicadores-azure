"""Configuración por entorno (dev | prod).

El entorno activo lo elige la variable ``ENTORNO`` (en ``.env`` o en el sistema); sin
ella es ``prod``. Cada valor se toma, en este orden, de:

1. la variable de entorno (``DB_HOST``, ``DB_PASSWORD``, ``BLOB_CONNECTION_STRING``...),
2. la sección del entorno en ``config/entornos.toml``,
3. el valor por defecto del código.

En Azure el job recibe todo por variables, así que funciona igual aunque el archivo no esté.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

ENTORNOS = ("dev", "prod")
RAIZ_REPO = Path(__file__).resolve().parents[2]


def _cargar_env_local() -> None:
    """Carga un .env (directorio actual o raíz del repo) sin pisar variables ya definidas."""

    for archivo in (Path.cwd() / ".env", RAIZ_REPO / ".env"):
        if archivo.exists():
            break
    else:
        return
    for linea in archivo.read_text(encoding="utf-8-sig").splitlines():
        linea = linea.strip()
        if linea and not linea.startswith("#") and "=" in linea:
            nombre, valor = linea.split("=", 1)
            os.environ.setdefault(nombre.strip(), valor.strip().strip('"').strip("'"))


def archivo_entornos() -> Path | None:
    """``CONFIG_ENTORNOS`` si está definida; si no, ``config/entornos.toml`` del directorio actual o del repo."""

    if os.getenv("CONFIG_ENTORNOS"):
        return Path(os.environ["CONFIG_ENTORNOS"])
    for candidato in (Path.cwd() / "config" / "entornos.toml", RAIZ_REPO / "config" / "entornos.toml"):
        if candidato.exists():
            return candidato
    return None


def entorno_activo() -> str:
    _cargar_env_local()
    entorno = (os.getenv("ENTORNO") or "prod").strip().lower()
    if entorno not in ENTORNOS:
        raise RuntimeError(f"ENTORNO={entorno!r} no es válido: usa {' o '.join(ENTORNOS)}.")
    return entorno


def valores_entorno(entorno: str) -> dict:
    """Valores de la sección del entorno en el archivo de configuración (vacío si no hay archivo)."""

    archivo = archivo_entornos()
    if archivo is None or not archivo.exists():
        return {}
    with archivo.open("rb") as f:
        return dict(tomllib.load(f).get(entorno, {}))


def exportar_al_entorno(entorno: str | None = None) -> str:
    """Copia los valores del archivo a variables de entorno (sin pisar las existentes).

    Lo usan la web local y el seeder, que leen ``os.environ`` igual que en Azure.
    """

    entorno = entorno or entorno_activo()
    for clave, valor in valores_entorno(entorno).items():
        os.environ.setdefault(clave.upper(), str(valor))
    os.environ.setdefault("ENTORNO", entorno)
    return entorno


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
    entorno: str = "prod"

    @property
    def es_dev(self) -> bool:
        return self.entorno == "dev"

    @classmethod
    def desde_entorno(cls) -> "Config":
        entorno = entorno_activo()
        archivo = valores_entorno(entorno)

        def valor(nombre: str, defecto: str | None = None) -> str | None:
            if os.getenv(nombre) is not None:
                return os.environ[nombre]
            if nombre.lower() in archivo:
                return str(archivo[nombre.lower()])
            return defecto

        faltan = [n for n in ("DB_HOST", "DB_USER", "DB_PASSWORD", "BLOB_CONNECTION_STRING") if not valor(n)]
        if faltan:
            raise RuntimeError(f"Faltan variables para el entorno {entorno}: " + ", ".join(faltan))
        return cls(
            db_host=valor("DB_HOST"),
            db_port=int(valor("DB_PORT", "3306")),
            db_name=valor("DB_NAME", "indicadores_bi"),
            db_user=valor("DB_USER"),
            db_password=valor("DB_PASSWORD"),
            db_ssl_ca=valor("DB_SSL_CA") or None,
            blob_connection_string=valor("BLOB_CONNECTION_STRING"),
            blob_container=valor("BLOB_CONTAINER", "cargas"),
            queue_name=valor("QUEUE_NAME") or None,
            batch_size=int(valor("BATCH_SIZE", "5000")),
            entorno=entorno,
        )
