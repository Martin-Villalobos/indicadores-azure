-- Base portal_reportes (MySQL, mismo servidor que indicadores_bi): menú dinámico de Power BI de la web interna y permisos por usuario.
-- Menú dinámico de Power BI + permisos con usuarios de Entra ID.
-- No es una migración del job: se ejecuta a mano (mysql ... < web/sql/portal_reportes.sql).

CREATE DATABASE IF NOT EXISTS portal_reportes CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE portal_reportes;

-- Tabs laterales: 'Indicadores operacionales', 'ITE', ...
CREATE TABLE menu (
  id          INT AUTO_INCREMENT PRIMARY KEY,
  nombre      VARCHAR(100) NOT NULL,
  icono       VARCHAR(50)  NULL,
  orden       INT NOT NULL DEFAULT 0,
  activo      TINYINT(1) NOT NULL DEFAULT 1
);

-- Submenú: cada Power BI dentro de una tab: 'ICFP', 'IP', 'IE', 'ITE'
CREATE TABLE reporte (
  id          INT AUTO_INCREMENT PRIMARY KEY,
  menu_id     INT NOT NULL,
  nombre      VARCHAR(100) NOT NULL,
  descripcion VARCHAR(500) NULL,
  url_powerbi VARCHAR(1000) NOT NULL,
  orden       INT NOT NULL DEFAULT 0,
  activo      TINYINT(1) NOT NULL DEFAULT 1,
  FOREIGN KEY (menu_id) REFERENCES menu(id)
);

-- Usuarios de Entra ID, registrados a mano por su email (= userDetails del clientPrincipal).
CREATE TABLE usuario (
  id            INT AUTO_INCREMENT PRIMARY KEY,
  email         VARCHAR(255) NOT NULL UNIQUE,
  nombre        VARCHAR(150) NULL,
  activo        TINYINT(1) NOT NULL DEFAULT 1,
  ultimo_acceso DATETIME NULL
);

-- Perfiles: 'Administrador', 'Operaciones', 'Gerencia', ...
CREATE TABLE rol (
  id              INT AUTO_INCREMENT PRIMARY KEY,
  nombre          VARCHAR(100) NOT NULL UNIQUE,
  es_admin        TINYINT(1) NOT NULL DEFAULT 0   -- puede gestionar menús, reportes y permisos
);

CREATE TABLE usuario_rol (
  usuario_id  INT NOT NULL,
  rol_id      INT NOT NULL,
  PRIMARY KEY (usuario_id, rol_id),
  FOREIGN KEY (usuario_id) REFERENCES usuario(id),
  FOREIGN KEY (rol_id)     REFERENCES rol(id)
);

-- Qué ve cada perfil: una tab completa (menu_id) o un reporte puntual (reporte_id).
CREATE TABLE permiso (
  id          INT AUTO_INCREMENT PRIMARY KEY,
  rol_id      INT NOT NULL,
  menu_id     INT NULL,
  reporte_id  INT NULL,
  FOREIGN KEY (rol_id)     REFERENCES rol(id),
  FOREIGN KEY (menu_id)    REFERENCES menu(id),
  FOREIGN KEY (reporte_id) REFERENCES reporte(id),
  CHECK ((menu_id IS NULL) <> (reporte_id IS NULL)),
  UNIQUE (rol_id, menu_id, reporte_id)
);

-- Lo que la API lee para el usuario que inició sesión (email del header x-ms-client-principal):
-- SELECT DISTINCT m.id menu_id, m.nombre menu, m.icono, m.orden orden_menu,
--        r.id reporte_id, r.nombre reporte, r.descripcion, r.url_powerbi, r.orden
-- FROM usuario u
-- JOIN usuario_rol ur ON ur.usuario_id = u.id
-- JOIN rol ro ON ro.id = ur.rol_id
-- JOIN permiso p ON p.rol_id = ro.id
-- JOIN reporte r ON r.id = p.reporte_id OR r.menu_id = p.menu_id
-- JOIN menu m ON m.id = r.menu_id
-- WHERE u.email = ? AND u.activo = 1 AND m.activo = 1 AND r.activo = 1
-- ORDER BY m.orden, r.orden;
