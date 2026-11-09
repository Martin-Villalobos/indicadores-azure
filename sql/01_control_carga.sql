-- Registro de cada archivo procesado por el job (uno por tipo + contenido).
CREATE TABLE IF NOT EXISTS control_carga (
  carga_id        BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  tipo_archivo    VARCHAR(40)  NOT NULL,
  nombre_archivo  VARCHAR(255) NOT NULL,
  blob_nombre     VARCHAR(400) NOT NULL,
  hash_sha256     CHAR(64)     NOT NULL,
  estado          ENUM('PROCESANDO','COMPLETADO','ERROR') NOT NULL,
  subido_por      VARCHAR(255) NULL,
  inicio_at       DATETIME     NOT NULL,
  fin_at          DATETIME     NULL,
  filas_leidas    INT UNSIGNED NULL,
  filas_cargadas  INT UNSIGNED NULL,
  mensaje_error   TEXT         NULL,
  PRIMARY KEY (carga_id),
  UNIQUE KEY uq_control_carga_tipo_hash (tipo_archivo, hash_sha256),
  KEY ix_control_carga_estado (estado, inicio_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
