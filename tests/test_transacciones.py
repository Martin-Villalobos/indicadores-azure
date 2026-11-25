import io
import zipfile
from datetime import date, datetime

import pytest

from indicadores_azure.control import ErrorDeCarga
from indicadores_azure.lectores import LECTORES, transacciones

ENC = "Entidad;Sitio;Fecha;Chip;Tarjeta;NTT;Tipo Trx;Contrato;Monto;Estado;Liquidacion;Consolidado;csa;Scsa;ctla;Cla;BNP;sa;CODIGOSITIO;CL;CRC"
BUS = "U16 - Gran Americas US16;VLZY-71;28/10/2026 23:58:15;3588217580;114321086;47;Uso Monedero;Valor;795;LIQU;LQ20261030001.40;PQ20261029000177_889999_0040.ZIP;2;0;2;783;0;0;11101;960;0"
ZP = "U16 - Gran Americas US16;RM-1234;29/10/2026 07:01:00;1;2;3;Uso Monedero;Tam DTPM (564);0;LIQU;LQ20261030001.40;PQ1.ZIP;0;0;0;0;0;0;1;997;0"
PIE = "Cantidad TRX :{n}\nCantidad Preliquidado  : 0\nCantidad Liquidado : {n}\nCantidad Pre-Liquidado : 0\n \nNomenclatura de campos LVAT\nCodigolinea = CL\n"


def txt(*filas, n=None):
    n = len(filas) if n is None else n
    return ("Fecha Generacion30/10/2026 09:45:39\n" + ENC + "\n" + "\n".join(filas) + "\n" + PIE.format(n=n)).encode()


def comprimido(contenido: bytes, nombre="Gran Americas US16_202610300944.txt") -> bytes:
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w") as zf:
        zf.writestr(nombre, contenido)
        zf.writestr("LQ20261030001.40 Entidad.US16.pdf", b"%PDF-1.4")
    return salida.getvalue()


def test_registrado():
    assert LECTORES["transacciones"] is transacciones


def test_zip_lee_bus_y_zona_paga():
    filas = [dict(zip(transacciones.COLUMNAS, f)) for f in transacciones.leer(comprimido(txt(BUS, ZP)))]
    assert len(filas) == 2
    bus, zp = filas
    assert bus["archivo_txt"] == "Gran Americas US16_202610300944.txt" and bus["numero_fila"] == 3
    assert bus["fecha_generacion"] == datetime(2026, 10, 30, 9, 45, 39)
    assert bus["ppu"] == "VLZY71" and bus["es_zona_paga"] == 0
    assert bus["fecha"] == date(2026, 10, 28) and bus["mes"] == 202610  # mes de la validación, no del archivo
    assert bus["chip"] == 3588217580 and bus["monto"] == 795 and bus["cl"] == 960 and bus["crc"] == 0
    assert bus["fecha_liquidacion"] == date(2026, 10, 30) and bus["contrato"] == "Valor"
    assert zp["ppu"] is None and zp["es_zona_paga"] == 1 and zp["sitio"] == "RM-1234"
    assert len(filas[0]) == len(transacciones.COLUMNAS)


def test_txt_suelto_y_latin1():
    filas = list(transacciones.leer(txt(BUS.replace("Valor", "Escolar Básica")).decode().encode("latin-1")))
    assert dict(zip(transacciones.COLUMNAS, filas[0]))["contrato"] == "Escolar Básica"


def test_pie_que_no_calza():
    with pytest.raises(ErrorDeCarga, match="Cantidad TRX 3 pero el archivo trae 2"):
        list(transacciones.leer(comprimido(txt(BUS, ZP, n=3))))


def test_sin_pie():
    contenido = ("Fecha Generacion30/10/2026 09:45:39\n" + ENC + "\n" + BUS + "\n").encode()
    with pytest.raises(ErrorDeCarga, match="falta el pie"):
        list(transacciones.leer(contenido))


def test_otra_unidad():
    with pytest.raises(ErrorDeCarga, match="no es de la unidad 16"):
        list(transacciones.leer(txt(BUS.replace("U16 - Gran Americas US16", "U5 - Otro"))))


def test_columnas_y_fechas_malas():
    with pytest.raises(ErrorDeCarga, match="línea 3: se esperan 21 columnas"):
        list(transacciones.leer(txt(BUS + ";extra")))
    with pytest.raises(ErrorDeCarga, match="columna Fecha"):
        list(transacciones.leer(txt(BUS.replace("28/10/2026 23:58:15", "2026-10-28"))))
    with pytest.raises(ErrorDeCarga, match="encabezado"):
        list(transacciones.leer(txt(BUS).replace(b"Entidad;Sitio", b"Sitio;Entidad")))
    with pytest.raises(ErrorDeCarga, match="Fecha Generacion"):
        list(transacciones.leer(b"hola\n"))


def test_zip_sin_txt():
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w") as zf:
        zf.writestr("a.pdf", b"x")
    with pytest.raises(ErrorDeCarga, match=r"no trae el archivo"):
        list(transacciones.leer(salida.getvalue()))


def test_web_acepta_zip():
    import importlib.util
    from pathlib import Path

    texto = (Path(__file__).parents[1] / "web/api/cargar/__init__.py").read_text(encoding="utf-8")
    assert '"transacciones": {".zip", ".txt"}' in texto
