"""Qué carga de cada tipo de archivo rige cada fecha (tabla ``vigencia_archivo``).

Regla: para cada fecha manda la carga cuyo rango completo es más corto; si empatan, la
última cargada. No hay anexos "generales" ni "especiales": un anexo de julio a noviembre
y otro del 18 al 19 de septiembre son iguales, sólo que el segundo es más corto, así que
esos dos días los rige el segundo y el resto el primero.

``vigencia_archivo`` guarda fragmentos: tramos de fechas consecutivas regidos por una
carga. Cuando una carga nueva le gana a un fragmento, ese fragmento queda con vigente=0
(no se borra, para poder auditar y recalcular) y sus partes fuera del rango nuevo se
vuelven a insertar como fragmentos vigentes de la misma carga.

Basta comparar la carga nueva con los fragmentos vigentes que se cruzan con su rango:
lo que la carga nueva no le gana a la vigente actual, tampoco se lo gana a las que esa
ya había reemplazado.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

UN_DIA = timedelta(days=1)


@dataclass(frozen=True)
class Fragmento:
    vigencia_id: int | None
    carga_id: int
    fecha_inicio: date
    fecha_termino: date
    rango_desde: date
    rango_hasta: date
    origen: str = "CARGA"

    @property
    def largo(self) -> int:
        return (self.rango_hasta - self.rango_desde).days


@dataclass(frozen=True)
class Plan:
    reemplazados: list[Fragmento]  # pasan a vigente=0
    reinsertar: list[Fragmento]  # partes de los reemplazados que siguen vigentes
    nuevos: list[Fragmento]  # fragmentos de la carga nueva

    @property
    def rangos_cambiados(self) -> list[tuple[date, date]]:
        """Fechas que cambian de carga: hay que recalcular los indicadores que usan este tipo."""
        return [(f.fecha_inicio, f.fecha_termino) for f in self.nuevos]


def _restar(desde: date, hasta: date, tramos: list[tuple[date, date]]) -> list[tuple[date, date]]:
    """[desde, hasta] menos los tramos (todos cerrados)."""

    resultado = []
    actual = desde
    for inicio, termino in sorted(tramos):
        if termino < actual or inicio > hasta:
            continue
        if inicio > actual:
            resultado.append((actual, inicio - UN_DIA))
        actual = max(actual, termino + UN_DIA)
    if actual <= hasta:
        resultado.append((actual, hasta))
    return resultado


def planificar(carga_id: int, desde: date, hasta: date, vigentes: list[Fragmento]) -> Plan:
    """Calcula los cambios sin tocar la base. ``vigentes`` son los fragmentos que se cruzan con el rango."""

    if hasta < desde:
        raise ValueError("El rango de vigencia termina antes de empezar.")
    largo = (hasta - desde).days
    reemplazados, reinsertar, se_mantienen = [], [], []
    for f in vigentes:
        if f.fecha_termino < desde or f.fecha_inicio > hasta:
            continue
        if f.largo < largo:  # el otro es más corto: conserva sus fechas
            se_mantienen.append((f.fecha_inicio, f.fecha_termino))
            continue
        reemplazados.append(f)
        for inicio, termino in _restar(f.fecha_inicio, f.fecha_termino, [(desde, hasta)]):
            reinsertar.append(Fragmento(None, f.carga_id, inicio, termino, f.rango_desde, f.rango_hasta, f.origen))
    nuevos = [Fragmento(None, carga_id, i, t, desde, hasta) for i, t in _restar(desde, hasta, se_mantienen)]
    return Plan(reemplazados, reinsertar, nuevos)


def registrar_vigencia(cur, *, tipo: str, carga_id: int, desde: date, hasta: date, usuario: str) -> Plan:
    """Aplica la regla dentro de la transacción de la carga (si la carga falla, se revierte)."""

    cur.execute(
        """SELECT vigencia_id, carga_id, fecha_inicio, fecha_termino, rango_desde, rango_hasta, origen
           FROM vigencia_archivo WHERE tipo_archivo = %s AND vigente = 1
           AND fecha_inicio <= %s AND fecha_termino >= %s ORDER BY fecha_inicio FOR UPDATE""",
        (tipo, hasta, desde),
    )
    vigentes = [Fragmento(int(r[0]), int(r[1]), *r[2:]) for r in cur.fetchall()]
    if any(f.carga_id == carga_id for f in vigentes):
        return Plan([], [], [])  # ya registrada

    plan = planificar(carga_id, desde, hasta, vigentes)
    ahora = datetime.now()
    if plan.reemplazados:
        ids = [f.vigencia_id for f in plan.reemplazados]
        cur.execute(
            "UPDATE vigencia_archivo SET vigente = 0, reemplazada_por = %s, reemplazado_at = %s "
            f"WHERE vigencia_id IN ({', '.join(['%s'] * len(ids))})",
            (carga_id, ahora, *ids),
        )
    filas = [
        (tipo, f.carga_id, f.fecha_inicio, f.fecha_termino, f.rango_desde, f.rango_hasta, f.origen, usuario, ahora)
        for f in plan.reinsertar + plan.nuevos
    ]
    if filas:
        cur.executemany(
            """INSERT INTO vigencia_archivo (tipo_archivo, carga_id, fecha_inicio, fecha_termino,
               rango_desde, rango_hasta, origen, creado_por, creado_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            filas,
        )
    return plan


def rango_mes(desde: date, hasta: date) -> tuple[date, date]:
    """Extiende un rango a meses completos."""

    siguiente = (hasta.replace(day=28) + timedelta(days=4)).replace(day=1)
    return desde.replace(day=1), siguiente - UN_DIA
