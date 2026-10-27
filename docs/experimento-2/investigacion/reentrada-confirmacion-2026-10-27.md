# Re-entrada «de confirmación» (caída y vuelta a la entrada) — 27-oct-2026

> **Veredicto: NO.** Que el precio caiga y luego vuelva al precio de entrada **no confirma nada**.
> - Después de esa vuelta, la operación rinde **igual o peor** que una operación normal.
> - Rinde lo mismo que entrar en cualquier momento en que el precio esté cerca de la entrada.
> - **Big One:** la re-entrada no aporta. Fuera de muestra empeora el resultado.
> - **Momentum:** suma beneficio porque añade más exposición a una pata que ya gana. A tamaño 1×, el peor día pasa de −12 % a −20 %.
> - Ninguna de las 1 080 variantes por pata le gana a «abrir más lote desde el principio» con la corrección por pruebas múltiples.
> **Recomendación:** no implementarlo en el bot.

Scripts (solo simulación; no se tocó el bot ni MT5):
- `bot_backtesting/fullsim/reentrada_confirmacion.py`: descriptivo, rejilla, nulos, BH y cartera.
- `bot_backtesting/fullsim/reentrada_comparar.py`: estabilidad IS→OOS y variantes representativas contra un lote mayor.

Se reutilizan las operaciones y los caminos M5 del estudio de recargas (`recargas-minimo-2026-10-27.md`):
- mismas reglas e2 (Big One 01:00 → 10:00 y Momentum 15:00 → 21:00);
- 3 tercios (por hora / TP +2 ATR15 / TP +3 ATR15);
- candado a −1 ATR_D;
- mismos costos: spread 0,17 $/oz, comisión 3 $/lote por lado, deslizamiento 0,05 $/oz en cada re-entrada y 0,23 $/oz por volumen bajo candado;
- elegir con 2022-2024 (IS) y comprobar con 2025-2026 (OOS).

## 1. La idea

Tras abrir la Big One o el Momentum:
1. El precio va en contra al menos **D**.
2. Después **vuelve** al precio de entrada.
3. En ese momento se abre un **segundo juego de 3 tercios** en la misma dirección. Sale a la misma hora, con TP en los **mismos precios** que el original o **recalculados** desde la nueva entrada.

El candado (a −1 ATR_D de la entrada **original**) congela también la re-entrada si llega a saltar.

**Rejilla: 1 080 variantes por pata**, cada una con 3 tamaños.

| Parámetro | Valores |
|---|---|
| Caída mínima D | 0,25 / 0,5 / 0,75 / 1 / 1,5 × ATR15 y 0,1 / 0,2 / 0,3 / 0,5 × ATR_D |
| «Vuelta» | toca la entrada −0,25 ATR15, exacta o +0,25 ATR15 (orden stop); o una vela M5 cierra por encima de la entrada (entra en la apertura siguiente) |
| Ventana | en cualquier momento, o dentro de 15 / 30 / 60 / 120 min desde la caída |
| Corte | sin re-entrada en los últimos 0 / 60 / 120 min antes de la salida |
| TP | mismos precios que el original, o recalculados |
| Tamaño | 1/3, 1/2 o 1 × el lote original; como máximo una re-entrada por operación |

**Pruebas:**
- **Nulos al azar**, en los mismos días:
  - (a) una vela cualquiera;
  - (b) una vela cuya apertura está a ±0,25 ATR15 de la entrada, es decir, «entrar en la entrada» sin exigir caída previa.
- **Alfa contra un lote mayor**, por regresión.
- **Benjamini-Hochberg** (q = 0,10) en IS.

## 2. ¿La vuelta a la entrada es una confirmación? (descriptivo)

Se toma la vuelta al precio exacto de entrada, en cualquier momento.

**Cómo se lee la tabla:**
- «Resto» = R de 1 lote abierto en la vuelta y cerrado a la hora de salida (o por el candado).
- «Azar cerca» = lo mismo, pero entrando en una vela al azar con el precio cerca de la entrada, en esos mismos días.
- 1 R = 8 % de la cuenta.

| Pata | D | Cae ≥ D | Vuelve (si cayó) | Minutos de la caída a la vuelta (p25 / mediana / p75) | P(TP2) después | P(TP3) después | R del resto | R azar cerca |
|---|---|---|---|---|---|---|---|---|
| Big One | sin condición (desde la entrada) | — | — | — | **71 %** | **56 %** | **+0,027** | — |
| Big One | 0,5 ATR15 | 87 % | 91 % | 5 / 15 / 60 | 65 % | 50 % | +0,012 | +0,011 |
| Big One | 1 ATR15 | 79 % | 82 % | 10 / 35 / 90 | 61 % | 47 % | +0,004 | +0,003 |
| Big One | 0,2 ATR_D | 45 % | 40 % | 45 / 95 / 208 | 51 % | 35 % | +0,003 | +0,001 |
| Big One | 0,3 ATR_D | 29 % | 26 % | 65 / 133 / 234 | 44 % | 28 % | −0,038 | −0,049 |
| Momentum | sin condición (desde la entrada) | — | — | — | **71 %** | **58 %** | **+0,051** | — |
| Momentum | 0,5 ATR15 | 91 % | 90 % | 5 / 10 / 25 | 70 % | 55 % | +0,042 | +0,052 |
| Momentum | 1 ATR15 | 83 % | 83 % | 5 / 20 / 55 | 65 % | 52 % | +0,036 | +0,040 |
| Momentum | 0,2 ATR_D | 58 % | 53 % | 20 / 50 / 90 | 57 % | 46 % | +0,033 | +0,047 |
| Momentum | 0,3 ATR_D | 42 % | 38 % | 30 / 65 / 93 | 55 % | 45 % | +0,053 | +0,064 |

Lo que dice la tabla:
1. **Caer y volver es lo normal, no una señal.**
   - Una caída pequeña (≤ 1 ATR15) ocurre en 8-9 de cada 10 operaciones.
   - Casi todas vuelven, y en minutos.
2. **Tras la vuelta, las probabilidades de llegar a TP2 y TP3 son menores que las de una operación sin condición.** Cuanto más grande fue la caída, peor. Lo que queda de recorrido también rinde menos.
3. **Entrar tras la vuelta rinde lo mismo que entrar al azar cerca del precio de entrada** (columnas «R del resto» y «R azar cerca»). En el Momentum, el azar incluso rinde un poco más.

La «confirmación» no añade información.

## 3. Resultados de la rejilla

| | Big One | Momentum |
|---|---|---|
| Pasan BH, alfa contra lote mayor (IS) | **0 de 1 080** (mejor p = 0,10) | **0 de 1 080** (mejor p = 0,047 antes de corregir por la cantidad de pruebas) |
| R por re-entrada (mediana de las variantes): IS → OOS | +0,001 → **−0,005** | +0,030 → +0,030 |
| Variantes con alfa > 0 en OOS | 2 % | 62 % |
| Correlación del R por disparo, IS contra OOS | 0,53 | **−0,58** (lo que fue bien en IS tiende a ir mal en OOS) |
| Variantes frecuentes (≥ 25 % de días): R por disparo contra el nulo «azar cerca de la entrada» | IS 0,004 frente a 0,005; OOS 0,007 frente a 0,001 | IS 0,028 frente a 0,032; OOS 0,034 frente a 0,033 |

**Las mejores de IS cayeron en OOS:**
- Big One, D = 0,2 ATR_D, vuelta exacta, 60 min: +0,087 R por disparo en IS y **−0,016 en OOS**.
- Momentum, D = 0,5 ATR_D: solo 7 disparos en IS, con +0,11 R; en OOS, **−0,17 R**.

**Por qué no cuenta que «le gane al azar»:** muchas variantes pasan BH contra el nulo «vela al azar» (314 en la Big One, 478 en el Momentum). Es el mismo espejismo que en el estudio de recargas:
- La regla solo dispara en ciertos días.
- El nulo, en esos mismos días, compra también en momentos peores.

La prueba que importa es contra un lote mayor, y ahí no pasa ninguna.

**Lo único que se acerca, en el Momentum:**
- Es la vuelta a «entrada −0,25 ATR15», es decir, volver casi a la entrada pero comprando un poco más barato.
- Le gana al nulo «azar cerca de la entrada»: +0,045 contra +0,028 en IS y +0,046 contra +0,018 en OOS.
- Su alfa contra el lote mayor es **negativo en IS** (p = 0,62) y positivo solo en OOS (p = 0,015). Con 1 080 variantes y sin haberla elegido en IS, eso no es una prueba.
- Es la misma «recarga en un retroceso» del estudio anterior (la REV k = 0), con otro nombre.

## 4. En dinero: cartera Big One + Momentum al 8 %, sin interés compuesto

Una variante típica y frecuente: D = 0,5 ATR15, vuelta exacta, en cualquier momento, sin re-entrada en la última hora, TP en los mismos precios.

| Pata, tamaño, período | Cartera | Beneficio por mes | Caída máxima | Retorno/caída | Sharpe | Peor día | Peor mes |
|---|---|---|---|---|---|---|---|
| — (OOS 2025-2026) | **Base** | 6,8 % | 38,6 % | 3,9 | 1,92 | −12,0 % | −15,8 % |
| Big One 1/3, OOS | re-entrada | 7,2 % | 45,6 % | 3,5 | 1,83 | −13,7 % | −17,6 % |
| Big One 1/3, OOS | lote mayor (×1,10) | 7,2 % | 41,8 % | 3,8 | 1,94 | −12,4 % | −16,9 % |
| Big One 1×, OOS | re-entrada | 8,0 % | **61,0 %** | 2,9 | 1,64 | **−19,0 %** | −21,2 % |
| Big One 1×, OOS | lote mayor (×1,30) | 8,0 % | 48,4 % | 3,6 | 1,97 | −13,4 % | −19,0 % |
| Momentum 1/3, OOS | re-entrada | 7,9 % | 37,3 % | 4,7 | 1,98 | −14,7 % | −14,7 % |
| Momentum 1/3, OOS | lote mayor (×1,42) | 7,9 % | 42,8 % | 4,1 | 1,81 | −15,4 % | −18,0 % |
| Momentum 1×, OOS | re-entrada | 10,1 % | 37,7 % | 5,9 | 2,00 | **−20,1 %** | −12,3 % |
| Momentum 1×, OOS | lote mayor (×2,26) | 10,1 % | 57,5 % | 3,9 | 1,61 | −22,1 % | −22,2 % |
| Momentum 1×, IS | re-entrada | 9,1 % (base 7,3 %) | 40,1 % (base 29,0 %) | 6,4 (base 7,0) | 2,21 (base 2,66) | −17,8 % (base −9,7 %) | −13,4 % (base −7,4 %) |

**R añadido por año** (re-entrada 1×; 2022 / 2023 / 2024 / 2025 / 2026):

| Pata | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|
| Big One | +1,3 | +0,7 | +1,8 | +1,7 | +1,7 |
| Momentum | +1,3 | −0,2 | +5,3 | +5,8 | +3,3 |

En la Big One suma R todos los años, pero:
- lo suma con más caída que un lote mayor;
- el alfa en OOS es negativo en el 96 % de las variantes frecuentes.

**Interacción con el candado:**
- Con caídas pequeñas (D ≤ 1 ATR15), la re-entrada está dentro en la mayoría de los días en que salta el candado. Con D = 0,5 ATR15: en 11 de los 14 días de candado de la Big One y en 11 de los 17 del Momentum (2022-2026).
- Ese día el candado congela un volumen hasta 2× el normal, y la pérdida del día pasa de 1 R a casi 2 R.
- De ahí salen los peores días de −19 % a −20 % al 8 % de riesgo.
- Cuando la re-entrada exige una caída mayor y una vuelta, casi nunca coincide con días de candado (en esos días el precio no vuelve). Pero entonces dispara pocas veces y su resultado es ruido.

## 5. Limitaciones

| Limitación | Efecto |
|---|---|
| Resolución de 5 min | No hay M1 del broker para 2022-2025, así que la vuelta «por cierre» se probó solo en M5. Si en la misma vela se tocan el candado y un objetivo, gana el candado. La re-entrada no cobra su TP en la vela en que entra. |
| 2022-2025 con velas M5 de Dukascopy ajustadas al broker | Igual que en el estudio de recargas. |
| Solo la primera caída y la primera vuelta | Se miran la primera caída ≥ D y la primera vuelta. Si la vuelta llega fuera de la ventana o después del corte, no hay re-entrada. |

## 6. Recomendación

- **No** añadir la re-entrada de confirmación al bot e2, ni en la Big One ni en el Momentum.
- La vuelta al precio de entrada no predice que la operación vaya a salir bien. Si acaso, una caída grande predice lo contrario.
- La ganancia que se ve en el Momentum es **más exposición** a una pata que ya es positiva. Se consigue igual decidiendo explícitamente un peso mayor para el Momentum, sabiendo que el peor día empeora en proporción.
- La variante «vuelta a entrada −0,25 ATR15» del Momentum queda **solo en observación**. Es la misma conclusión que la REV del estudio de recargas.
