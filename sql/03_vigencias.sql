-- Tipos de archivo y vigencia: qué carga rige cada fecha, por tipo de archivo.
-- Ver docs/modelo/modelo.dbml (tipo_archivo, vigencia_archivo) y src/indicadores_azure/vigencias.py.

CREATE TABLE IF NOT EXISTS tipo_archivo (
  codigo     VARCHAR(40)  NOT NULL,
  nombre     VARCHAR(100) NOT NULL,
  cobertura  VARCHAR(10)  NOT NULL,
  PRIMARY KEY (codigo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

INSERT IGNORE INTO tipo_archivo (codigo, nombre, cobertura) VALUES
  ('anexo1', 'Anexo 1 - Horarios de operación', 'RANGO'),
  ('anexo3', 'Anexo 3 - Parámetros de operación', 'RANGO'),
  ('velocidades', 'Velocidades DTPM', 'DIA'),
  ('exclusiones', 'Exclusiones DTPM (eventos exógenos)', 'MES');

-- Entre filas vigentes del mismo tipo los rangos no se cruzan: para (tipo, fecha) hay a lo sumo
-- una carga vigente. Gana la carga cuyo rango completo (rango_desde..rango_hasta) es más corto;
-- a igual largo, la cargada después. Las filas reemplazadas quedan con vigente = 0.
CREATE TABLE IF NOT EXISTS vigencia_archivo (
  vigencia_id      BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  tipo_archivo     VARCHAR(40)  NOT NULL,
  carga_id         BIGINT UNSIGNED NOT NULL,
  fecha_inicio     DATE         NOT NULL,
  fecha_termino    DATE         NOT NULL,
  rango_desde      DATE         NOT NULL,
  rango_hasta      DATE         NOT NULL,
  vigente          TINYINT(1)   NOT NULL DEFAULT 1,
  reemplazada_por  BIGINT UNSIGNED NULL,
  origen           VARCHAR(10)  NOT NULL DEFAULT 'CARGA',
  creado_por       VARCHAR(255) NULL,
  creado_at        DATETIME     NOT NULL,
  reemplazado_at   DATETIME     NULL,
  PRIMARY KEY (vigencia_id),
  KEY ix_vigencia_rango (tipo_archivo, vigente, fecha_inicio, fecha_termino),
  KEY ix_vigencia_carga (carga_id),
  CONSTRAINT fk_vigencia_tipo FOREIGN KEY (tipo_archivo) REFERENCES tipo_archivo (codigo),
  CONSTRAINT fk_vigencia_carga FOREIGN KEY (carga_id) REFERENCES control_carga (carga_id),
  CONSTRAINT fk_vigencia_reemplazo FOREIGN KEY (reemplazada_por) REFERENCES control_carga (carga_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
