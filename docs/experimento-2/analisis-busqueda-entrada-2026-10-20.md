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

## Rondas 4 y 5 (20-oct): swap, ideas nuevas y validación móvil

**Cambios en el método** (a pedido del usuario: «¿los años están bien segmentados?»):
- **Swap incluido:** −0,774 $/oz por noche en compra, +0,367 $/oz en venta, triple el miércoles.
- **Validación móvil (`wf.py`):** para cada año de 2023 a 2026, la salida de cada regla se elige solo con los 2 años anteriores y se juzga en ese año.
- **Mezcla por escenario:** tendencia diaria × volatilidad × sesión. En cada escenario se elige, también con los 2 años anteriores, la mejor regla y salida.

**Ideas nuevas:**
- banda de ruido de Zarattini;
- noticias (FOMC, NFP e IPC: seguir o ir en contra; calendario en `bot_backtesting/fullsim/events_us.csv`, armado por un agente con fuentes oficiales);
- plata, euro/dólar, índice del dólar y bono de EE. UU. como adelantados del oro (Dukascopy, `fetch_cross.py`);
- picos de volumen (seguir o ir en contra);
- reversión al VWAP;
- un modelo de dirección con LightGBM (`ml_direction.py`): acierta el 50–51 % cada año, **no sirve**.

**Validación móvil por regla** (2023–2026, ganancia por operación en $/oz con todos los costes; ventaja = ganancia − azar):

| Regla | Años con ganancia | Años con ventaja | Operaciones | $/oz por operación | Ventaja | Salida que eligió |
|---|---|---|---|---|---|---|
| **Compra en la reapertura (01:00→10:00) con tendencia diaria alcista** | 4/4 | 4/4 | 569 | +2,82 | +2,59 | sin salida en contra; objetivo o hora |
| Compra en la reapertura (01:00→06:00), sin filtro | 4/4 | 4/4 | 979 | +1,62 | +1,61 | sin salida en contra |
| **Banda de ruido (10:00–22:00, una por día, cierre a las 23:00)** | 3/3 | 3/3 | 596 | +2,29 | +2,93 | sin objetivo ni salida en contra (por hora) |
| **Compresión de Bollinger H1 + ruptura** | 3/3 | 3/3 | 360 | +3,40 | +5,57 | sin salida en contra |
| Momentum diario (mantener 3 días) | 3/3 | 2/3 | 531 | +6,17 | +8,00 | depende mucho de 2026 |
| Resto (rupturas de Londres y Nueva York, reversión, VWAP, noticias, volumen, entre mercados, modelo ML) | — | — | — | ≈0 o negativo, o muy pocas operaciones | — | — |

**Mezcla por escenario** (elegida cada año con los 2 anteriores):

| Año | Resultado |
|---|---|
| 2023 | −636 $/oz |
| 2024 | +1 081 $/oz |
| 2025 | +3 186 $/oz |
| 2026 | +1 513 $/oz |

Gana 3 de 4 años, pero lo que elige cambia mucho de un año a otro y muchos escenarios tienen pocas operaciones. **Es menos fiable que quedarse con las reglas que funcionan solas.**

**Lectura:**
1. Hay **tres módulos** que sobreviven a la validación móvil, con ganancia y ventaja positivas todos los años probados:
   - la **compra en la reapertura asiática**, la candidata para la «Op Big One»;
   - la **banda de ruido** intradía (de 10:00 a 22:00);
   - la **compresión de volatilidad en H1**.
2. **En los tres, la mejor salida no usa salida en contra:** cierran por objetivo o por **hora**, en el mismo día. Eso encaja con no usar stop: la pérdida de cada operación queda acotada por el tiempo que está abierta, sin recovery ni cobertura.
3. **Cautelas:**
   - 2024–2026 fue un mercado alcista fuerte y los tres módulos son, sobre todo, de tendencia o de compra;
   - la ventaja de la reapertura vive en sus primeros minutos (la ejecución hay que medirla en vivo);
   - elegir estos tres mirando los resultados de la validación móvil es una segunda selección: hay que confirmarlo en demo.

## Los tres módulos juntos en un solo bot (`portfolio.py`, 20-oct)

**Simulación:** 2023-01 → 2026-10, con costes y swap. La salida de cada módulo se elige cada año con los 2 años anteriores, entre tres tipos:
- solo hora;
- objetivo de 1–3 ATR;
- trailing que se activa a 1–2 ATR y sigue a 0,5–1,5 ATR.

**1. Sin protección de precio (solo cierre por hora): inviable.** En enero–marzo de 2026 algunas operaciones fueron 300–400 $/oz en contra antes de la hora de cierre. Con el lote del bot (0,12 lotes por 5 000 $, la Big One al doble), la caída máxima fue del 118 % y la cuenta se quemó. Con la mitad del lote, la caída fue del 94 %.

**2. Con candado (Hedge Lock) a 1–3 ATR en contra:** congela la pérdida hasta la hora de cierre. En dinero equivale a un stop, más ~0,32 $/oz de coste. El lote se calcula para que el candado cueste un % fijo del equity (la Big One, el doble).

**Ganancia por unidad de riesgo (R)** fuera de muestra:

| Módulo | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|
| Big One | +0,17 | +0,22 | +0,22 | **−0,07** |
| Banda de ruido | −0,15 | +0,07 | −0,02 | +0,06 |
| Compresión H1 | 0,00 | +0,01 | −0,06 | +0,11 |

Con candado, **solo la Big One aporta**. La banda de ruido y la compresión quedan en ≈0: su ganancia sin candado venía de aguantar movimientos enormes.

**Cuentas, solo con la Big One** (ganancia anual compuesta, peor caída y resultado por año):

| Cuenta | Riesgo por operación | Anual | Peor caída | 2023 / 2024 / 2025 / 2026 |
|---|---|---|---|---|
| 1 000 | 0,5 % | +24,7 % | 19,7 % | +20 / +39 / +45 / −7 % |
| 5 000 | 0,5 % | +28,5 % | 21,4 % | +22 / +44 / +52 / −5 % |
| 10 000 | 0,5 % | +29,1 % | 21,5 % | +22 / +44 / +53 / −5 % |
| 10 000 | 1 % | +62,1 % | 38,9 % | +49 / +98 / +124 / −11 % |

- En 1 000 el lote mínimo de 0,01 hace que el riesgo real sea mayor que el nominal.
- **2026 es negativo.** Con la volatilidad muy alta, el candado a 1 ATR saltó en 42 de 63 operaciones.

**Trailing que eligió la validación móvil para la Big One:** se activa tras **2 ATR** a favor y sigue a **0,5–1,5 ATR**, según el año. No hay objetivo fijo, porque el trailing rinde más.

**Cautelas:**
- la ventaja vive en los primeros minutos tras la reapertura (la ejecución real no está medida);
- Dukascopy no es el feed del broker;
- hubo selección de módulos mirando resultados;
- 2023–2025 fueron años alcistas y **2026 ya muestra deterioro**.

**Siguiente paso:** validarlo en una cuenta demo antes de cualquier otra cosa.
