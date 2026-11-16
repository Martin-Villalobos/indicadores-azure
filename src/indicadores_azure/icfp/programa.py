"""Exigencia por hora desde el Anexo 3 (adaptado de indicadores-bi ``programacion/periodos.py``).

El Anexo 3 trae una fila por media hora (MH). El periodo del cálculo es la hora: se suman las
salidas y plazas de sus dos MH, igual que indicadores-bi y que los periodos del DTPM. Los km
programados del periodo son Σ distancia base · salidas de cada MH (5.3.1.6.2: kmp = L · Σ ep).
"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

from .normalizar import codigo, hora, sentido, texto, tipo_dia, unidad


def construir_programa(filas: Iterable[dict]) -> dict[tuple, dict]:
    """filas de raw_anexo3 -> {(unidad, codigo_ts, sentido, tipo_dia, hora): exigencia}.

    Una hora con una sola MH o una MH repetida falla: no se inventa programación.
    """

    grupos: dict[tuple, dict[int, dict]] = {}
    for f in filas:
        mh = hora(f["mh"])
        if mh.minute not in (0, 30) or mh.second:
            raise ValueError(f"MH fuera de la grilla de 30 minutos en raw_anexo3 {f['id']}: {mh}.")
        salidas, plazas = f["numero_salidas"], f["capacidad_plazas"]
        if any(v is None or int(v) != v or v < 0 for v in (salidas, plazas)):
            raise ValueError(f"Salidas/plazas inválidas en raw_anexo3 {f['id']}.")
        clave = (unidad(f["unidad_de_servicio"]), codigo(f["codigo_ts_servicio"]), sentido(f["sentido"]),
                 tipo_dia(f["tipo_dia"]), mh.hour)
        if not clave[1]:
            raise ValueError(f"Código TS vacío en raw_anexo3 {f['id']}.")
        grupo = grupos.setdefault(clave, {})
        if mh.minute in grupo:
            raise ValueError(f"Media hora duplicada: {clave}, MH={mh}.")
        grupo[mh.minute] = f

    programa = {}
    for clave, grupo in sorted(grupos.items()):
        if set(grupo) != {0, 30}:
            raise ValueError(f"Periodo incompleto (faltan una de las dos MH): {clave}.")
        mhs = [grupo[0], grupo[30]]
        km = sum((Decimal(str(m["distancia_base_km"] or 0)) * int(m["numero_salidas"]) for m in mhs), Decimal(0))
        programa[clave] = {
            "salidas_programadas": sum(int(m["numero_salidas"]) for m in mhs),
            "plazas_programadas": sum(int(m["capacidad_plazas"]) for m in mhs),
            "km_programados": km,
            "codigo_usuario": texto(mhs[0]["codigo_usuario_servicio"]) or None,
        }
    return programa
