-- Terminales. dim_bus y dim_servicio_terminal apuntan aquí por el nombre de la terminal.
CREATE TABLE IF NOT EXISTS dim_terminal (
  terminal        VARCHAR(60)  NOT NULL,
  actualizado_por VARCHAR(255) NULL,
  actualizado_at  DATETIME     NULL,
  PRIMARY KEY (terminal)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

INSERT IGNORE INTO dim_terminal (terminal) VALUES
  ('El Retiro'), ('Gabriela'), ('Jardín Alto'), ('Lo Blanco'), ('Los Sauces');
INSERT IGNORE INTO dim_terminal (terminal) SELECT DISTINCT terminal FROM dim_servicio_terminal;

-- Los ALTER que ya se aplicaron (columna o FK existente) se saltan solos al volver a correr.
ALTER TABLE dim_servicio_terminal ADD CONSTRAINT fk_servicio_terminal_terminal
  FOREIGN KEY (terminal) REFERENCES dim_terminal (terminal) ON UPDATE CASCADE;

ALTER TABLE dim_bus ADD COLUMN terminal VARCHAR(60) NULL AFTER plazas;
ALTER TABLE dim_bus ADD CONSTRAINT fk_dim_bus_terminal
  FOREIGN KEY (terminal) REFERENCES dim_terminal (terminal) ON UPDATE CASCADE;

ALTER TABLE raw_flota ADD COLUMN terminal VARCHAR(60) NULL AFTER plazas;
