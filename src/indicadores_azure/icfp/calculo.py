"""Lee las cargas vigentes, calcula el ICFP de un rango de fechas y lo guarda como un cálculo nuevo.

Para cada fecha usa la carga que vigencia_archivo dice que rige: velocidades del día, Anexo 3
y exclusiones del mes. Además calcula los días vecinos (d-1 y d+1) sólo para el trasvasije,
sin guardarlos. La flota es la de dim_bus.

Una fecha con velocidades pero sin un Anexo 3 vigente que traiga su tipo de día se omite y se
anota en calculo.mensaje_error; el resto del rango se guarda igual.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from . import correcciones, inicial, programa, sspd

log = logging.getLogger("indicadores_azure")

VERSION = "ICFP_HORA_V1"
UN_DIA = timedelta(days=1)


class ErrorDeCalculo(Exception):
    pass


def _dicts(cur, sql, args=()):
    cur.execute(sql, args)
    columnas = [c[0] for c in cur.description]
    return [dict(zip(columnas, fila)) for fila in cur.fetchall()]


def _vigencias(cur, tipo: str, desde: date, hasta: date) -> dict[date, int]:
    cur.execute(
        """SELECT fecha_inicio, fecha_termino, carga_id FROM vigencia_archivo
           WHERE tipo_archivo = %s AND vigente = 1 AND fecha_inicio <= %s AND fecha_termino >= %s""",
        (tipo, hasta, desde),
    )
    resultado = {}
    for inicio, termino, carga in cur.fetchall():
        d = max(inicio, desde)
        while d <= min(termino, hasta):
            resultado[d] = int(carga)
            d += UN_DIA
    return resultado


def _insertar(cur, tabla: str, filas: list[dict], lote: int = 5000) -> None:
    if not filas:
        return
    columnas = list(filas[0])
    sql = (f"INSERT INTO `{tabla}` (" + ", ".join(f"`{c}`" for c in columnas) + ") VALUES ("
           + ", ".join(["%s"] * len(columnas)) + ")")
    valores = [tuple(f[c] for c in columnas) for f in filas]
    for i in range(0, len(valores), lote):
        cur.executemany(sql, valores[i:i + lote])


def calcular(conn, desde: date, hasta: date) -> int | None:
    """Calcula y guarda el ICFP de [desde, hasta]. Devuelve el calculo_id, o None si no hay
    velocidades en el rango."""

    if hasta < desde:
        raise ValueError("Rango de fechas invertido.")
    with conn.cursor() as cur:
        dias_velocidades = _vigencias(cur, "velocidades", desde - UN_DIA, hasta + UN_DIA)
    if not any(desde <= d <= hasta for d in dias_velocidades):
        return None
    desde = max(desde, min(d for d in dias_velocidades if d >= desde))
    hasta = min(hasta, max(d for d in dias_velocidades if d <= hasta))

    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO calculo (indicador, fecha_desde, fecha_hasta, version_algoritmo, estado, inicio_at)
               VALUES ('ICFP', %s, %s, %s, 'PROCESANDO', %s)""",
            (desde, hasta, VERSION, datetime.now()),
        )
        calculo_id = int(cur.lastrowid)
    conn.commit()

    try:
        with conn.cursor() as cur:
            omitidas, filas, entradas, expediciones, trasvasijes = _calcular(cur, calculo_id, desde, hasta, dias_velocidades)
            _insertar(cur, "icfp_sspd", [{"calculo_id": calculo_id, **f} for f in filas])
            _insertar(cur, "icfp_expedicion", expediciones)
            _insertar(cur, "icfp_trasvasije", trasvasijes)
            _insertar(cur, "calculo_entrada", entradas)
            fechas = len({f["fecha"] for f in filas})
            if not fechas:
                raise ErrorDeCalculo("Ninguna fecha del rango se pudo calcular. " + " ".join(omitidas))
            cur.execute(
                """UPDATE calculo SET estado = 'OK', fin_at = %s, fechas_calculadas = %s, mensaje_error = %s
                   WHERE calculo_id = %s""",
                (datetime.now(), fechas, (" ".join(omitidas)[:4000] or None), calculo_id),
            )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE calculo SET estado = 'ERROR', fin_at = %s, mensaje_error = %s WHERE calculo_id = %s",
                (datetime.now(), str(exc)[:4000], calculo_id),
            )
        conn.commit()
        raise
    log.info("ICFP %s..%s: cálculo %s, %s filas, %s trasvasijes.", desde, hasta, calculo_id, len(filas), len(trasvasijes))
    return calculo_id


def _calcular(cur, calculo_id: int, desde: date, hasta: date, dias_velocidades: dict[date, int]):
    ext_desde, ext_hasta = desde - UN_DIA, hasta + UN_DIA
    anexos = _vigencias(cur, "anexo3", ext_desde, ext_hasta)
    exclusiones_carga = _vigencias(cur, "exclusiones", desde, hasta)
    cur.execute("SELECT ppu, tipo_bus, plazas FROM dim_bus")
    buses = inicial.mapa_buses(cur.fetchall())
    cur.execute("SELECT codigo_usuario, terminal FROM dim_servicio_terminal")
    terminales = {str(c).strip().casefold(): t for c, t in cur.fetchall()}

    programas: dict[int, dict] = {}
    periodos, expediciones, omitidas, entradas = [], [], [], []
    for fecha in sorted(dias_velocidades):
        en_rango = desde <= fecha <= hasta
        anexo = anexos.get(fecha)
        try:
            if anexo is None:
                raise ErrorDeCalculo("no hay Anexo 3 vigente")
            if anexo not in programas:
                programas[anexo] = programa.construir_programa(_dicts(
                    cur, """SELECT id, unidad_de_servicio, codigo_ts_servicio, codigo_usuario_servicio, sentido,
                               tipo_dia, mh, numero_salidas, capacidad_plazas, distancia_base_km
                            FROM raw_anexo3 WHERE carga_id = %s""", (anexo,)))
            velocidades = _dicts(
                cur, """SELECT id, un, servicio, patente, sentido, inicio, estado, fecha, tipo_dia
                        FROM raw_velocidades WHERE carga_id = %s AND fecha = %s ORDER BY id""",
                (dias_velocidades[fecha], fecha))
            exp, per = inicial.construir(fecha, programas[anexo], velocidades, buses)
        except (ErrorDeCalculo, ValueError) as exc:
            if en_rango:
                omitidas.append(f"{fecha}: {exc}.")
            continue
        expediciones += exp
        periodos += per
        if en_rango:
            entradas += [
                {"calculo_id": calculo_id, "fecha": fecha, "tipo_archivo": "velocidades", "carga_id": dias_velocidades[fecha]},
                {"calculo_id": calculo_id, "fecha": fecha, "tipo_archivo": "anexo3", "carga_id": anexo},
            ]
            if fecha in exclusiones_carga:
                entradas.append({"calculo_id": calculo_id, "fecha": fecha, "tipo_archivo": "exclusiones",
                                 "carga_id": exclusiones_carga[fecha]})

    estados, asignaciones, movimientos = correcciones.corregir(periodos, expediciones)
    iniciales = sspd.iniciales_con_ratios(periodos)

    exclusiones = {}
    for fecha, carga in exclusiones_carga.items():
        cur.execute(
            """SELECT codigo_ts_servicio, sentido, periodo FROM raw_exclusiones
               WHERE carga_id = %s AND fecha = %s AND UPPER(hoja) = 'ICFP-IE'""", (carga, fecha))
        exclusiones[fecha] = sspd.exclusiones_del_dia(cur.fetchall())

    filas = sspd.armar(estados, iniciales, desde, hasta, exclusiones, terminales)
    filas_exp = [{
        "calculo_id": calculo_id, "raw_velocidades_id": e["fact_expedicion_id"], "fecha": e["fecha"],
        "codigo_ts": e["servicio"], "sentido": e["sentido"], "tipo_dia": e["tipo_dia"],
        "periodo": e["periodo_original"], "fh_salida": e["fecha_hora_inicio"], "patente": e["patente"],
        "tipo_bus": e["tipo_bus"], "plazas": e["plazas"], "estado_plazas": e["estado_plazas"],
        "fecha_asignada": asignaciones[e["fact_expedicion_id"]][-1].date(),
        "periodo_asignado": asignaciones[e["fact_expedicion_id"]][-1].hour,
    } for e in expediciones if desde <= e["fecha"] <= hasta]
    filas_tras = [{
        "calculo_id": calculo_id, "raw_velocidades_id": m["fact_expedicion_id"],
        "codigo_ts": m["origen"][1], "sentido": m["origen"][2],
        "fecha_origen": m["origen"][-1].date(), "periodo_origen": m["origen"][-1].hour,
        "fecha_destino": m["destino"][-1].date(), "periodo_destino": m["destino"][-1].hour,
        "regla": m["regla"], "plazas": m["plazas"],
    } for m in movimientos if desde <= m["origen"][-1].date() <= hasta or desde <= m["destino"][-1].date() <= hasta]
    return omitidas, filas, entradas, filas_exp, filas_tras
