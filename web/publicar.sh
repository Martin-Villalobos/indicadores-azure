#!/usr/bin/env bash
# Publica la web y su API en la Static Web App. Correr en Cloud Shell desde la raíz del repo:
#   bash web/publicar.sh
# Pide el token de implementación sin mostrarlo (portal → web-indicadores →
# Información general → Administrar token de implementación).
#
# "swa deploy" no instala las dependencias de la API: se empaquetan aquí en
# web/api/.python_packages (si faltan, /api/cargar responde 500 vacío).
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== Dependencias de la API"
rm -rf web/api/.python_packages
pip3 install -q -r web/api/requirements.txt --target web/api/.python_packages/lib/site-packages \
  --platform manylinux2014_x86_64 --python-version 3.11 --implementation cp --only-binary=:all:

if [ -z "${SWA_TOKEN:-}" ]; then
  read -rsp "Token de implementación: " SWA_TOKEN; echo
fi

echo "== Publicando"
npx -y @azure/static-web-apps-cli deploy ./web/app --api-location ./web/api \
  --api-language python --api-version 3.11 --deployment-token "$SWA_TOKEN" --env production
