"""Mantenedor de usuarios y roles de la web (sólo administradores).

GET  /api/usuarios -> {"usuarios": [...], "roles": [...], "menus": [...]}
POST /api/usuarios  {"accion": "guardar_usuario", "usuario": {"id"?, "email", "nombre", "activo", "roles": [ids]}}
                    {"accion": "borrar_usuario", "id": 3}
                    {"accion": "guardar_rol", "rol": {"id"?, "nombre", "es_admin", "puede_cargar",
                                                      "puede_maestros", "menus": [ids]}}
                    {"accion": "borrar_rol", "id": 2}

Escribe en la base portal_reportes (usuario, usuario_rol, rol, permiso). El email es el de la
cuenta de Microsoft (Entra ID) con que la persona entra a la web. Los menús de un rol son sus
permisos por menú; los permisos por reporte puntual (permiso.reporte_id) no se tocan desde aquí.
Ningún cambio puede dejar al propio administrador sin acceso de administrador.
"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

import azure.functions as func

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # web/api, para "compartido"

from compartido import portal, web  # noqa: E402

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ErrorUsuario(Exception):
    pass


def _ids(valores, que: str) -> list[int]:
    try:
        ids = sorted({int(v) for v in valores or []})
    except (TypeError, ValueError):
        raise ErrorUsuario(f"Lista de {que} inválida.") from None
    return ids


def _existen(cur, tabla: str, ids: list[int], que: str) -> None:
    if not ids:
        return
    cur.execute(f"SELECT id FROM {tabla} WHERE id IN ({', '.join(['%s'] * len(ids))})", tuple(ids))
    faltan = set(ids) - {int(f[0]) for f in cur.fetchall()}
    if faltan:
        raise ErrorUsuario(f"No existe{'n' if len(faltan) > 1 else ''} {que} {', '.join(map(str, sorted(faltan)))}.")


def _id(valor) -> int | None:
    if valor in (None, ""):
        return None
    try:
        return int(valor)
    except (TypeError, ValueError):
        raise ErrorUsuario("id inválido.") from None


def _bool(valor) -> int:
    return 1 if valor in (True, 1, "1", "true", "on") else 0


def _duplicado(exc: Exception) -> bool:
    return (exc.args or [None])[0] == 1062  # pymysql.err.IntegrityError: clave única repetida


def listar(cur) -> dict:
    cur.execute("SELECT id, email, nombre, activo, ultimo_acceso FROM usuario ORDER BY email")
    usuarios = [{"id": int(i), "email": e, "nombre": n or "", "activo": bool(a), "ultimo_acceso": u, "roles": []}
                for i, e, n, a, u in cur.fetchall()]
    por_id = {u["id"]: u for u in usuarios}
    cur.execute("SELECT usuario_id, rol_id FROM usuario_rol ORDER BY rol_id")
    for usuario_id, rol_id in cur.fetchall():
        if int(usuario_id) in por_id:
            por_id[int(usuario_id)]["roles"].append(int(rol_id))

    cur.execute("SELECT id, nombre, es_admin, puede_cargar, puede_maestros FROM rol ORDER BY nombre")
    roles = [{"id": int(i), "nombre": n, "es_admin": bool(a), "puede_cargar": bool(c), "puede_maestros": bool(m),
              "menus": [], "reportes_sueltos": 0, "usuarios": 0} for i, n, a, c, m in cur.fetchall()]
    rol_id = {r["id"]: r for r in roles}
    cur.execute("SELECT rol_id, menu_id, reporte_id FROM permiso ORDER BY rol_id, menu_id")
    for r, menu_id, reporte_id in cur.fetchall():
        if int(r) not in rol_id:
            continue
        if menu_id is not None:
            rol_id[int(r)]["menus"].append(int(menu_id))
        elif reporte_id is not None:
            rol_id[int(r)]["reportes_sueltos"] += 1
    for u in usuarios:
        for r in u["roles"]:
            if r in rol_id:
                rol_id[r]["usuarios"] += 1

    cur.execute("SELECT id, nombre, activo FROM menu ORDER BY orden, id")
    menus = [{"id": int(i), "nombre": n, "activo": bool(a)} for i, n, a in cur.fetchall()]
    return {"usuarios": usuarios, "roles": roles, "menus": menus}


def guardar_usuario(cur, datos: dict) -> str:
    email = str(datos.get("email") or "").strip().lower()
    if not EMAIL.match(email):
        raise ErrorUsuario("Email inválido: tiene que ser el de la cuenta de Microsoft con que entra (nombre@empresa.cl).")
    nombre = str(datos.get("nombre") or "").strip()[:150] or None
    activo = _bool(datos.get("activo", True))
    roles = _ids(datos.get("roles"), "roles")
    _existen(cur, "rol", roles, "el rol")
    usuario_id = _id(datos.get("id"))
    try:
        if usuario_id is None:
            cur.execute("INSERT INTO usuario (email, nombre, activo) VALUES (%s, %s, %s)", (email, nombre, activo))
            usuario_id = int(cur.lastrowid)
            mensaje = f"Usuario {email} agregado."
        else:
            _existen(cur, "usuario", [usuario_id], "el usuario")
            cur.execute("UPDATE usuario SET email = %s, nombre = %s, activo = %s WHERE id = %s",
                        (email, nombre, activo, usuario_id))
            mensaje = f"Usuario {email} guardado."
    except Exception as exc:
        if _duplicado(exc):
            raise ErrorUsuario(f"Ya existe un usuario con el email {email}.") from None
        raise
    cur.execute("DELETE FROM usuario_rol WHERE usuario_id = %s", (usuario_id,))
    for rol in roles:
        cur.execute("INSERT INTO usuario_rol (usuario_id, rol_id) VALUES (%s, %s)", (usuario_id, rol))
    if not roles:
        mensaje += " Sin roles no ve ningún reporte ni herramienta."
    return mensaje


def borrar_usuario(cur, datos: dict) -> str:
    usuario_id = _id(datos.get("id"))
    if usuario_id is None:
        raise ErrorUsuario("Falta el id del usuario.")
    cur.execute("SELECT email FROM usuario WHERE id = %s", (usuario_id,))
    fila = cur.fetchone()
    if not fila:
        raise ErrorUsuario(f"No existe el usuario {usuario_id}.")
    cur.execute("DELETE FROM usuario_rol WHERE usuario_id = %s", (usuario_id,))
    cur.execute("DELETE FROM usuario WHERE id = %s", (usuario_id,))
    return f"Usuario {fila[0]} eliminado."


def guardar_rol(cur, datos: dict) -> str:
    nombre = str(datos.get("nombre") or "").strip()[:100]
    if not nombre:
        raise ErrorUsuario("Falta el nombre del rol.")
    banderas = (_bool(datos.get("es_admin")), _bool(datos.get("puede_cargar")), _bool(datos.get("puede_maestros")))
    menus = _ids(datos.get("menus"), "menús")
    _existen(cur, "menu", menus, "el menú")
    rol_id = _id(datos.get("id"))
    try:
        if rol_id is None:
            cur.execute("INSERT INTO rol (nombre, es_admin, puede_cargar, puede_maestros) VALUES (%s, %s, %s, %s)",
                        (nombre, *banderas))
            rol_id = int(cur.lastrowid)
            mensaje = f"Rol {nombre} agregado."
        else:
            _existen(cur, "rol", [rol_id], "el rol")
            cur.execute("UPDATE rol SET nombre = %s, es_admin = %s, puede_cargar = %s, puede_maestros = %s WHERE id = %s",
                        (nombre, *banderas, rol_id))
            mensaje = f"Rol {nombre} guardado."
    except Exception as exc:
        if _duplicado(exc):
            raise ErrorUsuario(f"Ya existe un rol llamado {nombre}.") from None
        raise
    cur.execute("DELETE FROM permiso WHERE rol_id = %s AND menu_id IS NOT NULL", (rol_id,))
    for menu in menus:
        cur.execute("INSERT INTO permiso (rol_id, menu_id) VALUES (%s, %s)", (rol_id, menu))
    return mensaje


def borrar_rol(cur, datos: dict) -> str:
    rol_id = _id(datos.get("id"))
    if rol_id is None:
        raise ErrorUsuario("Falta el id del rol.")
    cur.execute("SELECT nombre FROM rol WHERE id = %s", (rol_id,))
    fila = cur.fetchone()
    if not fila:
        raise ErrorUsuario(f"No existe el rol {rol_id}.")
    cur.execute("SELECT COUNT(*) FROM usuario_rol WHERE rol_id = %s", (rol_id,))
    usuarios = int(cur.fetchone()[0])
    if usuarios:
        raise ErrorUsuario(f"El rol {fila[0]} tiene {usuarios} usuario(s): quítaselo antes de eliminarlo.")
    cur.execute("DELETE FROM permiso WHERE rol_id = %s", (rol_id,))
    cur.execute("DELETE FROM rol WHERE id = %s", (rol_id,))
    return f"Rol {fila[0]} eliminado."


ACCIONES = {
    "guardar_usuario": ("usuario", guardar_usuario),
    "borrar_usuario": (None, borrar_usuario),
    "guardar_rol": ("rol", guardar_rol),
    "borrar_rol": (None, borrar_rol),
}


def _main(req: func.HttpRequest) -> func.HttpResponse:
    email = web.usuario(req)
    conn = web.conexion_portal()
    try:
        with conn.cursor() as cur:
            if not portal.permisos_cursor(cur, email)["admin"]:
                return web.respuesta({"estado": "ERROR", "mensaje": "Sólo un administrador puede gestionar usuarios."}, 403)
            if req.method == "GET":
                return web.respuesta(listar(cur))
            try:
                cuerpo = req.get_json() or {}
            except ValueError:
                return web.respuesta({"estado": "ERROR", "mensaje": "Cuerpo JSON inválido."}, 400)
            if cuerpo.get("accion") not in ACCIONES:
                return web.respuesta({"estado": "ERROR", "mensaje": "accion no válida."}, 400)
            clave, funcion = ACCIONES[cuerpo["accion"]]
            try:
                mensaje = funcion(cur, (cuerpo.get(clave) if clave else cuerpo) or {})
                if not portal.permisos_cursor(cur, email)["admin"]:
                    raise ErrorUsuario("No puedes quitarte a ti mismo el acceso de administrador: "
                                       "pídeselo a otro administrador.")
            except ErrorUsuario as exc:
                conn.rollback()
                return web.respuesta({"estado": "ERROR", "mensaje": str(exc)}, 400)
        conn.commit()
    finally:
        conn.close()
    return web.respuesta({"estado": "OK", "mensaje": mensaje})


def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        resp = _main(req)
    except KeyError as exc:
        resp = web.respuesta({"estado": "ERROR", "mensaje": f"Falta la variable de entorno {exc} en la Static Web App."}, 500)
    except Exception as exc:  # noqa: BLE001
        logging.exception("Error en la API de usuarios")
        resp = web.respuesta({"estado": "ERROR", "mensaje": f"Error del servidor: {exc.__class__.__name__}: {exc}"}, 500)
    resp.headers["Cache-Control"] = "no-store"
    return resp
