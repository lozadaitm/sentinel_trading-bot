# Búsqueda de una entrada nueva con ventaja (20-oct): rondas 1 a 3

**Motivo:** la señal de la Op1 no gana con ninguna salida (`analisis-geometria-op1-2026-10-20.md`).

**Herramienta:** `bot_backtesting/fullsim/entrylab.py`.

**Datos:** M5 continuo de Dukascopy (2021-01 → 2026-01) más el broker (2026-01 → 2026-10), con M15, H1, H4 y D1 en hora de servidor.

## Método

**Entrada:** a la **apertura** de la primera vela M5 tras la decisión. Al principio se entraba al cierre de la vela anterior, lo que regalaba el salto tras la pausa diaria; se corrigió en la ronda 3.

**Salidas** (20 combinaciones):
- objetivo de 0,5 / 1 / 2 / 3 × ATR de la regla, o sin objetivo;
- salida en contra a 0,5 / 1 / 2 × ATR, o sin ella;
- y siempre, cierre por tiempo.

**Costes:** spread de 0,20 $ y comisión de 0,12 $/oz. La mediana real del broker es 0,12 $ en todas las horas y su p90 es 0,17 $ a la 01:00.

**Referencia:** 3 entradas al azar por evento, con el mismo lado y en otro día del mismo tramo:
- a la misma hora (`matched`);
- o a cualquier hora (`anytime`), para las reglas de horario, porque si no se anularía el efecto que se quiere medir.

La «ventaja» es la ganancia de la señal menos la del azar. Su t se calcula agrupando por día.

**Validación:** se elige con 2021–2023 y se juzga con 2024–2026.

**Criterio para aprobar:** ganancia > 0 y ventaja > 0, en los dos tramos.

## Ronda 1: 18 reglas clásicas, 360 pruebas

- **Reglas:** rupturas Donchian (H1, H4, D1), cruces de EMA (H1, H4, D1), rango asiático → Londres, rupturas del primer tramo de Londres y Nueva York, momentum intradía, compresión de Bollinger (M15, H1), reversión tras velas de 3 ATR (M15, H1) y RSI(2) a favor de la SMA200 diaria.
- **Resultado:** **7 de 360** cumplen el criterio, todas con t < 1,5. Es menos de lo que daría el azar. **Ninguna sirve.**

## Ronda 2: 8 reglas con respaldo en la literatura, 160 pruebas

Fuente: `investigacion/entradas-oro-evidencia-2026-10-20.md`.

| Regla | Ventaja 2021–23 | Ventaja 2024–26 | Lectura |
|---|---|---|---|
| Momentum diario (1 y 3 meses), mantener 1, 3 o 5 días | +0,5 a +2,0 $ (t ≤ 1,3) | +2 a +4 $ (t ≤ 1,0) | Positivo pero no significativo; muy dependiente de la subida del oro |
| Venta 16:00 → 23:00 (sesión de Nueva York) | +0,5 (t 1,9–2,1) | +1,4 (t 1,7) | Supera al azar 6/6 años, pero en dinero pierde 4 de 6 años según la salida |
| Momentum hacia el cierre COMEX | ≈0 | +1,1 (t 2,0) | No pasa en 2021–23 |
| Reversión al día siguiente de un día extremo | +1,9 (t 1,8) | ≈0 en dinero | Muy pocos eventos (61) |
| **Compra 01:00 → 10:00 (sesión asiática)** | +0,46 (t 7,9) | +0,45 (t 2,1) | **Fuerte, pero ver la ronda 3** |

## Ronda 3: variantes fijadas de antemano

**Hora de entrada de la compra asiática:**
- A la 01:15 la t cae de 7,9 a 1,5; a las 02:00, a 2,0.
- **El efecto está casi entero en los primeros 15 minutos tras la reapertura diaria.**

**Con filtro de momentum diario** (s = signo(C−C21) + signo(C−C63) del día anterior = +2):

| Variante | Mejor salida | 2021–23: ganancia / ventaja / t | 2024–26: ganancia / ventaja / t | Años con ventaja |
|---|---|---|---|---|
| **Compra 01:00, solo con tendencia diaria alcista** | objetivo 2 ATR, en contra 0,5 ATR, máx. 9 h | +0,27 / +0,70 / 4,0 | +1,13 / +1,19 / 2,8 | **6/6** |
| Misma, entrada 01:15 | — | −0,17 / +0,49 / 1,4 | +0,81 / +0,82 / 0,9 | 5/6 |
| Misma, entrada 02:00 | — | −0,17 / +0,09 / 1,3 | −0,32 / +0,07 / 0,4 | 4/6 |
| Venta Nueva York si la tendencia no es alcista | — | −0,08 / +0,62 / 1,1 | +0,81 / +1,39 / 0,6 | 5/6 |

**Ganancia por año de la candidata** (01:00, objetivo 2 ATR, en contra 0,5 ATR; $/oz por operación, con la del azar entre paréntesis):

| Año | Ganancia (azar) |
|---|---|
| 2021 | +0,03 (−0,37) |
| 2022 | +0,16 (−0,50) |
| 2023 | +0,46 (−0,42) |
| 2024 | +0,41 (−0,01) |
| 2025 | +1,23 (+0,29) |
| 2026 | +2,88 (−1,33) |

## Conclusión de las rondas 1 a 3

- De unas **30 reglas y unas 600 pruebas**, la única candidata que cumple en los dos tramos y los 6 años es la **compra en la reapertura diaria (01:00 hora servidor) con la tendencia diaria alcista**.
- **Hay una duda que la simulación no puede resolver:** su ventaja vive en los primeros 15 minutos tras la pausa diaria. Ahí el spread y el deslizamiento reales pueden ser peores que en las velas M5. Las velas solo guardan el spread mínimo, y la ganancia por operación es pequeña: 0,1–0,7 ATR M15.
- **Siguiente paso propuesto:** probarla en una cuenta demo aparte, solo esa entrada y con lote mínimo, para medir los precios reales de ejecución a la 01:00 antes de construir nada encima.
- **El respaldo de la Op3 en adelante** se diseña después, con la entrada que sobreviva.
- **Riesgo de búsqueda múltiple:** con unas 600 pruebas cabe esperar algún falso positivo. Esta candidata tiene t 4,0 dentro de muestra y se confirmó fuera de muestra en variantes fijadas de antemano, lo que reduce ese riesgo pero no lo elimina.
