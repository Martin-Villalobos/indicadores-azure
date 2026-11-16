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
| `src/indicadores_azure/` | El job: `procesar.py` (entrada), `control.py` (registro en `control_carga`, carga en una transacción), `vigencias.py` (qué carga rige cada fecha), `lectores/` (uno por tipo de archivo), `icfp/` (cálculo del ICFP) y `recalculo.py` (cola de recálculos después de cada carga) |
| `sql/` | Tablas que necesita el job |
| `docker/` | Imagen del job |
| `web/` | Static Web App: `app/` (página) y `api/` (`/api/cargar` sube, `/api/estado` dice en qué quedó, `/api/dashboards` lista los reportes y `/api/reporte/<id>` abre uno) |
| `local/` | Script rclone que envía Reporte 1.117 y Velocidades desde el espejo FTP de la máquina local |
| `infra/` | Script que crea almacenamiento, cola, Event Grid, registro y job |
| `docs/DESPLIEGUE.md` | Paso a paso del despliegue |
| `config/entornos.toml` | Conexiones de cada entorno (`dev`, `prod`); el activo lo elige `ENTORNO` |
| `seeds/` | Datos de ejemplo que carga el seeder en dev |
| `dev/` | Web local (`servidor_web.py`), reemplaza a la Static Web App en dev |
| `docker-compose.yml` | Entorno dev completo: MySQL, Azurite, seeder, job y web |

## Cálculo del ICFP

Cuando el job completa una carga de Anexo 3, velocidades, exclusiones o flota, encola en `recalculo_pendiente` las fechas que esa carga rige (±1 día por el trasvasije) y las recalcula. El cálculo (`src/indicadores_azure/icfp/`) es el de indicadores-bi:

1. exigencia por hora desde el Anexo 3 vigente (suma de sus dos MH);
2. ICF e ICP iniciales con las expediciones OK de velocidades y las plazas de `dim_bus`;
3. trasvasije de extremos (5.3.1.6.6), copiado de `icf_icp/correcciones.py`;
4. km programados (distancia base · salidas), km válidos y exclusiones DTPM (hoja ICFP-IE).

Cada corrida es un `calculo` nuevo; `v_icfp_dashboard` muestra el último por fecha y `v_icfp_mes` el ICFP y los km con derecho a pago del mes. A mano: `indicadores-azure-icfp --desde 2026-02-01 --hasta 2026-02-28` o `indicadores-azure-icfp --pendientes`.

## Agregar un tipo de archivo

1. Crear `src/indicadores_azure/lectores/<tipo>.py` con `TABLA`, `COLUMNAS`, `EXTENSIONES`, `VIGENCIA` (columnas con el rango de fechas que cubre el archivo) y `leer(contenido) -> filas`. Los errores para el usuario se lanzan con `ErrorDeCarga` diciendo hoja, fila y columna.
2. Registrarlo en `lectores/__init__.py`, agregarlo a `tipo_archivo` (`sql/03_vigencias.sql`) y crear la tabla en `sql/`.
3. Si se sube desde la web: agregarlo a `TIPOS` en `web/api/cargar/__init__.py` y al `<select id="tipo">` de `web/app/index.html`.
4. Pruebas en `tests/`, luego nueva imagen del job.

## Entornos

| | dev | prod |
|---|---|---|
| Rama | `dev` (y ramas de trabajo) | `main`: lo que se mezcla aquí se publica en Azure |
| Base | MySQL 8 local (docker) con semillas | Azure Database for MySQL |
| Archivos | Azurite, el emulador local de Azure Storage | Cuenta de almacenamiento `stindicadoresprueba` |
| Web | `dev/servidor_web.py` en http://localhost:8080, login simulado | Static Web App con login de Entra ID |
| Job | Revisa `entrada/` cada 5 s | Container Apps Job disparado por la cola |

El código es el mismo en los dos. Lo que cambia son las conexiones, que salen de
`config/entornos.toml` según la variable `ENTORNO` (`dev` o `prod`; sin ella es `prod`).
Cualquier variable de entorno (`DB_HOST`, `DB_PASSWORD`, `BLOB_CONNECTION_STRING`...)
gana sobre el archivo, así que en Azure todo sigue como antes. Las claves de prod nunca van
en el archivo: sólo en `.env` (no versionado) o en los secretos de Azure.

### Levantar dev (necesita Docker Desktop)

```
docker compose up --build
```

- Web: http://localhost:8080 (entras como `dev@local` con rol "empleado"; se cambia con `DEV_USUARIO`).
- MySQL: `localhost:3306`, base `indicadores_bi`, usuario y clave `indicadores` (para DBeaver).
- Al partir, el servicio `semilla` crea las tablas de `sql/` y carga `seeds/` si la base está vacía.
- Lo que subas desde la web lo procesa el job local igual que en Azure.

Comandos útiles:

```
docker compose run --rm semilla indicadores-azure-semilla --reiniciar   # base de nuevo, sólo con semillas
docker compose down -v                                                   # borra base y archivos locales
```

Si el puerto 3306 u 8080 ya está ocupado: `MYSQL_PUERTO_LOCAL=3307 WEB_PUERTO_LOCAL=8081 docker compose up`.

Para agregar datos de ejemplo, crear otro `seeds/NN_<tema>.sql`. El seeder se niega a correr si `ENTORNO` no es `dev`.

### Correr el job o la web fuera de docker

Con `docker compose up mysql azurite semilla` corriendo, copiar `.env.example` a `.env` (trae `ENTORNO=dev`) y:

```
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
indicadores-azure-procesar        # job
python dev/servidor_web.py        # web
```

Para apuntar a prod desde el PC: en `.env` poner `ENTORNO=prod` y completar `DB_USER`, `DB_PASSWORD`, `DB_SSL_CA` y `BLOB_CONNECTION_STRING`.

## Pruebas

```
pip install -e ".[test]"
pytest
```
