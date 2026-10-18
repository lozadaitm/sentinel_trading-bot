# Op4 tendencia: ¿un «seguro de empate» por debajo de 1 ATR? (19-oct-2026)

**Pregunta del usuario:** la Op4 de la cuenta de 10k llegó a +70 $ y volvió a −40 $ porque el trailing solo se arma a +1 ATR. ¿Conviene protegerla antes, aunque sea con holgura?

**Respuesta corta:** no como mejora clara. Un seguro temprano suaviza los episodios normales, pero recorta justo lo que la Op4 gana en las tendencias fuertes, que son su razón de ser. Se mantiene 1,0/0,5 ATR sin seguro.

## Qué se simuló

- **Modelo:** el mismo que `analisis-op4-direccion-2026-10-16.md`.
  - 245 recoveries reales, agrupadas en 46 episodios.
  - Velas M15, con orden conservador dentro de la vela.
  - Op4 tendencia con K = 2, entrada al cierre de vela y trailing 1,0/0,5 ATR.
  - El curador se queda el 90 % de cada ganancia.
- **Seguro añadido:** si la Op4 llega a +X ATR antes de armar el trailing, el SL pasa a entrada + Y ATR. Cuando llega a +1 ATR, manda el trailing normal.
- **Coste de spread:** 0 y 0,3 $/oz por cada Op4.

## Resultados (spread 0,3 $/oz; con 0 el orden es el mismo)

| Seguro | Mejora total $/oz | Sin los 3 mejores episodios | 14-oct $/oz | Peor episodio | Episodios + / − | Op4 |
|---|---|---|---|---|---|---|
| **Sin seguro (actual)** | **+377** | −81 | **+77** | −44 | 6 / 14 | 106 |
| a 0,3 ATR → SL en entrada | +334 | **+17** | +48 | −47 | 9 / 10 | 134 |
| a 0,3 ATR → SL en entrada + 0,1 ATR | +321 | +12 | +47 | −44 | 11 / 9 | 134 |
| a 0,5 ATR → entrada + 0,0–0,2 ATR | +255 a +280 | −27 a −47 | +47 a +50 | −44 | 7–8 / 11–12 | 123 |
| a 0,7 ATR → entrada + 0,0–0,2 ATR | +333 a +362 | −57 a −92 | +76 | −44 | 6 / 13–14 | 115 |

## Lectura

- **Seguro a 0,3 ATR:**
  - es el único que cambia algo: más episodios en positivo (9–11 frente a 6) y el resto del historial pasa de −81 a +12 / +17 $/oz;
  - a cambio, pierde un 40 % de lo que la Op4 gana en tendencias fuertes. El 14-oct baja de +77 a +48 $/oz, unos 640 $ menos en la cuenta de 10k.
  - Se cierran más Op4 en empate y la recovery queda más veces sin cobertura hasta la vela siguiente.
- **Seguro a 0,5 ATR:** peor en todo.
- **Seguro a 0,7 ATR:** casi igual que sin seguro; no aporta.
- **Peor episodio:** no cambia en ninguna variante (−41 a −47 $/oz), así que el seguro no reduce el riesgo de cola.
- **Por qué no hace falta:** con la exposición neta en cero, una Op4 en rojo no le cuesta nada al ciclo, porque la recovery gana lo mismo. El seguro solo sirve para cobrar algo en los vaivenes, y el precio es cortar las tendencias.

## Limitaciones

- **Velas M15 con orden conservador:** los stops cercanos se tocan más que en la realidad, así que los seguros tempranos pueden salir algo peor de lo que serían. Una pasada con M1 (disponible desde el 7-jul) lo afinaría.
- **Simulación aproximada:** sin el resto del ciclo (Unwind, cesta, candado) y con una muestra pequeña (8 episodios graves).

## Decisión

- Sin cambios: trailing 1,0/0,5 ATR y sin seguro.
- Si con más meses de datos los episodios normales pesan más que las tendencias, la opción a revisar es el seguro a 0,3 ATR → SL en entrada + 0,1 ATR.
