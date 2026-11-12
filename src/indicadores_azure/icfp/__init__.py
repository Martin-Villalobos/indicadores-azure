"""Cálculo del ICFP (Contrato 5.3.1.6), por servicio-sentido-hora-día.

Pasos (los mismos de indicadores-bi, ``icf_icp/inicial.py`` y ``icf_icp/correcciones.py``):
  1. ``programa``: exigencia por hora desde el Anexo 3 vigente (suma de sus dos MH).
  2. ``inicial``: expediciones OK de velocidades contra la exigencia -> ICF e ICP iniciales.
  3. ``correcciones``: trasvasije de extremos (5.3.1.6.6) entre horas vecinas, incluso entre días.
  4. ``sspd``: km programados, km válidos y exclusiones DTPM (hoja ICFP-IE) por fila.
  5. ``calculo``: lee la base según vigencia_archivo y guarda todo en un ``calculo`` nuevo.
"""
