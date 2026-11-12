"""Velocidades DTPM: archivo diario con una fila por expedición (hoja "velocidad").

Sólo se guardan las filas de la U16 (columna UN = U16 o 16). El archivo trae todas las
unidades, así que si no hay ninguna fila U16 se rechaza. La vigencia es el día del archivo
(columna FECHA); un archivo con más de una fecha se rechaza.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from ..control import ErrorDeCarga
from ._comun import abrir_excel, clave, decimal, entero, fecha, hora, texto

TABLA = "raw_velocidades"
EXTENSIONES = {".xlsx"}
HOJA = "velocidad"
UNIDAD = 16

# columna de la tabla -> (encabezado del archivo, conversor)
CAMPOS = {
    "un": ("UN", "texto"),
    "operador": ("OPERADOR", "texto"),
    "servicio": ("SERVICIO", "texto"),
    "patente": ("PATENTE", "texto"),
    "sentido": ("SENTIDO", "texto"),
    "inicio": ("INICIO", "hora"),
    "intervalo_salida": ("INTERVALO DE SALIDA", "hora"),
    "control": ("CONTROL", "hora"),
    "fin": ("FIN", "hora"),
    "distancia_m": ("DISTANCIA (M)", "decimal"),
    "tiempo": ("TIEMPO (HH:MM:SS)", "hora"),
    "velocidad_km_hr": ("VELOCIDAD (KM/HR)", "decimal"),
    "capacidad": ("CAPACIDAD (#)", "entero"),
    "estado": ("ESTADO", "texto"),
    "fecha": ("FECHA", "fecha"),
    "dia": ("DIA", "entero"),
    "tipo_dia": ("TIPO DIA", "texto"),
    "periodo": ("PERIODO", "texto"),
    "cada_5_minutos": ("CADA 5 MINUTOS", "hora"),
    "cada_media_hora": ("CADA MEDIA HORA", "hora"),
}
OBLIGATORIOS = ("UN", "SERVICIO", "SENTIDO", "INICIO", "ESTADO", "FECHA", "TIPO DIA")
COLUMNAS = ("numero_fila", *CAMPOS)
VIGENCIA = ("fecha", "fecha")

_CONVERSORES = {
    "texto": lambda v, _: texto(v),
    "hora": hora,
    "decimal": decimal,
    "entero": entero,
    "fecha": fecha,
}


def _es_u16(valor: object, donde: str) -> bool:
    t = clave(texto(valor)).replace(" ", "")
    if not re.fullmatch(r"U?\d+(?:\.0+)?", t):
        raise ErrorDeCarga(f"{donde}: unidad '{valor}' no válida.")
    return int(float(t.removeprefix("U"))) == UNIDAD


def leer(contenido: bytes) -> Iterator[tuple]:
    libro = abrir_excel(contenido)
    try:
        if HOJA not in libro.sheetnames:
            raise ErrorDeCarga(f"El archivo no tiene la hoja '{HOJA}'.")
        hoja = libro[HOJA]
        filas = hoja.iter_rows(values_only=True)
        encabezados = [clave(v) for v in next(filas, ())]
        faltan = [e for e in OBLIGATORIOS if e not in encabezados]
        if faltan:
            raise ErrorDeCarga(f"A la hoja '{HOJA}' le faltan las columnas: " + ", ".join(faltan) + ".")
        indices = {campo: encabezados.index(enc) for campo, (enc, _) in CAMPOS.items() if enc in encabezados}

        fecha_archivo = None
        filas_u16 = 0
        for numero, fila in enumerate(filas, start=2):
            valores = list(fila)
            if not any(v not in (None, "") for v in valores):
                continue
            donde = f"Hoja '{HOJA}', fila {numero}"
            if not _es_u16(valores[indices["un"]], donde):
                continue
            datos = []
            for campo, (encabezado, tipo) in CAMPOS.items():
                i = indices.get(campo)
                valor = valores[i] if i is not None and i < len(valores) else None
                datos.append(_CONVERSORES[tipo](valor, f"{donde}, columna {encabezado}"))
            dia = datos[list(CAMPOS).index("fecha")]
            if dia is None:
                raise ErrorDeCarga(f"{donde}: falta la FECHA.")
            if fecha_archivo is None:
                fecha_archivo = dia
            elif dia != fecha_archivo:
                raise ErrorDeCarga(f"{donde}: el archivo trae más de una fecha ({fecha_archivo} y {dia}).")
            filas_u16 += 1
            yield (numero, *datos)
        if not filas_u16:
            raise ErrorDeCarga(f"El archivo no tiene filas de la unidad {UNIDAD}.")
    finally:
        libro.close()
