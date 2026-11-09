"""Anexo 1: horarios de operación por servicio, sentido, tipo de día y tramo.

Formato esperado (hoja activa del .xlsx):
    Filas de cabecera con el valor en la columna B:
        UNIDAD DE SERVICIOS | AÑO | FECHA INICIO | FECHA TÉRMINO
    Una fila de encabezados que incluya al menos:
        CÓDIGO TS SERVICIO, SENTIDO, TIPO DÍA, HORA INICIO
    y opcionalmente UNIDAD DE SERVICIO, CÓDIGO USUARIO SERVICIO, TRAMO HORARIO,
    HORA TÉRMINO.
    Luego, una fila por tramo. Las filas vacías se ignoran.

Los encabezados se comparan sin tildes ni mayúsculas.
"""

from __future__ import annotations

import io
import unicodedata
import zipfile
from collections.abc import Iterator
from datetime import date, datetime, time

from ..control import ErrorDeCarga

TABLA = "raw_anexo1"
EXTENSIONES = {".xlsx"}
COLUMNAS = (
    "numero_fila", "unidad_servicios", "anio", "codigo_ts_servicio",
    "codigo_usuario_servicio", "sentido", "tipo_dia", "tramo_horario",
    "hora_inicio", "hora_termino", "fecha_inicio", "fecha_termino",
)

ENCABEZADOS_OBLIGATORIOS = ("CODIGO TS SERVICIO", "SENTIDO", "TIPO DIA", "HORA INICIO")
CABECERAS = {"UNIDAD DE SERVICIOS", "ANO", "FECHA INICIO", "FECHA TERMINO"}


def _clave(valor: object) -> str:
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    return "".join(c for c in texto if not unicodedata.combining(c)).strip().upper()


def _texto(valor: object) -> str | None:
    texto = str(valor if valor is not None else "").strip()
    return texto or None


def _fecha(valor: object, donde: str) -> date | None:
    if valor in (None, ""):
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    for formato in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(str(valor).strip(), formato).date()
        except ValueError:
            pass
    raise ErrorDeCarga(f"{donde}: '{valor}' no es una fecha válida (se espera DD/MM/AAAA).")


def _hora(valor: object, donde: str) -> time | None:
    if valor in (None, ""):
        return None
    if isinstance(valor, datetime):
        return valor.time()
    if isinstance(valor, time):
        return valor
    for formato in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(str(valor).strip(), formato).time()
        except ValueError:
            pass
    raise ErrorDeCarga(f"{donde}: '{valor}' no es una hora válida (se espera HH:MM o HH:MM:SS).")


def _entero(valor: object, donde: str) -> int | None:
    if valor in (None, ""):
        return None
    try:
        return int(float(valor))
    except (TypeError, ValueError):
        raise ErrorDeCarga(f"{donde}: '{valor}' no es un número entero.") from None


def leer(contenido: bytes) -> Iterator[tuple]:
    from openpyxl import load_workbook

    try:
        libro = load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
    except (zipfile.BadZipFile, KeyError, ValueError):
        raise ErrorDeCarga("El archivo no es un Excel .xlsx válido (¿está dañado o es otro formato?).") from None

    try:
        hoja = libro.active
        cabecera: dict[str, object] = {}
        columnas: dict[str, int] | None = None
        for numero, fila in enumerate(hoja.iter_rows(values_only=True), start=1):
            valores = list(fila)
            if columnas is None:
                claves = [_clave(v) for v in valores]
                if set(ENCABEZADOS_OBLIGATORIOS).issubset(claves):
                    columnas = {clave: i for i, clave in enumerate(claves) if clave}
                    continue
                if claves and claves[0] in CABECERAS:
                    cabecera[claves[0]] = next((v for v in valores[1:] if v not in (None, "")), None)
                continue
            if not any(v not in (None, "") for v in valores):
                continue

            def celda(*nombres: str) -> object:
                for nombre in nombres:
                    indice = columnas.get(nombre)
                    if indice is not None and indice < len(valores):
                        return valores[indice]
                return None

            donde = f"Hoja '{hoja.title}', fila {numero}"
            for obligatorio in ENCABEZADOS_OBLIGATORIOS:
                if celda(obligatorio) in (None, ""):
                    raise ErrorDeCarga(f"{donde}: falta el valor de la columna {obligatorio}.")
            yield (
                numero,
                _texto(celda("UNIDAD DE SERVICIO", "UNIDAD DE SERVICIOS")) or _texto(cabecera.get("UNIDAD DE SERVICIOS")),
                _entero(cabecera.get("ANO"), "Cabecera AÑO"),
                _texto(celda("CODIGO TS SERVICIO")),
                _texto(celda("CODIGO USUARIO SERVICIO")),
                _texto(celda("SENTIDO")),
                _texto(celda("TIPO DIA")),
                _entero(celda("TRAMO HORARIO"), f"{donde}, columna TRAMO HORARIO"),
                _hora(celda("HORA INICIO"), f"{donde}, columna HORA INICIO"),
                _hora(celda("HORA TERMINO"), f"{donde}, columna HORA TÉRMINO"),
                _fecha(cabecera.get("FECHA INICIO"), "Cabecera FECHA INICIO"),
                _fecha(cabecera.get("FECHA TERMINO"), "Cabecera FECHA TÉRMINO"),
            )

        if columnas is None:
            raise ErrorDeCarga(
                f"No se encontró la fila de encabezados en la hoja '{hoja.title}'. Debe tener las columnas: "
                + ", ".join(ENCABEZADOS_OBLIGATORIOS) + "."
            )
    finally:
        libro.close()
