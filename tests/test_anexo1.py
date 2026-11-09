from datetime import date, time

import pytest

from conftest import ANEXO1_OK, excel
from indicadores_azure.control import ErrorDeCarga
from indicadores_azure.lectores import anexo1


def test_lee_cabecera_y_filas():
    filas = list(anexo1.leer(excel(ANEXO1_OK)))
    assert len(filas) == 2
    assert filas[0] == (7, "U1", 2026, "T201 00I", "201", "IDA", "LABORAL", 1, time(5, 30), time(6, 29), date(2026, 3, 1), date(2026, 12, 31))
    assert filas[1][0] == 9 and filas[1][6] == "SÁBADO"
    assert len(filas[0]) == len(anexo1.COLUMNAS)


def test_archivo_que_no_es_excel():
    with pytest.raises(ErrorDeCarga, match="no es un Excel"):
        list(anexo1.leer(b"hola"))


def test_sin_encabezados():
    with pytest.raises(ErrorDeCarga, match="No se encontró la fila de encabezados"):
        list(anexo1.leer(excel([("A", "B"), (1, 2)])))


def test_hora_invalida_indica_fila_y_columna():
    datos = ANEXO1_OK[:6] + [("T201 00I", "201", "IDA", "LABORAL", 1, "25 horas", "06:29")]
    with pytest.raises(ErrorDeCarga, match=r"fila 7, columna HORA INICIO"):
        list(anexo1.leer(excel(datos)))


def test_falta_valor_obligatorio():
    datos = ANEXO1_OK[:6] + [("T201 00I", "201", None, "LABORAL", 1, "05:30", "06:29")]
    with pytest.raises(ErrorDeCarga, match="falta el valor de la columna SENTIDO"):
        list(anexo1.leer(excel(datos)))
