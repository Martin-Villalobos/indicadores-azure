-- Una vez: recalcular el ICFP de todos los días con velocidades. En la base de prueba de Azure, la
-- primera carga inicial corrió en dos ejecuciones a la vez y la que se cayó no alcanzó a encolar el
-- recálculo de los anexos que cargó. En una base nueva (sin velocidades todavía) no inserta nada.
INSERT IGNORE INTO recalculo_pendiente (indicador, fecha_desde, fecha_hasta, creado_at)
SELECT 'ICFP', MIN(vigencia_desde), MAX(vigencia_hasta), NOW()
FROM control_carga
WHERE tipo_archivo = 'velocidades' AND estado = 'COMPLETADO'
HAVING COUNT(*) > 0;
