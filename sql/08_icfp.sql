-- Cálculo del ICFP (Contrato 5.3.1.6). Ver src/indicadores_azure/icfp/ y docs/modelo/modelo.dbml.
-- Periodo = hora de despacho (0-23), igual que indicadores-bi y que los periodos del DTPM en ICFP-IE.

-- Terminal de cada servicio por código usuario (maestro servicios_terminales.csv de indicadores-bi).
CREATE TABLE IF NOT EXISTS dim_servicio_terminal (
  codigo_usuario  VARCHAR(20) NOT NULL,
  terminal        VARCHAR(60) NOT NULL,
  actualizado_por VARCHAR(255) NULL,
  actualizado_at  DATETIME     NULL,
  PRIMARY KEY (codigo_usuario)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

INSERT IGNORE INTO dim_servicio_terminal (codigo_usuario, terminal) VALUES
  ('503', 'Los Sauces'),
  ('J19', 'Los Sauces'),
  ('225', 'Gabriela'),
  ('225c', 'Gabriela'),
  ('325', 'Gabriela'),
  ('E12', 'Gabriela'),
  ('E13', 'Gabriela'),
  ('E15c', 'Gabriela'),
  ('E16', 'Gabriela'),
  ('246', 'Gabriela'),
  ('207', 'El Retiro'),
  ('209', 'El Retiro'),
  ('234', 'El Retiro'),
  ('F28', 'El Retiro'),
  ('J07c', 'Los Sauces'),
  ('322', 'Jardín Alto'),
  ('323', 'Jardín Alto'),
  ('E03', 'Jardín Alto'),
  ('E07', 'Jardín Alto'),
  ('E10', 'Jardín Alto'),
  ('E20', 'Jardín Alto'),
  ('207c', 'El Retiro'),
  ('207e', 'El Retiro'),
  ('209c', 'El Retiro'),
  ('302', 'Lo Blanco'),
  ('302N', 'Lo Blanco'),
  ('E05', 'Lo Blanco'),
  ('E18', 'Lo Blanco'),
  ('G28', 'Lo Blanco');

-- Flota: patente -> tipo de bus -> plazas. La llena cada carga de "flota" (raw_flota) y se puede
-- editar desde la web (Datos maestros). El ICP usa estas plazas, nunca la capacidad de velocidades.
CREATE TABLE IF NOT EXISTS dim_bus (
  ppu              VARCHAR(12)  NOT NULL,
  tipo_bus         VARCHAR(40)  NULL,
  plazas           SMALLINT UNSIGNED NULL,
  origen           VARCHAR(10)  NOT NULL DEFAULT 'CARGA' COMMENT 'CARGA | MANUAL',
  carga_id         BIGINT UNSIGNED NULL,
  actualizado_por  VARCHAR(255) NULL,
  actualizado_at   DATETIME     NULL,
  PRIMARY KEY (ppu)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS indicador (
  codigo  VARCHAR(20)  NOT NULL,
  nombre  VARCHAR(200) NOT NULL,
  PRIMARY KEY (codigo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

INSERT IGNORE INTO indicador (codigo, nombre) VALUES
  ('ICFP', 'Índice de Cumplimiento de Frecuencia y Plazas (Contrato 5.3.1.6)');

-- De qué archivos depende cada indicador y cuántos días vecinos afecta un cambio (trasvasije: 1).
CREATE TABLE IF NOT EXISTS indicador_fuente (
  indicador     VARCHAR(20) NOT NULL,
  tipo_archivo  VARCHAR(40) NOT NULL,
  desfase_dias  SMALLINT    NOT NULL DEFAULT 0,
  PRIMARY KEY (indicador, tipo_archivo),
  CONSTRAINT fk_fuente_indicador FOREIGN KEY (indicador) REFERENCES indicador (codigo),
  CONSTRAINT fk_fuente_tipo FOREIGN KEY (tipo_archivo) REFERENCES tipo_archivo (codigo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

INSERT IGNORE INTO indicador_fuente (indicador, tipo_archivo, desfase_dias) VALUES
  ('ICFP', 'anexo3', 1), ('ICFP', 'velocidades', 1), ('ICFP', 'exclusiones', 0), ('ICFP', 'flota', 1);

-- Cada corrida de un indicador para un rango de fechas. Nunca se sobrescribe.
CREATE TABLE IF NOT EXISTS calculo (
  calculo_id         BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  indicador          VARCHAR(20)  NOT NULL,
  fecha_desde        DATE         NOT NULL,
  fecha_hasta        DATE         NOT NULL,
  version_algoritmo  VARCHAR(50)  NOT NULL,
  estado             VARCHAR(12)  NOT NULL,
  inicio_at          DATETIME     NOT NULL,
  fin_at             DATETIME     NULL,
  fechas_calculadas  INT          NULL,
  mensaje_error      TEXT         NULL,
  PRIMARY KEY (calculo_id),
  KEY ix_calculo_indicador (indicador, estado, fecha_desde),
  CONSTRAINT fk_calculo_indicador FOREIGN KEY (indicador) REFERENCES indicador (codigo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Qué carga de cada tipo se usó para cada fecha del cálculo.
CREATE TABLE IF NOT EXISTS calculo_entrada (
  calculo_id    BIGINT UNSIGNED NOT NULL,
  fecha         DATE            NOT NULL,
  tipo_archivo  VARCHAR(40)     NOT NULL,
  carga_id      BIGINT UNSIGNED NOT NULL,
  PRIMARY KEY (calculo_id, fecha, tipo_archivo),
  CONSTRAINT fk_entrada_calculo FOREIGN KEY (calculo_id) REFERENCES calculo (calculo_id),
  CONSTRAINT fk_entrada_carga FOREIGN KEY (carga_id) REFERENCES control_carga (carga_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Cola de recálculos: la llena el job al cargar un archivo del que depende el indicador.
CREATE TABLE IF NOT EXISTS recalculo_pendiente (
  recalculo_id     BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  indicador        VARCHAR(20)     NOT NULL,
  fecha_desde      DATE            NOT NULL,
  fecha_hasta      DATE            NOT NULL,
  motivo_carga_id  BIGINT UNSIGNED NULL,
  estado           VARCHAR(12)     NOT NULL DEFAULT 'PENDIENTE',
  calculo_id       BIGINT UNSIGNED NULL,
  creado_at        DATETIME        NOT NULL,
  resuelto_at      DATETIME        NULL,
  PRIMARY KEY (recalculo_id),
  KEY ix_recalculo_estado (estado, indicador),
  CONSTRAINT fk_recalculo_indicador FOREIGN KEY (indicador) REFERENCES indicador (codigo),
  CONSTRAINT fk_recalculo_carga FOREIGN KEY (motivo_carga_id) REFERENCES control_carga (carga_id),
  CONSTRAINT fk_recalculo_calculo FOREIGN KEY (calculo_id) REFERENCES calculo (calculo_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Expediciones válidas (OK) usadas en el cálculo, con el periodo al que quedaron asignadas.
CREATE TABLE IF NOT EXISTS icfp_expedicion (
  calculo_id          BIGINT UNSIGNED NOT NULL,
  raw_velocidades_id  BIGINT UNSIGNED NOT NULL,
  fecha               DATE         NOT NULL,
  codigo_ts           VARCHAR(20)  NOT NULL,
  sentido             CHAR(1)      NOT NULL,
  tipo_dia            VARCHAR(10)  NOT NULL,
  periodo             TINYINT      NOT NULL COMMENT 'hora de despacho',
  fh_salida           DATETIME     NOT NULL,
  patente             VARCHAR(12)  NULL,
  tipo_bus            VARCHAR(40)  NULL,
  plazas              SMALLINT     NULL,
  estado_plazas       VARCHAR(15)  NOT NULL COMMENT 'OK | SIN_BUS | SIN_CAPACIDAD',
  fecha_asignada      DATE         NOT NULL COMMENT 'distinta de fecha si hubo trasvasije a otro día',
  periodo_asignado    TINYINT      NOT NULL,
  PRIMARY KEY (calculo_id, raw_velocidades_id),
  CONSTRAINT fk_icfp_exp_calculo FOREIGN KEY (calculo_id) REFERENCES calculo (calculo_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Grano servicio-sentido-periodo-día (5.3.1.6). ev, pl_val, icf, icp y km_validos son DESPUÉS
-- del trasvasije (5.3.1.6.6); las columnas *_inicial son la foto antes de corregir.
CREATE TABLE IF NOT EXISTS icfp_sspd (
  calculo_id          BIGINT UNSIGNED NOT NULL,
  fecha               DATE          NOT NULL,
  codigo_ts           VARCHAR(20)   NOT NULL,
  sentido             CHAR(1)       NOT NULL,
  periodo             TINYINT       NOT NULL COMMENT 'hora 0-23',
  mes                 DATE          NOT NULL,
  tipo_dia            VARCHAR(10)   NOT NULL,
  codigo_usuario      VARCHAR(20)   NULL,
  terminal            VARCHAR(60)   NULL,
  ep                  INT           NULL COMMENT 'expediciones programadas',
  ev                  INT           NOT NULL,
  pl_prog             INT           NULL,
  pl_val              INT           NULL COMMENT 'NULL si alguna expedición no tiene plazas',
  icf                 DECIMAL(10,6) NULL,
  icp                 DECIMAL(10,6) NULL,
  feo                 DECIMAL(8,5)  NOT NULL DEFAULT 1,
  ft                  DECIMAL(8,5)  NOT NULL DEFAULT 1,
  km_programados      DECIMAL(12,3) NOT NULL DEFAULT 0 COMMENT 'Σ distancia base · salidas de las MH del periodo',
  km_validos          DECIMAL(12,3) NULL COMMENT 'min(1, icf·FEO·FT, icp·FEO·FT) · kmp',
  ev_inicial          INT           NOT NULL,
  pl_val_inicial      INT           NULL,
  icf_inicial         DECIMAL(10,6) NULL,
  icp_inicial         DECIMAL(10,6) NULL,
  km_validos_inicial  DECIMAL(12,3) NULL,
  expediciones_recibidas INT        NOT NULL DEFAULT 0,
  expediciones_cedidas   INT        NOT NULL DEFAULT 0,
  excluido            TINYINT(1)    NOT NULL DEFAULT 0 COMMENT 'exclusión DTPM (hoja ICFP-IE)',
  estado              VARCHAR(20)   NOT NULL COMMENT 'OK | SIN_EXIGENCIA | SIN_PROGRAMA | SIN_CAPACIDAD | EXCLUIDO',
  PRIMARY KEY (calculo_id, fecha, codigo_ts, sentido, periodo),
  KEY ix_icfp_fecha (fecha, calculo_id),
  KEY ix_icfp_mes (calculo_id, mes, terminal),
  CONSTRAINT fk_icfp_sspd_calculo FOREIGN KEY (calculo_id) REFERENCES calculo (calculo_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Expediciones movidas a un periodo vecino (5.3.1.6.6). La fecha destino puede ser d-1 o d+1.
CREATE TABLE IF NOT EXISTS icfp_trasvasije (
  calculo_id          BIGINT UNSIGNED NOT NULL,
  raw_velocidades_id  BIGINT UNSIGNED NOT NULL,
  codigo_ts           VARCHAR(20)  NOT NULL,
  sentido             CHAR(1)      NOT NULL,
  fecha_origen        DATE         NOT NULL,
  periodo_origen      TINYINT      NOT NULL,
  fecha_destino       DATE         NOT NULL,
  periodo_destino     TINYINT      NOT NULL,
  regla               VARCHAR(15)  NOT NULL COMMENT 'PRIMERA_5_MIN (al anterior) | ULTIMA_5_MIN (al siguiente)',
  plazas              SMALLINT     NOT NULL,
  PRIMARY KEY (calculo_id, raw_velocidades_id),
  CONSTRAINT fk_icfp_tras_calculo FOREIGN KEY (calculo_id) REFERENCES calculo (calculo_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Último cálculo OK de cada fecha: recalcular unos días no obliga a recalcular el mes.
CREATE OR REPLACE VIEW v_calculo_vigente AS
SELECT s.fecha, MAX(s.calculo_id) AS calculo_id
FROM icfp_sspd s JOIN calculo c ON c.calculo_id = s.calculo_id AND c.estado = 'OK'
GROUP BY s.fecha;

-- ICFP vigente por servicio-sentido-periodo-día, para el dashboard.
CREATE OR REPLACE VIEW v_icfp_dashboard AS
SELECT s.* FROM icfp_sspd s
JOIN v_calculo_vigente v ON v.fecha = s.fecha AND v.calculo_id = s.calculo_id;

-- ICFP y km con derecho a pago por mes (5.3.1.5 y 5.3.1.6). Se mide sobre las filas no excluidas
-- y con plazas conocidas; km_sin_capacidad muestra lo que quedó fuera por patentes sin flota.
CREATE OR REPLACE VIEW v_icfp_mes AS
SELECT mes,
       SUM(km_programados) AS km_programados_total,
       SUM(CASE WHEN excluido = 0 AND km_validos IS NOT NULL THEN km_programados ELSE 0 END) AS km_programados_medidos,
       SUM(CASE WHEN excluido = 0 THEN km_validos ELSE 0 END) AS km_validos,
       SUM(CASE WHEN excluido = 0 THEN km_validos ELSE 0 END)
         / NULLIF(SUM(CASE WHEN excluido = 0 AND km_validos IS NOT NULL THEN km_programados ELSE 0 END), 0) AS icfp,
       SUM(km_programados) * SUM(CASE WHEN excluido = 0 THEN km_validos ELSE 0 END)
         / NULLIF(SUM(CASE WHEN excluido = 0 AND km_validos IS NOT NULL THEN km_programados ELSE 0 END), 0) AS km_derecho_pago,
       SUM(CASE WHEN excluido = 1 THEN km_programados ELSE 0 END) AS km_excluidos,
       SUM(CASE WHEN excluido = 0 AND km_validos IS NULL THEN km_programados ELSE 0 END) AS km_sin_capacidad
FROM v_icfp_dashboard
GROUP BY mes;
