"""Conexión a Azure Database for MySQL (exige TLS)."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import pymysql

from .config import Config


@contextmanager
def conexion(config: Config) -> Iterator[pymysql.connections.Connection]:
    ssl = {"ca": config.db_ssl_ca} if config.db_ssl_ca else None
    conn = pymysql.connect(
        host=config.db_host,
        port=config.db_port,
        user=config.db_user,
        password=config.db_password,
        database=config.db_name,
        charset="utf8mb4",
        autocommit=False,
        connect_timeout=15,
        read_timeout=900,
        write_timeout=900,
        ssl=ssl,
    )
    try:
        yield conn
    finally:
        conn.close()
