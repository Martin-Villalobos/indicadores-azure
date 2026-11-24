"""Menú de Power BI y permisos por usuario, leídos de la base portal_reportes.

El usuario es el email con que inició sesión en Entra ID (userDetails del header
x-ms-client-principal, que pone Static Web Apps; el navegador no lo puede falsificar).
Un usuario ve un reporte si alguno de sus roles tiene permiso sobre el reporte o sobre su menú.
Esquema: web/sql/portal_reportes.sql.
"""

from __future__ import annotations

_VISIBLES = """
    FROM usuario u
    JOIN usuario_rol ur ON ur.usuario_id = u.id
    JOIN permiso p      ON p.rol_id = ur.rol_id
    JOIN reporte r      ON r.id = p.reporte_id OR r.menu_id = p.menu_id
    JOIN menu m         ON m.id = r.menu_id
    WHERE u.email = %s AND u.activo = 1 AND m.activo = 1 AND r.activo = 1
"""


def menu_usuario(conn, email: str) -> list[dict]:
    """Menús del usuario, en orden, cada uno con sus reportes. Sin la URL de Power BI."""

    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT m.id, m.nombre, m.icono, m.orden, r.id, r.nombre, r.descripcion, r.orden,"
            " r.ancho_lienzo, r.alto_lienzo"
            + _VISIBLES + "ORDER BY m.orden, m.id, r.orden, r.id",
            (email,),
        )
        filas = cur.fetchall()

    menus: dict[int, dict] = {}
    for menu_id, menu, icono, _, reporte_id, reporte, descripcion, _, ancho, alto in filas:
        m = menus.setdefault(menu_id, {"id": menu_id, "nombre": menu, "icono": icono, "reportes": []})
        m["reportes"].append({"id": reporte_id, "nombre": reporte, "descripcion": descripcion or "",
                              "ancho": ancho, "alto": alto})
    return list(menus.values())


def url_reporte(conn, email: str, reporte_id: int) -> str | None:
    """URL de Power BI del reporte si el usuario lo puede ver; None si no existe o no tiene permiso."""

    with conn.cursor() as cur:
        cur.execute("SELECT r.url_powerbi" + _VISIBLES + "AND r.id = %s LIMIT 1", (email, reporte_id))
        fila = cur.fetchone()
    return fila[0] if fila else None


def permisos_cursor(cur, email: str) -> dict:
    """Qué herramientas de la web puede usar el usuario, según sus roles.

    {"admin": bool, "cargar": bool, "maestros": bool}. Un rol administrador puede todo.
    Un usuario inactivo o que no está en la tabla no puede nada.
    """

    cur.execute(
        """SELECT COALESCE(MAX(ro.es_admin), 0), COALESCE(MAX(ro.puede_cargar), 0), COALESCE(MAX(ro.puede_maestros), 0)
           FROM usuario u
           JOIN usuario_rol ur ON ur.usuario_id = u.id
           JOIN rol ro         ON ro.id = ur.rol_id
           WHERE u.email = %s AND u.activo = 1""",
        (email,),
    )
    admin, cargar, maestros = cur.fetchone() or (0, 0, 0)
    admin = bool(admin)
    return {"admin": admin, "cargar": admin or bool(cargar), "maestros": admin or bool(maestros)}


def permisos(conn, email: str) -> dict:
    with conn.cursor() as cur:
        return permisos_cursor(cur, email)
