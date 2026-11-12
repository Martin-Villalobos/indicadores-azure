"""Lectores de archivos de entrada.

Cada lector define:
    TABLA       tabla raw_ de destino.
    COLUMNAS    columnas de la tabla (sin carga_id), en el orden que entrega leer().
    EXTENSIONES extensiones aceptadas.
    leer(contenido: bytes) -> Iterator[tuple]  filas listas para insertar.
    VIGENCIA    (columna desde, columna hasta) de COLUMNAS con el rango de fechas que cubre el
                archivo; se registra en vigencia_archivo (ver vigencias.py).
    VIGENCIA_POR_MES  opcional: True si el rango se extiende a meses completos.

Para agregar un tipo nuevo: crear el módulo y sumarlo a LECTORES.
"""

from __future__ import annotations

from types import ModuleType

from . import anexo1, anexo3, exclusiones, velocidades

LECTORES: dict[str, ModuleType] = {
    "anexo1": anexo1,
    "anexo3": anexo3,
    "velocidades": velocidades,
    "exclusiones": exclusiones,
}
