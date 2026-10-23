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
