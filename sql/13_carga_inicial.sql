-- Archivos de datos_iniciales/ que el job ya subió (ver src/indicadores_azure/datos_iniciales.py).
-- Cada archivo se sube una sola vez por base: si después se elimina su carga en la web, no vuelve.
CREATE TABLE IF NOT EXISTS carga_inicial (
    sha256      CHAR(64)     NOT NULL PRIMARY KEY,
    archivo     VARCHAR(500) NOT NULL,
    tamano      BIGINT       NOT NULL,
    blob_nombre VARCHAR(500) NOT NULL,
    subido_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY ix_carga_inicial_archivo (archivo(255), tamano)
);
