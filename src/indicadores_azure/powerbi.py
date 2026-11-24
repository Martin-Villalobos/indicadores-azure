"""Pide a Power BI que actualice los modelos semánticos después de recalcular indicadores.

Usa la API REST de Power BI con una entidad de servicio (app registrada en Entra ID):
    POST https://api.powerbi.com/v1.0/myorg/groups/<área>/datasets/<modelo>/refreshes

Variables (si falta alguna, no hace nada y lo deja en el log):
    POWERBI_TENANT_ID, POWERBI_CLIENT_ID, POWERBI_CLIENT_SECRET
    POWERBI_WORKSPACE_ID   id del área de trabajo (no sirve "Mi área de trabajo")
    POWERBI_DATASET_IDS    ids de los modelos semánticos, separados por coma

Un error aquí nunca corta el job: los datos ya quedaron en MySQL y la actualización
programada de Power BI los recoge igual. Con licencia Pro, Power BI permite 8
actualizaciones al día por modelo (sumando las programadas y las de la API).
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request

log = logging.getLogger(__name__)

API = "https://api.powerbi.com/v1.0/myorg"
TIMEOUT = 30


def _config() -> dict | None:
    nombres = ("POWERBI_TENANT_ID", "POWERBI_CLIENT_ID", "POWERBI_CLIENT_SECRET", "POWERBI_WORKSPACE_ID",
               "POWERBI_DATASET_IDS")
    valores = {n: (os.getenv(n) or "").strip() for n in nombres}
    if not all(valores.values()):
        return None
    valores["POWERBI_DATASET_IDS"] = [d.strip() for d in valores["POWERBI_DATASET_IDS"].split(",") if d.strip()]
    return valores


def _token(cfg: dict) -> str:
    datos = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": cfg["POWERBI_CLIENT_ID"],
        "client_secret": cfg["POWERBI_CLIENT_SECRET"],
        "scope": "https://analysis.windows.net/powerbi/api/.default",
    }).encode()
    url = f"https://login.microsoftonline.com/{cfg['POWERBI_TENANT_ID']}/oauth2/v2.0/token"
    with urllib.request.urlopen(urllib.request.Request(url, data=datos), timeout=TIMEOUT) as resp:
        return json.loads(resp.read())["access_token"]


def _detalle(exc: urllib.error.HTTPError) -> str:
    try:
        return exc.read().decode("utf-8", "replace")[:500]
    except Exception:  # noqa: BLE001
        return ""


def actualizar_modelos() -> int:
    """Pide la actualización de cada modelo configurado. Devuelve cuántas pidió con éxito."""

    cfg = _config()
    if cfg is None:
        log.info("Power BI: sin POWERBI_* configuradas; no se pide actualizar el dashboard.")
        return 0
    try:
        token = _token(cfg)
    except Exception:  # noqa: BLE001
        log.exception("Power BI: no se pudo obtener el token de Entra ID.")
        return 0

    pedidas = 0
    for modelo in cfg["POWERBI_DATASET_IDS"]:
        url = f"{API}/groups/{cfg['POWERBI_WORKSPACE_ID']}/datasets/{modelo}/refreshes"
        peticion = urllib.request.Request(
            url, data=json.dumps({"notifyOption": "NoNotification"}).encode(), method="POST",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(peticion, timeout=TIMEOUT):
                pass
            pedidas += 1
            log.info("Power BI: actualización pedida para el modelo %s.", modelo)
        except urllib.error.HTTPError as exc:
            # 400 con otra actualización en curso o el límite diario alcanzado, 401/403 sin permisos.
            log.warning("Power BI: el modelo %s respondió %s: %s", modelo, exc.code, _detalle(exc))
        except Exception:  # noqa: BLE001
            log.exception("Power BI: falló la petición para el modelo %s.", modelo)
    return pedidas
