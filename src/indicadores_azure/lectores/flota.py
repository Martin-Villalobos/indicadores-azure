"""Maestro de flota: patente, tipo de bus y plazas (lo que en indicadores-bi es bi.buses + bi.tipo_bus).

Formato: CSV (separado por coma o punto y coma) o Excel con una fila de encabezados que trae
PPU (o PATENTE), TIPO_BUS (o TIPO BUS / TIPOLOGIA) y CAPACIDAD (o PLAZAS). Sirve directo el
resultado de:

    SELECT b.ppu, b.tipo_bus, t.capacidad FROM bi.buses b LEFT JOIN bi.tipo_bus t ON t.id = b.tipo_bus

No tiene vigencia por fechas: el cálculo usa siempre la última flota cargada. Las plazas del ICP
salen de aquí y nunca de la columna Capacidad del archivo de velocidades.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterator

from ..control import ErrorDeCarga
from ._comun import abrir_excel, clave, entero, texto

TABLA = "raw_flota"
EXTENSIONES = {".csv", ".xlsx"}
COLUMNAS = ("numero_fila", "ppu", "tipo_bus", "plazas")

ALIAS = {
    "ppu": ("PPU", "PATENTE"),
    "tipo_bus": ("TIPO_BUS", "TIPO BUS", "TIPOLOGIA", "TIPO"),
    "plazas": ("CAPACIDAD", "PLAZAS"),
}


def patente(valor: object) -> str:
    return clave(valor).replace("-", "").replace(" ", "")


def _filas(contenido: bytes) -> list[list[object]]:
    if contenido[:2] == b"PK":  # xlsx es un zip
        libro = abrir_excel(contenido)
        try:
            return [list(f) for f in libro.worksheets[0].iter_rows(values_only=True)]
        finally:
            libro.close()
    try:
        texto_csv = contenido.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto_csv = contenido.decode("latin-1")
    primera = texto_csv.splitlines()[0] if texto_csv else ""
    separador = ";" if primera.count(";") > primera.count(",") else ","
    return [fila for fila in csv.reader(io.StringIO(texto_csv), delimiter=separador)]


def leer(contenido: bytes) -> Iterator[tuple]:
    filas = _filas(contenido)
    if not filas:
        raise ErrorDeCarga("El archivo de flota está vacío.")
    encabezados = [clave(v) for v in filas[0]]
    indices = {}
    for campo, alias in ALIAS.items():
        i = next((encabezados.index(a) for a in alias if a in encabezados), None)
        if i is None:
            raise ErrorDeCarga(f"Falta la columna {alias[0]} (o {', '.join(alias[1:])}).")
        indices[campo] = i
    vistas: dict[str, int] = {}
    for numero, fila in enumerate(filas[1:], start=2):
        if not any(str(v or "").strip() for v in fila):
            continue
        valores = list(fila) + [None] * len(encabezados)
        ppu = patente(valores[indices["ppu"]])
        if not ppu:
            raise ErrorDeCarga(f"Fila {numero}: falta la patente.")
        if ppu in vistas:
            raise ErrorDeCarga(f"Fila {numero}: la patente {ppu} está repetida (fila {vistas[ppu]}).")
        vistas[ppu] = numero
        plazas = entero(valores[indices["plazas"]], f"Fila {numero}, columna CAPACIDAD")
        if plazas is not None and plazas <= 0:
            raise ErrorDeCarga(f"Fila {numero}: capacidad {plazas} no válida.")
        yield (numero, ppu, texto(valores[indices["tipo_bus"]]), plazas)
