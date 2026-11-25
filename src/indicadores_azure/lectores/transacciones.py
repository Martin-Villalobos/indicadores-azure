"""Transacciones de Sonda (TRX_ACUM_DIA): un .zip diario con el archivo LVAT (.txt) de la U16.

El .zip trae el .txt y el PDF de la liquidación diaria; sólo se lee el .txt (también se acepta el
.txt suelto). Formato del .txt:

    Fecha Generacion30/10/2026 09:45:39
    Entidad;Sitio;Fecha;Chip;Tarjeta;NTT;Tipo Trx;Contrato;Monto;Estado;Liquidacion;...;CL;CRC
    U16 - Gran Americas US16;VLZY-71;28/10/2026 23:58:15;...      (una fila por validación)
    Cantidad TRX :148360
    Cantidad Preliquidado  : 0
    Cantidad Liquidado : 148360
    ...

Cada archivo trae lo que Sonda liquidó ese día, que incluye validaciones atrasadas de días
anteriores. Para el pago (q de la cláusula 5.3.1.1) se cuenta por fecha de la validación: así lo
hace el DTPM (cuadrado contra las cartas L453 y L455). Por eso el archivo no tiene vigencia: los
archivos se suman, no se reemplazan.

Se rechaza el archivo si alguna fila no es de la U16 o si el número de filas no coincide con
"Cantidad TRX" del pie (archivo cortado).
"""

from __future__ import annotations

import io
import re
import zipfile
from collections.abc import Iterator
from datetime import date, datetime

from ..control import ErrorDeCarga

TABLA = "raw_transacciones"
EXTENSIONES = {".zip", ".txt"}
UNIDAD = 16

ENCABEZADO = ("ENTIDAD", "SITIO", "FECHA", "CHIP", "TARJETA", "NTT", "TIPO TRX", "CONTRATO", "MONTO", "ESTADO",
              "LIQUIDACION", "CONSOLIDADO", "CSA", "SCSA", "CTLA", "CLA", "BNP", "SA", "CODIGOSITIO", "CL", "CRC")

COLUMNAS = (
    "archivo_txt", "numero_fila", "fecha_generacion",
    "entidad", "sitio", "ppu", "es_zona_paga", "fecha_hora", "fecha", "mes",
    "chip", "tarjeta", "ntt", "tipo_trx", "contrato", "monto", "estado",
    "liquidacion", "fecha_liquidacion", "consolidado",
    "csa", "scsa", "ctla", "cla", "bnp", "sa", "codigo_sitio", "cl", "crc",
)

_FECHA_GEN = re.compile(r"Fecha\s*Generacion\s*(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2})", re.I)
_PIE_TRX = re.compile(r"Cantidad\s+TRX\s*:\s*(\d+)", re.I)
_LIQUIDACION = re.compile(r"LQ(\d{8})")
_UNIDAD = re.compile(r"\s*U(\d+)\b", re.I)


def _textos(contenido: bytes) -> Iterator[tuple[str, str]]:
    """(nombre, texto) de cada .txt: los del .zip, o el contenido mismo si no es un .zip."""

    if contenido[:4] != b"PK\x03\x04":
        yield "", _decodificar(contenido)
        return
    try:
        zf = zipfile.ZipFile(io.BytesIO(contenido))
    except zipfile.BadZipFile:
        raise ErrorDeCarga("El archivo no es un .zip válido (¿está dañado?).") from None
    with zf:
        nombres = [n for n in zf.namelist() if n.lower().endswith(".txt")]
        if not nombres:
            raise ErrorDeCarga("El .zip no trae el archivo de transacciones (.txt).")
        for nombre in sorted(nombres):
            yield nombre, _decodificar(zf.read(nombre))


def _decodificar(datos: bytes) -> str:
    try:
        return datos.decode("utf-8-sig")
    except UnicodeDecodeError:
        return datos.decode("latin-1")


def _entero(valor: str, donde: str) -> int | None:
    valor = valor.strip()
    if not valor:
        return None
    try:
        return int(valor)
    except ValueError:
        raise ErrorDeCarga(f"{donde}: '{valor}' no es un número entero.") from None


def _fecha_hora(valor: str, donde: str) -> datetime:
    try:
        return datetime.strptime(valor.strip(), "%d/%m/%Y %H:%M:%S")
    except ValueError:
        raise ErrorDeCarga(f"{donde}: '{valor}' no es una fecha válida (se espera DD/MM/AAAA HH:MM:SS).") from None


def _fecha_liquidacion(codigo: str) -> date | None:
    m = _LIQUIDACION.match(codigo)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y%m%d").date()
    except ValueError:
        return None


def _leer_txt(nombre: str, texto: str) -> Iterator[tuple]:
    archivo = nombre.rsplit("/", 1)[-1] or None
    lineas = texto.splitlines()
    prefijo = f"Archivo '{archivo}', " if archivo else ""
    m = _FECHA_GEN.search(lineas[0]) if lineas else None
    if not m:
        raise ErrorDeCarga(f"{prefijo}línea 1: falta 'Fecha Generacion' (¿es un archivo LVAT de Sonda?).")
    generacion = datetime.strptime(m.group(1), "%d/%m/%Y %H:%M:%S")
    encabezado = tuple(c.strip().upper() for c in (lineas[1] if len(lineas) > 1 else "").split(";"))
    if encabezado != ENCABEZADO:
        raise ErrorDeCarga(f"{prefijo}línea 2: el encabezado no es el esperado ({';'.join(ENCABEZADO)}).")

    filas = 0
    pie = None
    for numero, linea in enumerate(lineas[2:], start=3):
        if not linea.strip():
            continue
        pie = _PIE_TRX.search(linea)
        if pie:
            break
        donde = f"{prefijo}línea {numero}"
        p = linea.split(";")
        if len(p) != len(ENCABEZADO):
            raise ErrorDeCarga(f"{donde}: se esperan {len(ENCABEZADO)} columnas y vienen {len(p)}.")
        p = [v.strip() for v in p]
        unidad = _UNIDAD.match(p[0])
        if not unidad or int(unidad.group(1)) != UNIDAD:
            raise ErrorDeCarga(f"{donde}: la entidad '{p[0]}' no es de la unidad {UNIDAD}.")
        sitio = p[1]
        zona_paga = sitio.upper().startswith("RM-")
        fh = _fecha_hora(p[2], f"{donde}, columna Fecha")
        filas += 1
        yield (
            archivo, numero, generacion,
            p[0], sitio, None if zona_paga else sitio.replace("-", "").upper(), int(zona_paga),
            fh, fh.date(), fh.year * 100 + fh.month,
            _entero(p[3], f"{donde}, columna Chip"), _entero(p[4], f"{donde}, columna Tarjeta"),
            _entero(p[5], f"{donde}, columna NTT"), p[6] or None, p[7] or None,
            _entero(p[8], f"{donde}, columna Monto"), p[9] or None,
            p[10] or None, _fecha_liquidacion(p[10]), p[11] or None,
            *(_entero(v, f"{donde}, columna {c}") for v, c in zip(p[12:], ENCABEZADO[12:])),
        )
    if pie is None:
        raise ErrorDeCarga(f"{prefijo}falta el pie 'Cantidad TRX' (¿el archivo está cortado?).")
    esperadas = int(pie.group(1))
    if filas != esperadas:
        raise ErrorDeCarga(f"{prefijo}el pie dice Cantidad TRX {esperadas} pero el archivo trae {filas} filas.")


def leer(contenido: bytes) -> Iterator[tuple]:
    for nombre, texto in _textos(contenido):
        yield from _leer_txt(nombre, texto)
