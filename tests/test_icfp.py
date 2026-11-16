from datetime import date, time
from decimal import Decimal

import pytest

from indicadores_azure.icfp import correcciones, inicial, programa, sspd

D = date(2026, 2, 8)


def mh(h, m, salidas=1, plazas=90, km="20", ts="T503 00I", sen="Ida", tipo="Domingo", i=[0]):
    i[0] += 1
    return dict(id=i[0], unidad_de_servicio="16", codigo_ts_servicio=ts, codigo_usuario_servicio="503",
                sentido=sen, tipo_dia=tipo, mh=time(h, m), numero_salidas=salidas, capacidad_plazas=plazas,
                distancia_base_km=Decimal(km))


def vel(i, inicio, patente="AAAA11", estado="OK", servicio="T50300I"):
    return dict(id=i, un="U16", servicio=servicio, patente=patente, sentido="Ida", inicio=inicio,
                estado=estado, fecha=D, tipo_dia="Domingo")


def test_programa_suma_las_dos_mh_y_km():
    p = programa.construir_programa([mh(6, 0, 1, 90, "20"), mh(6, 30, 2, 180, "21")])
    assert p == {("16", "T50300I", "I", "DOMINGO", 6): {
        "salidas_programadas": 3, "plazas_programadas": 270, "km_programados": Decimal("62"), "codigo_usuario": "503"}}


def test_programa_con_una_sola_mh_falla():
    with pytest.raises(ValueError, match="incompleto"):
        programa.construir_programa([mh(6, 0)])


def test_inicial_cuenta_ok_y_plazas_de_flota():
    prog = programa.construir_programa([mh(6, 0), mh(6, 30)])  # ep 2, pp 180
    buses = inicial.mapa_buses([("AAAA-11", "B1", 90), ("BBBB22", "C1", None)])
    exp, per = inicial.construir(D, prog, [
        vel(1, time(6, 10)), vel(2, time(6, 40), estado="NOK"), vel(3, time(6, 50), patente="BBBB22"),
        vel(4, time(7, 5), patente="ZZZZ99")], buses)
    assert [e["estado_plazas"] for e in exp] == ["OK", "SIN_CAPACIDAD", "SIN_BUS"]
    seis, siete = per
    assert (seis["expediciones_validas"], seis["plazas_validas"], seis["plazas_conocidas"]) == (2, None, 90)
    assert siete["tiene_programa"] is False and siete["expediciones_validas"] == 1


def test_inicial_sin_programa_del_tipo_de_dia():
    prog = programa.construir_programa([mh(6, 0, tipo="Laboral"), mh(6, 30, tipo="Laboral")])
    with pytest.raises(ValueError, match="DOMINGO"):
        inicial.construir(D, prog, [vel(1, time(6, 10))], {})


def _calcular(prog, velocidades, buses, exclusiones=None):
    exp, per = inicial.construir(D, prog, velocidades, buses)
    estados, _, movs = correcciones.corregir(per, exp)
    filas = sspd.armar(estados, sspd.iniciales_con_ratios(per), D, D, {D: exclusiones or set()}, {"503": "Los Sauces"})
    return {f["periodo"]: f for f in filas}, movs


def test_icfp_con_trasvasije_y_km():
    # 6h exige 2, se hacen 1; 7h exige 1, se hacen 2 y una sale a las 7:02 -> pasa a las 6h
    prog = programa.construir_programa([mh(6, 0), mh(6, 30), mh(7, 0, 1), mh(7, 30, 0, 0)])
    buses = inicial.mapa_buses([("AAAA11", "B1", 90)])
    filas, movs = _calcular(prog, [vel(1, time(6, 10)), vel(2, time(7, 2)), vel(3, time(7, 40))], buses)
    assert len(movs) == 1
    seis, siete = filas[6], filas[7]
    assert (seis["ev_inicial"], seis["ev"], seis["icf_inicial"], seis["icf"]) == (1, 2, Decimal("0.5"), 1)
    assert seis["km_programados"] == Decimal("40.000") and seis["km_validos"] == Decimal("40.000")
    assert seis["km_validos_inicial"] == Decimal("20.000")
    assert siete["ev"] == 1 and siete["km_validos"] == Decimal("20.000")
    assert seis["terminal"] == "Los Sauces" and seis["estado"] == "OK"


def test_icp_limita_los_km_validos():
    prog = programa.construir_programa([mh(6, 0, 1, 150), mh(6, 30, 0, 0)])  # exige 150 plazas
    filas, _ = _calcular(prog, [vel(1, time(6, 10))], inicial.mapa_buses([("AAAA11", "B1", 90)]))
    f = filas[6]
    assert f["icf"] == 1 and f["icp"] == Decimal("0.6") and f["km_validos"] == Decimal("12.000")


def test_sin_capacidad_deja_kmv_nulo():
    prog = programa.construir_programa([mh(6, 0), mh(6, 30, 0, 0)])
    filas, _ = _calcular(prog, [vel(1, time(6, 10))], {})
    assert filas[6]["estado"] == "SIN_CAPACIDAD" and filas[6]["km_validos"] is None


def test_exclusion_dtpm_por_periodo_y_comodin():
    assert sspd.hora_dtpm("7") == 6 and sspd.hora_dtpm("55") == 6 and sspd.hora_dtpm("*") is None
    excl = sspd.exclusiones_del_dia([("T503 00I", "Ida", "55")])
    assert sspd.esta_excluido(excl, "T50300I", "I", 6) and not sspd.esta_excluido(excl, "T50300I", "I", 7)
    todo = sspd.exclusiones_del_dia([("*", "*", "*")])
    assert sspd.esta_excluido(todo, "X", "R", 3)

    prog = programa.construir_programa([mh(6, 0), mh(6, 30, 0, 0)])
    filas, _ = _calcular(prog, [vel(1, time(6, 10))], inicial.mapa_buses([("AAAA11", "B1", 90)]), excl)
    assert filas[6]["estado"] == "EXCLUIDO" and filas[6]["excluido"] == 1
    assert filas[6]["km_programados"] == Decimal("20.000")  # cuenta para km con derecho a pago


def test_sin_exigencia():
    prog = programa.construir_programa([mh(6, 0, 0, 0), mh(6, 30, 0, 0)])
    filas, _ = _calcular(prog, [vel(1, time(6, 10))], inicial.mapa_buses([("AAAA11", "B1", 90)]))
    assert filas[6]["estado"] == "SIN_EXIGENCIA" and filas[6]["km_validos"] == 0


def test_recalculos_que_se_tocan_se_juntan():
    from indicadores_azure.recalculo import _juntar

    d = lambda m, dd: date(2026, m, dd)
    assert _juntar([(1, d(2, 7), d(2, 9)), (2, d(2, 1), d(2, 28)), (3, d(3, 1), d(3, 2)), (4, d(5, 1), d(5, 1))]) == [
        ([2, 1, 3], d(2, 1), d(3, 2)), ([4], d(5, 1), d(5, 1))]
