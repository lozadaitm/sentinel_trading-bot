# Recargas cerca del mínimo (entradas adicionales) — 27-oct-2026

> **Veredicto: NO.** Ninguna regla de recarga supera a «usar un lote inicial más grande».
> En la Big One empeoran casi todas fuera de muestra.
> En el Momentum, dos reglas suben el beneficio, pero a costa de casi duplicar el peor día. Su «inteligencia» no le gana a recargar al azar.
> **Recomendación:** no implementarlo en el bot.

Scripts:
- `bot_backtesting/fullsim/recargas_minimo.py`: medición, 152 variantes por pata, nulos y BH.
- `bot_backtesting/fullsim/recargas_comparar.py`: comparación contra un lote mayor.

Solo simulación; no se tocó el bot.

## 1. La idea que se probó

Después de abrir la Big One o el Momentum, el bot vigila el precio. Cuando el precio va en contra y «parece que va a girar», abre **otra posición en la misma dirección**:
- en una compra, cerca del mínimo;
- en una venta, cerca del máximo.

No reemplaza la entrada normal: es **adicional**.

La recarga:
- sale con la pata, a la misma hora;
- en una variante, además, sale con un objetivo de +2 × ATR15 medido desde su propio precio;
- queda dentro del candado: si el precio llega a −1 × ATR_D desde la entrada original, el candado congela también la recarga.

## 2. Cómo se midió

| Tema | Detalle |
|---|---|
| Operaciones | Las mismas reglas del diseño e2: Big One 01:00 → 10:00, peso 1 / 0,5 (×0,5 en días de noticia); Momentum 15:00 → 21:00, umbral 0,232 % y s = ±2. Base de 3 tercios (hora / TP 2 / TP 3) con candado a 1 ATR_D. |
| Precios | Entrada, ATR y señales con las velas M15 del broker (2022-11 → 2026-10). Dentro de cada operación, el camino se sigue en velas **M5**: Dukascopy hasta 2025, ajustada al nivel del broker y recortada al rango de su M15; broker en 2026. |
| Velas de 5 min | Si en la misma vela se tocan el candado y un objetivo, gana el candado. Una recarga nunca cobra su objetivo en la vela en que entra. |
| Costos | Spread 0,17 $/oz, comisión 0,06 $/oz ida y vuelta (3 $/lote por lado), **deslizamiento 0,05 $/oz en cada recarga** y 0,23 $/oz por volumen candado. |
| Unidad | R = ganancia en $/oz ÷ ATR_D, multiplicado por el peso de la pata. Al 8 % de riesgo, 1 R ≈ 8 % de la cuenta (sin interés compuesto). |
| Muestras | Elegir en 2022-2024 (IS) y comprobar en 2025-2026 (OOS). Operaciones: Big One 1 058, Momentum 503. |

**Familias de reglas** (todas sin mirar el futuro):
- tamaño 0,5 o 1 × el lote base;
- salida por hora, o por TP +2 ATR15;
- 152 variantes por pata en total.

| Familia | Qué hace |
|---|---|
| FIX | Orden límite a 1-4 × ATR15, o a 0,25 / 0,5 / 0,75 × ATR_D en contra. También en rejilla, repartida en varios niveles. |
| REV | Giro confirmado en M5: tras ir k × ATR15 en contra (k = 0-3), una vela rompe el máximo de la anterior, o cierra 0,5-1 × ATR15 por encima del mínimo. Se entra en la apertura siguiente. |
| LVL | Soportes y resistencias previos, tocados (orden límite) o tocados y rechazados: mínimo/máximo del día anterior, de la sesión previa, números redondos de 10 y 50 $, **racimo de pivotes M15 de 5 días** y **nivel con más mechas tocadas en 5 días**. |
| TIME | A los 30, 60, 120, 180 o 240 min, si va perdiendo. |

**Pruebas:**
- **Nulo «al azar»:** el mismo número de recargas en momentos al azar del mismo día, en cualquier vela o solo en velas en pérdida. Responde si el *momento* elegido aporta algo.
- **Contraste «lote mayor»:** regresión «recarga = a + b × base» por operación. Si el alfa `a` no es > 0, la recarga equivale a abrir más lote desde el principio, pero con más riesgo de cola.
- **Benjamini-Hochberg** (q = 0,10) sobre las 152 variantes de cada pata.

## 3. Línea base: cuánto va en contra y cuándo

| Pata | Excursión en contra (MAE), mediana | p75 | p90 | Minuto del mínimo (mediana / p75) | Llega a 1 ATR_D (candado) |
|---|---|---|---|---|---|
| Big One | 2,9 ATR15 = 0,18 ATR_D | 0,33 ATR_D | 0,50 ATR_D | 220 / 450 min (de 540) | 1 % |
| Momentum | 3,1 ATR15 = 0,25 ATR_D | 0,44 ATR_D | 0,66 ATR_D | 105 / 205 min (de 360) | 3 % |

- Las ganadoras suelen ir en contra poco: mediana de 0,11 ATR_D (Big One) y 0,16 (Momentum).
- Las perdedoras, mucho: 0,36 y 0,47.

**El problema de fondo:** cuanto más baja el precio, más probable es que sea una perdedora. Recargar «en el fondo» suele significar recargar en los días malos.

**Oráculo** (recargar 1× en el mínimo exacto, sabiendo el futuro; imposible en la práctica):
- Big One: +0,20 R extra por operación. La base gana +0,022 R.
- Momentum: +0,36 R extra por operación. La base gana +0,041 R.

El premio teórico es enorme, pero ninguna regla real captura ni una fracción útil de él. Ver la sección 4.

## 4. Resultados

### Big One

| | Resultado |
|---|---|
| Pasan BH, alfa contra lote mayor | **0 de 152** (mejor p = 0,13) |
| Variantes que mejoran retorno/caída | 10 % en IS → **4 % en OOS** |
| Mejor de IS: recompra tras rechazar el mínimo del día anterior, 1×, TP 2 | IS: retorno/caída +41 %. **OOS: −12 %**. Peor día −16,8 % (base −12,0 %). |
| Rejilla simple (0,25/0,5/0,75 ATR_D) | Todo el período: retorno/caída 7,9, frente a 9,1 de la base. Caída 45 %, frente a 39 %. |

La recarga en la Big One **no sirve**.

### Momentum EE. UU.

| | Resultado |
|---|---|
| Pasan BH, alfa contra lote mayor | **0 de 152** (mejor p = 0,058 antes de corregir por la cantidad de pruebas) |
| Mejor de IS: REV k = 0, giro de 0,5 ATR15, 1×, TP 2 | La recarga sumó R positivo los 5 años (+1,3 / +1,5 / +3,5 / +4,5 / +3,3). OOS: retorno/caída de la cartera 5,2, frente a 3,9 de la base y 3,9 de un lote mayor con el mismo beneficio. |
| Comparación con el nulo al azar en pérdida | Recargar **al azar** (en una vela cualquiera en pérdida de esos mismos días) gana **más**: 0,052 R contra 0,033 R por disparo; p = 0,99. El momento elegido no aporta nada: el efecto viene de añadir exposición a una pata que ya es positiva. |
| Segunda: TIME 60 min si va perdiendo, 1×, TP 2 | Parecido. OOS: alfa p = 0,057; no le gana al azar (p = 0,57). |

**Lo importante en dinero** (cuenta al 8 %, cartera Big One + Momentum, 2025-2026, sin interés compuesto):

| | Base | + recarga REV (Momentum) | Lote mayor (×2,08 en Momentum, mismo beneficio) |
|---|---|---|---|
| Beneficio medio por mes | 6,8 % | 9,6 % (**+2,8 pp**) | 9,6 % |
| Caída máxima | 39 % | 41 % | 54 % |
| Peor día | −12,0 % | **−20,0 %** | −20,7 % |
| Peor mes | −15,8 % | −21,2 % | −21,3 % |
| Sharpe diario | 1,92 | 1,99 | 1,65 |

**Cómo se lee esta tabla:**
- La recarga sube el beneficio unos 2,8 puntos al mes, pero el peor día pasa de −12 % a −20 %.
- En los días en que salta el candado, la recarga casi siempre está dentro: el volumen extra medio candado es 1,0 × el lote base. La pérdida de ese día sube de 1 R a unas 1,3-1,5 R.
- El Sharpe casi no cambia (1,92 → 1,99).
- La mejora en retorno/caída depende de un solo camino de caídas: es frágil.
- Ninguna variante pasa la corrección por múltiples pruebas.
- Se obtiene casi lo mismo subiendo el riesgo del Momentum, que es una decisión simple y conocida, y no una regla nueva de «recargar en el fondo».

### Por familia (IS, mediana del cambio en retorno/caída)

| Familia | Big One | Momentum |
|---|---|---|
| FIX (distancia fija / rejilla) | −14 % | +2 % |
| LVL (soportes, mechas, pivotes) | −18 % | +3 % |
| REV (giro confirmado) | −24 % | +10 % |
| TIME | −28 % | −3 % |

Los niveles de «más mechas tocadas» y de racimos de pivotes **no** son mejores que una distancia fija ni que el azar.

## 5. Por qué parece que «le gana al azar» y no significa nada

Contra el nulo «al azar en el mismo día», muchas reglas FIX y LVL salen con p ≈ 0,001. Es un espejismo:
- Esas reglas solo disparan en días que bajaron mucho.
- El nulo, en esos mismos días, compra también *antes* de la caída, a peor precio.

La prueba que importa es **contra un lote mayor** (el alfa), y ahí no pasa ninguna en ninguna pata.

## 6. Limitaciones

| Limitación | Efecto |
|---|---|
| Resolución de 5 minutos | Una regla de «giro» en ticks o M1 podría ser algo distinta. Hay M1 del broker solo desde 2026-01: no alcanza para elegir y comprobar. |
| 2022-2025 con velas M5 de Dukascopy ajustadas al broker | Diferencia mediana de 0,1-0,25 $/oz y rangos casi iguales. |
| Órdenes límite sin deslizamiento extra | Además de los 0,05 $/oz, no se añadió nada. Si acaso, esto **favorece** a las recargas. |

## 7. Recomendación

- **No** añadir recargas al bot e2: ni en la Big One ni en el Momentum.
- Si se busca más rendimiento en el Momentum, la vía honesta es decidir explícitamente su riesgo (peso > 1), sabiendo que el peor día empeora en proporción. Eso no necesita una regla nueva.
- La REV del Momentum queda como **observación**, no como candidata. Se podría reevaluar cuando haya un año de M1/ticks del broker y de operaciones demo.
