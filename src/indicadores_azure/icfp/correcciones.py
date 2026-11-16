"""Trasvasije de extremos de periodo (Contrato 5.3.1.6.6). Copiado de indicadores-bi
``icf_icp/correcciones.py`` (función ``corregir``, sin cambios de lógica).

Una expedición despachada en los primeros 5 minutos de una hora puede contarse en la hora
anterior, y una de los últimos 5 minutos en la siguiente, si el donante tiene más expediciones
que las programadas, conserva ICP >= 1 y el receptor tiene menos que las programadas.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, time, timedelta
from decimal import Decimal


def clave(f):
    return (f['unidad_servicio'], f['servicio'], f['sentido'],
            datetime.combine(f['fecha'], time(int(f['periodo']))))


def corregir(periodos, expediciones):
    """Primero anterior, luego siguiente, donantes en orden cronológico.

    Reparte sólo expediciones originales y nunca mueve una misma expedición
    dos veces. Los contadores se actualizan después de cada movimiento.
    El tipo de día lo determina el período destino (puede cambiar a medianoche).
    """
    estados, originales, asignaciones = {}, defaultdict(list), {}
    for row in periodos:
        k = clave(row)
        if k in estados:
            raise ValueError(f'Período inicial duplicado: {k}')
        estados[k] = dict(row, expediciones_recibidas=0, expediciones_cedidas=0,
                          plazas_recibidas=0, plazas_cedidas=0)
    for e in expediciones:
        eid = e['fact_expedicion_id']
        k = (e['unidad_servicio'], e['servicio'], e['sentido'],
             datetime.combine(e['fecha'], time(int(e['periodo_original']))))
        if eid in asignaciones or k not in estados:
            raise ValueError(f'Expedición duplicada o sin período inicial: {eid}')
        if e['fecha_hora_inicio'].replace(minute=0, second=0, microsecond=0) != k[-1]:
            raise ValueError(f'Fecha/hora original inconsistente: {eid}')
        originales[k].append(e)
        asignaciones[eid] = k
    # La reconstrucción debe coincidir con el snapshot antes de tocar contadores.
    for k, p in estados.items():
        lista = originales[k]
        faltantes = sum(e['plazas'] is None for e in lista)
        conocidas = sum(e['plazas'] or 0 for e in lista)
        if (len(lista), faltantes, conocidas) != (p['expediciones_validas'], p['expediciones_sin_plazas'], p['plazas_conocidas']):
            raise ValueError(f'Expediciones no reconcilian con el inicial: {k}')
        if p['plazas_validas'] != (None if faltantes else conocidas):
            raise ValueError(f'Plazas iniciales inconsistentes: {k}')
        lista.sort(key=lambda e: (e['fecha_hora_inicio'], e['fact_expedicion_id']))

    movimientos = []
    movidas = set()
    # Orden por fecha/hora y después unidad/servicio/sentido, reproducible.
    for k in sorted(estados, key=lambda x: (x[-1], x[:-1])):
        donante = estados[k]
        lista = originales[k]
        if not lista:
            continue
        for delta, candidato, regla in [(-1, lista[0], 'PRIMERA_5_MIN'), (1, lista[-1], 'ULTIMA_5_MIN')]:
            ep, pp = donante['expediciones_programadas'], donante['plazas_programadas']
            if ep is None or donante['expediciones_validas'] <= ep:
                continue
            destino = (*k[:-1], k[-1] + timedelta(hours=delta))
            receptor = estados.get(destino)
            if receptor is None or receptor['expediciones_programadas'] is None or receptor['expediciones_programadas'] <= 0:
                continue
            if receptor['expediciones_validas'] >= receptor['expediciones_programadas']:
                continue
            eid = candidato['fact_expedicion_id']
            segundos = (candidato['fecha_hora_inicio'] - k[-1]).total_seconds()
            ventana = 0 <= segundos < 300 if delta == -1 else 3300 <= segundos < 3600
            plazas = candidato['plazas']
            if not ventana or eid in movidas or plazas is None:
                continue
            # Sin capacidad/exigencia positiva no podemos acreditar ICP >= 1.
            pv = donante['plazas_validas']
            if pp is None or pp <= 0 or pv is None or pv - plazas < pp:
                continue
            movimientos.append(dict(
                fact_expedicion_id=eid, origen=k, destino=destino, regla=regla,
                plazas=plazas, ev_donante_antes=donante['expediciones_validas'],
                ep_donante=ep, pv_donante_antes=pv, pp_donante=pp,
                ev_receptor_antes=receptor['expediciones_validas'],
                ep_receptor=receptor['expediciones_programadas'],
            ))
            donante['expediciones_validas'] -= 1
            donante['plazas_validas'] -= plazas
            donante['plazas_conocidas'] -= plazas
            donante['expediciones_cedidas'] += 1
            donante['plazas_cedidas'] += plazas
            receptor['expediciones_validas'] += 1
            receptor['plazas_conocidas'] += plazas
            if receptor['plazas_validas'] is not None:
                receptor['plazas_validas'] += plazas
            receptor['expediciones_recibidas'] += 1
            receptor['plazas_recibidas'] += plazas
            asignaciones[eid] = destino
            movidas.add(eid)
    for p in estados.values():
        ep, pp = p['expediciones_programadas'], p['plazas_programadas']
        p['ratio_frecuencia'] = Decimal(p['expediciones_validas']) / ep if ep else None
        p['ratio_plazas'] = Decimal(p['plazas_validas']) / pp if pp and p['plazas_validas'] is not None else None
        p['icf'] = min(Decimal(1), p['ratio_frecuencia']) if p['ratio_frecuencia'] is not None else None
        p['icp'] = min(Decimal(1), p['ratio_plazas']) if p['ratio_plazas'] is not None else None
    return estados, asignaciones, movimientos
