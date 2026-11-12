"""Datos maestros (tablas dim_) para ver y editar desde la web.

GET  /api/maestros                    -> tablas disponibles y sus columnas
GET  /api/maestros?tabla=dim_bus      -> filas
POST /api/maestros?tabla=dim_bus      -> {"accion": "guardar" | "borrar", "fila": {...}}

Cada cambio queda con el usuario y la hora (actualizado_por / actualizado_at), y encola un
recálculo del ICFP para todas las fechas con velocidades; para que el job lo procese de
inmediato se deja un aviso en ``recalculo/entrada/`` del blob (Event Grid -> cola -> job).
Variables: DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD, DB_SSL_CA (opcional),
BLOB_CONNECTION_STRING, BLOB_CONTAINER.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from datetime import date, datetime
from decimal import Decimal

import azure.functions as func

# tabla -> columnas (nombre, tipo, es_clave, titulo). Sólo estas tablas se pueden editar.
TABLAS = {
    "dim_bus": {
        "nombre": "Flota (buses)",
        "descripcion": "Plazas por patente para el ICP. Se llena al cargar un archivo de flota; aquí se corrige a mano.",
        "columnas": [
            ("ppu", "texto", True, "Patente"),
            ("tipo_bus", "texto", False, "Tipo de bus"),
            ("plazas", "entero", False, "Plazas"),
        ],
        "extra": ["origen", "actualizado_por", "actualizado_at"],
        "manual": {"origen": "MANUAL", "carga_id": None},
    },
    "dim_servicio_terminal": {
        "nombre": "Terminal por servicio",
        "descripcion": "Terminal de cada servicio (código usuario) para agrupar el ICFP.",
        "columnas": [
            ("codigo_usuario", "texto", True, "Código usuario"),
            ("terminal", "texto", False, "Terminal"),
        ],
        "extra": ["actualizado_por", "actualizado_at"],
        "manual": {},
    },
}


class ErrorUsuario(Exception):
    pass


def _respuesta(datos, status: int = 200) -> func.HttpResponse:
    def conv(v):
        if isinstance(v, (date, datetime)):
            return v.isoformat(sep=" ") if isinstance(v, datetime) else v.isoformat()
        if isinstance(v, Decimal):
            return float(v)
        raise TypeError(type(v))

    return func.HttpResponse(json.dumps(datos, ensure_ascii=False, default=conv), status_code=status,
                             mimetype="application/json")


def _usuario(req: func.HttpRequest) -> str:
    try:
        principal = json.loads(base64.b64decode(req.headers.get("x-ms-client-principal", "")))
        return principal.get("userDetails") or "desconocido"
    except (ValueError, TypeError):
        return "desconocido"


def _conexion():
    import pymysql

    host = os.environ["DB_HOST"]
    ca = os.getenv("DB_SSL_CA")
    if ca:
        ssl = {"ca": ca}
    elif host in ("localhost", "127.0.0.1", "mysql"):
        ssl = None  # MySQL local de docker compose
    else:
        import certifi  # Azure Database for MySQL exige TLS

        ssl = {"ca": certifi.where()}
    return pymysql.connect(host=host, port=int(os.getenv("DB_PORT", "3306")), user=os.environ["DB_USER"],
                           password=os.environ["DB_PASSWORD"], database=os.getenv("DB_NAME", "indicadores_bi"),
                           charset="utf8mb4", autocommit=False, connect_timeout=15, ssl=ssl)


def _valor(tipo: str, valor, titulo: str):
    if valor is None or str(valor).strip() == "":
        return None
    if tipo == "entero":
        try:
            numero = int(str(valor).strip())
        except ValueError:
            raise ErrorUsuario(f"{titulo}: '{valor}' no es un número entero.") from None
        if numero <= 0:
            raise ErrorUsuario(f"{titulo}: debe ser mayor que cero.")
        return numero
    return str(valor).strip()


def _normalizar_clave(tabla: str, valor: str) -> str:
    if tabla == "dim_bus":
        return valor.upper().replace("-", "").replace(" ", "")
    return valor


def _encolar_recalculo(cur) -> None:
    cur.execute("""SELECT MIN(fecha_inicio), MAX(fecha_termino) FROM vigencia_archivo
                   WHERE tipo_archivo = 'velocidades' AND vigente = 1""")
    desde, hasta = cur.fetchone()
    if desde:
        cur.execute("""INSERT INTO recalculo_pendiente (indicador, fecha_desde, fecha_hasta, creado_at)
                       VALUES ('ICFP', %s, %s, %s)""", (desde, hasta, datetime.now()))


def _avisar_job(usuario: str) -> None:
    """Deja un aviso en recalculo/entrada/ para que el job resuelva el recálculo pendiente."""
    from azure.storage.blob import BlobServiceClient

    contenedor = BlobServiceClient.from_connection_string(os.environ["BLOB_CONNECTION_STRING"]).get_container_client(
        os.getenv("BLOB_CONTAINER", "cargas"))
    nombre = f"recalculo/entrada/{datetime.now():%Y%m%d_%H%M%S_%f}.txt"
    contenedor.get_blob_client(nombre).upload_blob(f"Cambio en datos maestros por {usuario}\n".encode(), overwrite=True)


def _listar(cur, tabla: str) -> list[dict]:
    t = TABLAS[tabla]
    columnas = [c[0] for c in t["columnas"]] + t["extra"]
    cur.execute(f"SELECT {', '.join(columnas)} FROM {tabla} ORDER BY {t['columnas'][0][0]} LIMIT 20000")
    return [dict(zip(columnas, fila)) for fila in cur.fetchall()]


def _guardar(cur, tabla: str, fila: dict, usuario: str, accion: str) -> None:
    t = TABLAS[tabla]
    clave, tipo_clave, _, titulo_clave = t["columnas"][0]
    valor_clave = _valor(tipo_clave, fila.get(clave), titulo_clave)
    if valor_clave is None:
        raise ErrorUsuario(f"Falta {titulo_clave}.")
    valor_clave = _normalizar_clave(tabla, valor_clave)
    if accion == "borrar":
        cur.execute(f"DELETE FROM {tabla} WHERE {clave} = %s", (valor_clave,))
        if not cur.rowcount:
            raise ErrorUsuario(f"No existe {titulo_clave} {valor_clave}.")
        return
    valores = {clave: valor_clave}
    for nombre, tipo, _, titulo in t["columnas"][1:]:
        valores[nombre] = _valor(tipo, fila.get(nombre), titulo)
    if tabla == "dim_servicio_terminal" and not valores["terminal"]:
        raise ErrorUsuario("Falta la terminal.")
    valores.update(t["manual"], actualizado_por=usuario, actualizado_at=datetime.now())
    columnas = list(valores)
    cur.execute(
        f"INSERT INTO {tabla} ({', '.join(columnas)}) VALUES ({', '.join(['%s'] * len(columnas))}) "
        "ON DUPLICATE KEY UPDATE " + ", ".join(f"{c} = VALUES({c})" for c in columnas if c != clave),
        tuple(valores.values()),
    )


def _main(req: func.HttpRequest) -> func.HttpResponse:
    tabla = req.params.get("tabla")
    if not tabla:
        return _respuesta([{"tabla": k, "nombre": v["nombre"], "descripcion": v["descripcion"],
                            "columnas": [{"nombre": c[0], "tipo": c[1], "clave": c[2], "titulo": c[3]} for c in v["columnas"]],
                            "extra": v["extra"]} for k, v in TABLAS.items()])
    if tabla not in TABLAS:
        return _respuesta({"estado": "ERROR", "mensaje": f"Tabla no editable: {tabla}"}, 400)

    conn = _conexion()
    try:
        with conn.cursor() as cur:
            if req.method == "GET":
                return _respuesta({"filas": _listar(cur, tabla)})
            try:
                cuerpo = req.get_json()
            except ValueError:
                return _respuesta({"estado": "ERROR", "mensaje": "Cuerpo JSON inválido."}, 400)
            accion = cuerpo.get("accion")
            if accion not in ("guardar", "borrar"):
                return _respuesta({"estado": "ERROR", "mensaje": "accion debe ser guardar o borrar."}, 400)
            usuario = _usuario(req)
            try:
                _guardar(cur, tabla, cuerpo.get("fila") or {}, usuario, accion)
            except ErrorUsuario as exc:
                conn.rollback()
                return _respuesta({"estado": "ERROR", "mensaje": str(exc)}, 400)
            _encolar_recalculo(cur)
        conn.commit()
    finally:
        conn.close()
    try:
        _avisar_job(usuario)
        aviso = "Guardado. El ICFP se recalcula en unos minutos."
    except Exception:  # noqa: BLE001 - el cambio ya quedó; el recálculo espera al próximo archivo
        logging.exception("No se pudo avisar al job")
        aviso = "Guardado. El recálculo quedó pendiente para la próxima carga."
    return _respuesta({"estado": "OK", "mensaje": aviso})


def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        return _main(req)
    except KeyError as exc:
        return _respuesta({"estado": "ERROR", "mensaje": f"Falta la variable de entorno {exc} en la Static Web App."}, 500)
    except Exception as exc:  # noqa: BLE001
        logging.exception("Error en la API")
        return _respuesta({"estado": "ERROR", "mensaje": f"Error del servidor: {exc.__class__.__name__}: {exc}"}, 500)
