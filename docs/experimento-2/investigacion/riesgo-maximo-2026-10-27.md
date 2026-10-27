# ¿Estamos en el lote máximo que aguantan las cuentas? (bot e2) — 27-oct-2026

> Solo simulación. Script: `bot_backtesting/fullsim/riesgo_max_e2.py` (prioridad baja, sin MT5).
> Datos: precios del broker 2022-10 → 2026-10 (1 603 operaciones: Big One 1 047, Momentum 510, NFP 46).
> Resultados crudos: `bot_backtesting/fullsim/results/riesgo_max_e2.pkl` (fuera de git).

## Respuesta corta

**No estamos en el máximo: el margen y la matemática del crecimiento permiten mucho más que 8 %.
El límite real es cuánta caída se tolera, y la ventaja real todavía no está confirmada.**

- **Margen:** al 8 % sobra con creces. El stop-out solo se acerca entre **20 y 25 %** de riesgo, en un día
  extremo con tres patas bloqueadas y deslizamiento.
- **Riesgo de máximo crecimiento (Kelly):** con la ventaja medida ronda el **40 %** por operación. Si la
  ventaja real fuese la mitad, ronda el **22 %**. El 8 % está muy por debajo en los dos casos.
- **Caída:** crece casi en proporción al riesgo. En el camino histórico fue de **33 % al 8 %**, **40 % al
  10 %**, **47 % al 12 %** y **56 % al 15 %**.

**Recomendación:**
- **Mantener 8 % durante la demo.**
- Pasar a **10 %** solo si la demo confirma al menos ~75 % de la ventaja medida y se acepta una caída de ~40 %.
- Por encima de **12 %** no tiene sentido: casi no se gana más si la ventaja está sobrestimada, y la
  probabilidad de caer más de la mitad se dispara.

## Supuestos (reglas e2 vigentes)

- **Patas:**
  - Big One: compra 01:00 → 10:00. Peso 1 con tendencia +2, 0,5 si no, y ×0,5 en día de NFP, IPC o FOMC.
  - Momentum EE. UU.: 15:00 → 21:00, solo con tendencia ±2.
  - NFP.
  - Todas con escalera de tercios (hora / TP 2 / TP 3 ATR15), candado a −1 ATR_D y cierre a la hora de salida.
- **Entrada a las 01:01:** se restó un **14 %** de la ventaja de la Big One, porque el broker no acepta
  órdenes a las 01:00 (ver memoria `broker-sesion-trading-0101`).
- **Lotes reales:** tercio = floor(lote/3; 0,01), con mínimo 0,01, y balance cerrado al entrar.
- **Costos:** comisión RAW, spread y swap, como en el simulador.
- **Ventaja recortada:** a cada pata se le resta un 25 % o un 50 % de su R medio, sin tocar la dispersión.
  Responde a la pregunta «¿y si el backtest exagera?».
- **Margen:**
  - Apalancamiento 1:500, contrato de 100 oz.
  - El broker informa `margin_hedged = 0`, así que el candado no debería sumar margen. Aun así, por
    prudencia, **se cobró margen completo en ambos lados**.
  - Stop-out del broker: **20 %** y margin call 50 %, según la auditoría de margen de las cuentas del mismo
    broker. Para ir sobre seguro, también se usa 50 % como referencia.

Nota: este camino rinde menos que la tabla del diseño (×26–35 frente a ×50–60 al 8 %). Influyen dos cosas:
- el retraso a las 01:01;
- el ×0,5 de la Big One en días de noticia, que la proyección anterior no aplicaba.

## 1. Camino histórico 2022-10 → 2026-10 (ventaja medida)

Cuenta de 10 000. La de 25 000 da casi lo mismo y la de 3 000 se ve en la nota debajo de la tabla.

| Riesgo | Crec. anual (CAGR) | Mes medio | Caída máx. por operación | Caída a fin de mes | Peor día | Peor mes | Racha bajo el máximo | Margen mínimo histórico |
|---|---|---|---|---|---|---|---|---|
| 4 % | 53 % | 3,6 % | 17 % | 10 % | −5,5 % | −6,6 % | 260 días | 3 300 % |
| 6 % | 93 % | 5,6 % | 25 % | 15 % | −8,7 % | −9,7 % | 260 días | 2 100 % |
| **8 %** | **138 %** | **7,5 %** | **33 %** | **20 %** | **−11,6 %** | **−13,1 %** | **261 días** | **1 500 %** |
| 10 % | 190 % | 9,2 % | 40 % | 25 % | −14,5 % | −16,5 % | 261 días | 1 170 % |
| 12 % | 247 % | 10,9 % | 47 % | 30 % | −17,3 % | −19,7 % | 261 días | 940 % |
| 15 % | 348 % | 13,2 % | 56 % | 37 % | −21,5 % | −24,5 % | 262 días | 720 % |
| 20 % | 543 % | 16,7 % | 68 % | 49 % | −28,1 % | −32,3 % | 276 días | 490 % |
| 25 % | 754 % | 19,5 % | 78 % | 59 % | −34,5 % | −39,8 % | 290 días | 355 % |
| 30 % | 948 % | 21,5 % | 85 % | 69 % | −40,7 % | −46,9 % | 292 días | 254 % |

**Cuenta de 3 000:** las caídas son iguales y crece algo menos (al 8 %: ×26 frente a ×34). El lote mínimo
hace que el riesgo suba a saltos:
- Cada tercio es como mínimo 0,01, así que la escalera mínima es de 0,03 lotes.
- Las Big One de medio peso arriesgan de verdad ~5 % en vez de 4 %.
- Con ATR bajo, el 8 % y el 10 % dan **el mismo lote**.

**Lo que dice esta tabla:** el peor día histórico fue de **−1,5 R** (sumando todas las patas del día), así que
el peor día ≈ −1,5 × riesgo. La racha más larga sin nuevo máximo ronda los **8–9 meses** con cualquier riesgo.

## 2. Próximos 12 meses: remuestreo (4 000 caminos, lotes recalculados con el balance simulado)

Se usaron dos métodos: meses al azar y bloques de 10 días al azar. Se muestra el más pesimista de los dos.
Cuenta de 10 000.

| Riesgo | Ventaja | Capital típico (p50) | P(perder en el año) | P(caída > 30 %) | P(caída > 40 %) | P(caída > 50 %) |
|---|---|---|---|---|---|---|
| 8 % | 100 % | ×2,2 | 1 % | 9 % | 1 % | 0 % |
| 8 % | 75 % | ×1,8 | 6 % | 16 % | 3 % | 0,4 % |
| 8 % | 50 % | ×1,46 | 16 % | 28 % | 7 % | 1 % |
| 10 % | 100 % | ×2,7 | 2 % | 25 % | 5 % | 1 % |
| 10 % | 75 % | ×2,0 | 6 % | 37 % | 11 % | 2 % |
| 10 % | 50 % | ×1,55 | 18 % | 52 % | 21 % | 6 % |
| 12 % | 100 % | ×3,2 | 2 % | 45 % | 14 % | 3 % |
| 12 % | 50 % | ×1,65 | 20 % | 72 % | 38 % | 15 % |
| 15 % | 100 % | ×4,1 | 3 % | 73 % | 35 % | 12 % |
| 15 % | 50 % | ×1,77 | 22 % | 90 % | 63 % | 35 % |
| 20 % | 100 % | ×5,9 | 4 % | 95 % | 72 % | 38 % |
| 20 % | 50 % | ×1,89 | 27 % | 99 % | 89 % | 67 % |
| 30 % | 50 % | ×1,76 | 36 % | 100 % | 100 % | 96 % |

**3 000:** al 8 % y 4–6 %, las probabilidades de caída son algo **mayores** que en 10 000. El redondeo
arriesga de más en las operaciones de medio peso. Por ejemplo, al 8 % con la ventaja medida P(caída > 40 %)
es 3 %, frente a 1 %.

**25 000:** prácticamente igual que 10 000.

**Lectura:** con la mitad de la ventaja, subir del 8 % al 15 % apenas mejora el capital típico (×1,46 → ×1,77),
mientras que la probabilidad de caer más de la mitad pasa de 1 % a 35 %.

## 3. Riesgo de máximo crecimiento (Kelly), con bandas

El crecimiento geométrico se calcula como la media diaria de log(1 + riesgo × Σ w·R). Las bandas salen de
remuestrear bloques de 10 días (1 000 réplicas).

| Ventaja | Riesgo óptimo (Kelly) | Banda 5 %–95 % | Crec. anual al 8 % | Crec. anual al 15 % | Crec. anual al óptimo |
|---|---|---|---|---|---|
| 100 % | 40 % | 28–51 % | +135 % | +334 % | +1 120 % |
| 75 % | 31 % | 19–44 % | +86 % | +180 % | +328 % |
| 50 % | 22 % | **8,5–36 %** | +47 % | +81 % | +94 % |

- El 8 % equivale a **1/5 de Kelly** con la ventaja medida y a **~1/3 de Kelly** si la ventaja real es la mitad.
- Con la mitad de la ventaja, el borde bajo de la banda (8,5 %) coincide con el 8 %. Por eso el 8 % es
  «prudente» solo si la ventaja real es al menos la mitad de la medida.
- Kelly maximiza el crecimiento a largo plazo, pero lo hace con caídas enormes: al Kelly completo, más del
  80 %. En la práctica se usa entre 1/4 y 1/2 de Kelly.
- Además, este Kelly supone días independientes. Una racha de régimen malo, como un oro bajista y lateral
  que no está en los datos, lo bajaría.

## 4. Margen y stop-out (restricción dura)

### En el camino histórico

- Como mucho hubo **2 patas abiertas a la vez** (NFP con Momentum del viernes, o NFP con la Big One del lunes).
- Nivel de margen mínimo, con todas las abiertas en su peor punto y cobertura cobrada doble:
  - **1 500 % al 8 %**;
  - 720 % al 15 %;
  - 254 % al 30 %.
- Nunca se acercó al stop-out.

### Estrés sintético

Supuestos del peor día:
- todas las patas bloqueadas a la vez;
- lotes con el ATR_D/precio más bajo de la historia (0,66 %, es decir, lotes más grandes);
- precio actual (~4 026);
- candado cobrado en ambos lados.

Nivel de margen que queda (cuenta de 10 000):

| Riesgo | 2 patas a −1 R | 2 patas a −1,5 R (hueco) | 3 patas a −1 R | 3 patas a −1,5 R | Capital que queda (peor caso) |
|---|---|---|---|---|---|
| 8 % | 871 % | 789 % | 526 % | 444 % | 64 % |
| 10 % | 699 % | 617 % | 411 % | 329 % | 57 % |
| 12 % | 526 % | 444 % | 296 % | 214 % | 47 % |
| 15 % | 411 % | 329 % | 220 % | 138 % | 36 % |
| 20 % | 250 % | 168 % | 112 % | **30 %** ← cerca del stop-out | 11 % |
| 25 % | 170 % | **88 %** | **59 %** | **negativo** (cuenta quemada) | <0 |
| 30 % | 116 % | **34 %** | **23 %** | **negativo** | <0 |

- **El stop-out (20 %) se acerca recién en 20–25 % de riesgo.** Con la referencia prudente de 50 %, el
  límite queda en **~20 %**.
- Antes que el margen, lo que mata a esos riesgos es la propia pérdida: 3 patas × −1,5 R al 25 % es −112 % del capital.
- El tope de volumen (100 lotes por orden) no limita: al 8 % sobre 25 000 la escalera es de ~1 lote.
- El bot ya reparte en varias órdenes si hiciera falta. Más allá de unos 7–8 millones de balance, la
  liquidez real del broker sería otro tema.

## 5. Recomendación por cuenta

| Cuenta | Máximo que «aguanta» (margen / estrés) | Óptimo matemático (ventaja medida → mitad) | **Sensato** | Por qué |
|---|---|---|---|---|
| 3 000 | ~20 % | 40 % → 22 % | **8 %** (no subir) | Por el lote mínimo ya arriesga algo más de lo nominal; el 10 % da el mismo lote casi siempre. |
| 10 000 | ~20 % | 40 % → 22 % | **8 % ahora; 10 % tras la demo si la ventaja se confirma** | Al 10 %, caída histórica 40 % y P(caída > 50 % en 12 m) 1–6 % según la ventaja. |
| 25 000 | ~20 % | 40 % → 22 % | **8 % ahora; 10 % tras la demo si la ventaja se confirma** | Igual que la de 10 000. |

**Conclusión honesta:**
- No, el 8 % **no es el máximo que soportan las cuentas**: técnicamente aguantan hasta ~20 %.
- Pero el máximo que soportan no es el recomendable. El 8 % ya implica caídas del ~33 %. Si la ventaja real
  resulta ser la mitad de la medida, el 8 % queda en el borde bajo de lo óptimo, y subir a 15–20 % agrega muy
  poco crecimiento a cambio de un riesgo alto de perder más de la mitad.
- La demo de 10 semanas es la que dirá cuánta ventaja es real. Con ese dato se decide si conviene el 10 %.
- **No subir de 12 % en ningún caso.**

## Límites

- 4 años de un oro mayormente alcista. Un mercado bajista y lateral largo no está en los datos.
- El simulador es de cierre de vela M15. Los saltos dentro de la vela y los huecos de fin de semana se
  aproximan con el escenario de −1,5 R.
- El remuestreo diario trata cada día por separado. La pata NFP, que cruza el fin de semana, se cuenta en su día de entrada.
- La corrección por 01:01 (−14 %) sale de 123 días de ticks de 2026 y tiene error estadístico.
