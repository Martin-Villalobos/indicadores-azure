"""Normalización de claves para cruzar Anexo 3, velocidades y exclusiones (copiado de indicadores-bi)."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, time, timedelta


def texto(value) -> str:
    return str(value).strip() if value is not None else ""


def normalizar(value) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto(value).upper()) if not unicodedata.combining(c))


def codigo(value) -> str:
    """Código TS sin espacios: 'T503 00I' y 'T50300I' cruzan."""
    return normalizar(value).replace(" ", "")


def es_u16(value) -> bool:
    return re.fullmatch(r"U?0*16(?:\.0+)?", normalizar(value).replace(" ", "")) is not None


def unidad(value) -> str:
    value = normalizar(value).replace(" ", "").removeprefix("U")
    if not re.fullmatch(r"\d+(?:\.0+)?", value):
        raise ValueError(f"Unidad inválida: {value!r}")
    return str(int(value.split(".")[0]))


SENTIDOS = {"I": "I", "IDA": "I", "R": "R", "RET": "R", "RETORNO": "R", "REGRESO": "R", "VUELTA": "R"}


def sentido(value) -> str:
    result = SENTIDOS.get(normalizar(value))
    if result is None:
        raise ValueError(f"Sentido desconocido: {value!r}")
    return result


TIPOS_DIA = {"LABORAL", "SABADO", "DOMINGO"}


def tipo_dia(value) -> str:
    result = normalizar(value)
    if result not in TIPOS_DIA:
        raise ValueError(f"Tipo de día no reconocido: {value!r}")
    return result


def hora(value) -> time:
    """MySQL entrega TIME como timedelta."""
    if isinstance(value, timedelta):
        seconds = value.total_seconds()
        if not 0 <= seconds < 86400:
            raise ValueError(f"Hora fuera del día: {value}")
        return (datetime.min + value).time()
    if isinstance(value, time):
        return value
    raise ValueError(f"Hora ausente o inválida: {value!r}")


def patente(value) -> str:
    return normalizar(value).replace("-", "").replace(" ", "")
