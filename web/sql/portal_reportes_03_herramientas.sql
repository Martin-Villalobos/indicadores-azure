-- Herramientas por rol y mantenedor de usuarios, sobre una base portal_reportes ya creada.
-- Correr una vez, antes de publicar la web que lo usa:
--   mysql -h mysql-prueba-indicadores.mysql.database.azure.com -u mvillalobos -p --ssl-mode=REQUIRED < web/sql/portal_reportes_03_herramientas.sql
USE portal_reportes;

ALTER TABLE rol
  ADD COLUMN puede_cargar   TINYINT(1) NOT NULL DEFAULT 0 AFTER es_admin,
  ADD COLUMN puede_maestros TINYINT(1) NOT NULL DEFAULT 0 AFTER puede_cargar;

-- Hasta ahora todos veían las herramientas: los administradores las siguen viendo (es_admin incluye todo).
UPDATE rol SET puede_cargar = 1, puede_maestros = 1 WHERE es_admin = 1;

-- El mantenedor de usuarios escribe en esta base. Si la web usa otro usuario de MySQL que el tuyo, dale permiso:
-- GRANT SELECT, INSERT, UPDATE, DELETE ON portal_reportes.* TO '<usuario de la web>'@'%';

-- Perfil Operaciones: sólo ve el menú Indicadores Operacionales, sin herramientas.
INSERT INTO rol (nombre, es_admin, puede_cargar, puede_maestros)
SELECT 'Operaciones', 0, 0, 0 FROM DUAL WHERE NOT EXISTS (SELECT 1 FROM rol WHERE nombre = 'Operaciones');
INSERT INTO permiso (rol_id, menu_id)
SELECT r.id, m.id FROM rol r JOIN menu m ON m.nombre = 'Indicadores Operacionales'
WHERE r.nombre = 'Operaciones'
  AND NOT EXISTS (SELECT 1 FROM permiso p WHERE p.rol_id = r.id AND p.menu_id = m.id);
