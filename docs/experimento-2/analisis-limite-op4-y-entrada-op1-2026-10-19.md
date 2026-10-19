# Límite de Op4 en ciclo completo y entrada de la Op1 (19-oct-2026)

**Origen:** continuación de `analisis-ciclo-paralelo-2026-10-19.md`.
- **Mismo arnés:** motor real, del 1-mar al 16-oct, con swap y spread fijo.
- **El usuario intuía** que lo mejor era quitar el límite de Op4.
- **Y pidió** investigar cómo mejorar la entrada de la Op1, porque los ciclos congelados nacen de ella.

## 1. Límite de Op4: sin límite es mejor (el usuario tenía razón)

| Cuenta | Bot actual, límite 20 | Bot actual, sin límite | Parejas, límite 20 | **Parejas, sin límite** |
|---|---|---|---|---|
| 10k | 5 973 (−40 %, caída máx. −43 %) | 6 445 (−36 %, −37 %) | 6 858 (−31 %, −33 %) | **7 061 (−29 %, −30 %)** |
| 5k | 3 058 (−39 %, −42 %) | 3 261 (−35 %, −36 %) | 3 471 (−31 %, −33 %) | **3 674 (−27 %, −28 %)** |
| 1k | 447 (−55 %, −75 %) | 651 (−35 %, −36 %) | 447 (−55 %, −75 %) | **651 (−35 %, −36 %)** |

- **Con límite 50, el resultado es idéntico a sin límite:** en 7,5 meses el máximo usado fue de 32 Op4 en un ciclo.
- **La cuenta de 1k** es la que más gana al quitar el límite: su caída máxima baja del 75 % al 36 %.
- **Lo que no cambia:** el ciclo de marzo tampoco se libera sin límite.
  - Tras la caída, el oro se mueve de lado y la Op4 abierta deja de cobrar.
  - El ciclo pasa 155 días congelado, con neto 0, en vez de quedar con la recovery expuesta. Pierde menos, pero sigue atascado.
- Esto contradice al análisis por recoveries sueltas (`analisis-op4-limite-y-secundaria-2026-10-19.md`), que salía peor sin límite. El ciclo completo es la medida más fiable, porque incluye cesta, swap, candado y margen.

**Recomendación:** `rescue_trend_max_legs` sin límite en la práctica (p. ej. 1000). Es solo configuración, con recarga en caliente.

## 2. Entrada de la Op1: los filtros apenas ayudan; el problema es la proporción ganancia/riesgo

**Datos:**
- Con el motor real se registraron todas las barras en que la Op1 abriría (gates del ESTADO 0), del 20-feb al 16-oct: 2 668 barras, 960 de ellas primeras de una racha.
- Para cada una se simuló la Op1 sola en velas M5:
  - **WIN:** el trailing de cesta la cierra en verde (pico ≥ max(0,83; 0,33 + retroceso) $/oz más comisión);
  - **HEDGE:** llega a la distancia de cobertura, max(8 $, 2 ATR).

**Resultados:**
- **Acaban en cobertura el 10 %** (10,5 % de las primeras entradas, 9,7 % del resto).
- **Ninguno de los 13 rasgos de entrada separa las coberturas.**
  - Rasgos: volatilidad relativa, extensión sobre la EMA, RSI, rango y cuerpo de la vela, impulso de 4 h y de 24 h, posición en el rango de 24 h, pendiente de la EMA50 H4, distancia a la EMA200 H4, distancia al nivel roto, hora, día y mes.
  - Por quintiles, todos quedan entre el 8 y el 12 %.
- **Solo 2 filtros son estables** en las dos mitades (feb–jun y jul–oct):
  - impulso de 4 h a favor > 2,6 ATR: 8–9 % frente a 11 %;
  - RSI a favor > 67,6: 8 % frente a 10–11 %.

  Los dos eliminan entre el 60 y el 80 % de las entradas.
- **Peor que al azar:** con su objetivo y su distancia de cobertura, un paseo aleatorio daría un 7,1 % de coberturas; las rupturas del bot dan un 10 %. Comprar o vender la ruptura tiende a revertir justo después.
- **La proporción es el problema de fondo:**
  - una Op1 ganadora cobra unos 0,33 $/oz (estimación conservadora, hasta 0,8);
  - hasta la cobertura arriesga unos 19 $/oz de media (ATR medio 9,5 $).
  - Con un 10 % de coberturas, la Op1 solo es rentable si un ciclo cuesta de media menos de ~3 $/oz, y los ciclos cuestan mucho más.

**Conclusión:** un filtro de entrada sí puede aportar algo (de 11 a 8 %), pero no cambia la cuenta. Las palancas reales son:
1. el coste medio de un ciclo (Op4 sin límite, recorte por parejas, ya medidos);
2. la relación entre lo que gana la Op1 y la distancia de cobertura. Con entradas que no tienen ventaja, cambiar esa relación mueve el reparto entre ganancias pequeñas y ciclos, no la esperanza. Hay que medirlo en ciclo completo antes de proponer nada.

## Limitaciones

- Las del arnés: cierre de vela M15, sin noticias ni M5, un solo camino de precios.
- En el estudio de la Op1, el desenlace se simuló con velas M5 y orden conservador, con una ganancia estimada al mínimo.
