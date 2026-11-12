"""Después de cargar archivos: actualiza los maestros y recalcula los indicadores afectados.

Cuando una carga queda COMPLETADO:
  - si es de flota, sus patentes se copian a dim_bus (pisan las de cargas anteriores; las
    patentes que no vienen en el archivo se mantienen);
  - si un indicador depende de su tipo (indicador_fuente), se encola en recalculo_pendiente el
    rango de fechas que esa carga rige ahora, ampliado en desfase_dias por el trasvasije.
Luego se resuelven los pendientes: los rangos que se tocan se juntan en un solo cálculo.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime, timedelta

log = logging.getLogger("indicadores_azure")


def sincronizar_flota(cur, carga_id: int, usuario: str | None = None) -> int:
    cur.execute(
        """INSERT INTO dim_bus (ppu, tipo_bus, plazas, origen, carga_id, actualizado_por, actualizado_at)
           SELECT ppu, tipo_bus, plazas, 'CARGA', carga_id, %s, %s FROM raw_flota WHERE carga_id = %s
           ON DUPLICATE KEY UPDATE tipo_bus = VALUES(tipo_bus), plazas = VALUES(plazas), origen = 'CARGA',
             carga_id = VALUES(carga_id), actualizado_por = VALUES(actualizado_por),
             actualizado_at = VALUES(actualizado_at)""",
        (usuario, datetime.now(), carga_id),
    )
    return cur.rowcount


def _rango_de_carga(cur, tipo: str, carga_id: int) -> tuple[date, date] | None:
    if tipo == "flota":  # cambia las plazas de todos los días con velocidades
        cur.execute("""SELECT MIN(fecha_inicio), MAX(fecha_termino) FROM vigencia_archivo
                       WHERE tipo_archivo = 'velocidades' AND vigente = 1""")
    else:
        cur.execute("""SELECT MIN(fecha_inicio), MAX(fecha_termino) FROM vigencia_archivo
                       WHERE carga_id = %s AND vigente = 1""", (carga_id,))
    fila = cur.fetchone()
    return (fila[0], fila[1]) if fila and fila[0] else None


def encolar_por_carga(conn, tipo: str, carga_id: int) -> int:
    """Encola los recálculos que gatilla una carga recién completada. Devuelve cuántos encoló."""

    encolados = 0
    with conn.cursor() as cur:
        if tipo == "flota":
            sincronizar_flota(cur, carga_id)
        cur.execute("SELECT indicador, desfase_dias FROM indicador_fuente WHERE tipo_archivo = %s", (tipo,))
        fuentes = cur.fetchall()
        rango = _rango_de_carga(cur, tipo, carga_id) if fuentes else None
        if rango:
            for indicador, desfase in fuentes:
                margen = timedelta(days=int(desfase))
                cur.execute(
                    """INSERT INTO recalculo_pendiente (indicador, fecha_desde, fecha_hasta, motivo_carga_id, creado_at)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (indicador, rango[0] - margen, rango[1] + margen, carga_id, datetime.now()),
                )
                encolados += 1
    conn.commit()
    return encolados


def _juntar(rangos: list[tuple[int, date, date]]) -> list[tuple[list[int], date, date]]:
    grupos: list[tuple[list[int], date, date]] = []
    for rid, desde, hasta in sorted(rangos, key=lambda r: r[1]):
        if grupos and desde <= grupos[-1][2] + timedelta(days=1):
            ids, d, h = grupos[-1]
            grupos[-1] = (ids + [rid], d, max(h, hasta))
        else:
            grupos.append(([rid], desde, hasta))
    return grupos


def procesar_pendientes(conn) -> int:
    """Resuelve los recálculos pendientes del ICFP. Devuelve cuántos cálculos hizo."""

    from .icfp.calculo import calcular

    with conn.cursor() as cur:
        cur.execute("""SELECT recalculo_id, fecha_desde, fecha_hasta FROM recalculo_pendiente
                       WHERE estado = 'PENDIENTE' AND indicador = 'ICFP'""")
        pendientes = [(int(r[0]), r[1], r[2]) for r in cur.fetchall()]
    calculos = 0
    for ids, desde, hasta in _juntar(pendientes):
        marcas = ", ".join(["%s"] * len(ids))
        try:
            calculo_id = calcular(conn, desde, hasta)
            estado = "HECHO"
            calculos += calculo_id is not None
        except Exception:
            log.exception("Falló el recálculo del ICFP %s..%s", desde, hasta)
            calculo_id, estado = None, "ERROR"
        with conn.cursor() as cur:
            cur.execute(
                f"""UPDATE recalculo_pendiente SET estado = %s, calculo_id = %s, resuelto_at = %s
                    WHERE recalculo_id IN ({marcas})""",
                (estado, calculo_id, datetime.now(), *ids),
            )
        conn.commit()
    return calculos


def main(argv: list[str] | None = None) -> int:
    """indicadores-azure-icfp --desde 2026-02-01 [--hasta 2026-02-28]   o   --pendientes"""

    from .config import Config
    from .db import conexion
    from .icfp.calculo import calcular

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Calcula el ICFP de un rango de fechas.")
    parser.add_argument("--desde", type=date.fromisoformat)
    parser.add_argument("--hasta", type=date.fromisoformat)
    parser.add_argument("--pendientes", action="store_true", help="resuelve la cola recalculo_pendiente")
    args = parser.parse_args(argv)
    if not args.pendientes and not args.desde:
        parser.error("indica --desde (y opcionalmente --hasta) o --pendientes")
    with conexion(Config.desde_entorno()) as conn:
        if args.pendientes:
            print(f"Cálculos hechos: {procesar_pendientes(conn)}")
        else:
            calculo_id = calcular(conn, args.desde, args.hasta or args.desde)
            print(f"Cálculo {calculo_id}" if calculo_id else "No hay velocidades en ese rango.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
