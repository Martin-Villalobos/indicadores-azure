-- Maestro de flota (patente -> tipo de bus -> plazas). El cálculo usa la última carga COMPLETADO.
INSERT IGNORE INTO tipo_archivo (codigo, nombre, cobertura) VALUES
  ('flota', 'Flota (patente, tipo de bus y plazas)', 'NINGUNA');

CREATE TABLE IF NOT EXISTS raw_flota (
  id           BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  carga_id     BIGINT UNSIGNED NOT NULL,
  numero_fila  INT UNSIGNED NOT NULL,
  ppu          VARCHAR(12)  NOT NULL,
  tipo_bus     VARCHAR(40)  NULL,
  plazas       SMALLINT UNSIGNED NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_raw_flota_ppu (carga_id, ppu),
  CONSTRAINT fk_raw_flota_carga FOREIGN KEY (carga_id) REFERENCES control_carga (carga_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
