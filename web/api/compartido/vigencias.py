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

Desde la web se puede eliminar una carga o cambiarle las fechas (``eliminar_carga`` y
``cambiar_fechas``). Ahí no basta la comparación incremental: ``reconstruir`` vuelve a decidir,
día por día, qué carga gana entre todas las COMPLETADO del tipo (con el rango de
control_carga.vigencia_desde..vigencia_hasta), con la misma regla. Las dos funciones tienen modo
simulación para mostrar en la web qué va a cambiar antes de confirmar.

Este archivo se copia tal cual en web/api/compartido/vigencias.py (la web no instala el paquete);
un test verifica que las dos copias sean iguales.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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

    cur.execute(
        "UPDATE control_carga SET vigencia_desde = %s, vigencia_hasta = %s WHERE carga_id = %s",
        (desde, hasta, carga_id),
    )
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


# ----------------------------------------------------------------------------------------------
# Eliminar una carga o cambiarle las fechas (desde la web)
# ----------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Candidato:
    carga_id: int
    desde: date
    hasta: date
    orden: tuple  # (fecha de carga o de la última modificación, carga_id): a igual largo gana el mayor

    @property
    def largo(self) -> int:
        return (self.hasta - self.desde).days


@dataclass(frozen=True)
class Cambio:
    """Tramo de fechas que pasa de la carga ``antes`` a la carga ``despues`` (None = ninguna)."""

    desde: date
    hasta: date
    antes: int | None
    despues: int | None


@dataclass
class Resultado:
    tipo: str | None = None
    cambios: list[Cambio] = field(default_factory=list)
    errores: list[str] = field(default_factory=list)
    advertencias: list[str] = field(default_factory=list)
    recalculos: list[tuple[str, date, date]] = field(default_factory=list)  # (indicador, desde, hasta)


def asignar(candidatos: list[Candidato], desde: date, hasta: date) -> dict[date, int]:
    """Qué carga rige cada día de [desde, hasta]: la de rango más corto; si empatan, la más nueva."""

    ordenados = sorted(candidatos, key=lambda c: c.orden, reverse=True)
    ordenados.sort(key=lambda c: c.largo)  # estable: a igual largo queda primero la más nueva
    dias: dict[date, int] = {}
    for c in ordenados:
        d = max(c.desde, desde)
        while d <= min(c.hasta, hasta):
            dias.setdefault(d, c.carga_id)
            d += UN_DIA
    return dias


def comparar(antes: dict[date, int], despues: dict[date, int], desde: date, hasta: date) -> list[Cambio]:
    """Tramos consecutivos de días que cambian de carga."""

    cambios: list[Cambio] = []
    d = desde
    while d <= hasta:
        a, b = antes.get(d), despues.get(d)
        if a != b:
            ultimo = cambios[-1] if cambios else None
            if ultimo and ultimo.hasta == d - UN_DIA and (ultimo.antes, ultimo.despues) == (a, b):
                cambios[-1] = Cambio(ultimo.desde, d, a, b)
            else:
                cambios.append(Cambio(d, d, a, b))
        d += UN_DIA
    return cambios


def _tramos(dias: dict[date, int]) -> list[tuple[date, date, int]]:
    tramos: list[tuple[date, date, int]] = []
    for d in sorted(dias):
        if tramos and tramos[-1][1] == d - UN_DIA and tramos[-1][2] == dias[d]:
            tramos[-1] = (tramos[-1][0], d, dias[d])
        else:
            tramos.append((d, d, dias[d]))
    return tramos


def _vigentes(cur, tipo: str, desde: date, hasta: date, bloquear: bool) -> list[Fragmento]:
    cur.execute(
        """SELECT vigencia_id, carga_id, fecha_inicio, fecha_termino, rango_desde, rango_hasta, origen
           FROM vigencia_archivo WHERE tipo_archivo = %s AND vigente = 1
           AND fecha_inicio <= %s AND fecha_termino >= %s ORDER BY fecha_inicio""" + (" FOR UPDATE" if bloquear else ""),
        (tipo, hasta, desde),
    )
    return [Fragmento(int(r[0]), int(r[1]), *r[2:]) for r in cur.fetchall()]


def _candidatos(cur, tipo: str, desde: date, hasta: date) -> list[Candidato]:
    cur.execute(
        """SELECT carga_id, vigencia_desde, vigencia_hasta, COALESCE(modificado_at, fin_at, inicio_at)
           FROM control_carga WHERE tipo_archivo = %s AND estado = 'COMPLETADO'
           AND vigencia_desde IS NOT NULL AND vigencia_desde <= %s AND vigencia_hasta >= %s""",
        (tipo, hasta, desde),
    )
    return [Candidato(int(r[0]), r[1], r[2], (r[3], int(r[0]))) for r in cur.fetchall()]


def reconstruir(cur, tipo: str, desde: date, hasta: date, *, usuario: str, excluir: set[int] = frozenset(),
                rangos: dict[int, tuple[date, date]] | None = None, aplicar: bool = True) -> list[Cambio]:
    """Vuelve a decidir qué carga rige cada día de [desde, hasta] y devuelve lo que cambia.

    ``excluir``: cargas que dejan de contar (eliminadas). ``rangos``: cargas con fechas nuevas
    {carga_id: (desde, hasta)}; a igual largo le ganan a las demás (son el cambio más reciente).
    Con ``aplicar=False`` sólo calcula (para mostrar en la web antes de confirmar).
    """

    rangos = rangos or {}
    # También los fragmentos que tocan el rango por fuera: así se rehacen enteros y los tramos
    # consecutivos de una misma carga quedan en una sola fila.
    vigentes = _vigentes(cur, tipo, desde - UN_DIA, hasta + UN_DIA, bloquear=aplicar)
    if vigentes:
        desde = min(desde, min(f.fecha_inicio for f in vigentes))
        hasta = max(hasta, max(f.fecha_termino for f in vigentes))
    antes: dict[date, int] = {}
    for f in vigentes:
        d = max(f.fecha_inicio, desde)
        while d <= min(f.fecha_termino, hasta):
            antes[d] = f.carga_id
            d += UN_DIA

    ahora = datetime.now()
    candidatos = {c.carga_id: c for c in _candidatos(cur, tipo, desde, hasta) if c.carga_id not in excluir}
    for carga_id, (r_desde, r_hasta) in rangos.items():
        candidatos[carga_id] = Candidato(carga_id, r_desde, r_hasta, (ahora, carga_id))
    candidatos = {k: c for k, c in candidatos.items() if c.desde <= hasta and c.hasta >= desde}
    despues = asignar(list(candidatos.values()), desde, hasta)
    cambios = comparar(antes, despues, desde, hasta)
    if not aplicar or (not cambios and not rangos):
        return cambios

    if vigentes:
        ids = [f.vigencia_id for f in vigentes]
        cur.execute(
            "UPDATE vigencia_archivo SET vigente = 0, reemplazado_at = %s "
            f"WHERE vigencia_id IN ({', '.join(['%s'] * len(ids))})",
            (ahora, *ids),
        )
    origen_previo = {f.carga_id: f.origen for f in vigentes}
    filas = []
    for f in vigentes:  # lo que esos fragmentos rigen fuera de [desde, hasta] sigue igual
        for inicio, termino in _restar(f.fecha_inicio, f.fecha_termino, [(desde, hasta)]):
            filas.append((tipo, f.carga_id, inicio, termino, f.rango_desde, f.rango_hasta, f.origen, usuario, ahora))
    for inicio, termino, carga_id in _tramos(despues):
        c = candidatos[carga_id]
        origen = "MANUAL" if carga_id in rangos else origen_previo.get(carga_id, "CARGA")
        filas.append((tipo, carga_id, inicio, termino, c.desde, c.hasta, origen, usuario, ahora))
    if filas:
        cur.executemany(
            """INSERT INTO vigencia_archivo (tipo_archivo, carga_id, fecha_inicio, fecha_termino,
               rango_desde, rango_hasta, origen, creado_por, creado_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            filas,
        )
    return cambios


def _carga(cur, carga_id: int, bloquear: bool):
    cur.execute(
        """SELECT c.tipo_archivo, c.estado, c.vigencia_desde, c.vigencia_hasta, c.nombre_archivo, t.cobertura
           FROM control_carga c JOIN tipo_archivo t ON t.codigo = c.tipo_archivo
           WHERE c.carga_id = %s""" + (" FOR UPDATE" if bloquear else ""),
        (carga_id,),
    )
    return cur.fetchone()


def _procesando(cur, tipo: str) -> bool:
    cur.execute("SELECT COUNT(*) FROM control_carga WHERE tipo_archivo = %s AND estado = 'PROCESANDO'", (tipo,))
    return bool(cur.fetchone()[0])


def _fmt(d: date) -> str:
    return d.strftime("%d-%m-%Y")


def _tramo(c: Cambio) -> str:
    return _fmt(c.desde) if c.desde == c.hasta else f"{_fmt(c.desde)} al {_fmt(c.hasta)}"


def _recalculos(cur, tipo: str, cambios: list[Cambio]) -> list[tuple[str, date, date]]:
    if not cambios:
        return []
    cur.execute("SELECT indicador, desfase_dias FROM indicador_fuente WHERE tipo_archivo = %s", (tipo,))
    desde, hasta = min(c.desde for c in cambios), max(c.hasta for c in cambios)
    return [(ind, desde - timedelta(days=int(des)), hasta + timedelta(days=int(des))) for ind, des in cur.fetchall()]


def encolar_recalculos(cur, recalculos: list[tuple[str, date, date]], carga_id: int | None = None) -> None:
    for indicador, desde, hasta in recalculos:
        cur.execute(
            """INSERT INTO recalculo_pendiente (indicador, fecha_desde, fecha_hasta, motivo_carga_id, creado_at)
               VALUES (%s, %s, %s, %s, %s)""",
            (indicador, desde, hasta, carga_id, datetime.now()),
        )


def _advertir(r: Resultado, carga_id: int, nombres: dict[int, str]) -> None:
    def nombre(cid):
        return f"«{nombres.get(cid, cid)}» (carga {cid})"

    sin = [c for c in r.cambios if c.despues is None]
    if sin:
        dias = sum((c.hasta - c.desde).days + 1 for c in sin)
        r.advertencias.append(
            f"{dias} día(s) quedan sin ningún archivo de este tipo: " + ", ".join(_tramo(c) for c in sin)
            + ". El indicador de esos días deja de calcularse.")
    for c in r.cambios:
        if c.despues is not None and c.despues != carga_id:
            r.advertencias.append(f"Del {_tramo(c)} pasa a regir {nombre(c.despues)}"
                                  + (f" en vez de {nombre(c.antes)}." if c.antes else "."))
        elif c.despues == carga_id and c.antes is not None:
            r.advertencias.append(f"Del {_tramo(c)} este archivo reemplaza a {nombre(c.antes)}.")
        elif c.despues == carga_id:
            r.advertencias.append(f"Del {_tramo(c)} este archivo pasa a regir días que no tenían archivo.")
    for indicador, desde, hasta in r.recalculos:
        r.advertencias.append(f"Se recalcula el {indicador} del {_fmt(desde)} al {_fmt(hasta)}.")


def _nombres(cur, cambios: list[Cambio]) -> dict[int, str]:
    ids = sorted({c for cambio in cambios for c in (cambio.antes, cambio.despues) if c is not None})
    if not ids:
        return {}
    cur.execute(f"SELECT carga_id, nombre_archivo FROM control_carga WHERE carga_id IN ({', '.join(['%s'] * len(ids))})", ids)
    return {int(a): b for a, b in cur.fetchall()}


def eliminar_carga(cur, carga_id: int, *, usuario: str, aplicar: bool = True) -> Resultado:
    """Saca una carga: deja de regir sus fechas, que pasan a la carga que corresponda (o a ninguna)."""

    fila = _carga(cur, carga_id, bloquear=aplicar)
    if not fila:
        return Resultado(errores=[f"No existe la carga {carga_id}."])
    tipo, estado, v_desde, v_hasta, _, cobertura = fila
    r = Resultado(tipo=tipo)
    if estado != "COMPLETADO":
        r.errores.append(f"La carga {carga_id} está {estado}: sólo se pueden eliminar cargas completadas.")
    if tipo == "flota":
        r.errores.append("La flota no se elimina por archivo: se corrige en Datos maestros.")
    if _procesando(cur, tipo):
        r.errores.append("Hay un archivo de este tipo procesándose. Espera a que termine e inténtalo de nuevo.")
    if r.errores:
        return r
    if v_desde is not None:
        r.cambios = reconstruir(cur, tipo, v_desde, v_hasta, usuario=usuario, excluir={carga_id}, aplicar=aplicar)
    r.recalculos = _recalculos(cur, tipo, r.cambios)
    _advertir(r, carga_id, _nombres(cur, r.cambios))
    if not r.cambios:
        r.advertencias.append("Este archivo no rige ningún día: eliminarlo no cambia el cálculo.")
    if aplicar:
        cur.execute(
            """UPDATE control_carga SET estado = 'ELIMINADO', modificado_por = %s, modificado_at = %s
               WHERE carga_id = %s""",
            (usuario, datetime.now(), carga_id),
        )
        encolar_recalculos(cur, r.recalculos, carga_id)
    return r


def cambiar_fechas(cur, carga_id: int, desde: date, hasta: date, *, usuario: str, aplicar: bool = True) -> Resultado:
    """Cambia el rango que cubre una carga (anexos). El rango nuevo decide, con la regla de siempre,
    qué días rige; a igual largo le gana a las otras cargas."""

    fila = _carga(cur, carga_id, bloquear=aplicar)
    if not fila:
        return Resultado(errores=[f"No existe la carga {carga_id}."])
    tipo, estado, v_desde, v_hasta, _, cobertura = fila
    r = Resultado(tipo=tipo)
    if estado != "COMPLETADO":
        r.errores.append(f"La carga {carga_id} está {estado}: sólo se pueden modificar cargas completadas.")
    if cobertura != "RANGO" or v_desde is None:
        r.errores.append("Las fechas sólo se pueden cambiar en los anexos. Los demás archivos se reemplazan.")
    if desde is None or hasta is None:
        r.errores.append("Faltan las fechas de inicio y fin.")
    elif hasta < desde:
        r.errores.append("La fecha de fin es anterior a la de inicio.")
    elif (hasta - desde).days > 3 * 366:
        r.errores.append("El rango no puede superar 3 años.")
    if _procesando(cur, tipo):
        r.errores.append("Hay un archivo de este tipo procesándose. Espera a que termine e inténtalo de nuevo.")
    if r.errores:
        return r
    if (desde, hasta) == (v_desde, v_hasta):
        r.errores.append("Las fechas son las mismas que ya tiene.")
        return r

    cur.execute(
        """SELECT rango_desde, rango_hasta FROM vigencia_archivo WHERE carga_id = %s AND origen = 'CARGA'
           ORDER BY vigencia_id LIMIT 1""",
        (carga_id,),
    )
    original = cur.fetchone()
    if original and (desde < original[0] or hasta > original[1]):
        r.advertencias.append(
            f"El archivo trae fechas del {_fmt(original[0])} al {_fmt(original[1])}: fuera de eso no tiene "
            "programa para los días que agregues, y esos días no se podrán calcular.")
    total_desde, total_hasta = min(desde, v_desde), max(hasta, v_hasta)
    r.cambios = reconstruir(cur, tipo, total_desde, total_hasta, usuario=usuario,
                            rangos={carga_id: (desde, hasta)}, aplicar=aplicar)
    r.recalculos = _recalculos(cur, tipo, r.cambios)
    _advertir(r, carga_id, _nombres(cur, r.cambios))
    if not r.cambios:
        r.advertencias.append("Con estas fechas ningún día cambia de archivo (otros archivos más cortos los rigen).")
    if aplicar:
        cur.execute(
            """UPDATE control_carga SET vigencia_desde = %s, vigencia_hasta = %s, modificado_por = %s,
               modificado_at = %s WHERE carga_id = %s""",
            (desde, hasta, usuario, datetime.now(), carga_id),
        )
        encolar_recalculos(cur, r.recalculos, carga_id)
    return r


def completar_faltantes(cur, usuario: str = "sistema") -> list[tuple[str, list[Cambio]]]:
    """Arma los tramos de las cargas COMPLETADO que tienen rango pero ninguna fila en vigencia_archivo
    (cargas hechas antes de que existieran las vigencias) y encola el recálculo de lo que cambie.
    El job lo llama al partir; si no falta nada, no hace nada."""

    cur.execute(
        """SELECT c.tipo_archivo, MIN(c.vigencia_desde), MAX(c.vigencia_hasta) FROM control_carga c
           WHERE c.estado = 'COMPLETADO' AND c.vigencia_desde IS NOT NULL
           AND NOT EXISTS (SELECT 1 FROM vigencia_archivo v WHERE v.carga_id = c.carga_id)
           GROUP BY c.tipo_archivo"""
    )
    resultado = []
    for tipo, desde, hasta in cur.fetchall():
        cambios = reconstruir(cur, tipo, desde, hasta, usuario=usuario)
        if cambios:
            encolar_recalculos(cur, _recalculos(cur, tipo, cambios))
            resultado.append((tipo, cambios))
    return resultado
