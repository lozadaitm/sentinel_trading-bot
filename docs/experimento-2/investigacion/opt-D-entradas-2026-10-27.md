# Línea D — proyectar entradas (orden límite, stop de entrada, escalonado, TWAP) — 27-oct-2026

> **Veredicto: NO pasa ninguna idea.** Ninguna de las 1 082 variantes llega a 1,25 × el MAR base en `sel` y en `val`.
> - **Orden límite (Big One y Momentum):** comprar un poco más barato llena sobre todo las operaciones que después van mal. Las que se escapan sin llenar son las buenas.
> - **Stop de entrada (Momentum):** el MAR de `sel` sube (×1,66), pero solo porque quita la mitad de las operaciones y baja la caída. Gana menos R que la base, depende de 2023 y en `val` queda en ×1,03 / ×0,84.
> - **Escalonar y TWAP:** peor que entrar de una vez.
> - **Big One:** cualquier mejora del precio de entrada en 2022-2025-05 está contaminada por los datos. La primera vela M5 de Dukascopy no reproduce la subida de 01:01 a 01:05 que sí muestra el broker (+1,0 $/oz).
>
> **Recomendación:** dejar la entrada como está (a mercado, a la hora de la señal).

Solo simulación. No se tocó `bot/` ni MT5, y 2026 no se miró.

**Scripts** (en `bot_backtesting/fullsim/`):

| Script | Qué hace |
|---|---|
| `opt_D_common.py` | Simulador de entradas. Reproduce la base exacta: diferencia 0,0 $/oz en las 1 256 operaciones. |
| `opt_D_limite.py` | Grillas `limit`, `stop` y `ladder`. |
| `opt_D_otras.py` | `twap`, `mom_pre` y `qlim`. |
| `opt_D_final.py` | Finalistas, nulos y `val`. |

Los resultados crudos están en `results/optD_*`.

## 1. Cómo se simuló (y por qué es conservador)

- **Misma operación.** Se mantienen la pata, el lado, el peso, el lote (calculado con el balance al momento de la señal) y la hora de salida. Solo cambian el precio y el momento de entrada.
- **Medida de los TP y del candado.** Se probaron las dos formas:
  - `new`: desde el precio nuevo;
  - `orig`: desde el precio original de la señal.
- **Llenado de la orden límite de compra.** Llena solo si el ask (bid mínimo de la vela + spread máximo de sus 5 minutos) atraviesa el límite en **0,05 $/oz**. Un simple toque no cuenta.
  - Llena al límite, o al open si la vela ya abre por debajo.
  - Sin deslizamiento; la comisión sí se cobra.
  - Prueba de robustez: exigir 0,15 $/oz no cambia nada.
- **Vela del llenado (lo peor para la idea).** Después de llenar, el precio solo va en contra (hasta el mínimo de la vela) y lo mejor que puede pasar es el cierre de esa vela. Por eso el TP no se cobra en la vela del llenado.
- **Stop de entrada.** Llena al nivel más 0,05 $/oz de deslizamiento. La vela del llenado se trata igual de conservadora.
- **Si la orden no llena al vencer:**
  - `lost`: la operación se pierde;
  - `mkt`: entra a mercado en el open siguiente (spread + deslizamiento).
  - El escalonado cubre el caso «la parte no llenada a mercado».
- **Niveles fijos.** Todos los niveles se fijan al poner la orden, con el precio y el ATR conocidos en ese momento. Nunca se recalculan con el máximo o el mínimo de la vela en curso. No aplica el artefacto que encontró la Línea A con los trailing.
- **Big One.** El camino empieza en la vela de 01:05: la vela 01:00-01:05 queda fuera, igual que en `trade_path`. Así no se puede llenar con el bid hundido del rollover.

## 2. Resultados por idea (`sel` = 2022-10 → 2024-12; base MAR 3,39)

| Idea | Variantes | Mejor MAR ×base en `sel` | Mediana | Veredicto |
|---|---|---|---|---|
| 1. Límite a −x (x = 0,25-3 ATR15 o 0,01-0,10 ATR_D; N = 15/30/60/120 min; `lost`/`mkt`; `new`/`orig`), por pata | 480 | Big One 1,19 · Momentum 1,07 · NFP 1,01 | 0,76-0,88 | descartada |
| 1b. Límite en un cuantil **predicho** del mínimo de la primera hora (Big One, regresión por cuantiles walk-forward) | 24 | 1,05 | 0,87 | descartada |
| 2. Escalonar la misma orden en 2-3 límites | 288 | 1,08 (Momentum) | 0,80 | descartada |
| 3. Stop de entrada (confirmación a favor) | 240 | **1,66** (Momentum, falla el peor día) | 0,82 | descartada (ver §3) |
| 4. Momentum adelantado (señal y entrada a 14:45 o 14:30) | 2 | 0,98 (14:30) / 0,82 (14:45) | — | descartada |
| 4b. Momentum con límite en el retroceso de 15:00-15:30 (dentro de la idea 1) | (en 1) | 1,07 | — | descartada |
| 5. TWAP / entrada retrasada (01:05-01:30; +5-30 min) | 48 | 1,10 (Big One a 01:05, artefacto de datos) | 0,87 | descartada |

**Lo que dicen las grillas:**

- **Ganar precio cuesta operaciones buenas.**
  - En la Big One, un límite a −1 ATR15 llena el 55-72 % de las veces. Con `lost`, el MAR baja a 0,65-0,86 ×.
  - Con `mkt`, baja a 0,47-0,76 ×: las que no llenan entran después, más caras.
  - Es la misma selección adversa que en las recargas: el precio llega al límite en los días malos.
- **Solo funcionan los límites minúsculos.** El único rincón ≥ 1,1 × es la Big One a −0,01 ATR_D (≈ 0,3-1 $/oz, más o menos el costo de entrar a 01:01 en vez de 01:00) con `lost`. Pero es **una pérdida de operaciones disfrazada**: el 36 % de las Big One no llena.
- **`orig` frente a `new`.** Medir los TP y el candado desde el precio original ayuda un poco cuando la orden llena (el TP queda más lejos y el candado más cerca). Empeora mucho con `mkt`, porque el candado queda más lejos del precio real; hay peores días de −16 %. No cambia ningún veredicto.

## 3. Finalistas (máx. 5): `sel`, nulos y `val` (vista una sola vez)

**Cómo leer las columnas:**
- **ΣR pata:** suma de peso × R de esa pata, candidato / base. Es más estable que el MAR.
- **Nulo «quitar»:** percentil del MAR del candidato entre 200 bases a las que se les quitó al azar la misma fracción de operaciones (permutando la fracción llenada).
- **Nulo «tiempo»:** cambio de ΣR de la pata cuando se aplica la misma regla a `random_entries(mode='time')`, mediana de 10 semillas.

| Finalista | Pata | Llenado | `sel` MAR (×base) | `sel` ΣR pata | p boot | Peor día / mes `sel` (base −9,2 / −15,7 %) | 2023 / 2024 | Vecinos | Nulo quitar (pct) | Nulo tiempo: ΔR real / azar | `val` MAR (×base 3,60) | `val` ΣR pata | Peor día / mes `val` (base −10,1 / −13,7 %) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Límite −0,01 ATR_D, 15 min, `lost`, `orig` | Big One | 64 % | 4,04 (1,19) | 10,0 / 7,5 | 0,105 | −9,3 / −11,2 | 1,13 / 1,64 | 1,09 · 1,12 · 1,15 | 92 % | +2,6 / +1,8 | **1,73 (0,48)** | **0,1 / 5,9** | −9,6 / −11,3 |
| Stop +0,05 ATR_D, 30 min, `lost` | Momentum | 67 % | 5,63 (1,66) | **11,1 / 12,5** | 0,46 | **−9,7** / −14,8 | **2,57 / 0,73** | 0,78 · 1,33 · 1,46 · 1,01 | 98,5 % | −1,5 / +2,8 | 3,72 (1,03) | 3,4 / 3,4 | −8,4 / −13,7 |
| Stop +1 ATR15, 30 min, `lost` | Momentum | 50 % | 5,64 (1,66) | 8,9 / 12,5 | 0,50 | **−10,4** / −9,9 | 2,57 / 0,71 | 0,85 · 0,79 · 1,28 · 0,87 | 99,5 % | −3,7 / +2,1 | 3,03 (0,84) | 0,6 / 3,4 | −7,8 / −13,5 |
| Límite −0,01 ATR_D, 15 min, `mkt` | Momentum | 100 % | 3,63 (1,07) | 13,0 / 12,5 | 0,24 | −8,8 / −15,5 | 1,07 / 1,03 | 1,05 · 1,04 · 1,01 | n/a (no quita) | +0,4 / −0,0 | 2,58 (0,72) | 1,9 / 3,4 | −9,1 / **−18,9** |
| TWAP: Big One a 01:05 en vez de 01:01, `orig` | Big One | 100 % | 3,72 (1,10) | 9,7 / 7,5 | **0,009** | −9,4 / −14,9 | 0,97 / 1,44 | 0,89 · 1,04 · 1,09 | n/a | +2,3 / +0,4 | 3,19 (0,89) | 4,8 / 5,9 | −10,1 / −12,1 |

**Lote mayor** (CAGR de la base con el riesgo que da la misma caída que el candidato), por finalista:

| Finalista | CAGR lote mayor | CAGR candidato |
|---|---|---|
| Límite Big One | 109 % | 136 % |
| Stop Momentum (+0,05 ATR_D) | 52 % | 109 % |
| Stop Momentum (+1 ATR15) | 41 % | 93 % |
| Límite Momentum | 105 % | 120 % |
| TWAP Big One | 122 % | 134 % |

### Lectura de cada finalista

- **Límite Big One.**
  - En `sel` gana R de verdad (+2,6 R) y supera al azar de quitar operaciones (pct 92 %). Pero no llega a 1,25 ×, y en `val` se hunde: ΣR 0,1 frente a 5,9, MAR 0,48 ×.
  - Pierde tanto en el tramo Dukascopy de 2025 (1,1 frente a 3,8 R) como en el del broker (−1,0 frente a 2,1 R).
  - **Descartada.**
- **Stop de entrada en el Momentum** (las dos variantes).
  - El MAR sube porque la caída baja de 34 % a 17-19 % al quitar la mitad de las operaciones. Pero **gana menos R que la base** y el peor día empeora (falla la regla).
  - Todo el efecto viene de 2023 (×2,57); en 2024 da ×0,7.
  - Los vecinos van de 0,78 a 1,46 (inestable).
  - En el nulo de momentos al azar, la misma regla **suma** R (+2-3 R), mientras que en las señales reales **resta**. Lo que hace la regla es filtrar operaciones, no anticipar la dirección.
  - El percentil 98-99 % contra quitar al azar es el único dato a favor, y con 1 082 variantes no basta.
  - En `val`: ×1,03 (mismo ΣR) y ×0,84.
  - **Descartada.**
- **Límite Momentum con `mkt`.**
  - Mejora real pero mínima en `sel` (+0,4 R; al azar 0,0). En `val` empeora (1,9 frente a 3,4 R, peor mes −18,9 %).
  - **Descartada.**
- **TWAP de la Big One a 01:05.**
  - p = 0,009 y +2,3 R en `sel`, muy por encima del azar. Pero es un **artefacto de datos**, comprobado: el open de la vela M5 de 01:05 queda respecto del precio de entrada de 01:01 en:

| Datos | Período | Diferencia media |
|---|---|---|
| Dukascopy | 2022 | −0,33 $/oz |
| Dukascopy | 2023 | −0,01 $/oz |
| Dukascopy | 2024 | −0,21 $/oz |
| Dukascopy | 2025 | −0,17 $/oz |
| Broker M5 | 2025-06 → 12 | **+0,64 $/oz** |

  - Los ticks reales de 2026 (memoria `broker-sesion-trading-0101`) dicen lo mismo que el broker: el precio **sube** de 01:01 a 01:05.
  - En `val` (que incluye el tramo del broker) da 0,89 ×.
  - **Descartada.** Además, invalida en general cualquier conclusión de `sel` sobre el precio de entrada de la Big One en sus primeros minutos.

## 4. Cuantil predicho del mínimo (Big One)

- La profundidad del mínimo de la primera hora (en ATR15) **sí** es algo predecible con información previa a 01:01:
  - correlación de 0,31 a 0,38;
  - pérdida de cuantil (pinball) entre 2 % y 9 % menor que la del cuantil incondicional, en walk-forward mensual 2023-2024.
- Aun así, poner el límite en el cuantil predicho no mejora la cartera: el mejor da 1,05 × (q = 0,5, `lost`, 46 % de llenado). Saber cuánto va a bajar no dice si la operación va a ser buena.

## 5. Nulos y cuenta honesta

- **Registro:** 1 106 filas `line = 'D'` en `results/opt_registry.jsonl`.
  - 1 082 variantes de grilla: 480 límite, 240 stop, 288 escalonado, 48 TWAP, 2 Momentum adelantado y 24 cuantil.
  - 25 filas de finalistas: bootstrap, 2023, 2024, robustez y `val`.
  - 1 fila duplicada por un fallo de `mom_pre`.
  - Pueden faltar 1-2 filas del escalonado por escrituras simultáneas de otras líneas: hay 1 línea corrupta en el jsonl compartido.
- **`val`:** mirado una sola vez, con 5 finalistas.
- **Ninguna variante cumple a la vez** MAR ≥ 1,25 × en `sel`, peor día y peor mes no peores, y p ≤ 0,10. Con una corrección por pruebas múltiples, tampoco quedaría nada.

## 6. Recomendación

- **No cambiar la entrada del bot e2.** Mantener orden a mercado en 01:01 (Big One), 15:00 (Momentum) y T+60 (NFP).
- **No reproponer** límites, stops de confirmación, escalonado ni TWAP con los datos actuales. Es la misma familia que las recargas y la reentrada, ya descartadas: bajar a buscar precio selecciona los días malos.
- **Para la Big One:** si algún día se quiere revisar su entrada, hacerlo solo con ticks o M1 del broker (≥ 12 meses de demo). La M5 de Dukascopy no sirve para los primeros minutos tras la reapertura.
- **Para el coordinador (2026):** no hay candidatos que pasen, así que no hay función que reproducir. Si quiere ver el «stop de confirmación del Momentum» como control:
  - plan `dict(kind="stop", u="ad", levels=[(0.05, 1.0)], N=30, fb="lost", anchor="new")`;
  - en la pata `momentum`, con `opt_D_limite.run_plan` / `opt_D_common.sim`;
  - parámetros fijados con datos ≤ 2024.
