"""powerbi.actualizar_modelos: sin variables no hace nada; con ellas pide token y una actualización por modelo."""

from __future__ import annotations

import io
import json
import urllib.error

import pytest

from indicadores_azure import powerbi

VARIABLES = {
    "POWERBI_TENANT_ID": "tenant", "POWERBI_CLIENT_ID": "app", "POWERBI_CLIENT_SECRET": "secreto",
    "POWERBI_WORKSPACE_ID": "area", "POWERBI_DATASET_IDS": "m1, m2",
}


class Respuesta(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def peticiones(monkeypatch):
    hechas = []

    def urlopen(req, timeout):
        hechas.append(req)
        if "login.microsoftonline.com" in req.full_url:
            return Respuesta(json.dumps({"access_token": "tok"}).encode())
        if req.full_url.endswith("/m2/refreshes"):
            raise urllib.error.HTTPError(req.full_url, 400, "Bad Request", {}, io.BytesIO(b"limite diario"))
        return Respuesta(b"")

    monkeypatch.setattr(powerbi.urllib.request, "urlopen", urlopen)
    return hechas


def test_sin_variables_no_llama(monkeypatch, peticiones):
    for nombre in VARIABLES:
        monkeypatch.delenv(nombre, raising=False)
    assert powerbi.actualizar_modelos() == 0
    assert peticiones == []


def test_pide_una_actualizacion_por_modelo(monkeypatch, peticiones):
    for nombre, valor in VARIABLES.items():
        monkeypatch.setenv(nombre, valor)
    assert powerbi.actualizar_modelos() == 1  # m2 falla y no corta
    token, m1, m2 = peticiones
    assert token.full_url == "https://login.microsoftonline.com/tenant/oauth2/v2.0/token"
    assert m1.full_url == "https://api.powerbi.com/v1.0/myorg/groups/area/datasets/m1/refreshes"
    assert m1.get_method() == "POST" and m1.headers["Authorization"] == "Bearer tok"
    assert m2.full_url.endswith("/datasets/m2/refreshes")


def test_token_falla_no_corta(monkeypatch):
    for nombre, valor in VARIABLES.items():
        monkeypatch.setenv(nombre, valor)

    def urlopen(req, timeout):
        raise OSError("sin red")

    monkeypatch.setattr(powerbi.urllib.request, "urlopen", urlopen)
    assert powerbi.actualizar_modelos() == 0
