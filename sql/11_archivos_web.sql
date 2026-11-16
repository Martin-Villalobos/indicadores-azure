-- Archivos cargados en la web: eliminar una carga o cambiarle las fechas (ver vigencias.py).
-- ELIMINADO: la carga dejó de regir; sus filas raw quedan como historia hasta que se vuelva a subir.
ALTER TABLE control_carga MODIFY estado ENUM('PROCESANDO','COMPLETADO','ERROR','ELIMINADO') NOT NULL;

-- Rango que cubre la carga (el del archivo, o el que se le puso en la web). Decide qué días rige.
ALTER TABLE control_carga ADD COLUMN vigencia_desde DATE NULL AFTER filas_cargadas;
ALTER TABLE control_carga ADD COLUMN vigencia_hasta DATE NULL AFTER vigencia_desde;
ALTER TABLE control_carga ADD COLUMN modificado_por VARCHAR(255) NULL AFTER mensaje_error;
ALTER TABLE control_carga ADD COLUMN modificado_at DATETIME NULL AFTER modificado_por;

-- Cargas anteriores a este cambio: el rango sale de vigencia_archivo.
UPDATE control_carga c
JOIN (SELECT carga_id, MIN(rango_desde) AS desde, MAX(rango_hasta) AS hasta
      FROM vigencia_archivo GROUP BY carga_id) v ON v.carga_id = c.carga_id
SET c.vigencia_desde = v.desde, c.vigencia_hasta = v.hasta
WHERE c.vigencia_desde IS NULL;
