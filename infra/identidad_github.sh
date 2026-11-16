#!/usr/bin/env bash
# Identidad para que GitHub Actions actualice el job sin secretos (OIDC).
# No necesita permisos de directorio (Entra ID): usa una identidad administrada del grupo de
# recursos con credencial federada para la rama main. Correr una vez en Azure Cloud Shell (Bash).
set -euo pipefail

RG=${RG:-rg-prueba-indicadores}
ID=${ID:-id-github-indicadores}
REPO=${REPO:-Martin-Villalobos/indicadores-azure}

az identity create -g "$RG" -n "$ID" -o none
CLIENT_ID=$(az identity show -g "$RG" -n "$ID" --query clientId -o tsv)
PRINCIPAL_ID=$(az identity show -g "$RG" -n "$ID" --query principalId -o tsv)

# Permiso sólo sobre el grupo de recursos (la identidad recién creada puede tardar en propagarse).
for i in 1 2 3 4 5 6; do
  az role assignment create --assignee-object-id "$PRINCIPAL_ID" --assignee-principal-type ServicePrincipal \
    --role Contributor --scope "$(az group show -n "$RG" --query id -o tsv)" -o none && break
  echo "Reintentando la asignación de rol..."; sleep 10
done

az identity federated-credential create -g "$RG" --identity-name "$ID" -n github-main \
  --issuer https://token.actions.githubusercontent.com \
  --subject "repo:${REPO}:ref:refs/heads/main" \
  --audiences api://AzureADTokenExchange -o none 2>/dev/null || echo "(la credencial federada ya existía)"

echo
echo "Crear en GitHub → Settings → Secrets and variables → Actions → pestaña Variables:"
echo "  AZURE_CLIENT_ID       = $CLIENT_ID"
echo "  AZURE_TENANT_ID       = $(az account show --query tenantId -o tsv)"
echo "  AZURE_SUBSCRIPTION_ID = $(az account show --query id -o tsv)"
