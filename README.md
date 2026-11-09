# indicadores-azure

Prueba de arquitectura en Azure para los indicadores de operación: una web interna con login que muestra los reportes de Power BI y recibe archivos, y un job que lee esos archivos y los carga en MySQL.

Es un proyecto aparte de `indicadores-bi`: comparte las reglas de negocio, no el código.

```
Web (Static Web Apps) ──sube──┐
                              ├──► Blob cargas/<tipo>/entrada/ ──Event Grid──► Cola ──► Container Apps Job
Máquina local (rclone) ──sube─┘                                                        (src/indicadores_azure)
                                                                                         │
      Web consulta /api/estado ◄── cargas/<tipo>/procesados|errores/ ◄───────────────────┴──► MySQL de Azure
```

Hay un solo lector de archivos, el job. La web y la máquina local sólo suben.

## Carpetas

| Carpeta | Qué hay |
|---|---|
| `src/indicadores_azure/` | El job: `procesar.py` (entrada), `control.py` (registro en `control_carga`, carga en una transacción), `lectores/` (uno por tipo de archivo) |
| `sql/` | Tablas que necesita el job |
| `docker/` | Imagen del job |
| `web/` | Static Web App: `app/` (página) y `api/` (`/api/cargar` sube, `/api/estado` dice en qué quedó) |
| `local/` | Scripts rclone para enviar Reporte 117 y Velocidades desde la máquina local |
| `infra/` | Script que crea almacenamiento, cola, Event Grid, registro y job |
| `docs/DESPLIEGUE.md` | Paso a paso del despliegue |

## Agregar un tipo de archivo

1. Crear `src/indicadores_azure/lectores/<tipo>.py` con `TABLA`, `COLUMNAS`, `EXTENSIONES` y `leer(contenido) -> filas`. Los errores para el usuario se lanzan con `ErrorDeCarga` diciendo hoja, fila y columna.
2. Registrarlo en `lectores/__init__.py` y crear la tabla en `sql/`.
3. Si se sube desde la web: agregarlo a `TIPOS` en `web/api/cargar/__init__.py` y al `<select id="tipo">` de `web/app/index.html`.
4. Pruebas en `tests/`, luego nueva imagen del job.

## Desarrollo local

```
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[test]"
pytest
```

Para correr el job contra Azure desde el PC: copiar `.env.example` a `.env`, completar y ejecutar `indicadores-azure-procesar`. El `.env` no se sube al repo.
