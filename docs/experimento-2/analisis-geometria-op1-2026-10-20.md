# ¿Tiene ventaja la señal de la Op1 con alguna forma de salir? (20-oct)

**Pregunta:** después de 5 análisis que solo frenan la pérdida del ciclo (Op4, recortes, orden, filtro ML), queda medir si la **señal de entrada de la Op1** gana dinero con **alguna** salida simple. Si gana, se rediseña la salida. Si no, ningún ajuste del ciclo la salva.

**Método** (`bot_backtesting/fullsim/geometry.py`):
- **Entradas:** las primeras de cada racha del motor real. Son 8 161: 7 201 de Dukascopy (2021-2026) y 960 del broker (2026).
- **Salidas:** cierre a +TP × ATR (0,25 a 3), a −SL × ATR (0,5 a 4) o a mercado al cabo de 24 h o 120 h. En total, 72 combinaciones.
- **Costes:** spread de 0,20 $ y comisión de 0,12 $/oz. Si en una misma vela M5 se tocan las dos salidas, cuenta la de pérdida.
- **Referencias con la misma salida:**
  - entrar a la misma hora en la **dirección contraria**;
  - entrar en velas M15 al **azar**, con dirección al azar.
- Es una vara de medir: no implica adoptar stops.

## Resultado

| | |
|---|---|
| Combinaciones con ganancia media positiva | **0 de 72** |
| Mejor combinación (TP 3 ATR, SL 1,5 ATR, 24 h) | **−0,17 $/oz por entrada** |
| La misma combinación al azar / en dirección contraria | −0,48 / −0,33 $/oz |
| Combinaciones en que la señal supera al azar | 66 de 72, por 0,03–0,43 $/oz |

**Mejor combinación, por año** ($/oz por entrada):

| Año | Señal | Contraria | Azar |
|---|---|---|---|
| 2021 | −0,28 | −0,44 | −0,49 |
| 2022 | **−0,42** | −0,33 | −0,28 |
| 2023 | −0,10 | −0,49 | −0,32 |
| 2024 | −0,30 | −0,59 | −0,32 |
| 2025 | +0,10 | −0,36 | −1,16 |
| 2026 | +0,02 | +0,49 | −0,25 |

## Lectura

- **La señal tiene algo de información de dirección:** supera al azar y a la dirección contraria en casi todas las combinaciones. Pero esa ventaja, de unos 0,1 a 0,3 $/oz, es **menor que el coste de operar** (~0,32 $/oz por ida y vuelta). Y no es estable: en 2022 fue peor que el azar.
- **Con ninguna forma simple de salir la Op1 gana dinero.** La estructura actual (objetivo pequeño y cobertura a 2 ATR, con el ciclo detrás) tampoco: ver `analisis-op4-criterio-propio-2026-10-19.md`, sección 5.
- **Consecuencia:** optimizar lo que pasa después de la cobertura (Op2, Op3, Op4, curador) solo puede frenar la pérdida, no darle la vuelta. Para que el bot gane, **la entrada tiene que cambiar**: una señal con una ventaja claramente mayor que el coste.

**Límites:**
- Salidas simples: no prueba trailing ni salidas por señal.
- Coste constante.
- La referencia al azar depende de la tendencia del oro (fuertemente alcista entre 2021 y 2026).
