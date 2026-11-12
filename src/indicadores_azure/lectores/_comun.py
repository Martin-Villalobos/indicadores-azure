"""Conversión de celdas compartida por los lectores (mensajes pensados para quien corrige el archivo)."""

from __future__ import annotations

import io
import unicodedata
import zipfile
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation

from ..control import ErrorDeCarga


def clave(valor: object) -> str:
    """Texto sin tildes, en mayúsculas y con espacios simples, para comparar encabezados."""

    texto = unicodedata.normalize("NFKD", str(valor if valor is not None else ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return " ".join(texto.upper().split()).rstrip(":")


def texto(valor: object) -> str | None:
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)  # 1622.0 -> "1622"
    resultado = str(valor if valor is not None else "").strip()
    return resultado or None


def fecha(valor: object, donde: str) -> date | None:
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


def hora(valor: object, donde: str) -> time | None:
    if valor in (None, "", "-"):
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


def decimal(valor: object, donde: str) -> Decimal | None:
    if valor in (None, "", "-", "--"):
        return None
    try:
        resultado = Decimal(str(valor).strip().replace(",", "."))
    except (InvalidOperation, ValueError):
        raise ErrorDeCarga(f"{donde}: '{valor}' no es un número.") from None
    if not resultado.is_finite():
        raise ErrorDeCarga(f"{donde}: '{valor}' no es un número.")
    return resultado


def entero(valor: object, donde: str) -> int | None:
    numero = decimal(valor, donde)
    if numero is None:
        return None
    if numero != numero.to_integral_value():
        raise ErrorDeCarga(f"{donde}: '{valor}' no es un número entero.")
    return int(numero)


def abrir_excel(contenido: bytes):
    from openpyxl import load_workbook

    try:
        return load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
    except (zipfile.BadZipFile, KeyError, ValueError, OSError):
        raise ErrorDeCarga("El archivo no es un Excel .xlsx válido (¿está dañado o es otro formato?).") from None
