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
| `sql/` | Tablas que necesita el job. Se aplican solas: el job corre los archivos pendientes al partir (`migracion_aplicada`) |
| `datos_iniciales/` | Anexos y otros archivos que el job carga solo en una base nueva (ver su README) |
| `docker/` | Imagen del job |
| `web/` | Static Web App: `app/` (página) y `api/` (`/api/cargar` sube, `/api/estado` dice en qué quedó, `/api/dashboards` arma el menú de reportes desde la base `portal_reportes` y `/api/reporte/<id>` abre uno, `/api/yo` dice qué herramientas ve el usuario según su rol y `/api/usuarios` es el mantenedor de usuarios y roles) y `sql/portal_reportes.sql` (esquema de esa base, se aplica a mano) |
| `local/` | Script rclone que envía Reporte 1.117 y Velocidades desde el espejo FTP de la máquina local |
| `infra/` | Script que crea almacenamiento, cola, Event Grid, registro y job |
| `docs/DESPLIEGUE.md` | Paso a paso del despliegue |
| `config/entornos.toml` | Conexiones de cada entorno (`dev`, `prod`); el activo lo elige `ENTORNO` |
| `seeds/` | Datos de ejemplo que carga el seeder en dev |
| `dev/` | Web local (`servidor_web.py`), reemplaza a la Static Web App en dev |
| `docker-compose.yml` | Entorno dev completo: MySQL, Azurite, seeder, job y web |

## Archivos cargados (web)

En la pestaña **Cargar archivos**, debajo del formulario, se listan los archivos COMPLETADO de cada tipo (`/api/archivos`):

- **Anexos y exclusiones**: una fila por tramo vigente ("cortado"): si un anexo más corto cubre parte de las fechas de otro, el otro rige sólo el resto.
- **Velocidades**: una fila por archivo con su día.
- **Descargar** baja el original desde el blob.
- **Eliminar**: la carga queda ELIMINADO (sus filas quedan como historia) y sus fechas pasan al archivo que corresponda por la regla, o a ninguno. Volver a subir el mismo archivo la reactiva.
- **Cambiar fechas** (anexos): cambia `control_carga.vigencia_desde/hasta` y se vuelve a decidir qué archivo rige cada día. A igual largo gana el último cambiado.
- **Reemplazar**: sube el archivo nuevo con `?reemplaza=<carga_id>`. Cuando el job lo carga, elimina el anterior; si el nuevo falla, no se toca nada.

Antes de confirmar, la web muestra lo que cambia: tramos que pasan de un archivo a otro, días que quedan sin archivo y fechas que se recalculan. Al confirmar, se encola el recálculo y se avisa al job.

La lógica está en `src/indicadores_azure/vigencias.py` (`reconstruir`, `eliminar_carga`, `cambiar_fechas`). La web usa una copia en `web/api/compartido/vigencias.py`, y un test revisa que sean iguales.

Un cálculo cubre siempre todo el rango pedido, aunque algunas fechas queden sin datos, y `v_calculo_vigente` toma el último cálculo que cubre cada fecha. Así, al eliminar un archivo, los resultados viejos de esas fechas dejan de verse.

## Cálculo del ICFP

Cuando el job completa una carga de Anexo 3, velocidades, exclusiones o flota, encola en `recalculo_pendiente` las fechas que esa carga rige (±1 día por el trasvasije) y las recalcula. El cálculo (`src/indicadores_azure/icfp/`) es el de indicadores-bi:

1. exigencia por hora desde el Anexo 3 vigente (suma de sus dos MH);
2. ICF e ICP iniciales con las expediciones OK de velocidades y las plazas de `dim_bus`;
3. trasvasije de extremos (5.3.1.6.6), copiado de `icf_icp/correcciones.py`;
4. km programados (distancia base · salidas), km válidos y exclusiones DTPM (hoja ICFP-IE).

Cada corrida es un `calculo` nuevo; `v_icfp_dashboard` muestra el último por fecha y `v_icfp_mes` el ICFP y los km con derecho a pago del mes. A mano: `indicadores-azure-icfp --desde 2026-02-01 --hasta 2026-02-28` o `indicadores-azure-icfp --pendientes`.

## Transacciones

El tipo `transacciones` carga los `TRX_ACUM_DIA*.zip` diarios de Sonda (sólo el `.txt` LVAT de adentro) en `raw_transacciones`, una fila por validación. El archivo se rechaza si alguna fila no es de la U16 o si las filas no calzan con "Cantidad TRX" del pie. No tienen vigencia: cada archivo trae lo liquidado ese día (incluidas validaciones atrasadas) y se suman.

- `v_transacciones`: las filas de cargas COMPLETADO con `nombre_servicio` y `codigo_ts_servicio` (por el CL, desde `dim_codigo_linea`) y `tipo_dia` (del archivo de velocidades vigente). En zona paga (`sitio` RM-xxxx, `es_zona_paga = 1`) el servicio queda NULL.
- `v_transacciones_mes`: q del mes por fecha de validación, sin el Ajuste ZPM. Más el Ajuste ZPM de la liquidación da los "TRX totales" de la carta de pago (cuadró exacto en marzo 2026 y a 84 en abril).
- `transacciones_bus_sin_servicio` cuenta las validaciones en bus con un CL que no está en `dim_codigo_linea`: si no es 0, falta agregar esa línea en `sql/15_transacciones.sql`.

## Agregar un tipo de archivo

1. Crear `src/indicadores_azure/lectores/<tipo>.py` con `TABLA`, `COLUMNAS`, `EXTENSIONES`, `VIGENCIA` (columnas con el rango de fechas que cubre el archivo) y `leer(contenido) -> filas`. Los errores para el usuario se lanzan con `ErrorDeCarga` diciendo hoja, fila y columna.
2. Registrarlo en `lectores/__init__.py`, agregarlo a `tipo_archivo` (`sql/03_vigencias.sql`) y crear la tabla en un archivo nuevo de `sql/` (idempotente; se aplica solo al desplegar).
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
