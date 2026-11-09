"""Lectores de archivos de entrada.

Cada lector define:
    TABLA       tabla raw_ de destino.
    COLUMNAS    columnas de la tabla (sin carga_id), en el orden que entrega leer().
    EXTENSIONES extensiones aceptadas.
    leer(contenido: bytes) -> Iterator[tuple]  filas listas para insertar.

Para agregar un tipo nuevo: crear el módulo y sumarlo a LECTORES.
"""

from __future__ import annotations

from types import ModuleType

from . import anexo1

LECTORES: dict[str, ModuleType] = {
    "anexo1": anexo1,
}
