"""Servidor local de la web para el entorno dev (reemplaza a la Static Web App).

    python dev/servidor_web.py            # http://localhost:8080

Sirve ``web/app`` y ejecuta las mismas funciones de ``web/api`` que corren en Azure,
sin modificarlas: arma el ``azure.functions.HttpRequest`` y devuelve su respuesta.
Las variables que en Azure vienen de la Static Web App (BLOB_CONNECTION_STRING,
DASHBOARDS...) se toman de ``config/entornos.toml`` según ENTORNO (o de las variables
de entorno, que tienen prioridad).

El login de Azure se simula: todo el que entra es ``DEV_USUARIO`` con el rol "empleado".
"""

from __future__ import annotations

import base64
import importlib.util
import json
import mimetypes
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from indicadores_azure.config import exportar_al_entorno  # noqa: E402

APP = RAIZ / "web" / "app"
API = RAIZ / "web" / "api"


def _principal() -> dict:
    usuario = os.getenv("DEV_USUARIO", "dev@local")
    return {
        "identityProvider": "dev",
        "userId": "dev",
        "userDetails": usuario,
        "userRoles": ["anonymous", "authenticated", "empleado"],
    }


_funciones: dict[str, object] = {}


def _funcion(nombre: str):
    """Carga web/api/<nombre>/__init__.py (una vez) y devuelve su ``main``."""

    if nombre not in _funciones:
        archivo = API / nombre / "__init__.py"
        if not archivo.exists():
            return None
        spec = importlib.util.spec_from_file_location(f"api_{nombre}", archivo)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        _funciones[nombre] = modulo.main
    return _funciones[nombre]


def _parametros_ruta(nombre: str, resto: str) -> dict[str, str] | None:
    """Arma route_params según el "route" de function.json (por ejemplo "reporte/{id}").

    Devuelve None si la ruta pedida no calza con la de la función.
    """

    try:
        bindings = json.loads((API / nombre / "function.json").read_text(encoding="utf-8"))["bindings"]
        plantilla = next(b.get("route", nombre) for b in bindings if b.get("type") == "httpTrigger")
    except (OSError, ValueError, KeyError, StopIteration):
        plantilla = nombre
    esperadas = plantilla.split("/")[1:]
    pedidas = resto.split("/") if resto else []
    if len(esperadas) != len(pedidas):
        return None
    parametros = {}
    for esperada, pedida in zip(esperadas, pedidas):
        if esperada.startswith("{") and esperada.endswith("}"):
            parametros[esperada[1:-1].split(":")[0].rstrip("?")] = pedida
        elif esperada != pedida:
            return None
    return parametros


class Manejador(BaseHTTPRequestHandler):
    server_version = "indicadores-dev"

    def _enviar(self, status: int, cuerpo: bytes, tipo: str = "application/json", cabeceras: dict | None = None):
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(cuerpo)))
        for k, v in (cabeceras or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(cuerpo)

    def _api(self, ruta: str, consulta: str):
        import azure.functions as func

        nombre, _, resto = ruta.partition("/")
        funcion = _funcion(nombre)
        parametros = _parametros_ruta(nombre, resto)
        if funcion is None or parametros is None:
            return self._enviar(404, b'{"mensaje": "API no encontrada"}')
        largo = int(self.headers.get("Content-Length") or 0)
        cabeceras = {k.lower(): v for k, v in self.headers.items()}
        cabeceras["x-ms-client-principal"] = base64.b64encode(json.dumps(_principal()).encode()).decode()
        req = func.HttpRequest(
            method=self.command,
            url=f"http://{self.headers.get('Host', 'localhost')}{self.path}",
            headers=cabeceras,
            params=dict(parse_qsl(consulta)),
            route_params=parametros,
            body=self.rfile.read(largo) if largo else b"",
        )
        resp = funcion(req)
        cabeceras_resp = {k: v for k, v in resp.headers.items() if k.lower() not in ("content-type", "content-length")}
        self._enviar(resp.status_code, resp.get_body(), resp.mimetype or "application/octet-stream", cabeceras_resp)

    def _ruta(self):
        partes = urlsplit(self.path)
        ruta = partes.path
        if ruta == "/.auth/me":
            return self._enviar(200, json.dumps({"clientPrincipal": _principal()}).encode())
        if ruta.startswith("/.auth/"):
            return self._enviar(302, b"", "text/plain", {"Location": "/"})
        if ruta.startswith("/api/"):
            return self._api(ruta[len("/api/"):].strip("/"), partes.query)
        archivo = (APP / ruta.lstrip("/")).resolve()
        if archivo.is_dir():
            archivo = archivo / "index.html"
        if APP not in archivo.parents or not archivo.is_file() or archivo.name == "staticwebapp.config.json":
            return self._enviar(404, b"No encontrado", "text/plain")
        tipo = mimetypes.guess_type(archivo.name)[0] or "application/octet-stream"
        self._enviar(200, archivo.read_bytes(), tipo)

    do_GET = do_POST = do_HEAD = _ruta


def main() -> None:
    entorno = exportar_al_entorno()
    if entorno != "dev":
        print(f"Aviso: ENTORNO={entorno}; la web local usará las conexiones de ese entorno.", file=sys.stderr)
    host = os.getenv("WEB_HOST", "127.0.0.1")
    puerto = int(os.getenv("WEB_PUERTO", "8080"))
    print(f"Web local ({entorno}) en http://{'localhost' if host in ('0.0.0.0', '127.0.0.1') else host}:{puerto}")
    ThreadingHTTPServer((host, puerto), Manejador).serve_forever()


if __name__ == "__main__":
    main()
