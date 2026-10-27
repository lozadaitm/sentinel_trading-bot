# Línea A — mejores salidas para el e2 (27-oct-2026)

> Solo simulación, sin MT5 y sin tocar `bot/`. 2026 no se miró.
> Scripts: `bot_backtesting/fullsim/opt_A_common.py` (caché de caminos + gestor genérico), `opt_A_grid.py`,
> `opt_A_trail_fine.py`, `opt_A_trail_bc.py`, `opt_A_quantile.py`, `opt_A_final.py`.
> Resultados crudos: `bot_backtesting/fullsim/results/optA_*.csv|pkl` (fuera de git).

## Respuesta corta

**Ninguna salida nueva pasa la regla de aceptación.** La mejor, un trailing en ganancia en los tercios 2 y 3,
da ×1,23 en `sel` y ×1,22 en `val`. Se queda justo debajo de ×1,25, con `p` = 0,12 y un vecindario inestable.
Queda **en vigilancia**: no se recomienda cambiar el bot.

**Hallazgo importante, de método:** con el modo «intra-vela» de la plantilla, un trailing corto parecía dar
×1,5 a ×2,3. Era un **artefacto de resolución**: el mismo trailing mejoraba *más* cuanto más gruesas eran las
velas (con M15, ×2,5–3,1). En el modo exacto (el stop solo se mueve al cerrar cada vela M5), casi toda esa
ventaja desaparece. Cualquier línea que pruebe trailings ajustados con velas M5 debe usar el modo exacto.

## Cómo se probó

- Las mismas entradas, lados y pesos que el e2. Solo cambia la gestión de cada tercio.
- **Camino intra-vela M5:** Dukascopy con desfase al broker hasta 2025-05-29 y M5 del broker después. Se
  calcula una vez y se guarda en caché (`cache_paths`). El gestor genérico `manage` reproduce `leg_ladder` al
  céntimo (diferencia máxima 4e-15) y la base da exactamente MAR 3,39 en `sel` y 3,60 en `val`.
- **Restricción dura:** los stops en ganancia tienen un piso = comisión + deslizamiento + swap + 0,10 $/oz.
  Su nivel garantiza P&L neto > 0. La única excepción es un hueco de precio (se llena al open). Con el
  finalista pasó en 14 de 1 574 salidas por trailing, casi todas en el hueco del fin de semana del NFP.
- **Modo exacto** (`CFG["barclose"]=True`): el stop se recalcula solo al cierre de cada vela M5, con el máximo
  de las velas ya cerradas. Dentro de la vela queda fijo, así que con M5 la simulación es exacta y el bot lo
  puede implementar tal cual (mover el SL en cada cierre M5).
- Todo con `compare(..., 'sel')`. Las grillas sin bootstrap y los finalistas con bootstrap. Solo 3 finalistas
  fueron a `val`, una sola vez, y quedó registrado.
- **Candado con lote a igual riesgo:** en las variantes `lockK_size`, la columna `atrd` del dimensionado se
  multiplicó por `lock_k`. Así el lote = riesgo / (lock_k × ATR_D), es decir, la distancia real del candado.
  Las variantes `_nosize` dejan el lote vigente (más riesgo por candado si K > 1) solo como referencia.

## Lluvia de ideas y orden (ganancia esperada ÷ costo)

| # | Idea | Costo | Probada |
|---|---|---|---|
| 1 | Trailing en ganancia (ATR15 / ATR_D / Chandelier / que se aprieta con el tiempo) en t3, t2+t3 o los tres | bajo | sí (F1, G1–G3, BC*) |
| 2 | Trailing + objetivo tope | bajo | sí (F2) |
| 3 | Fracciones y composición de la escalera | bajo | sí (F8) |
| 4 | TP distintos por pata | bajo | sí (F7) |
| 5 | Posición del candado a igual riesgo | bajo | sí (F6) |
| 6 | Agotamiento (vela M5 grande en contra tras +x) y estancamiento (n velas sin nuevo máximo) | medio | sí (F4) |
| 7 | Parabólico (SAR) en ganancia | medio | sí (F3) |
| 8 | Extender la hora de salida si va en ganancia (con o sin tendencia), por pata | medio | sí (F5) |
| 9 | TP proyectado por cuantiles (LightGBM y QuantReg, walk-forward) | alto | sí (Q1) |
| 10 | Deshacer el candado (REQUIERE CERRAR EN PÉRDIDA) | bajo | sí, aparte (F6X) |
| — | Salida parcial al tocar la vela de noticia; trailing por volumen de ticks; TP por niveles de Asia | alto | no: no hay ticks fuera de 2026, o lo cubren 1/6 |

## Resultados por idea (`sel`; base MAR 3,39, peor día −9,2 %, peor mes −15,7 %)

| Idea | Mejor variante (sel) | MAR | × base | Peor día | 2023 / 2024 | Veredicto |
|---|---|---|---|---|---|---|
| **1. Trailing (modo exacto)** | t2+t3, se arma a +2,5 ATR15, distancia 0,75 ATR15 | 4,17 | **1,23** | −9,8 % | ×1,24 / ×1,23 | **vigilancia** (ver finalistas) |
| 1. Trailing (modo intra-vela) | los tres tercios, ATR_D a0,2 d0,05 | 7,76 | 2,29 | −10,5 % | — | **artefacto**: con M15 da ×3,1 y en modo exacto ×1,11 |
| 2. Trailing + tope (exacto) | t3 a3 d1, tope 6 | 3,47 | 1,02 | −9,5 % | ×1,02 / ×1,01 | descartada |
| 3. Fracciones | todo a la hora | 3,91 | 1,15 | **−15,6 %** | ×1,57 / ×0,51 | descartada (peor día y mes mucho peores, depende de 2023) |
| 4. TP por pata | NFP con TP 1 y 3 | 3,80 | 1,12 | −9,6 % | ×1,15 / ×1,18 | descartada (< 1,25; solo 26 operaciones NFP en sel) |
| 5. Candado a igual riesgo | 0,5 / 0,75 / 1,25 / 1,5 ATR_D | 2,86–3,10 | 0,85–0,91 | — | — | **descartada**: el 1,0 vigente es el mejor |
| 6. Agotamiento | t3, +1 ATR15, vela > 2× media | 4,32 | 1,28 | −9,8 % | ×1,61 / **×0,79** | descartada (no aguanta 2024 y empeora el día) |
| 6. Estancamiento | t3, +1, 24 velas | 3,71 | 1,10 | −11,6 % | ×1,30 / ×0,67 | descartada |
| 7. SAR (exacto) | t3 a1 | 3,24 | 0,96 | −8,3 % | — | descartada |
| 8. Extender la hora | +1 h, trailing 3 ATR15, con tendencia | 3,56 | 1,05 | −9,4 % | ×1,17 / ×1,14 | descartada |
| 9. TP por cuantiles | LightGBM q0,5 / q0,8 | 3,94 | 1,16 | −11,2 % | ×1,18 / ×0,89 | **descartada**: el modelo no predice (ver abajo) |
| 10. Deshacer el candado | candado 1,0, deshacer a −0,25 ATR_D | 3,29 | 0,97 | −13,2 % | — | descartada, y **REQUIERE CERRAR EN PÉRDIDA** |

**Notas por idea:**

- **Cuantiles (9):** fuera de muestra, la pérdida pinball del modelo es igual o peor que la de un cuantil
  constante en los 7 cuantiles. Con LightGBM fue 1,293 frente a 1,289 en q0,5, con correlación 0,10–0,14. Con
  la información disponible al entrar no se puede prever cuánto correrá la operación. Lo poco que mejora es
  solo por poner TPs más lejos, y empeora el peor día y el peor mes.
- **Candado (5):** más estrecho a igual riesgo implica un lote mayor y más candados; la caída sube a 50–55 %.
  Más ancho implica un lote menor, que gana menos de lo que reduce la caída. Las variantes `_nosize`, con más
  riesgo, no cuentan.
- **Trailing en el tercio de hora solo (t1):** es siempre peor (×0,66–0,86 en modo exacto). Cortar al
  ganador de la hora quita lo que más paga.
- **Robustez del mejor trailing en modo exacto:**
  - con +0,10 $/oz de deslizamiento extra en el stop, la variante ATR_D a0,2 d0,1 baja de ×1,22 a ×1,16;
  - con +0,25 $/oz baja a ×1,02;
  - la variante de los tres tercios, a3 d1, ya cae por debajo de la base con +0,10.

## Finalistas (modo exacto) — `sel` y `val`

| Finalista | Periodo | MAR (base) | × base | CAGR | Caída | Peor día (base) | Peor mes (base) | p | CAGR con lote mayor a igual caída |
|---|---|---|---|---|---|---|---|---|---|
| **t2+t3 a2,5 d0,75 ATR15** | sel | 4,17 (3,39) | **1,23** | 141 % | 33,8 % | −9,8 % (−9,2 %) | −15,2 % (−15,7 %) | 0,12 | 109 % |
|  | val | 4,39 (3,60) | **1,22** | 141 % | 32,1 % | −9,9 % (−10,1 %) | −14,3 % (−13,7 %) | 0,19 | 107 % |
| t2+t3 ATR_D a0,2 d0,05 | sel | 4,30 (3,39) | 1,27 | 136 % | 31,6 % | −10,6 % | −11,8 % | 0,16 | 99 % |
|  | val | 2,78 (3,60) | **0,77** | 102 % | 36,6 % | −9,2 % | −13,4 % | 0,76 | 156 % |
| t2+t3 ATR_D a0,2 d0,1 | sel | 4,15 (3,39) | 1,23 | 140 % | 33,7 % | −10,3 % | −13,0 % | 0,18 | 109 % |
|  | val | 3,26 (3,60) | **0,91** | 110 % | 33,8 % | −8,9 % | −13,1 % | 0,65 | 121 % |

### Vecindario del mejor (t2+t3, modo exacto, × base en `sel`)

| arma a \ distancia (ATR15) | 0,5 | 0,75 | 1,0 | 1,25 | 1,5 |
|---|---|---|---|---|---|
| 2,0 | 0,95 | 0,96 | 1,02 | 0,93 | 0,95 |
| **2,5** | 1,11 | **1,23** | 1,19 | 1,13 | 1,14 |
| 3,0 | 1,07 | 1,10 | 1,07 | 1,05 | 1,05 |

Los vecinos a ±1 paso dan entre 0,96 y 1,19, y la regla pide ≥ 1,15. **No es estable**: es un pico.

### Nulos del mejor finalista

- **Lote mayor:** a la misma caída que el candidato (33,8 %), la base con 7,7 % de riesgo hace 109 % de CAGR,
  frente a 141 % del candidato. La mejora no es solo más exposición.
- **Momentos al azar** (5 semillas por modo). Mejora del R medio por operación (en ATR_D):

| | `sel` | `val` |
|---|---|---|
| e2 (señal real) | +0,0044 | +0,0023 |
| mismo gestor, mismos días a la misma hora, al azar (`mode='day'`) | +0,0028 | +0,0006 |
| mismo gestor, hora y lado al azar (`mode='time'`) | −0,0012 | −0,0011 |

  En `sel`, cerca de dos tercios de la mejora aparecen también con días al azar a la misma hora. Es una
  propiedad de la gestión en esas horas (deriva del oro en la sesión), no de la señal. En entradas totalmente
  al azar no ayuda.
- **Por pata:** la mejora es pequeña en Big One (+0,003 R) y Momentum (+0,005 R). En NFP es mayor (+0,03 R),
  pero con solo 26 operaciones.

### Por qué no pasa

1. ×1,23 en `sel` y ×1,22 en `val`: la regla pide ≥ ×1,25 en ambos.
2. `p` = 0,12 en `sel`: la regla pide ≤ 0,10.
3. Empeora el peor día en `sel` (−9,8 % frente a −9,2 %) y el peor mes en `val` (−14,3 % frente a −13,7 %).
4. Vecindario inestable (0,96–1,19).
5. Es sensible al deslizamiento real del stop (+0,25 $/oz se lo come entero), y la línea B midió que el ruido
   del MAR es grande (quitar 30 % de operaciones al azar da ×1,42 en el p95).

## Cuenta honesta de variantes

**544 filas de la línea A** en el registro:
- 538 en `results/opt_registry.csv` (formato viejo);
- 6 en `results/opt_registry.jsonl`: 3 finalistas × `sel` y `val`.

Son 541 variantes distintas:

| Grupo | Variantes |
|---|---|
| F1–F8 en modo intra-vela | 192 |
| G1–G4 en modo intra-vela | 117 |
| Modo exacto (BCF1–BCF3, BCG1–BCG4, BCM15) | 207 |
| TP por cuantiles (Q1) | 18 |
| Deshacer el candado (F6X, que cierra en pérdida) | 4 |
| Finalistas | 3 |

## Recomendación

- **No cambiar la gestión del e2.** La escalera vigente (hora / TP 2 / TP 3 ATR15, candado a 1 ATR_D) queda
  como está. El candado a 1,0 ATR_D es el mejor a igual riesgo.
- **Vigilancia** (sin operarlo): el trailing en ganancia de los tercios 2 y 3, armado a +2,5 ATR15 con
  distancia 0,75 ATR15 y movido solo al cierre de cada vela M5. Si el coordinador quiere evaluarlo en 2026,
  el gestor exacto es el que se indica abajo. Con M1 y ticks de 2026 además se puede medir el deslizamiento
  real de un SL así.
- **Para todas las líneas:** cualquier trailing ajustado simulado con velas M5 debe usar el modo exacto.
  El modo intra-vela de `leg_ladder`, con la mejora del pico dentro de la misma vela, infla los resultados.

**Reproducción del finalista en vigilancia:**

```python
from bot_backtesting.fullsim import opt_A_common as AC
AC.CFG["barclose"] = True
rules = ({"k": "time"},
         {"k": "trail", "act": 2.5, "dist": 0.75, "u": "a15"},
         {"k": "trail", "act": 2.5, "dist": 0.75, "u": "a15"})
T = AC.run_cached(AC.cache_paths(entries(), "e2"), rules)
# cache_paths descarta 2026 a propósito: para 2026 hay que crear la caché sin _end_ok (solo el coordinador).
```
