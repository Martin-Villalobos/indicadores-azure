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

## 1. Tablas en MySQL (una vez)

Desde DBeaver (conexión a Azure) ejecutar `sql/01_control_carga.sql` y luego `sql/02_raw_anexo1.sql`. O desde Cloud Shell:

```
for f in sql/*.sql; do mysql -h mysql-prueba-indicadores.mysql.database.azure.com -u mvillalobos -p --ssl-mode=REQUIRED indicadores_bi < "$f"; done
```

Cloud Shell necesita acceso al MySQL: ya está marcado "Permitir acceso desde servicios de Azure"; si no conecta, agregar la IP de Cloud Shell en **Redes**.

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

## Dashboards

Los enlaces no están en el código: la página los pide a `/api/dashboards`, que sólo responde a usuarios con login. Se configuran en la Static Web App → **Configuración → Variables de entorno** → `DASHBOARDS`, con un JSON en una sola línea:

```
[{"nombre":"IP del mes","descripcion":"Índice de puntualidad por expedición.","url":"https://app.powerbi.com/view?r=..."},{"nombre":"IE","descripcion":"...","url":"https://app.powerbi.com/view?r=..."}]
```

Cambiar la variable no requiere volver a publicar la web. `&pageName=ReportSectionXXXX` en la URL abre una página concreta del reporte.

La página recorta la barra inferior de Power BI (compartir, pantalla completa, logo) y desactiva el clic derecho. Esto dificulta copiar el enlace, pero no lo impide: un usuario con login puede verlo con las herramientas del navegador (F12). Si un enlace se filtra, en app.powerbi.com → ⚙ → **Administrar códigos para insertar** se elimina y se genera uno nuevo.

## Dominio propio (pendiente)

DNS de `granamericassantiago.cl` en GoDaddy. App → **Dominios personalizados → + Agregar** `indicadores.granamericassantiago.cl`; en GoDaddy, registro **CNAME** `indicadores` → `witty-stone-0193e8a0f.8.azurestaticapps.net`, TTL 1 hora; luego **Validar** en Azure.

## Recordatorios

- Los iframes de "Publicar en la web" son públicos: el login protege la página, no el enlace del reporte.
- Al cambiar de red (teletrabajo), agregar la IP nueva en el MySQL → **Redes → Agregar dirección IP del cliente actual**.
- Nunca abrir el firewall del MySQL a todas las IPs.
