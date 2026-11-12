"""Exclusiones mensuales del DTPM por eventos exógenos (libro con hojas ICFP-IE, IP-Base e IP-Extra).

Sólo se guardan las filas de la U16. Cada hoja se guarda con su nombre en la columna ``hoja``;
un ``*`` en periodo, id de expedición o correlativo significa "todos". El periodo de ICFP-IE
numera las horas por tipo de día (1-24 laboral, 25-48 sábado, 49-72 domingo o festivo).

La vigencia son los meses completos que cubren las fechas del archivo, para que un archivo
corregido del mismo mes reemplace al anterior aunque traiga menos días.
"""

from __future__ import annotations

from collections.abc import Iterator

from ..control import ErrorDeCarga
from ._comun import abrir_excel, clave, fecha, texto

TABLA = "raw_exclusiones"
EXTENSIONES = {".xlsx"}
UNIDAD = "U16"

# hoja -> encabezados que debe traer (además de FECHA, US, CODIGO TS, SENTIDO)
HOJAS = {
    "ICFP-IE": ("PERIODO",),
    "IP-BASE": ("ID EXPEDICION", "CORRELATIVO PARADERO"),
    "IP-EXTRA": (),
}
COMUNES = ("FECHA", "US", "CODIGO TS", "SENTIDO")
COLUMNAS = ("hoja", "numero_fila", "fecha", "unidad_servicios", "codigo_ts_servicio", "sentido",
            "periodo", "id_expedicion", "correlativo_paradero")
VIGENCIA = ("fecha", "fecha")
VIGENCIA_POR_MES = True


def _periodo(valor: object, donde: str) -> str | None:
    t = texto(valor)
    if t is None or t == "*":
        return t
    if not t.isdigit() or not 1 <= int(t) <= 72:
        raise ErrorDeCarga(f"{donde}: periodo '{valor}' no válido (1 a 72 o *).")
    return t


def leer(contenido: bytes) -> Iterator[tuple]:
    libro = abrir_excel(contenido)
    try:
        hojas = {clave(nombre): nombre for nombre in libro.sheetnames}
        presentes = [h for h in HOJAS if h in hojas]
        if not presentes:
            raise ErrorDeCarga("El libro no tiene ninguna de las hojas " + ", ".join(HOJAS) + ".")
        for clave_hoja in presentes:
            nombre = hojas[clave_hoja]
            filas = libro[nombre].iter_rows(values_only=True)
            encabezados = [clave(v) for v in next(filas, ())]
            requeridos = COMUNES + HOJAS[clave_hoja]
            faltan = [e for e in requeridos if e not in encabezados]
            if faltan:
                raise ErrorDeCarga(f"A la hoja '{nombre}' le faltan las columnas: " + ", ".join(faltan) + ".")
            i = {e: encabezados.index(e) for e in requeridos}

            for numero, fila in enumerate(filas, start=2):
                valores = list(fila) + [None] * len(encabezados)
                if not any(v not in (None, "") for v in fila):
                    continue
                donde = f"Hoja '{nombre}', fila {numero}"
                unidad = texto(valores[i["US"]])
                if clave(unidad) != UNIDAD:
                    continue
                dia = fecha(valores[i["FECHA"]], f"{donde}, columna FECHA")
                codigo = texto(valores[i["CODIGO TS"]])
                sentido = texto(valores[i["SENTIDO"]])
                if dia is None or codigo is None or sentido is None:
                    raise ErrorDeCarga(f"{donde}: faltan FECHA, CÓDIGO TS o SENTIDO.")
                yield (
                    nombre, numero, dia, unidad, codigo, sentido,
                    _periodo(valores[i["PERIODO"]], f"{donde}, columna PERIODO") if "PERIODO" in i else None,
                    texto(valores[i["ID EXPEDICION"]]) if "ID EXPEDICION" in i else None,
                    texto(valores[i["CORRELATIVO PARADERO"]]) if "CORRELATIVO PARADERO" in i else None,
                )
    finally:
        libro.close()
