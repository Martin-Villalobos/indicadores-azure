# Imagen del job de carga. Construir desde la raíz del repo:
#   az acr build -r <acr> -t indicadores-job:1 -f docker/Dockerfile .
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DB_SSL_CA=/etc/ssl/certs/ca-certificates.crt

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir . && useradd --create-home job
USER job

CMD ["indicadores-azure-procesar"]
