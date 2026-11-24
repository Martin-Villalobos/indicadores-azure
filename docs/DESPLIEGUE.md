# Despliegue de la prueba en Azure

Recursos (grupo `rg-prueba-indicadores`, suscripción de prueba):

| Recurso | Nombre |
|---|---|
| Static Web App | `web-indicadores` → https://witty-stone-0193e8a0f.8.azurestaticapps.net |
| MySQL | `mysql-prueba-indicadores.mysql.database.azure.com`, base `indicadores_bi` |
| Cuenta de almacenamiento | `stindicadoresprueba` (contenedor `cargas`, cola `cargas-nuevas`) |
| Registro de contenedores | `acrindicadoresprueba` |
| Job | `job-cargas` en el entorno `cae-indicadores` |

Si algún nombre ya está tomado en Azure, cámbialo con la variable del script (`ST=... ACR=...`).

Todo se hace desde **Azure Cloud Shell (Bash)** con el repo clonado: `git clone https://github.com/Martin-Villalobos/indicadores-azure && cd indicadores-azure`.

## 1. Tablas en MySQL (automático)

No hay que correr los SQL a mano. El job aplica al partir los archivos de `sql/` que falten (o que cambiaron) y los registra en la tabla `migracion_aplicada`. En cada push a `main`, el workflow **job** publica la imagen, actualiza el job y lanza una ejecución para que la base quede al día; si esa ejecución falla, el workflow queda en rojo.

Antes de esa ejecución, el workflow copia `datos_iniciales/` al blob (`iniciales/`, sólo lo que falta; usa el secreto `conexion-blob` del job). Después de las tablas, el job procesa los archivos de `iniciales/` que esa base todavía no tiene (tabla `carga_inicial`). Así una instancia nueva parte con los anexos ya cargados, sin subirlos uno a uno en la web. Ver `datos_iniciales/README.md`.

Para que el workflow pueda entrar a Azure (sin secretos, por OIDC), correr una vez en Cloud Shell `bash infra/identidad_github.sh` y crear en GitHub las tres variables que imprime (`AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`). No necesita permisos de directorio: usa una identidad administrada del grupo de recursos.

Sin esas variables, el resumen del workflow muestra los dos comandos para correr en Cloud Shell (`az containerapp job update ...` y `az containerapp job start ...`). Sin ellos, las tablas igual se crean con el primer archivo que se suba, pero la pestaña Datos maestros no las ve hasta entonces.

Reglas para los SQL nuevos: un archivo nuevo por cambio, con nombre que siga el orden (`09_...sql`), e idempotente (`CREATE TABLE IF NOT EXISTS`, `INSERT IGNORE`, `CREATE OR REPLACE VIEW`). Un `CREATE TABLE IF NOT EXISTS` no agrega columnas a una tabla existente: eso va como `ALTER TABLE` en un archivo nuevo.

Para aplicarlos a mano (por ejemplo desde un equipo con acceso a la base): `ENTORNO=prod indicadores-azure-migrar`.

## 2. Almacenamiento, cola, Event Grid y job

```
read -s DB_PASSWORD && export DB_PASSWORD
bash infra/crear_recursos.sh
```

El script crea la cuenta de almacenamiento, el contenedor `cargas`, la cola, el aviso Event Grid de cada archivo nuevo en `<tipo>/entrada/`, el registro de contenedores, el entorno y el job. El entorno del job queda en Brasil Sur si Container Apps no está disponible en Chile Central.

**La imagen del job la construye GitHub Actions**, porque la suscripción de prueba no permite `az acr build`. La primera vez el script se detiene y pide:

1. En GitHub → repo → **Settings → Secrets and variables → Actions**: variable `ACR_NAME` = `acrindicadoresprueba`; secretos `ACR_USERNAME` = `acrindicadoresprueba` y `ACR_PASSWORD` = la clave de `az acr credential show -n acrindicadoresprueba --query "passwords[0].value" -o tsv`.
2. Pestaña **Actions → job → Run workflow** en `main`, y esperar el check verde.
3. Volver a correr el script.

Desde ahí, cada push a `main` corre las pruebas y publica una imagen nueva. Para que el job la use, copiar el comando `az containerapp job update ...` que aparece en el resumen de la corrida en Actions.

- El job tiene `--max-executions 1`, así que nunca corren dos cargas a la vez.
- Correrlo a mano (por ejemplo para reprocesar): `az containerapp job start -g rg-prueba-indicadores -n job-cargas`.
- Ver corridas: `az containerapp job execution list -g rg-prueba-indicadores -n job-cargas -o table`. El detalle de cada corrida está en el portal, en el job → **Historial de ejecución → Registros**.

## 3. Publicar la web

En la Static Web App → **Configuración → Variables de entorno** (Producción): `BLOB_CONNECTION_STRING` = la cadena de la cuenta (`az storage account show-connection-string -g rg-prueba-indicadores -n stindicadoresprueba -o tsv`) y `BLOB_CONTAINER` = `cargas`.

Para la pestaña **Datos maestros** (lee y edita `dim_bus` y `dim_servicio_terminal`) la API también necesita la base: `DB_HOST` = `mysql-prueba-indicadores.mysql.database.azure.com`, `DB_NAME` = `indicadores_bi`, `DB_USER` y `DB_PASSWORD`. La conexión usa TLS con los certificados de `certifi` (o `DB_SSL_CA` si se define). Cada cambio encola un recálculo del ICFP y deja un aviso en `cargas/recalculo/entrada/`, que dispara el job igual que un archivo nuevo.

**Automático (recomendado):** cada push a `main` que toque `web/` publica la web con GitHub Actions (`.github/workflows/web.yml`). Una vez, en GitHub → **Settings → Secrets and variables → Actions → New repository secret**: `AZURE_STATIC_WEB_APPS_API_TOKEN` = el token de implementación. También se puede correr a mano en **Actions → web → Run workflow**.

**A mano**, desde la raíz del repo en Cloud Shell: `bash web/publicar.sh` (pide el token sin mostrarlo y empaqueta las dependencias de la API).

No usar el PC con Windows: el CLI falla con la "í" de `C:\Users\MartínVillalobos`. El token está en la app → **Información general → Administrar token de implementación**; no pegarlo en chats y, si se filtra, **Restablecer token**.

## 4. Probar

En la web, pestaña **Cargar archivos**, subir un Anexo 1. En menos de un minuto aparece el resultado. Queda:

- en MySQL: una fila en `control_carga` y las filas en `raw_anexo1` con su `carga_id`;
- en el blob: el archivo en `anexo1/procesados/`, o en `anexo1/errores/` junto a un `.error.txt` con el motivo.

Subir el mismo archivo otra vez responde "ya se había cargado" sin duplicar filas. Un archivo con error no deja filas a medias.

## 5. Máquina local (Linux): Reporte 1.117 y Velocidades con rclone

> Los lectores de `reporte117` y `velocidades` todavía no están en el job. Mientras tanto los archivos llegan a `<tipo>/entrada/` y esperan ahí.

La máquina ya tiene el espejo FTP (`syndirectory.sh` con lftp en `/data/ftpmirror/...`). `local/subir_archivos.sh` toma de ese espejo lo nuevo y lo copia al blob, con la misma lógica que `copyToServer.sh`:

- Reporte 1.117: los `.zip` de `/data/ftpmirror/sonda/OUT/Reporte_1.117`.
- Velocidades: los `.xlsx` fuera de línea (`*OFF*`) y los en línea (`*ON*`) que todavía no tienen su versión fuera de línea.
- No mueve ni borra nada del espejo (lftp los volvería a bajar). Lo ya subido queda anotado en `~/.subir_azure/*.subidos`.
- Sólo considera archivos modificados desde `DESDE` (por defecto 2026-11-01) y con más de 2 minutos sin cambios.

**Credencial**, un SAS del contenedor que sólo permite crear y escribir (Cloud Shell):

```
az storage container generate-sas --name cargas --permissions racwl --expiry 2027-11-10 \
  --connection-string "$(az storage account show-connection-string -g rg-prueba-indicadores -n stindicadoresprueba -o tsv)" -o tsv
```

**En la máquina local** (una vez):

```
sudo -v && curl https://rclone.org/install.sh | sudo bash
rclone config create azcargas azureblob sas_url "https://stindicadoresprueba.blob.core.windows.net/cargas?SAS_DEL_PASO_ANTERIOR"
sudo mkdir -p /opt/indicadores-azure && sudo cp subir_archivos.sh /opt/indicadores-azure/ && sudo chmod 755 /opt/indicadores-azure/subir_archivos.sh
/opt/indicadores-azure/subir_archivos.sh        # primera corrida a mano
```

Luego, con `crontab -e` del mismo usuario que corre `syndirectory.sh`:

```
*/5 * * * * /opt/indicadores-azure/subir_archivos.sh >> $HOME/subir_azure.log 2>&1
```

- Para volver a subir un archivo: borrar su línea en `~/.subir_azure/<nombre>.subidos`.
- El SAS necesita lectura (`r`) porque rclone revisa la ruta destino antes de subir; no permite borrar.
- Sólo necesita salida HTTPS (443); no hay que abrir puertos hacia la máquina.

## Dar acceso a una persona a la web

App → **Administración de roles → Invitar**: proveedor Microsoft Entra ID, correo, dominio `witty-stone-0193e8a0f.8.azurestaticapps.net`, rol `empleado`, expiración → **Generar** y enviarle el enlace. Plan gratis: hasta 25 personas.

## Menú de reportes de Power BI

El menú lateral de la web se arma solo desde la base `portal_reportes` (mismo servidor MySQL, esquema en `web/sql/portal_reportes.sql`): `menu` son los grupos laterales, `reporte` los Power BI de cada grupo (con su `url_powerbi`), y `usuario`, `rol`, `usuario_rol` y `permiso` dicen qué ve cada persona. Agregar un reporte o dar acceso es sólo un INSERT; no hay que volver a publicar la web.

- El usuario se reconoce por el email con que inicia sesión en Entra ID (debe ser el mismo de `usuario.email`). Además tiene que tener el rol `empleado` en la Static Web App (ver arriba) para poder entrar.
- `ancho_lienzo` y `alto_lienzo` de `reporte` son el tamaño del lienzo en Power BI (Formato → Configuración de lienzo; por defecto 1280 × 720). La web da al recuadro esa proporción: un reporte vertical (p. ej. 1280 × 2000, con Ver → **Ajustar al ancho**) se ve completo y se recorre con el scroll de la página. En una base creada antes de estas columnas, correr `web/sql/portal_reportes_02_lienzo.sql`.
- Un permiso puede ser sobre un menú completo (`menu_id`, ve todos sus reportes, también los que se agreguen después) o sobre un reporte (`reporte_id`).
- Las herramientas también van por rol: `rol.puede_cargar` muestra **Cargar archivos**, `rol.puede_maestros` muestra **Datos maestros**, y `rol.es_admin` da todo, además de **Usuarios**. Quien no tiene ninguno no ve la sección Herramientas, y las API (`/api/cargar`, `/api/estado`, `/api/archivos`, `/api/maestros`) responden 403 aunque las llame directo. En una base creada antes de estas columnas, correr `web/sql/portal_reportes_03_herramientas.sql` (deja a los administradores con todo).
- **Usuarios** (sólo administradores) es el mantenedor: agregar, editar, desactivar o eliminar usuarios con sus roles, y crear roles con sus herramientas y los menús que ven. Los permisos por reporte puntual se siguen editando en la base. Nadie puede quitarse a sí mismo el acceso de administrador.
- Quien no tiene permisos ni herramientas ve un aviso para pedir acceso.
- La API usa las mismas `DB_HOST`, `DB_USER` y `DB_PASSWORD` de Datos maestros; ese usuario necesita `SELECT, INSERT, UPDATE, DELETE` sobre `portal_reportes.*` (el mantenedor y `ultimo_acceso` escriben ahí). `PORTAL_DB_NAME` cambia el nombre de la base (por defecto `portal_reportes`).

Ejemplo, un grupo con un reporte visible para un administrador:

```sql
USE portal_reportes;
INSERT INTO menu (nombre, orden) VALUES ('Indicadores Operacionales', 1);
SET @menu = LAST_INSERT_ID();
INSERT INTO reporte (menu_id, nombre, descripcion, url_powerbi, orden)
VALUES (@menu, 'ICFP', 'Índice de Cumplimiento de Frecuencia y Plazas.', 'https://app.powerbi.com/view?r=...', 1);
INSERT INTO rol (nombre, es_admin, puede_cargar, puede_maestros) VALUES ('Administrador', 1, 1, 1);
SET @rol = LAST_INSERT_ID();
INSERT INTO usuario (email, nombre) VALUES ('correo@empresa.cl', 'Nombre');
INSERT INTO usuario_rol (usuario_id, rol_id) VALUES (LAST_INSERT_ID(), @rol);
INSERT INTO permiso (rol_id, menu_id) VALUES (@rol, @menu);
```

Los enlaces no llegan a la página: `/api/dashboards` sólo entrega nombres, descripciones y números, y el iframe abre `/api/reporte/<número>`, que revisa el permiso y redirige (302) al enlace. `&pageName=ReportSectionXXXX` en la URL abre una página concreta del reporte.

La página recorta la barra inferior de Power BI (compartir, pantalla completa, logo) y desactiva el clic derecho. Esto dificulta copiar el enlace, pero no lo impide: un usuario con login puede verlo en la pestaña Red de las herramientas del navegador (F12), porque el navegador sigue la redirección. Si un enlace se filtra, en app.powerbi.com → ⚙ → **Administrar códigos para insertar** se elimina y se genera uno nuevo.

La variable `DASHBOARDS` de la Static Web App ya no se usa y se puede borrar.

## Dominio propio (pendiente)

DNS de `granamericassantiago.cl` en GoDaddy. App → **Dominios personalizados → + Agregar** `indicadores.granamericassantiago.cl`; en GoDaddy, registro **CNAME** `indicadores` → `witty-stone-0193e8a0f.8.azurestaticapps.net`, TTL 1 hora; luego **Validar** en Azure.

## Recordatorios

- Los iframes de "Publicar en la web" son públicos: el login protege la página, no el enlace del reporte.
- Al cambiar de red (teletrabajo), agregar la IP nueva en el MySQL → **Redes → Agregar dirección IP del cliente actual**.
- Nunca abrir el firewall del MySQL a todas las IPs.
