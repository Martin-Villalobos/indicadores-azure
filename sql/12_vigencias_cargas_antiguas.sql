-- Cargas hechas antes de que existieran las vigencias (sin filas en vigencia_archivo): su rango sale
-- de las fechas de sus filas raw. Después el job arma sus tramos con vigencias.completar_faltantes.
UPDATE control_carga c
JOIN (SELECT carga_id, MIN(fecha_inicio) AS desde, MAX(fecha_termino) AS hasta FROM raw_anexo1 GROUP BY carga_id) r
  ON r.carga_id = c.carga_id
SET c.vigencia_desde = r.desde, c.vigencia_hasta = r.hasta
WHERE c.vigencia_desde IS NULL AND c.estado = 'COMPLETADO' AND c.tipo_archivo = 'anexo1';

UPDATE control_carga c
JOIN (SELECT carga_id, MIN(fecha_inicio) AS desde, MAX(fecha_termino) AS hasta FROM raw_anexo3 GROUP BY carga_id) r
  ON r.carga_id = c.carga_id
SET c.vigencia_desde = r.desde, c.vigencia_hasta = r.hasta
WHERE c.vigencia_desde IS NULL AND c.estado = 'COMPLETADO' AND c.tipo_archivo = 'anexo3';

UPDATE control_carga c
JOIN (SELECT carga_id, MIN(fecha) AS desde, MAX(fecha) AS hasta FROM raw_velocidades GROUP BY carga_id) r
  ON r.carga_id = c.carga_id
SET c.vigencia_desde = r.desde, c.vigencia_hasta = r.hasta
WHERE c.vigencia_desde IS NULL AND c.estado = 'COMPLETADO' AND c.tipo_archivo = 'velocidades';

-- Exclusiones: meses completos (VIGENCIA_POR_MES).
UPDATE control_carga c
JOIN (SELECT carga_id, DATE_FORMAT(MIN(fecha), '%Y-%m-01') AS desde, LAST_DAY(MAX(fecha)) AS hasta
      FROM raw_exclusiones GROUP BY carga_id) r
  ON r.carga_id = c.carga_id
SET c.vigencia_desde = r.desde, c.vigencia_hasta = r.hasta
WHERE c.vigencia_desde IS NULL AND c.estado = 'COMPLETADO' AND c.tipo_archivo = 'exclusiones';
