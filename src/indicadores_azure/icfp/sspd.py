"""Filas finales del ICFP por servicio-sentido-hora-día: km programados, km válidos y exclusiones.

kmp = Σ L · ep (5.3.1.6.2); kmv = min(1, ICF·FEO·FT, ICP·FEO·FT) · kmp (5.3.1.6.3).
FEO y FT valen 1 hasta que se carguen. Estados:
  OK             exigencia y plazas conocidas
  SIN_EXIGENCIA  ep = 0 (kmp = 0)
  SIN_PROGRAMA   hubo expediciones en una hora sin programa (kmp = 0)
  SIN_CAPACIDAD  alguna expedición sin plazas en la flota: kmv queda NULL y no se mide
  EXCLUIDO       la hoja ICFP-IE del DTPM excluye el servicio-sentido-hora: cuenta en el kmp
                 total (km con derecho a pago) pero no en el ICFP
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from .normalizar import codigo, sentido

UNO = Decimal(1)
KM = Decimal("0.001")
RATIO = Decimal("0.000001")


def hora_dtpm(periodo: str) -> int | None:
    """Periodo DTPM 1-72 (1-24 laboral, 25-48 sábado, 49-72 domingo) -> hora; '*' -> None (todas)."""
    if periodo in (None, "", "*"):
        return None
    return (int(periodo) - 1) % 24


def exclusiones_del_dia(filas) -> set[tuple]:
    """(codigo_ts, sentido, periodo) de la hoja ICFP-IE -> {(codigo|'*', sentido|'*', hora|None)}."""
    resultado = set()
    for cod, sen, periodo in filas:
        c = "*" if str(cod).strip() == "*" else codigo(cod)
        s = "*" if str(sen).strip() == "*" else sentido(sen)
        resultado.add((c, s, hora_dtpm(periodo)))
    return resultado


def esta_excluido(excl: set[tuple], cod: str, sen: str, h: int) -> bool:
    return any(c in ("*", cod) and s in ("*", sen) and hh in (None, h) for c, s, hh in excl)


def _km(valor: Decimal | None) -> Decimal | None:
    return None if valor is None else valor.quantize(KM, ROUND_HALF_UP)


def _r(valor: Decimal | None) -> Decimal | None:
    return None if valor is None else valor.quantize(RATIO, ROUND_HALF_UP)


def km_validos(p: dict, kmp: Decimal, feo=UNO, ft=UNO) -> Decimal | None:
    ep = p["expediciones_programadas"]
    if not ep:
        return Decimal(0)
    icf, icp = p["icf"], p["icp"]
    if icf is None:
        return None
    if p["plazas_programadas"] and icp is None:  # faltan plazas: no se puede medir
        return None
    factores = [icf * feo * ft] + ([icp * feo * ft] if icp is not None else [])
    return min(UNO, *factores) * kmp


def armar(estados: dict, iniciales: dict, desde: date, hasta: date,
          exclusiones: dict[date, set], terminales: dict[str, str]) -> list[dict]:
    """estados/iniciales: salida de correcciones.corregir y el mismo cálculo antes de corregir."""

    filas = []
    for k, p in sorted(estados.items(), key=lambda x: (x[0][-1], x[0][:-1])):
        momento: datetime = k[-1]
        fecha = momento.date()
        if not desde <= fecha <= hasta:
            continue
        ini = iniciales[k]
        kmp = p["km_programados"] if p["tiene_programa"] else Decimal(0)
        kmv, kmv_ini = km_validos(p, kmp), km_validos(ini, kmp)
        excluido = esta_excluido(exclusiones.get(fecha, set()), p["servicio"], p["sentido"], momento.hour)
        if excluido:
            estado = "EXCLUIDO"
        elif not p["tiene_programa"]:
            estado = "SIN_PROGRAMA"
        elif not p["expediciones_programadas"]:
            estado = "SIN_EXIGENCIA"
        elif kmv is None:
            estado = "SIN_CAPACIDAD"
        else:
            estado = "OK"
        filas.append({
            "fecha": fecha, "codigo_ts": p["servicio"], "sentido": p["sentido"], "periodo": momento.hour,
            "mes": fecha.replace(day=1), "tipo_dia": p["tipo_dia"], "codigo_usuario": p["codigo_usuario"],
            "terminal": terminales.get((p["codigo_usuario"] or "").casefold()),
            "ep": p["expediciones_programadas"], "ev": p["expediciones_validas"],
            "pl_prog": p["plazas_programadas"], "pl_val": p["plazas_validas"],
            "icf": _r(p["icf"]), "icp": _r(p["icp"]), "feo": UNO, "ft": UNO,
            "km_programados": _km(kmp), "km_validos": _km(kmv),
            "ev_inicial": ini["expediciones_validas"], "pl_val_inicial": ini["plazas_validas"],
            "icf_inicial": _r(ini["icf"]), "icp_inicial": _r(ini["icp"]), "km_validos_inicial": _km(kmv_ini),
            "expediciones_recibidas": p["expediciones_recibidas"], "expediciones_cedidas": p["expediciones_cedidas"],
            "excluido": int(excluido), "estado": estado,
        })
    return filas


def iniciales_con_ratios(periodos: list[dict]) -> dict:
    """Los periodos de inicial.construir con icf/icp, indexados como en corregir (antes de mover nada)."""
    from .correcciones import clave

    resultado = {}
    for p in periodos:
        q = dict(p)
        ep, pp = q["expediciones_programadas"], q["plazas_programadas"]
        q["icf"] = min(UNO, Decimal(q["expediciones_validas"]) / ep) if ep else None
        q["icp"] = min(UNO, Decimal(q["plazas_validas"]) / pp) if pp and q["plazas_validas"] is not None else None
        resultado[clave(q)] = q
    return resultado


