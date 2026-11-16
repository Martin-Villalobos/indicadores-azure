import io
from datetime import date, time
from decimal import Decimal

import pytest

from indicadores_azure.control import ErrorDeCarga
from indicadores_azure.lectores import anexo3, exclusiones, velocidades


def libro(hojas: dict[str, list]) -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    wb.remove(wb.active)
    for nombre, filas in hojas.items():
        hoja = wb.create_sheet(nombre)
        for fila in filas:
            hoja.append(list(fila))
    salida = io.BytesIO()
    wb.save(salida)
    return salida.getvalue()


ENC3 = list(anexo3.ENCABEZADOS.keys())
ENC3[ENC3.index("AGRUPACION MH")] = "AGRUPACIÓN MH"
ANEXO3 = [
    ("PROGRAMA DE OPERACIÓN",),
    ("UNIDAD DE SERVICIO", None, None, "U16"),
    ("AÑO", None, None, 2025),
    ("FECHA INICIO", None, None, "11/09/2025"),
    ("FECHA TÉRMINO", None, None, "31/12/2025"),
    (),
    ENC3,
    ("U16", 1603, "503", "IDA", "LABORAL", "05:30", 18.5, 20.1, 22.4, 3, 90, "PMA", "F1", "SI"),
    ("U16", "T503 00R", "503", "REGRESO", "DOMINGO", "23:00:00", "--", None, None, 0, 0, None, None, None),
]


def test_anexo3_lee_cabecera_y_codigos_como_texto():
    filas = list(anexo3.leer(libro({"Parámetros": ANEXO3, "Reconocimiento KM": [("X",)]})))
    assert len(filas) == 2
    f = dict(zip(anexo3.COLUMNAS, filas[0]))
    assert f["fecha_inicio"] == date(2025, 9, 11) and f["fecha_termino"] == date(2025, 12, 31) and f["anio"] == 2025
    assert f["codigo_ts_servicio"] == "1603" and f["mh"] == time(5, 30) and f["velocidad_km_hora"] == Decimal("18.5")
    g = dict(zip(anexo3.COLUMNAS, filas[1]))
    assert g["velocidad_km_hora"] is None and g["numero_salidas"] == 0


def test_anexo3_mh_que_no_es_media_hora():
    malo = ANEXO3[:7] + [ANEXO3[7][:5] + ("05:15",) + ANEXO3[7][6:]]
    with pytest.raises(ErrorDeCarga, match="fila 8, columna MH"):
        list(anexo3.leer(libro({"P": malo})))


def test_anexo3_sin_fechas_en_cabecera():
    with pytest.raises(ErrorDeCarga, match="FECHA INICIO"):
        list(anexo3.leer(libro({"P": ANEXO3[:3] + [(), (), ()] + ANEXO3[6:]})))


ENCV = ["UN", "Operador", "Servicio", "Patente", "Sentido", "Inicio", "Intervalo de Salida", "Control", "Fin",
        "Distancia (m)", "Tiempo (hh:mm:ss)", "Velocidad (Km/hr)", "Capacidad (#)", "Estado", "Fecha", "Día",
        "Tipo Día", "Período", "Cada 5 minutos", "Cada media hora"]


def vel(un, fecha="08/02/2026"):
    return (un, "OP", "503", "ABCD12", "Ida", "06:01:00", "-", "06:30:00", "07:10:00", 15000, "01:09:00", 13.04,
            90, "OK", fecha, 8, "Domingo", "PMA", "06:00:00", "06:00:00")


def test_velocidades_solo_u16():
    contenido = libro({"velocidad": [ENCV, vel("U16"), vel("U5"), vel(16.0), vel("U1")]})
    filas = list(velocidades.leer(contenido))
    assert [f[0] for f in filas] == [2, 4]
    f = dict(zip(velocidades.COLUMNAS, filas[0]))
    assert f["fecha"] == date(2026, 2, 8) and f["intervalo_salida"] is None and f["servicio"] == "503"


def test_velocidades_sin_u16_o_dos_fechas():
    with pytest.raises(ErrorDeCarga, match="unidad 16"):
        list(velocidades.leer(libro({"velocidad": [ENCV, vel("U5")]})))
    with pytest.raises(ErrorDeCarga, match="más de una fecha"):
        list(velocidades.leer(libro({"velocidad": [ENCV, vel("U16"), vel("U16", "09/02/2026")]})))


def test_exclusiones_tres_hojas_con_comodin():
    contenido = libro({
        "ICFP-IE": [("Fecha", "US", "Código TS", "Sentido", "Periodo"),
                    ("03/03/2026", "U16", "T503 00I", "Ida", 7), ("03/03/2026", "U5", "X", "Ida", 7),
                    ("04/03/2026", "U16", "*", "*", "*")],
        "IP-Base": [("Fecha", "US", "Código TS", "Sentido", "Id Expedición", "Correlativo Paradero"),
                    ("05/03/2026", "U16", "T503 00I", "Ida", 123, "*")],
        "IP-Extra": [("Fecha", "US", "Código TS", "Sentido"), ("06/03/2026", "U16", "T503 00R", "Regreso")],
    })
    filas = [dict(zip(exclusiones.COLUMNAS, f)) for f in exclusiones.leer(contenido)]
    assert [(f["hoja"], f["fecha"].day, f["periodo"]) for f in filas] == [
        ("ICFP-IE", 3, "7"), ("ICFP-IE", 4, "*"), ("IP-Base", 5, None), ("IP-Extra", 6, None)]
    assert filas[2]["id_expedicion"] == "123" and filas[2]["correlativo_paradero"] == "*"


def test_exclusiones_periodo_fuera_de_rango():
    contenido = libro({"ICFP-IE": [("Fecha", "US", "Código TS", "Sentido", "Periodo"),
                                   ("03/03/2026", "U16", "T", "Ida", 80)]})
    with pytest.raises(ErrorDeCarga, match="periodo '80'"):
        list(exclusiones.leer(contenido))


def test_flota_csv_punto_y_coma_y_patente_normalizada():
    from indicadores_azure.lectores import flota

    filas = list(flota.leer("ppu;tipo_bus;capacidad\nAB-CD12;B1;90\nEFGH34;C1;\n".encode()))
    assert filas == [(2, "ABCD12", "B1", 90), (3, "EFGH34", "C1", None)]
    with pytest.raises(ErrorDeCarga, match="repetida"):
        list(flota.leer(b"ppu,tipo_bus,capacidad\nAB12,B1,90\nab-12,B1,90\n"))
    with pytest.raises(ErrorDeCarga, match="CAPACIDAD"):
        list(flota.leer(b"ppu,tipo\nAB12,B1\n"))
