# Búsqueda "agresivo pero estable" — plan y banco de ideas (2026-10-21)

Herramienta: `bot_backtesting/fullsim/race.py` con el bot de esta rama (motor real, swap,
comisión, spread). Cuentas de 1 000 $ y de 5 000 $ (con 5 000 $ el aguante deja más lote, el comportamiento cambia). Métrica: % que duplica antes de 120 días, % que se quema
(≤ 300 $ o stop-out), equity final media y mediana.

## Punto de partida (143 arranques, 2021-03 → 2026-08)

| Bot | Duplica | Se quema | Final medio |
|---|---|---|---|
| Viejo (main) | 21 % | 65 % | 756 $ |
| Viejo + candado externo (5 versiones) | 10–14 % | 34–55 % | 660–743 $ |
| Nuevo, aguante 350 $ | 1 % | 0 % | 910 $ |

## Método (contra el sobreajuste)

1. Elegir SOLO con arranques 2021-03 → 2023-12 (entrenamiento).
2. Validar lo elegido en 2024-01 → 2026-08 (nunca usado para elegir) y luego en la serie completa.
3. Etapas:
   - E1 lote × aguante: `base_lots` {0,12; 0,24; 0,36} × `survival_move_usd` {350, 150, 80}
     (candado y aflojado escalados en proporción).
   - E2 una idea por vez sobre la mejor base de E1, por operación (bancos abajo).
   - E3 combinar lo mejor de cada banco y validar.

## Banco Op2 (Hedge Lock)

Con parámetros existentes:
- `hedge_dist` 350 / 800 / 1500; `hedge_atr_mult` 1,5 / 2 / 3.
- `lock_trigger_usd` (candado de cesta) más temprano o más tarde.

Requieren código (solo en el simulador hasta aprobar diseño):
- Cobertura parcial (50–75 % del neto) en vez de total.
- Cobertura en dos escalones (½ a X, ½ a 2X).
- Cobertura solo si la tendencia diaria va en contra de la Op1.

## Banco Op3 (Recovery)

Con parámetros existentes:
- `recovery_min_spacing_atr` 0,5 / 1 / 2.
- `op3_start_atr`, `op3_base_dist_atr` (trailing de la Op3).
- `use_recovery_h4_gate` sí / no.

Requieren código:
- Op3 solo a favor de la tendencia diaria (tsmom).
- Lote de la Op3 fijo en vez de creciente.

## Banco Op4 (Rescate)

Con parámetros existentes:
- `rescue_mode` trend vs copia; `rescue_trend_k_atr` 1 / 2 / 3.
- `max_rescue_legs` 1 / 3 / 6.
- `rescue_trend_trail_start_atr` / `rescue_trend_trail_dist_atr`.

Requieren código:
- Op4 con lote mayor solo si coincide con la tendencia diaria (idea Big One).
- Op4 que cierra la peor pata con su ganancia (pareja inmediata).

## Criterio de elección

Máximo % de duplicar con % de quema ≤ 10 % y final medio > 1 000 $.

## Resultados E1 (2026-10-22) — entrenamiento 2021-03 → 2023-12, 74 arranques, 120 días

Final medio / mediana (% sobre el saldo inicial); ninguna variante duplica.

| Cuenta | Lote base | Aguante 350 | Aguante 150 | Aguante 80 |
|---|---|---|---|---|
| 1k | 0,12 | −10,7 % | −10,2 % | (= 150) |
| 1k | 0,24 | −11,6 % | −16,3 % | −18,4 % |
| 1k | 0,36 | −11,6 % | −19,9 % | −26,5 % (1 % quema) |
| 5k | 0,12 | −7,6 % | −8,9 % | −8,9 % |
| 5k | 0,24 | −8,4 % | −16,3 % | −19,9 % |
| 5k | 0,36 | −8,4 % | −22,1 % | −28,6 % (4 % quema) |

- Más lote = más pérdida, casi en proporción: escalar una ventaja negativa.
- El percentil 90 es negativo en todas: en 9 de cada 10 ventanas de 120 días el bot pierde.
- Por qué: en TODOS los arranques el bot entra en un ciclo de 4 patas (Op1 + Op2 congeladas
  + recovery + Op4) a los pocos días y no sale en los 120 días. Antes de congelarse gana
  rápido (traza 5k 2021-03: 16 ciclos verdes, +8 % en 4 días). Congelado, no abre Op1 y la
  pareja Op1+Op2 paga swap (≈ −41 $/lote/noche): el swap explica casi toda la pérdida medida.
- Prueba de salida del congelado (`--unfreeze 72`, cerrar la cesta congelada tras 72 h): en el
  arranque de la traza, 95 ciclos, 18 salidas que realizan −2 973 $ contra +2 055 $ de ciclos
  verdes. El congelado no es solo swap: cada ciclo que se congela pierde ~6 veces lo que gana
  uno verde y pasa ~1 de cada 5 veces. Para ganar hay que cambiar esa proporción.

Siguiente: E2 con `--unfreeze 72` como instrumento de medida (muchos ciclos por arranque):
tamaño de la ganancia (trailing de cesta), distancia de la cobertura (Op2), separación de la
Op3 y distancia de la Op4, en cuenta de 5k.

## E2 base y análisis de patrones (2026-10-22)

**E2 base** (5k, `--unfreeze 72`, 74 arranques): final medio 4 321 $ (p10 3 696, p90 4 876); 894
ciclos únicos, 19,6 % terminan en pérdida (−130 $ medio) y el resto gana +25,4 $ medio.
Esperanza por ciclo ≈ 0,804 × 25,4 − 0,196 × 130 ≈ **−5 $**. Para empatar: pérdida media ≤ 104 $
o frecuencia ≤ 16 %.

**¿Se puede anticipar el ciclo que se congela al abrirlo?** 20 rasgos de mercado al abrir el
ciclo (tendencia D1/H4, eficiencia de tendencia, variance ratio H1, volatilidad relativa,
compresión de Bollinger, posición en el rango de 20 días, RSI, retornos 1 h/4 h/24 h, hora,
día), alineados al lado del ciclo, por quintiles con cortes de train (antes de 2022-09) y
verificados en test. **Ninguno**: P(pérdida) queda en 0,15–0,27 en todos los quintiles y el
orden no se repite en test (salvo el lunes, algo peor y débil). Filtrar Op1 por régimen no
arregla el bot: la pérdida nace en la gestión después del movimiento en contra.

**Capacidad de predicción por escala** (doble barrera: ¿el precio toca antes +k o −k ATR
diario?): k 0,25 (lo que necesita Op1), 0,5 (Op2: ¿vuelve o sigue?), 1,0 (Op4 o salir del
candado). Con 2021-2023 aparecían patrones (distancia a la EMA50 H4); con **historia nueva
2008-2020** (Dukascopy, 77 000 horas, nunca usada) desaparecen: todos los quintiles de todos
los rasgos quedan en 0,46–0,56 y no repiten entre 2008-14 y 2014-20. Con estos indicadores **la
dirección del oro no se puede predecir** a ninguna de las escalas que usan las Op.

**Lo único estable es el calendario:** la hora de reapertura (01:00 servidor) sube en todas las
eras (t ≈ 14) y las horas 02-08 tienen deriva alcista pequeña; 16:00 baja (t ≈ −3); 23:00-00:00
bajan (posible efecto del spread ensanchado en el bid, no operable). La compra 01:00 → 10:00
gana bruto en 13 de 13 años 2008-2020 (0,14–1,82 $/oz) y neto de 0,32 $/oz en ~10 de 13; el
filtro de tendencia diaria (Big One) **no añade** en 2008-2020.

**Límite matemático:** sin ventaja, la probabilidad de llegar a 2× antes de caer a 0,3× es
como mucho (1 − 0,3)/(2 − 0,3) ≈ 41 %, y los costes (spread, comisión, swap) la bajan. Ninguna
regla de Op2/Op3/Op4 crea ventaja: solo cambia la forma (muchas ganancias chicas y pocas
pérdidas grandes, o al revés). "Agresivo y estable" exige (a) una fuente de ventaja real y
(b) no regalar costes.

Fuentes de ventaja o ahorro a explorar en adelante:
- Sesgo horario: Op1 solo compras en la ventana asiática; sin ventas antes de la reapertura.
- Swap: la pareja congelada paga ~−41 $/lote/noche (largo −77, corto +37); reducir noches
  congeladas o congelar con el corto mayor.
- Comisiones de los cortes del Healer de 0,01 en 0,01.
- Volatilidad (sí es predecible) para dimensionar, no para elegir dirección.

## Banco rápido, filtro de Op1 y mezclas (2026-10-23)

Método rápido: 9 tramos de 120 días sin solapar (2021-03 → 2024-01), cuenta de 5k,
`--unfreeze 72` (solo medición). Validado contra el método solapado (P(pérdida) 0,195 vs
0,196; −14,0 % vs −13,6 % por 120 días).

| Variante | Ciclos | P(pérdida) | % / 120 d | Op1 $ | Op2 $ | Op3 $ | Op4 $ |
|---|---|---|---|---|---|---|---|
| base | 737 | 0,195 | −14,0 | −3321 | +306 | −1610 | −1148 |
| Op1 solo compras | — | — | −12,1 | | | | |
| Op1 compra asiática (01–09) | 346 | 0,165 | −5,0 | −990 | +231 | −1720 | +648 |
| Op1 sin ventas 01–09 | 678 | 0,215 | −15,9 | −3186 | −663 | −1648 | −1155 |
| asiática + trail cesta 0,5 | 358 | 0,159 | −4,2 | −734 | +52 | −1593 | +562 |
| asiática + trail 0,5 + trail Op4 ancho | 358 | 0,156 | **−3,6** | −852 | +124 | −653 | −52 |
| asiática + trail Op4 ancho | 346 | 0,165 | −4,7 | −835 | +57 | −891 | +47 |
| asiática sin corte de pareja del Healer | 304 | 0,174 | −4,2 | −2411 | +1115 | −1029 | +1129 |
| asiática con lote doble (0,24) | 350 | 0,169 | −5,0 | −1376 | +340 | −1813 | +847 |

Del resto del banco: trail de cesta 0,5 −12,8; sin Op4 (norescue) −21,4 (se congela solo el
2,3 % de los ciclos pero cada congelado pierde −2 334 $); sin Healer −19,2; k de Op4 1 o 3 peor.

**Costos (3 años, 5k).** Base: bruto +2 931 $, spread −3 377, comisión −2 026, swap −3 300 →
neto −5 773 con 169 lotes. Mejor mezcla: bruto +2 496, spread −1 536, comisión −922, swap
−1 470 → neto −1 433 con 77 lotes. Filtrar la Op1 a la ventana asiática corta los costos a la
mitad y vuelve **positivo el bruto de la Op1** (+1 796 $).

**Dónde falla la Op1 asiática.** Patas cerradas en < 9 h: +5 443 $ de precio, swap 0. Patas que
quedan en el congelado (> 24 h): −4 781 $ de precio y −1 592 $ de swap (la compra paga −77
$/lote/noche). Por motivo: Basket Profit Trail +4 500; Freeze Exit −3 386 / −1 115 swap; Healer
Pair Cut −1 378 / −394. La ventaja horaria es real, pero se la come el ciclo que escala.

Siguiente prueba (cola 13): cerrar la Op1 sola a una hora fija (10, 14 o 23 servidor) si
todavía no tiene cobertura (`race --op1-exit`, solo simulación), y la mezcla sin corte de
pareja del Healer.

## Análisis profundo por Op, smart money, lote y M5 (2026-10-23, tarde)

**Cierre de la Op1 por hora (cola 13, `--op1-exit`).** Con la mejor mezcla (Op1 asiática +
trail 0,5 + trail Op4 ancho): cerrar la Op1 sola a las 10 h deja −3,8 % por 120 d (vs −3,6 %),
pero la pérdida media de un ciclo malo baja de −138 a −45 $, los congelados de 55 a 23 y el swap
de −1 437 a −489 $. Más estable, no más rentable. A las 14 h: −5,1 %; a las 23 h: sin efecto.

**Lote (cola 14, `--volsize 24`: lote × 24/ATR_D de ayer, acotado 0,4–2,5).**

| Variante | % / 120 d | Peor equity (de 5 000) |
|---|---|---|
| lote normal + volatilidad | −4,0 | 4 367 |
| lote ×2 + volatilidad | −3,2 | 4 262 |
| lote ×2 + volatilidad + cierre Op1 10 h | −4,0 | 4 403 |
| lote ×3 + volatilidad | −3,2 (idéntico a ×2: manda el tope de supervivencia) | 4 262 |

El M15 aguanta más lote sin quemar, pero sin ventaja el lote solo escala el resultado.

**Smart money como filtro de la Op1** (`op1_smc.py`, 19 702 señales 2021–2025, P(cobertura)
por quintil, train ≤ 2023 / test 2024–25): barridas de liquidez, FVG, BOS, premium/descuento
H4 y de 20 días, distancia al máximo/mínimo del día anterior, rango asiático y su barrida,
posición en el día, números redondos, hora. Ningún rasgo mueve P(cobertura) más de 4 puntos ni
mantiene el orden en test. **Sin capacidad de filtro.**

**Smart money como entrada con objetivo proyectado** (`smc_setups.py`, primer toque en M5, costo
0,32 $/oz): barrida + vela de desplazamiento → máximo/mínimo de swing o del día anterior, también
en killzones; descuento/premium H4 + BOS + FVG. El acierto es igual a la tasa justa que dan las
distancias (p. ej. 0,58–0,64 vs 0,62–0,68) y la esperanza es negativa en train en todos;
**la proyección a la liquidez no tiene ventaja**.

**Big One: cuánto riesgo aguanta** (`kelly_bigone.py`, 569 operaciones fuera de muestra
2023–2026, remuestreo de 12 meses por bloques mensuales; el lote ya escala con el ATR porque el
candado está a k·ATR):

| Riesgo por operación | P(×2 en 12 m) | P(caída ≥ 50 %) | Mediana ×12 m |
|---|---|---|---|
| 1 % | 1–2 % | 0 % | 1,3 |
| 2 % | 31–37 % | 1–2 % | 1,7 |
| 3 % | 52–54 % | 10–13 % | 2,1 |
| 4 % | 61–63 % | 31–34 % | 2,5 |

Cautela: muestra de años alcistas; 2026 da −0,07 R por operación y un filtro por volatilidad no
lo arregla (el R por tercil de volatilidad no tiene orden estable).

**M5 (`m5race.py`, motor M5 real, 2021-03 → 2024-01, 9 tramos de 120 d, 5 000 $).**

| Corrida | Operaciones | Acierto | Neto $ | Bruto antes de costos | Spread + comisión |
|---|---|---|---|---|---|
| ambos regímenes | 9 050 | 59 % | −1 944 | +1 040 | −2 958 |
| solo scalper (rango) | 132 | 67 % | −30 | +31 | −62 |
| solo surfer (tendencia) | 8 954 | 59 % | −1 947 | +1 014 | −2 934 |

- El surfer es el 99 % de las operaciones (~13 por día). Trail SL +8 047 $; TimeStop −8 261 $;
  SL inicial −1 731 $. Su bruto ≈ 0 no paga el costo de 0,32 $/oz.
- El scalper casi no dispara (~15 por tramo): sus compuertas rara vez coinciden. Ventas de
  reversión +52 $, compras −70 $.
- Rasgos de entrada (ADX, RSI, ATR, ancho de banda, distancia a la EMA, rango M15, racha, día,
  hora y los mismos rasgos SMC): ningún quintil supera el costo en train y test a la vez. Las
  horas 16–18 y 20 dan bruto +0,10–0,18 $/oz, por debajo del costo.
- Separar los regímenes en dos bots no ayuda: ninguno tiene ventaja por sí solo.

**Lectura de conjunto.** Op1, Op2, Op3, Op4, el M5 en sus dos regímenes y la proyección por
smart money no tienen ventaja predictiva sobre la dirección del oro; la gestión solo cambia la
forma de la distribución y los costos deciden el signo. La única ventaja que sobrevive a train,
test y validación móvil es **de calendario**: la compra en la reapertura asiática (Big One).
El camino agresivo-estable con evidencia es un módulo Big One con candado a k·ATR y 2–3 % de
riesgo por operación, validado antes en demo (ejecución real a las 01:00), con el M15 y el M5
apagados o en lote mínimo mientras no muestren ventaja.

## Big One al revés, meta mensual y estudio econométrico (2026-10-23, noche)

**¿Se puede invertir la Big One en mercado bajista?** No. Retorno bruto desde la apertura de
la 01:00 (servidor), en $/oz, según la tendencia diaria del día anterior
(s = signo(C−C21) + signo(C−C63)):

| Tendencia | Días | 01:00→01:15 | 01:00→03:00 | 01:00→10:00 |
|---|---|---|---|---|
| bajista (−2) | 290 | +0,21 | +0,48 | +0,93 |
| neutra (0) | 419 | +0,52 | +0,90 | +0,82 |
| alcista (+2) | 717 | +0,99 | +1,75 | +2,93 |

La reapertura tiene sesgo comprador en los tres estados. Una venta ahí paga el sesgo más el
costo. En 2026 los días bajistas dan −0,68 $/oz en los primeros 15 min: el filtro alcista se queda.

**Meta de +30 % a 2x mensual con la Big One** (`monthly_bigone`: meses reales 2023–2026
remuestreados; ~15 operaciones/mes, +0,18 R por operación, 36 % de meses negativos):

| Riesgo/op. | Mes típico | P(mes ≥ +30 %) | P(mes ≥ 2x) | P(caída ≥ 50 % en 12 m) |
|---|---|---|---|---|
| 2 % | +4 % | 3 % | 0 % | 1 % |
| 3 % | +6 % | 10 % | 0 % | 14 % |
| 5 % | +10 % | 31 % | 3 % | 56 % |
| 8 % | +16 % | 36 % | 5 % | 95 % |
| 12 % | +22 % | 38 % | 23 % | 100 % |

Con la ventaja medida, +30 % mensual frecuente exige un riesgo que casi seguro parte la cuenta a la mitad en un año.

**Estudio econométrico** (`econ_build.py`, `econ_model.py`; datos públicos FRED y CFTC en
`data/econ`, no versionados). Tabla diaria 2021-01 → 2026-10 (1 495 días). MCO con errores
Newey-West; train 2021–23, test 2024–26.

1. **Qué mueve al oro el mismo día** (por 1 desviación típica):
   - Dólar (DXY): −0,33 % / −0,54 % (t −9 / −7,5).
   - Tasa real a 10 años: −0,32 % en 2021–23, −0,09 % en 2024–26 (pierde fuerza: el ciclo de compras de bancos centrales desacopló oro y tasas).
   - VIX y petróleo: secundarios e inestables.
   - R²: 0,39 en 2021–23; 0,20–0,27 desde 2024.
   - Oro-plata: correlación 0,78 el mismo día.
2. **Qué predice** (solo con lo conocido antes de la 01:00): 35 variables × 5 objetivos (día
   siguiente, reapertura 15 min, 01–10 h, resto del día, semana siguiente) = 175 pruebas.
   - 14 tienen |t| > 2 en train; **ninguna** repite con el mismo signo en test.
   - Un modelo ridge con todo da R² fuera de muestra negativo en los 5 objetivos y un acierto de signo de 42–51 %.
   - **La dirección del oro no es predecible con macro, posicionamiento COT, cruzados ni técnico diario.**
3. **Volatilidad sí es predecible:**
   - HAR (volatilidad realizada de 1, 5 y 22 días): R² fuera de muestra 0,54, frente a 0,28 del promedio de 22 días (≈ ATR).
   - Agregar VIX y calendario no mejora (0,48).
   - Los días de FOMC/IPC suben la volatilidad prevista.
4. **R de la Big One por régimen** (569 operaciones 2023–2026; tercil de volatilidad prevista,
   VIX, cambio de tasa real y de dólar a 20 d, COT, momentum, distancia a la MA50, dólar del
   día anterior, eventos, día de la semana):
   - Ninguna variable ordena el R de forma monótona y estable.
   - Las diferencias caben dentro de ±1 error estándar (≈ 0,1 R por tercil).

**Lectura.**
- El modelo econométrico confirma lo de las simulaciones: lo que mueve al oro (dólar, tasas reales) se conoce recién cuando ya pasó.
- Un arnés en tiempo real que vigile esas variables no puede anticipar la dirección.
- Sí puede:
  - prever la volatilidad del día (HAR) y del calendario, para fijar el lote y el candado en volatilidad prevista en vez del ATR pasado;
  - bloquear o reducir el riesgo en días de evento.
- Es una mejora de estabilidad, no de dirección.
