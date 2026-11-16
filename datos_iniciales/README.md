# Datos iniciales

Archivos que el job carga solo en una base nueva, para no tener que subirlos uno a uno en la web
al pasar a otra instancia. Se dejan en la carpeta de su tipo:

| Carpeta        | Archivo                         |
|----------------|---------------------------------|
| `anexo1/`      | Anexo 1 (.xlsx)                 |
| `anexo3/`      | Anexo 3 (.xlsx)                 |
| `exclusiones/` | Exclusiones del DTPM (.xlsx)    |
| `velocidades/` | Velocidades (.xlsx)             |

Se pueden usar subcarpetas (por ejemplo `anexo1/2026/`). Se hace commit de los archivos y, al
desplegar a main, el workflow los copia al blob (`iniciales/`, sólo los que faltan; no van en la
imagen del job) y el job los procesa igual que si vinieran de la web: aparecen en
"Archivos cargados" como subidos por **carga inicial**, con sus vigencias, errores y advertencias.

- Cada archivo se carga **una sola vez por base** (queda en la tabla `carga_inicial`). Si después
  se elimina su carga en la web, no vuelve a aparecer.
- Un archivo que se agregue más tarde también se carga, en el próximo despliegue.
- En dev la carpeta está montada: el job la copia al Azurite y la carga al partir.
- Se procesan en orden alfabético de ruta. Si dos archivos cubren las mismas fechas con el mismo
  rango, rige el de nombre mayor; si no, la regla de siempre (el rango más corto).
- Un archivo con error queda con su motivo en "Archivos cargados" y no se reintenta: se corrige
  y se deja con otro contenido (o se sube por la web).
