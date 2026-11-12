from datetime import date

import pytest

from indicadores_azure.vigencias import Fragmento, planificar, rango_mes


def D(m, d):
    return date(2026, m, d)


def frag(i, carga, ini, fin, desde=None, hasta=None):
    return Fragmento(i, carga, ini, fin, desde or ini, hasta or fin)


def tramos(plan):
    return sorted((f.carga_id, f.fecha_inicio, f.fecha_termino) for f in plan.reinsertar + plan.nuevos)


def test_primera_carga_rige_todo_su_rango():
    plan = planificar(1, D(7, 1), D(11, 30), [])
    assert tramos(plan) == [(1, D(7, 1), D(11, 30))] and plan.reemplazados == []


def test_anexo_corto_dentro_de_uno_largo_parte_el_largo_en_dos():
    largo = frag(10, 1, D(7, 1), D(11, 30))
    plan = planificar(2, D(9, 18), D(9, 19), [largo])
    assert plan.reemplazados == [largo]
    assert tramos(plan) == [(1, D(7, 1), D(9, 17)), (1, D(9, 20), D(11, 30)), (2, D(9, 18), D(9, 19))]
    assert all(f.rango_desde == D(7, 1) and f.rango_hasta == D(11, 30) for f in plan.reinsertar)
    assert plan.rangos_cambiados == [(D(9, 18), D(9, 19))]


def test_anexo_largo_despues_de_uno_corto_no_le_quita_sus_dias():
    corto = frag(10, 1, D(9, 18), D(9, 19))
    plan = planificar(2, D(7, 1), D(11, 30), [corto])
    assert plan.reemplazados == []
    assert tramos(plan) == [(2, D(7, 1), D(9, 17)), (2, D(9, 20), D(11, 30))]


def test_mismo_largo_gana_el_ultimo():
    antes = frag(10, 1, D(7, 1), D(11, 30))
    plan = planificar(2, D(7, 1), D(11, 30), [antes])
    assert plan.reemplazados == [antes] and tramos(plan) == [(2, D(7, 1), D(11, 30))]


def test_cruce_parcial_gana_el_mas_corto():
    largo = frag(10, 1, D(1, 1), D(6, 30))
    plan = planificar(2, D(6, 1), D(8, 31), [largo])  # 3 meses contra 6
    assert tramos(plan) == [(1, D(1, 1), D(5, 31)), (2, D(6, 1), D(8, 31))]


def test_solo_compara_con_lo_vigente():
    # julio-noviembre partido por un especial 18-19 sept; llega otro julio-noviembre corregido
    vigentes = [
        frag(10, 1, D(7, 1), D(9, 17), D(7, 1), D(11, 30)),
        frag(11, 2, D(9, 18), D(9, 19)),
        frag(12, 1, D(9, 20), D(11, 30), D(7, 1), D(11, 30)),
    ]
    plan = planificar(3, D(7, 1), D(11, 30), vigentes)
    assert [f.vigencia_id for f in plan.reemplazados] == [10, 12]
    assert tramos(plan) == [(3, D(7, 1), D(9, 17)), (3, D(9, 20), D(11, 30))]


def test_rango_invertido():
    with pytest.raises(ValueError):
        planificar(1, D(2, 1), D(1, 1), [])


def test_rango_mes():
    assert rango_mes(D(2, 3), D(2, 27)) == (D(2, 1), D(2, 28))
    assert rango_mes(D(11, 5), date(2026, 12, 3)) == (D(11, 1), date(2026, 12, 31))
