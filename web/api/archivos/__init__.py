"""Archivos ya cargados: listar con sus vigencias, descargar el original, eliminar y cambiar fechas.

GET  /api/archivos?tipo=anexo3            archivos COMPLETADO, tramos vigentes y cargas con error
GET  /api/archivos?descargar=<carga_id>   el archivo original tal como se subió
POST /api/archivos  {"accion": "eliminar" | "cambiar_fechas", "carga_id": 12,
                     "desde": "2026-07-04", "hasta": "2026-11-13", "confirmar": false}

Con "confirmar": false sólo simula y devuelve qué cambia (tramos que pasan de un archivo a otro,
días que quedan sin archivo, recálculos) para mostrarlo antes de confirmar. Con true lo aplica,
encola el recálculo de los indicadores y avisa al job. Reemplazar un archivo se hace subiéndolo en
/api/cargar con ?reemplaza=<carga_id>: el job elimina el anterior cuando el nuevo queda cargado.
"""

from __future__ import annotations

import logging
import sys
from datetime import date
from pathlib import Path
from urllib.parse import quote

import azure.functions as func

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # web/api, para "compartido"

from compartido import vigencias, web  # noqa: E402

TIPOS = ("anexo1", "anexo3", "velocidades", "exclusiones")


def _listar(cur, tipo: str) -> dict:
    cur.execute("SELECT nombre, cobertura FROM tipo_archivo WHERE codigo = %s", (tipo,))
    nombre, cobertura = cur.fetchone() or (tipo, "RANGO")
    cur.execute(
        """SELECT carga_id, nombre_archivo, subido_por, fin_at, filas_cargadas, vigencia_desde, vigencia_hasta,
                  modificado_por, modificado_at
           FROM control_carga WHERE tipo_archivo = %s AND estado = 'COMPLETADO'
           ORDER BY vigencia_desde DESC, carga_id DESC""",
        (tipo,),
    )
    columnas = ["carga_id", "nombre_archivo", "subido_por", "cargado_at", "filas", "vigencia_desde",
                "vigencia_hasta", "modificado_por", "modificado_at"]
    archivos = [dict(zip(columnas, f)) for f in cur.fetchall()]
    cur.execute(
        """SELECT v.carga_id, v.rango_desde, v.rango_hasta FROM vigencia_archivo v
           JOIN (SELECT MIN(vigencia_id) AS id FROM vigencia_archivo
                 WHERE tipo_archivo = %s AND origen = 'CARGA' GROUP BY carga_id) p ON p.id = v.vigencia_id""",
        (tipo,),
    )
    originales = {int(c): (d, h) for c, d, h in cur.fetchall()}
    for a in archivos:
        d, h = originales.get(a["carga_id"], (a["vigencia_desde"], a["vigencia_hasta"]))
        a["archivo_desde"], a["archivo_hasta"] = d, h
    cur.execute(
        """SELECT carga_id, fecha_inicio, fecha_termino, origen FROM vigencia_archivo
           WHERE tipo_archivo = %s AND vigente = 1 ORDER BY fecha_inicio""",
        (tipo,),
    )
    tramos = [{"carga_id": int(c), "desde": d, "hasta": h, "origen": o} for c, d, h, o in cur.fetchall()]
    cur.execute(
        """SELECT carga_id, nombre_archivo, subido_por, inicio_at, mensaje_error FROM control_carga
           WHERE tipo_archivo = %s AND estado = 'ERROR' ORDER BY carga_id DESC LIMIT 20""",
        (tipo,),
    )
    errores = [dict(zip(["carga_id", "nombre_archivo", "subido_por", "subido_at", "mensaje"], f)) for f in cur.fetchall()]
    return {"tipo": tipo, "nombre": nombre, "cobertura": cobertura, "archivos": archivos, "tramos": tramos,
            "errores": errores}


def _descargar(cur, carga_id: str) -> func.HttpResponse:
    if not carga_id.isdigit():
        return web.respuesta({"estado": "ERROR", "mensaje": "descargar debe ser un número de carga"}, 400)
    cur.execute("SELECT blob_nombre, nombre_archivo FROM control_carga WHERE carga_id = %s", (int(carga_id),))
    fila = cur.fetchone()
    if not fila:
        return web.respuesta({"estado": "ERROR", "mensaje": f"No existe la carga {carga_id}."}, 404)
    from azure.core.exceptions import ResourceNotFoundError

    try:
        contenido = web.contenedor().download_blob(fila[0]).readall()
    except ResourceNotFoundError:
        return web.respuesta({"estado": "ERROR", "mensaje": f"El archivo ya no está en el blob ({fila[0]})."}, 404)
    nombre = fila[1] or Path(fila[0]).name
    return func.HttpResponse(contenido, status_code=200, mimetype="application/octet-stream", headers={
        "Content-Disposition": f"attachment; filename=\"{nombre.encode('ascii', 'replace').decode()}\"; "
                               f"filename*=UTF-8''{quote(nombre)}",
    })


def _fecha(valor) -> date | None:
    try:
        return date.fromisoformat(str(valor)) if valor else None
    except ValueError:
        return None


def _accion(conn, cuerpo: dict, usuario: str) -> func.HttpResponse:
    accion = cuerpo.get("accion")
    carga_id = cuerpo.get("carga_id")
    confirmar = cuerpo.get("confirmar") is True
    if accion not in ("eliminar", "cambiar_fechas"):
        return web.respuesta({"estado": "ERROR", "errores": ["accion debe ser eliminar o cambiar_fechas."]}, 400)
    if not isinstance(carga_id, int):
        return web.respuesta({"estado": "ERROR", "errores": ["Falta carga_id."]}, 400)
    with conn.cursor() as cur:
        if accion == "eliminar":
            r = vigencias.eliminar_carga(cur, carga_id, usuario=usuario, aplicar=confirmar)
        else:
            desde, hasta = _fecha(cuerpo.get("desde")), _fecha(cuerpo.get("hasta"))
            if (cuerpo.get("desde") and not desde) or (cuerpo.get("hasta") and not hasta):
                return web.respuesta({"estado": "ERROR", "errores": ["Fecha inválida (formato AAAA-MM-DD)."]}, 400)
            r = vigencias.cambiar_fechas(cur, carga_id, desde, hasta, usuario=usuario, aplicar=confirmar)
        if r.tipo and r.tipo not in TIPOS:
            r.errores.append("Este tipo de archivo no se modifica desde aquí.")
        if r.errores or not confirmar:
            conn.rollback()
            datos = {"estado": "ERROR" if r.errores else "SIMULACION", "errores": r.errores,
                     "advertencias": r.advertencias,
                     "cambios": [{"desde": c.desde, "hasta": c.hasta, "antes": c.antes, "despues": c.despues}
                                 for c in r.cambios]}
            return web.respuesta(datos, 400 if r.errores else 200)
    conn.commit()
    mensaje = "Eliminado." if accion == "eliminar" else "Fechas cambiadas."
    if r.recalculos:
        try:
            web.avisar_job(f"{accion} de la carga {carga_id} por {usuario}")
            mensaje += " Los indicadores se recalculan en unos minutos."
        except Exception:  # noqa: BLE001 - el cambio ya quedó; el recálculo espera al próximo archivo
            logging.exception("No se pudo avisar al job")
            mensaje += " No se pudo avisar al job: el recálculo se hará con la próxima carga."
    return web.respuesta({"estado": "OK", "mensaje": mensaje, "advertencias": r.advertencias})


def _main(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "GET":
        tipo = req.params.get("tipo")
        descargar = req.params.get("descargar")
        if not descargar and tipo not in TIPOS:
            return web.respuesta({"estado": "ERROR", "mensaje": f"Tipo no soportado: {tipo}"}, 400)
    else:
        try:
            cuerpo = req.get_json()
        except ValueError:
            return web.respuesta({"estado": "ERROR", "errores": ["Cuerpo JSON inválido."]}, 400)
    conn = web.conexion()
    try:
        if req.method == "GET":
            with conn.cursor() as cur:
                return _descargar(cur, descargar) if descargar else web.respuesta(_listar(cur, tipo))
        return _accion(conn, cuerpo or {}, web.usuario(req))
    finally:
        conn.close()


def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        return _main(req)
    except KeyError as exc:
        return web.respuesta({"estado": "ERROR", "mensaje": f"Falta la variable de entorno {exc} en la Static Web App."}, 500)
    except Exception as exc:  # noqa: BLE001
        logging.exception("Error en la API")
        return web.respuesta({"estado": "ERROR", "mensaje": f"Error del servidor: {exc.__class__.__name__}: {exc}"}, 500)
