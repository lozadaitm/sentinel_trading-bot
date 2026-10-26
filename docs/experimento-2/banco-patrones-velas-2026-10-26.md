# Banco de patrones de velas (M15 / M5 / M1) — resumen, 2026-10-26

Pregunta: ¿hay patrones de velas que se cumplan «siempre o casi siempre» y que el bot e2 pueda
operar con vigilancia tick a tick? Protocolo: investigacion/patrones-protocolo-2026-10-26.md.

| Equipo | Variantes | Pasan todos los filtros | Detalle |
|---|---|---|---|
| Geométricos (V, W, M, HCH, banderas, triángulos, rupturas falsas) | 8 600 | 0 | investigacion/patrones-geometricos-2026-10-26.md |
| Velas japonesas (envolventes, pin bars, interiores, estrellas, rachas…) | 14 400 | 0 | investigacion/patrones-velas-2026-10-26.md |
| Formas sin nombre (k-means / SAX / análogos) | 309 120 | 0 (la búsqueda no supera al azar en la permutación) | investigacion/patrones-formas-2026-10-26.md |

## Conclusiones

- **Ningún patrón pasa.** Lo mejor de la mitad A se cae en la B; el número de «ganadores» es el
  que daría el azar. Con el costo real (~0,15-0,26 $/oz) el patrón típico pierde.
- **Acierto alto ≠ ganar:** aparecen variantes con 60-62 % de acierto y −3,75 a −5,22 $/oz por
  operación; de 79 variantes geométricas con acierto ≥ 60 % en A, 44 pierden en B.
- **Una sola coincidencia, en vigilancia (no al bot):** dos equipos, por caminos distintos,
  llegaron al mismo fenómeno en M5: **compra tras una caída brusca (capitulación de 2-4 ATR en
  5-7 velas, mejor en tendencia diaria +2), salida a las 4 velas (20 min)**.
  Velas: n = 336, A +2,02 / B +1,98 $/oz (t_B 2,63). Formas: n = 397, A +2,02 / B +1,87
  (t_B 2,11). No pasa BH estricto, los vecinos (rachas de 4 y 6, M15, M1) no lo confirman y la
  permutación no lo respalda; además ambos equipos miraron los mismos datos, así que la
  coincidencia no es una confirmación independiente. Queda como registro en papel hacia
  adelante con los ticks que junta el recolector semanal; se reevalúa con 6 meses nuevos.

Decisión: el bot e2 sigue con sus tres patas; no se añade ninguna pata de patrones de velas.
