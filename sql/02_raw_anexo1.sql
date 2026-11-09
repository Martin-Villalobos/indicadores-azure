-- Anexo 1 tal como viene en el archivo, una fila por tramo.
CREATE TABLE IF NOT EXISTS raw_anexo1 (
  id                       BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  carga_id                 BIGINT UNSIGNED NOT NULL,
  numero_fila              INT UNSIGNED NOT NULL,
  unidad_servicios         VARCHAR(40)  NULL,
  anio                     SMALLINT     NULL,
  codigo_ts_servicio       VARCHAR(20)  NOT NULL,
  codigo_usuario_servicio  VARCHAR(20)  NULL,
  sentido                  VARCHAR(20)  NOT NULL,
  tipo_dia                 VARCHAR(20)  NOT NULL,
  tramo_horario            SMALLINT     NULL,
  hora_inicio              TIME         NOT NULL,
  hora_termino             TIME         NULL,
  fecha_inicio             DATE         NULL,
  fecha_termino            DATE         NULL,
  PRIMARY KEY (id),
  KEY ix_raw_anexo1_carga (carga_id),
  KEY ix_raw_anexo1_servicio (codigo_ts_servicio, sentido, tipo_dia),
  CONSTRAINT fk_raw_anexo1_carga FOREIGN KEY (carga_id) REFERENCES control_carga (carga_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
