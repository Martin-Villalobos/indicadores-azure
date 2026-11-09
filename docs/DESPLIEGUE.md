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

Desde la raíz del repo (no desde dentro de `web/`, o falla con "Current directory cannot be identical to or contained within artifact folders"):

```
npx -y @azure/static-web-apps-cli deploy ./web/app --api-location ./web/api --api-language python --api-version 3.11 --deployment-token TU_TOKEN --env production
```

No usar el PC con Windows: el CLI falla con la "í" de `C:\Users\MartínVillalobos`. El token está en la app → **Información general → Administrar token de implementación**; no pegarlo en chats y, si se filtra, **Restablecer token**.

## 4. Probar

En la web, pestaña **Cargar archivos**, subir un Anexo 1. En menos de un minuto aparece el resultado. Queda:

- en MySQL: una fila en `control_carga` y las filas en `raw_anexo1` con su `carga_id`;
- en el blob: el archivo en `anexo1/procesados/`, o en `anexo1/errores/` junto a un `.error.txt` con el motivo.

Subir el mismo archivo otra vez responde "ya se había cargado" sin duplicar filas. Un archivo con error no deja filas a medias.

## 5. Máquina local: Reporte 117 y Velocidades con rclone

> Los lectores de `reporte117` y `velocidades` todavía no están en el job. Mientras tanto los archivos llegan a `<tipo>/entrada/` y esperan ahí.

Credencial: un SAS del contenedor que sólo permite crear y escribir, con vencimiento:

```
az storage container generate-sas --name cargas --permissions acwl --expiry 2027-11-09 \
  --connection-string "$(az storage account show-connection-string -g rg-prueba-indicadores -n stindicadoresprueba -o tsv)" -o tsv
```

En la máquina local (una vez), con rclone instalado:

```
rclone config create azcargas azureblob sas_url "https://stindicadoresprueba.blob.core.windows.net/cargas?SAS_DEL_PASO_ANTERIOR"
```

Luego ajustar las rutas en `local/subir_archivos.ps1` (Windows) o `local/subir_archivos.sh` (Linux) y programarlo cada 5 minutos (Programador de tareas o cron).

- `move` borra el archivo local sólo si la subida terminó bien.
- `--min-age 2m` evita subir un archivo que todavía se está escribiendo.
- Si otro proceso local también necesita esos archivos, que los copie a una carpeta "salida" y rclone mueva desde ahí.
- Si rclone reclama permisos, generar el SAS con `racwl`.
- Sólo necesita salida HTTPS (443); no hay que abrir puertos hacia la máquina.

## Dar acceso a una persona a la web

App → **Administración de roles → Invitar**: proveedor Microsoft Entra ID, correo, dominio `witty-stone-0193e8a0f.8.azurestaticapps.net`, rol `empleado`, expiración → **Generar** y enviarle el enlace. Plan gratis: hasta 25 personas.

## Dashboards

En `web/app/index.html`, editar la lista `DASHBOARDS` (nombre, descripción y URL de "Publicar en la web"; `&pageName=ReportSectionXXXX` abre una página concreta). Luego volver a publicar (paso 3).

## Dominio propio (pendiente)

DNS de `granamericassantiago.cl` en GoDaddy. App → **Dominios personalizados → + Agregar** `indicadores.granamericassantiago.cl`; en GoDaddy, registro **CNAME** `indicadores` → `witty-stone-0193e8a0f.8.azurestaticapps.net`, TTL 1 hora; luego **Validar** en Azure.

## Recordatorios

- Los iframes de "Publicar en la web" son públicos: el login protege la página, no el enlace del reporte.
- Al cambiar de red (teletrabajo), agregar la IP nueva en el MySQL → **Redes → Agregar dirección IP del cliente actual**.
- Nunca abrir el firewall del MySQL a todas las IPs.
