-- Exclusiones mensuales del DTPM (eventos exógenos), sólo U16. Un libro trae tres hojas:
--   ICFP-IE  servicio-sentido-periodo excluido del ICFP y del IE (periodo 1-72 por hora y tipo de día, o *)
--   IP-Base  puntos de control excluidos del IP (id expedición y correlativo paradero, o *)
--   IP-Extra primeras y últimas expediciones excluidas del IP
-- Un * significa "todos".
CREATE TABLE IF NOT EXISTS raw_exclusiones (
  id                     BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  carga_id               BIGINT UNSIGNED NOT NULL,
  hoja                   VARCHAR(20)  NOT NULL,
  numero_fila            INT UNSIGNED NOT NULL,
  fecha                  DATE         NOT NULL,
  unidad_servicios       VARCHAR(10)  NOT NULL,
  codigo_ts_servicio     VARCHAR(20)  NOT NULL,
  sentido                VARCHAR(20)  NOT NULL,
  periodo                VARCHAR(10)  NULL,
  id_expedicion          VARCHAR(40)  NULL,
  correlativo_paradero   VARCHAR(20)  NULL,
  PRIMARY KEY (id),
  KEY ix_raw_exclusiones_carga (carga_id),
  KEY ix_raw_exclusiones_fecha (hoja, fecha, codigo_ts_servicio, sentido),
  CONSTRAINT fk_raw_exclusiones_carga FOREIGN KEY (carga_id) REFERENCES control_carga (carga_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
