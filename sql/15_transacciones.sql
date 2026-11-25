-- Transacciones de Sonda (TRX_ACUM_DIA, archivo LVAT): una fila por validación de la U16.
-- Los archivos se suman (cada uno trae lo liquidado ese día), por eso no tienen vigencia.
-- q del mes (cláusula 5.3.1.1) = transacciones con fecha de validación en el mes + Ajuste ZPM de
-- la liquidación. Cuadrado contra las cartas L453 (marzo) y L455 (abril) de 2026.
INSERT IGNORE INTO tipo_archivo (codigo, nombre, cobertura) VALUES
  ('transacciones', 'Transacciones Sonda (TRX_ACUM_DIA)', 'NINGUNA');

CREATE TABLE IF NOT EXISTS raw_transacciones (
  id                 BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  carga_id           BIGINT UNSIGNED NOT NULL,
  archivo_txt        VARCHAR(255) NULL,
  numero_fila        INT UNSIGNED NOT NULL,
  fecha_generacion   DATETIME     NOT NULL,
  entidad            VARCHAR(120) NULL,
  sitio              VARCHAR(40)  NULL,     -- patente del bus (VLZY-71) o validador de zona paga (RM-xxxx)
  ppu                VARCHAR(12)  NULL,     -- patente sin guion; NULL en zona paga
  es_zona_paga       TINYINT(1)   NOT NULL,
  fecha_hora         DATETIME     NOT NULL, -- momento de la validación
  fecha              DATE         NOT NULL,
  mes                INT          NOT NULL, -- AAAAMM de la validación
  chip               BIGINT       NULL,
  tarjeta            BIGINT       NULL,
  ntt                INT          NULL,
  tipo_trx           VARCHAR(60)  NULL,
  contrato           VARCHAR(80)  NULL,
  monto              INT          NULL,
  estado             VARCHAR(20)  NULL,
  liquidacion        VARCHAR(60)  NULL,
  fecha_liquidacion  DATE         NULL,     -- día del código LQAAAAMMDD...
  consolidado        VARCHAR(120) NULL,
  csa                INT          NULL,
  scsa               INT          NULL,
  ctla               INT          NULL,
  cla                INT          NULL,
  bnp                INT          NULL,
  sa                 INT          NULL,
  codigo_sitio       INT          NULL,
  cl                 INT          NULL,     -- código de línea: servicio en dim_codigo_linea
  crc                INT          NULL,
  PRIMARY KEY (id),
  KEY ix_raw_transacciones_carga (carga_id),
  KEY ix_raw_transacciones_mes (mes, fecha),
  KEY ix_raw_transacciones_ppu (ppu, fecha_hora),
  CONSTRAINT fk_raw_transacciones_carga FOREIGN KEY (carga_id) REFERENCES control_carga (carga_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Código de línea de Sonda (CL) -> servicio. Copia de bi.codigo_lineas de indicadores-bi (25-11-2026).
-- Una línea nueva se agrega aquí (INSERT IGNORE no cambia las que ya están).
CREATE TABLE IF NOT EXISTS dim_codigo_linea (
  codigo_linea        INT          NOT NULL,
  codigo_ts_servicio  VARCHAR(20)  NOT NULL, -- codigo_sinoptico (1625, 1615c)
  nombre_servicio     VARCHAR(20)  NOT NULL, -- cod_usuario_dtpm (325, E15c)
  codigo_clearing     VARCHAR(20)  NULL,     -- descripcion_numero_servicio_clearing (T1615C)
  terminal            VARCHAR(60)  NULL,
  PRIMARY KEY (codigo_linea)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

INSERT IGNORE INTO dim_codigo_linea (codigo_linea, codigo_ts_servicio, nombre_servicio, codigo_clearing, terminal) VALUES
  (10,  '1646',  '246',  'T1646',  'Gabriela'),
  (45,  '1610',  'E20',  'T1610',  'Jardín Alto'),
  (67,  '1622',  '322',  'T1622',  'Jardín Alto'),
  (126, '1637',  'E07',  'T1637',  'Jardín Alto'),
  (165, '1650e', '290e', 'T1650E', 'Jardín Alto'),
  (196, '1625',  '325',  'T1625',  'Gabriela'),
  (197, '1612',  'E12',  'T1612',  'Gabriela'),
  (198, '1613',  'E13',  'T1613',  'Gabriela'),
  (199, '1615c', 'E15c', 'T1615C', 'Gabriela'),
  (200, '1616',  'E16',  'T1616',  'Gabriela'),
  (263, '1607',  '207',  'T1607',  'El Retiro'),
  (264, '1607c', '207c', 'T1607C', 'El Retiro'),
  (265, '1607e', '207e', 'T1607E', 'El Retiro'),
  (266, '1609',  '209',  'T1609',  'El Retiro'),
  (268, '1609c', '209c', 'T1609C', 'El Retiro'),
  (269, '1634',  '234',  'T1634',  'El Retiro'),
  (270, '1645',  '225',  'T1645',  'Gabriela'),
  (271, '1645c', '225c', 'T1645C', 'Gabriela'),
  (310, '1604e', '204e', 'T1604E', 'El Retiro'),
  (490, '1638',  'F28',  'T1638',  'El Retiro'),
  (862, '1602',  '302',  'T1602',  'Lo Blanco'),
  (863, '1602n', '302n', 'T1602E', 'Lo Blanco'),
  (864, '1635',  'E05',  'T1635',  'Jardín Alto'),
  (865, '1640',  'E10',  'T1640',  'Jardín Alto'),
  (866, '1640y', 'E10y', 'T1640C', 'Jardín Alto'),
  (867, '1618',  'E18',  'T1618',  'Lo Blanco'),
  (871, '1628',  'G28',  'T1628',  'Lo Blanco'),
  (954, '1603',  '503',  'T1603',  'Los Sauces'),
  (955, '1617c', 'J07c', 'T1617C', 'Los Sauces'),
  (956, '1619',  'J19',  'T1619',  'Los Sauces'),
  (959, '1623',  '323',  'T1623',  'Jardín Alto'),
  (960, '1633',  'E03',  'T1633',  'Jardín Alto');

-- Tipo de día de cada fecha, del archivo de velocidades vigente.
CREATE OR REPLACE VIEW v_tipo_dia AS
SELECT r.fecha, MIN(r.tipo_dia) AS tipo_dia
FROM vigencia_archivo v
JOIN raw_velocidades r ON r.carga_id = v.carga_id AND r.fecha BETWEEN v.fecha_inicio AND v.fecha_termino
WHERE v.tipo_archivo = 'velocidades' AND v.vigente = 1
GROUP BY r.fecha;

-- Transacciones de las cargas completadas, con servicio y tipo de día (lo que en indicadores-bi es
-- bi.transacciones_row). En zona paga nombre_servicio queda NULL: la validación no queda asignada al
-- servicio abordado (Apéndice 3, M.2). Un bus con CL que no está en dim_codigo_linea queda con
-- nombre_servicio NULL pero es_zona_paga = 0: filtrar ZP por es_zona_paga, no por el NULL.
CREATE OR REPLACE VIEW v_transacciones AS
SELECT t.id, t.carga_id, t.sitio, t.ppu, t.es_zona_paga, t.fecha_hora, t.fecha, t.mes,
       t.chip, t.tarjeta, t.ntt, t.tipo_trx, t.contrato, t.monto, t.estado,
       t.liquidacion, t.fecha_liquidacion, t.cl, t.crc,
       CASE WHEN t.es_zona_paga = 0 THEN l.codigo_ts_servicio END AS codigo_ts_servicio,
       CASE WHEN t.es_zona_paga = 0 THEN l.nombre_servicio END AS nombre_servicio,
       d.tipo_dia
FROM raw_transacciones t
JOIN control_carga c ON c.carga_id = t.carga_id AND c.estado = 'COMPLETADO'
LEFT JOIN dim_codigo_linea l ON l.codigo_linea = t.cl
LEFT JOIN v_tipo_dia d ON d.fecha = t.fecha;

-- q del mes sin el Ajuste ZPM (ese lo informa la liquidación).
CREATE OR REPLACE VIEW v_transacciones_mes AS
SELECT mes,
       COUNT(*) AS transacciones,
       SUM(es_zona_paga) AS transacciones_zona_paga,
       SUM(es_zona_paga = 0 AND nombre_servicio IS NULL) AS transacciones_bus_sin_servicio
FROM v_transacciones
GROUP BY mes;
