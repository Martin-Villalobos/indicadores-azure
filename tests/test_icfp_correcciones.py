"""Pruebas de corregir() copiadas de indicadores-bi (tests/test_correcciones_icf_icp.py)."""

import copy
from datetime import datetime, timedelta

import pytest

from indicadores_azure.icfp import correcciones as m


def fixture(specs):
    periodos, expediciones = [], []
    for inicio, ep, pp, salidas in specs:
        known = sum(p or 0 for _, p in salidas)
        missing = sum(p is None for _, p in salidas)
        periodos.append(dict(fecha=inicio.date(), periodo=inicio.hour,
            unidad_servicio='16', servicio='1602', sentido='R', tipo_dia='SABADO',
            expediciones_programadas=ep, plazas_programadas=pp, expediciones_validas=len(salidas),
            plazas_validas=None if missing else known, plazas_conocidas=known,
            expediciones_sin_plazas=missing))
        for segundos, plazas in salidas:
            expediciones.append(dict(fact_expedicion_id=len(expediciones)+1,
                fecha=inicio.date(), periodo_original=inicio.hour,
                unidad_servicio='16', servicio='1602', sentido='R',
                fecha_hora_inicio=inicio+timedelta(seconds=segundos), plazas=plazas))
    return periodos, expediciones


H = datetime(2026, 5, 2, 5)


def run_case(specs):
    p, e = fixture(specs)
    original = copy.deepcopy((p, e))
    states, assignments, moves = m.corregir(p, e)
    assert (p, e) == original
    assert sum(x['expediciones_validas'] for x in states.values()) == len(e)
    assert sum(x['plazas_conocidas'] for x in states.values()) == sum(x['plazas'] or 0 for x in e)
    assert len(assignments) == len(e)
    for mv in moves:
        assert mv['pv_donante_antes'] - mv['plazas'] >= mv['pp_donante']
        assert mv['ev_donante_antes'] > mv['ep_donante']
        assert mv['ev_receptor_antes'] < mv['ep_receptor']
    return states, assignments, moves


def test_anterior():
    s, _, moves = run_case([(H, 1, 90, []), (H + timedelta(hours=1), 1, 90, [(60, 90), (1200, 90)])])
    assert [x['regla'] for x in moves] == ['PRIMERA_5_MIN']
    assert all(p['icf'] == 1 and p['icp'] == 1 for p in s.values())


def test_siguiente():
    _, _, moves = run_case([(H, 1, 90, [(1200, 90), (3540, 90)]), (H + timedelta(hours=1), 1, 90, [])])
    assert moves[0]['regla'] == 'ULTIMA_5_MIN'


def test_prioridad_anterior_y_revalida_exceso():
    _, _, moves = run_case([(H, 1, 90, []), (H + timedelta(hours=1), 1, 90, [(60, 90), (3540, 90)]),
                            (H + timedelta(hours=2), 1, 90, [])])
    assert [x['regla'] for x in moves] == ['PRIMERA_5_MIN']


def test_ambos_lados():
    _, _, moves = run_case([(H, 1, 90, []), (H + timedelta(hours=1), 1, 90, [(60, 90), (1200, 90), (3540, 90)]),
                            (H + timedelta(hours=2), 1, 90, [])])
    assert [x['regla'] for x in moves] == ['PRIMERA_5_MIN', 'ULTIMA_5_MIN']


def test_icp_donante_protege():
    _, _, moves = run_case([(H, 1, 90, []), (H + timedelta(hours=1), 1, 150, [(60, 90), (1200, 90)])])
    assert moves == []


def test_capacidad_desconocida():
    _, _, moves = run_case([(H, 1, 90, []), (H + timedelta(hours=1), 1, 90, [(60, 90), (1200, None)])])
    assert moves == []


@pytest.mark.parametrize("ep_donante, salidas_receptor", [(2, []), (1, [(1200, 90)])])
def test_no_dona_sin_exceso_o_sin_deficit(ep_donante, salidas_receptor):
    _, _, moves = run_case([(H, 1, 90, salidas_receptor), (H + timedelta(hours=1), ep_donante, 90, [(60, 90), (1200, 90)])])
    assert moves == []


@pytest.mark.parametrize("segundos, esperado", [(0, 1), (299, 1), (300, 0)])
def test_limite_ventana_anterior(segundos, esperado):
    _, _, moves = run_case([(H, 1, 90, []), (H + timedelta(hours=1), 1, 90, [(segundos, 90), (1200, 90)])])
    assert len(moves) == esperado


@pytest.mark.parametrize("segundos, esperado", [(3299, 0), (3300, 1), (3599, 1)])
def test_limite_ventana_siguiente(segundos, esperado):
    _, _, moves = run_case([(H, 1, 90, [(1200, 90), (segundos, 90)]), (H + timedelta(hours=1), 1, 90, [])])
    assert len(moves) == esperado


def test_maximo_uno_hacia_anterior():
    _, _, moves = run_case([(H, 4, 360, []), (H + timedelta(hours=1), 1, 90, [(0, 90), (60, 90), (120, 90), (180, 90)])])
    assert len(moves) == 1


def test_medianoche_anterior():
    inicio = datetime(2026, 5, 1, 23)
    _, assign, moves = run_case([(inicio, 1, 90, []), (inicio + timedelta(hours=1), 1, 90, [(60, 90), (1200, 90)])])
    assert assign[moves[0]['fact_expedicion_id']][-1] == inicio


def test_medianoche_siguiente():
    inicio = datetime(2026, 5, 2, 23)
    _, assign, moves = run_case([(inicio, 1, 90, [(1200, 90), (3599, 90)]), (inicio + timedelta(hours=1), 1, 90, [])])
    assert assign[moves[0]['fact_expedicion_id']][-1] == datetime(2026, 5, 3)


def test_no_cruza_servicios():
    p, e = fixture([(H, 1, 90, []), (H + timedelta(hours=1), 1, 90, [(60, 90), (1200, 90)])])
    p[0]['servicio'] = 'OTRO'
    assert m.corregir(p, e)[2] == []


def test_inconsistencia_falla():
    p, e = fixture([(H, 1, 90, [(60, 90)])])
    with pytest.raises(ValueError):
        m.corregir(p, [])
    with pytest.raises(ValueError):
        m.corregir(p + p, e)
