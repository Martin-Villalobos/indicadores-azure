-- Agrega el tamaño del lienzo de Power BI a una base portal_reportes ya creada.
-- Correr una vez, antes de publicar la web que lo usa:
--   mysql -h mysql-prueba-indicadores.mysql.database.azure.com -u mvillalobos -p --ssl-mode=REQUIRED < web/sql/portal_reportes_02_lienzo.sql
USE portal_reportes;

ALTER TABLE reporte
  ADD COLUMN ancho_lienzo INT NOT NULL DEFAULT 1280 AFTER url_powerbi,
  ADD COLUMN alto_lienzo  INT NOT NULL DEFAULT 720  AFTER ancho_lienzo;
