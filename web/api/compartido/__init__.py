"""Código compartido por las funciones de web/api (Azure Functions agrega web/api al sys.path).

vigencias.py es una copia exacta de src/indicadores_azure/vigencias.py: la web no instala el
paquete del job. tests/test_web_archivos.py verifica que no se desincronicen; para actualizarla:
    cp src/indicadores_azure/vigencias.py web/api/compartido/vigencias.py
"""
