"""Anexo 3 del PO o de un programa especial: parámetros de operación por media hora.

Formato esperado: un libro con una sola hoja de parámetros (las demás, como "Reconocimiento KM",
se ignoran). Antes de los encabezados vienen filas de cabecera con la etiqueta en la columna A y
el valor en la primera celda con dato a su derecha:
    UNIDAD DE SERVICIO | AÑO | FECHA INICIO | FECHA TÉRMINO
La fila de encabezados trae todas las columnas de ``ENCABEZADOS``; luego, una fila por servicio,
sentido, tipo de día y media hora (MH). Las filas sin operación (salidas 0, "--") se conservan.

La vigencia del archivo es FECHA INICIO..FECHA TÉRMINO de la cabecera.
"""

from __future__ import annotations

from collections.abc import Iterator

from ..control import ErrorDeCarga
from ._comun import abrir_excel, clave, decimal, entero, fecha, hora, texto

TABLA = "raw_anexo3"
EXTENSIONES = {".xlsx"}

ENCABEZADOS = {
    "UNIDAD DE SERVICIO": "unidad_de_servicio",
    "CODIGO TS SERVICIO": "codigo_ts_servicio",
    "CODIGO USUARIO SERVICIO": "codigo_usuario_servicio",
    "SENTIDO": "sentido",
    "TIPO DIA": "tipo_dia",
    "MH": "mh",
    "VELOCIDAD (KM/HRA)": "velocidad_km_hora",
    "DISTANCIA BASE (KM)": "distancia_base_km",
    "DISTANCIA TOTAL (POB+POI) (KM)": "distancia_total_km",
    "N° SALIDAS": "numero_salidas",
    "CAPACIDAD (PLAZAS)": "capacidad_plazas",
    "AGRUPACION MH": "agrupacion_mh",
    "FAMILIA DE SERVICIOS": "familia_servicios",
    "INDICADOR TIEMPO DE ESPERA": "indicador_tiempo_espera",
}
COLUMNAS = ("numero_fila", "hoja", "anio", "fecha_inicio", "fecha_termino", *ENCABEZADOS.values())
VIGENCIA = ("fecha_inicio", "fecha_termino")

_TEXTO = {"unidad_de_servicio", "codigo_ts_servicio", "codigo_usuario_servicio", "sentido", "tipo_dia",
          "agrupacion_mh", "familia_servicios", "indicador_tiempo_espera"}
_OBLIGATORIOS = {"unidad_de_servicio", "codigo_ts_servicio", "codigo_usuario_servicio", "sentido", "tipo_dia"}
_DECIMALES = {"velocidad_km_hora", "distancia_base_km", "distancia_total_km"}
_ENTEROS = {"numero_salidas", "capacidad_plazas"}


def _hoja_parametros(libro):
    """Devuelve (hoja, fila de encabezados, índices) de la única hoja con todos los encabezados."""

    candidatas = []
    for hoja in libro.worksheets:
        for numero, fila in enumerate(hoja.iter_rows(max_row=40, values_only=True), start=1):
            claves = [clave(v) for v in fila]
            if set(ENCABEZADOS) <= set(claves):
                candidatas.append((hoja, numero, {c: claves.index(c) for c in ENCABEZADOS}))
                break
    if len(candidatas) != 1:
        raise ErrorDeCarga(
            "No se encontró la hoja de parámetros del Anexo 3 (o hay más de una). Debe tener las columnas: "
            + ", ".join(ENCABEZADOS) + "."
        )
    return candidatas[0]


def leer(contenido: bytes) -> Iterator[tuple]:
    libro = abrir_excel(contenido)
    try:
        hoja, fila_encabezados, indices = _hoja_parametros(libro)
        cabecera: dict[str, object] = {}
        inicio = termino = anio = None
        for numero, fila in enumerate(hoja.iter_rows(values_only=True), start=1):
            valores = list(fila)
            if numero < fila_encabezados:
                if valores and clave(valores[0]):
                    cabecera[clave(valores[0])] = next((v for v in valores[1:] if v not in (None, "")), None)
                continue
            if numero == fila_encabezados:
                inicio = fecha(cabecera.get("FECHA INICIO"), "Cabecera FECHA INICIO")
                termino = fecha(cabecera.get("FECHA TERMINO"), "Cabecera FECHA TÉRMINO")
                if inicio is None or termino is None:
                    raise ErrorDeCarga("La cabecera del Anexo 3 debe traer FECHA INICIO y FECHA TÉRMINO.")
                if termino < inicio:
                    raise ErrorDeCarga("La FECHA TÉRMINO del Anexo 3 es anterior a la FECHA INICIO.")
                anio = entero(cabecera.get("ANO"), "Cabecera AÑO")
                continue
            if not any(v not in (None, "") for v in valores):
                continue

            donde = f"Hoja '{hoja.title}', fila {numero}"
            datos = []
            for encabezado, campo in ENCABEZADOS.items():
                i = indices[encabezado]
                valor = valores[i] if i < len(valores) else None
                lugar = f"{donde}, columna {encabezado}"
                if campo == "mh":
                    mh = hora(valor, lugar)
                    if mh is None or mh.minute not in (0, 30) or mh.second:
                        raise ErrorDeCarga(f"{lugar}: '{valor}' no es una media hora (HH:00 o HH:30).")
                    datos.append(mh)
                elif campo in _ENTEROS:
                    n = entero(valor, lugar)
                    if n is None:
                        raise ErrorDeCarga(f"{lugar}: falta el valor.")
                    datos.append(n)
                elif campo in _DECIMALES:
                    datos.append(decimal(valor, lugar))
                else:
                    t = texto(valor)
                    if t is None and campo in _OBLIGATORIOS:
                        raise ErrorDeCarga(f"{lugar}: falta el valor.")
                    datos.append(t)
            yield (numero, hoja.title, anio, inicio, termino, *datos)
    finally:
        libro.close()
