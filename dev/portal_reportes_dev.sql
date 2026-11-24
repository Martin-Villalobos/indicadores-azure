-- Sólo entorno dev (docker compose): MySQL lo corre al crear el volumen, después de
-- web/sql/portal_reportes.sql. Deja al usuario simulado (DEV_USUARIO, por defecto dev@local)
-- con un menú de ejemplo. Con un volumen ya creado: docker compose down -v (borra la base).
GRANT ALL PRIVILEGES ON portal_reportes.* TO 'indicadores'@'%';

USE portal_reportes;
INSERT INTO menu (nombre, orden) VALUES ('Indicadores Operacionales', 1);
INSERT INTO reporte (menu_id, nombre, descripcion, url_powerbi, orden) VALUES
  (LAST_INSERT_ID(), 'ICFP', 'Índice de Cumplimiento de Frecuencia y Plazas (ejemplo dev).',
   'https://app.powerbi.com/view?r=eyJrIjoiMWQyOGQ0MmEtN2VlZi00OGMyLThlMWEtYzk3ODgzNzQ5OWRiIiwidCI6ImQ1NzFiM2Q1LTRkNGItNDRkMy04ZGM3LWZkODkyZjQ1NTQ2OCIsImMiOjR9', 1);
INSERT INTO rol (nombre, es_admin, puede_cargar, puede_maestros) VALUES ('Administrador', 1, 1, 1);
INSERT INTO usuario (email, nombre) VALUES ('dev@local', 'Usuario dev');
INSERT INTO usuario_rol (usuario_id, rol_id) VALUES (LAST_INSERT_ID(), (SELECT id FROM rol WHERE nombre = 'Administrador'));
INSERT INTO permiso (rol_id, menu_id) SELECT r.id, m.id FROM rol r, menu m;
