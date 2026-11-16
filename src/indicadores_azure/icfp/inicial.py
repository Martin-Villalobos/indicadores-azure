"""ICF e ICP iniciales por hora, sin trasvasije (adaptado de indicadores-bi ``icf_icp/inicial.py``).

Una fila OK de velocidades es una expedición válida (1.1.22). Las plazas salen de la patente en
la flota, nunca de la capacidad del Excel; una patente sin flota o sin capacidad queda marcada y
deja el ICP en NULL, sin suponer plazas.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal

from .normalizar import codigo, es_u16, hora, normalizar, patente, sentido, texto, tipo_dia, unidad


def mapa_buses(filas) -> dict[str, tuple[str | None, int | None]]:
    """(ppu, tipo_bus, plazas) -> {ppu: (tipo_bus, plazas)}."""
    result = {}
    for ppu, tipo_bus, capacidad in filas:
        key = patente(ppu)
        if not key or key in result:
            raise ValueError(f"Patente vacía o duplicada en la flota: {ppu!r}")
        if capacidad is not None and (capacidad <= 0 or int(capacidad) != capacidad):
            raise ValueError(f"Capacidad inválida para {ppu}: {capacidad}")
        result[key] = (tipo_bus, int(capacidad) if capacidad is not None else None)
    return result


def construir(fecha: date, programa: dict[tuple, dict], velocidades: list[dict], buses: dict):
    """Devuelve (expediciones, periodos) de un día, con las claves que usa ``correcciones.corregir``.

    Clave: unidad/servicio/sentido/tipo de día/hora. No se deduplican viajes por patente y hora.
    """
    velocidades = [v for v in velocidades if es_u16(v.get("un"))]
    tipos = {}
    ids = set()
    for v in velocidades:
        if v["fecha"] != fecha:
            raise ValueError("Velocidades contiene otra fecha operacional.")
        if v["id"] in ids:
            raise ValueError("ID de velocidades duplicado.")
        ids.add(v["id"])
        un, tipo = unidad(v["un"]), tipo_dia(v["tipo_dia"])
        if un in tipos and tipos[un] != tipo:
            raise ValueError(f"Tipos de día contradictorios para la unidad {un}.")
        tipos[un] = tipo
    if not tipos:
        raise ValueError("Sin velocidades U16 no se infiere el tipo de día.")
    programas = {k: p for k, p in programa.items() if tipos.get(k[0]) == k[3]}
    if set(tipos) != {k[0] for k in programas}:
        raise ValueError(f"El Anexo 3 vigente no trae programación para tipo de día {', '.join(sorted(tipos.values()))}.")

    expediciones, grupos = [], defaultdict(list)
    for v in velocidades:
        if normalizar(v["estado"]) != "OK":
            continue
        salida = datetime.combine(fecha, hora(v["inicio"]))
        un = unidad(v["un"])
        key = (un, codigo(v["servicio"]), sentido(v["sentido"]), tipos[un], salida.hour)
        if not key[1]:
            raise ValueError(f"Servicio vacío en velocidades {v['id']}")
        ppu = patente(v["patente"])
        tipo_bus, plazas = buses.get(ppu, (None, None))
        estado = "OK" if plazas is not None else ("SIN_CAPACIDAD" if ppu in buses else "SIN_BUS")
        expediciones.append({
            "fact_expedicion_id": v["id"], "fecha": fecha, "periodo_original": salida.hour,
            "unidad_servicio": un, "servicio": key[1], "sentido": key[2], "tipo_dia": key[3],
            "fecha_hora_inicio": salida, "patente": texto(v["patente"]) or None, "tipo_bus": tipo_bus,
            "plazas": plazas, "estado_plazas": estado,
        })
        grupos[key].append(plazas)

    periodos = []
    for key in sorted(set(programas) | set(grupos)):
        p, capacidades = programas.get(key), grupos.get(key, [])
        faltantes = sum(c is None for c in capacidades)
        conocidas = sum(c for c in capacidades if c is not None)
        periodos.append({
            "fecha": fecha, "periodo": key[4], "unidad_servicio": key[0], "servicio": key[1],
            "sentido": key[2], "tipo_dia": key[3],
            "tiene_programa": p is not None,
            "expediciones_programadas": p["salidas_programadas"] if p else None,
            "plazas_programadas": p["plazas_programadas"] if p else None,
            "km_programados": p["km_programados"] if p else Decimal(0),
            "codigo_usuario": p["codigo_usuario"] if p else None,
            "expediciones_validas": len(capacidades),
            "plazas_validas": None if faltantes else conocidas,
            "plazas_conocidas": conocidas,
            "expediciones_sin_plazas": faltantes,
        })
    return expediciones, periodos
