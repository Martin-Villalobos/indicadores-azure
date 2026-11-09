#!/usr/bin/env bash
# Crea almacenamiento, cola, aviso Event Grid, registro de contenedores y el job.
# Correr en Azure Cloud Shell (Bash) desde la raíz del repo:
#   DB_PASSWORD='...' bash infra/crear_recursos.sh
# Es idempotente en lo posible: volver a correrlo actualiza la imagen del job.
set -euo pipefail

RG=${RG:-rg-prueba-indicadores}
LOC=${LOC:-chilecentral}
# ACR Tasks (az acr build) no existe en chilecentral: el registro va en Brasil.
ACR_LOC=${ACR_LOC:-brazilsouth}
ST=${ST:-stindicadoresprueba}
CONTAINER=${CONTAINER:-cargas}
QUEUE=${QUEUE:-cargas-nuevas}
ACR=${ACR:-acrindicadoresprueba}
ENV_NAME=${ENV_NAME:-cae-indicadores}
JOB=${JOB:-job-cargas}
TAG=${TAG:-$(date +%Y%m%d%H%M)}
DB_HOST=${DB_HOST:-mysql-prueba-indicadores.mysql.database.azure.com}
DB_USER=${DB_USER:-mvillalobos}
DB_NAME=${DB_NAME:-indicadores_bi}
: "${DB_PASSWORD:?Define DB_PASSWORD antes de correr el script}"

echo "== Suscripción: $(az account show --query name -o tsv)"
# En suscripciones nuevas los proveedores no vienen registrados; sin esto
# "az storage account create" responde SubscriptionNotFound.
for p in Microsoft.Storage Microsoft.EventGrid Microsoft.ContainerRegistry Microsoft.App Microsoft.OperationalInsights; do
  az provider register -n "$p" --wait
done

echo "== Almacenamiento y cola"
az storage account create -g "$RG" -n "$ST" -l "$LOC" --sku Standard_LRS --kind StorageV2 \
  --min-tls-version TLS1_2 --allow-blob-public-access false -o none
CONN=$(az storage account show-connection-string -g "$RG" -n "$ST" -o tsv 2>/dev/null)
az storage container create --name "$CONTAINER" --connection-string "$CONN" -o none
az storage queue create --name "$QUEUE" --connection-string "$CONN" -o none

echo "== Aviso de archivos nuevos (Event Grid -> cola)"
STID=$(az storage account show -g "$RG" -n "$ST" --query id -o tsv)
az eventgrid event-subscription create --name cargas-entrada --source-resource-id "$STID" \
  --endpoint-type storagequeue --endpoint "$STID/queueservices/default/queues/$QUEUE" \
  --included-event-types Microsoft.Storage.BlobCreated \
  --subject-begins-with "/blobServices/default/containers/$CONTAINER/blobs/" \
  --advanced-filter subject StringContains /entrada/ -o none

echo "== Imagen del job"
ACR_ACTUAL=$(az acr show -g "$RG" -n "$ACR" --query location -o tsv 2>/dev/null || true)
if [ -z "$ACR_ACTUAL" ]; then
  az acr create -g "$RG" -n "$ACR" -l "$ACR_LOC" --sku Basic --admin-enabled true -o none
elif [ "$ACR_ACTUAL" != "$ACR_LOC" ]; then
  echo "El registro $ACR está en $ACR_ACTUAL y ahí no se puede usar 'az acr build'." >&2
  echo "Bórralo (az acr delete -g $RG -n $ACR --yes) y vuelve a correr el script." >&2
  exit 1
fi
az acr build -r "$ACR" -t "indicadores-job:$TAG" -f docker/Dockerfile .
IMAGE="$ACR.azurecr.io/indicadores-job:$TAG"

echo "== Entorno y job"
az extension add -n containerapp --upgrade -y
# Container Apps puede no estar disponible en $LOC: si no, usa Brasil.
APP_LOC=${APP_LOC:-$(az provider show -n Microsoft.App \
  --query "resourceTypes[?resourceType=='managedEnvironments'].locations[]" -o tsv \
  | tr -d ' ' | tr '[:upper:]' '[:lower:]' | grep -qx "$LOC" && echo "$LOC" || echo brazilsouth)}
echo "Entorno de Container Apps en: $APP_LOC"
az containerapp env show -g "$RG" -n "$ENV_NAME" -o none 2>/dev/null || \
  az containerapp env create -g "$RG" -n "$ENV_NAME" -l "$APP_LOC" -o none

if az containerapp job show -g "$RG" -n "$JOB" -o none 2>/dev/null; then
  az containerapp job update -g "$RG" -n "$JOB" --image "$IMAGE" -o none
else
  ACRPASS=$(az acr credential show -n "$ACR" --query "passwords[0].value" -o tsv)
  az containerapp job create -g "$RG" -n "$JOB" --environment "$ENV_NAME" \
    --trigger-type Event --replica-timeout 3600 --replica-retry-limit 0 \
    --replica-completion-count 1 --parallelism 1 \
    --min-executions 0 --max-executions 1 --polling-interval 15 \
    --scale-rule-name cola --scale-rule-type azure-queue \
    --scale-rule-metadata queueName="$QUEUE" queueLength=1 accountName="$ST" \
    --scale-rule-auth connection=conexion-blob \
    --image "$IMAGE" \
    --registry-server "$ACR.azurecr.io" --registry-username "$ACR" --registry-password "$ACRPASS" \
    --cpu 1 --memory 2Gi \
    --secrets conexion-blob="$CONN" db-password="$DB_PASSWORD" \
    --env-vars BLOB_CONNECTION_STRING=secretref:conexion-blob BLOB_CONTAINER="$CONTAINER" \
               QUEUE_NAME="$QUEUE" DB_HOST="$DB_HOST" DB_USER="$DB_USER" DB_NAME="$DB_NAME" \
               DB_PASSWORD=secretref:db-password -o none
fi

echo "Listo. Imagen: $IMAGE"
echo "Para la web (Static Web App -> Variables de entorno): BLOB_CONNECTION_STRING = cadena de la cuenta $ST"
