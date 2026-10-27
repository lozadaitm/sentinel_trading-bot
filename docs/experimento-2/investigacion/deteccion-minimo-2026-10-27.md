# ¿Puede el bot «ver» el mínimo y recargar ahí? — 27-oct-2026

> **Veredicto: NO, por ahora.** Probamos 24 ideas y llevamos a prueba 11 familias, 222 variantes en total. Ninguna supera a la vez:
> - a recargar **al azar**,
> - y a usar un **lote inicial mayor**,
>
> de forma estable en 2022-2024 y en 2025-2026.
>
> Los detectores de «fondo» entran, en mediana, a **0,19 ATR_D** del mínimo final. Una recarga al azar en una vela en pérdida de esas mismas operaciones queda a **0,09-0,11 ATR_D**: el detector entra antes de tiempo, a peor precio.
>
> Lo único que salió bien fuera de muestra (un clasificador en el Momentum) salió **mal** en 2022-2024 y **no le gana** a recargar en días al azar.

Es la continuación de [recargas-minimo-2026-10-27.md](recargas-minimo-2026-10-27.md), que ya había probado 152 reglas simples. Aquí no se repiten: aquí se prueba **aprendizaje automático**, un **detector de día bueno o malo**, parada óptima, capitulación, ticks y M1.

Scripts (solo simulación; el bot no se tocó):

| Script | Qué hace |
|---|---|
| `bot_backtesting/fullsim/minimo_lab.py` | Rasgos por vela M5, modelos (logística y GBDT en numpy), 11 familias, nulos, BH, lote mayor y corte por día malo |
| `bot_backtesting/fullsim/minimo_profundo.py` | Revisión a fondo de las 5 variantes que salieron bien fuera de muestra: por año, con dos nulos y contra el lote mayor |
| `bot_backtesting/fullsim/minimo_m1.py` | Reglas con M1 y ticks del broker (solo 2026) |

## 1. Por qué «imposible en la práctica» no era una frase hecha

El mínimo de una operación se sabe **solo cuando ya pasó**. Para recargar ahí, el bot tiene que adivinar, en cada vela, si el precio ya tocó fondo o si seguirá bajando.

El estudio anterior mostró la trampa: cuanto más baja el precio, **más probable es que sea un día perdedor**. Las ganadoras van en contra una mediana de 0,11-0,16 ATR_D; las perdedoras, de 0,36-0,47.

Así que «ver el mínimo» exige, en el fondo, **saber pronto si el día es bueno o malo**. Eso es lo que medimos aquí con la mayor seriedad posible.

## 2. Lluvia de ideas (24)

**A. Aprendizaje automático**
1. Clasificador «si recargo ahora, ¿gano?» por vela M5 en pérdida (GBDT y logística). **Probado (ML_ya)**.
2. Clasificador «esto es el fondo»: entra a ≤ 0,1 ATR_D del mínimo final **y** la recarga gana. **Probado (ML_yb)**.
3. Detector de «día malo» (¿terminará la operación en pérdida?) en cada vela. **Probado (yc)**.
4. Usar el detector de día malo para **cortar** la base pronto. **Probado (CORTE)**.
5. Usar el detector de día malo para **filtrar** las órdenes límite. **Probado (LADML)**.
6. Regresión de cuantiles del mínimo restante (cuánto falta por bajar). *No probado: el problema es el mismo que en 2.*
7. Modelos secuenciales (LSTM o transformer) sobre el camino. *No probado: con unas 1 500 operaciones se sobreajustan seguro.*
8. Análogos («días que empezaron igual»: k vecinos sobre el camino normalizado). *Ya se hizo algo parecido en el banco de patrones (k-means, SAX y análogos), sin resultado.*

**B. Órdenes y parada óptima**
9. Escalera de límites en los cuantiles del MAE de las **ganadoras**, activa solo hasta el minuto típico de su mínimo. **Probado (LAD)**.
10. La misma escalera, cancelada si el detector de día malo se enciende. **Probado (LADML)**.
11. Parada óptima tipo «secretaria»: observar el primer 25-50 % del tiempo y recargar al romper ese mínimo, o al rebotar tras romperlo. **Probado (SEC)**.
12. Ventana horaria donde más se produce el mínimo, con el precio pegado al mínimo del momento. **Probado (SEAS)**.
13. Recarga escalonada en el tiempo (DCA en pérdida). *Equivale a las TIME y FIX del estudio anterior.*

**C. Agotamiento y giro**
14. Capitulación M5: vela de rango ≥ 1,5-2,5 × la media, mecha inferior ≥ 50 % y cierre arriba. **Probado (CAP)**.
15. Perforar Bollinger (2-3 σ) o Keltner y cerrar dentro. **Probado (BB, KC)**.
16. Divergencia alcista de RSI(14) en un mínimo nuevo. **Probado (DIV)**.
17. Rechazo en una vela M15 y confirmación M5 (cierre sobre el máximo de la M15). **Probado (MTF)**.
18. Lo mismo con disparo en M1. **Probado (MTF1, solo 2026)**.

**D. Microestructura (ticks, solo 2026)**
19. Pico de actividad (ticks por minuto) con mecha de rechazo. **Probado (TCAP)**.
20. Agotamiento: la actividad cae mientras el precio está en el mínimo. **Probado (TEXH)**.
21. Desequilibrio de ticks (más subidas que bajadas) en el mínimo, como señal de absorción. **Probado (IMB)**.
22. Ensanchamiento del spread como señal de pánico. *No probado: en 2026 el spread del broker es casi fijo (0,17).*

**E. Contexto externo**
23. Confirmación con otros mercados (DXY, plata, bonos) en el mínimo. *No probado aquí. Los estudios cruzados anteriores no dieron señal intradía útil.*
24. Noticias: no recargar en días de dato fuerte, o recargar justo después del dato. *Se incluyó «día de noticia» como rasgo de los modelos.*

## 3. Cómo se midió

Usamos la misma base y los mismos costos que el estudio anterior:
- Big One 01:00 → 10:00 y Momentum 15:00 → 21:00.
- 3 tercios con candado a 1 ATR_D.
- Camino dentro de la operación en velas M5 ajustadas al broker.
- Costos: spread 0,17 $/oz, comisión 0,06 $/oz ida y vuelta, **deslizamiento 0,05 $/oz en cada recarga**.

| Tema | Detalle |
|---|---|
| Rasgos (28, todos con lo ya cerrado) | Pérdida actual y máxima hasta ahora (en ATR_D y ATR15), rebote desde el mínimo, mejor ganancia hasta ahora, minuto desde la entrada, tiempo desde el último mínimo, velocidad de la caída (6 y 12 velas), rango reciente frente a la media (agotamiento), mecha inferior, posición del cierre, RSI(14), z-score 20, distancia al mínimo del día anterior y de la sesión, número redondo, día de la semana, tendencia s, peso, pata, día de noticia, ATR_D/ATR15, movimiento previo a la entrada (1 h y 1 día), velas bajistas en 6, «mínimo nuevo». |
| Filas | 66 998 velas M5 en pérdida, antes del candado. Cada operación pesa lo mismo. |
| Modelos | Logística con L2 y GBDT (árboles de profundidad 3, 150 rondas, submuestreo), escritos en numpy. |
| Validación | **Fuera de muestra móvil:** 2025 se predice con un modelo entrenado en 2022-2024, y 2026 con uno entrenado en 2022-2025. En 2022-2024, validación cruzada dejando un año fuera; con eso se fijan los umbrales (5 cuantiles: 50/80/90/95/98 %). |
| Regla de recarga | 1 × lote base en la apertura siguiente a la primera vela que dispara. Sale por hora o con TP +2 ATR15. Queda dentro del candado. |
| Pruebas | (a) **Nulo al azar, mismo día:** el mismo número de recargas en velas en pérdida al azar de esas operaciones. (b) **Nulo al azar, día al azar** (solo en la revisión a fondo): mide si el valor está en *elegir el día*. (c) **Alfa contra un lote mayor:** regresión por operación. (d) **Benjamini-Hochberg** (q = 0,10) sobre las 90 variantes de cada pata, en IS y en OOS por separado. |
| Cartera | Big One + Momentum al 8 % por R, sin interés compuesto. |

## 4. Qué tan bien «ve» el bot

### 4.1 Calidad de los detectores (AUC; 0,5 = adivinar, 1 = perfecto)

| Detector | Pata | 2022-24 (validación cruzada) | 2024 estricto | 2025-26 (OOS) |
|---|---|---|---|---|
| «Si recargo ahora, gano» (GBDT) | Big One | 0,60 | 0,60 | 0,63 |
| | Momentum | 0,66 | 0,70 | 0,66 |
| «Si recargo ahora, gano» (logística) | Big One | 0,64 | 0,65 | 0,64 |
| | Momentum | 0,67 | 0,68 | 0,66 |
| «Esto es el fondo» (GBDT) | Big One | 0,57 | 0,57 | 0,60 |
| | Momentum | 0,57 | 0,58 | 0,61 |

- El detector de «fondo» es **débil** (AUC 0,57-0,61).
- El de «gano si recargo» es algo mejor (0,60-0,67), pero casi todo lo que sabe es **«qué día es»**, no **«qué momento es»**. Se ve en los nulos (sección 5).
- Hay un detector de «día malo» con AUC de 0,78-0,85 si se mezclan todas las horas, **pero esa cifra engaña**: a las 3 horas, una operación que va 0,4 ATR_D en contra ya es, obviamente, mala. Lo que importa es **a una hora fija**, temprano:

| Detector de día malo, OOS 2025-26 | 15 min | 30 min | 60 min | 120 min | 180 min |
|---|---|---|---|---|---|
| Big One (AUC) | 0,53 | 0,57 | 0,56 | 0,55 | 0,66 |
| Momentum (AUC) | 0,59 | 0,67 | 0,67 | 0,75 | 0,85 |

- En la **Big One**, durante las primeras 2 horas, el bot casi no distingue un día bueno de uno malo (AUC 0,53-0,57).
- En el **Momentum** algo distingue a los 30-60 min (0,67), pero no lo bastante para ganar dinero con eso (sección 6).

### 4.2 Precisión: qué tan cerca del mínimo entra (mediana, OOS)

Recarga al azar = en una vela en pérdida cualquiera de esas mismas operaciones.

| Familia | Distancia al mínimo final (ATR_D), Big One | Al azar | Distancia, Momentum | Al azar | % de recargas en días perdedores (Big One / Momentum) |
|---|---|---|---|---|---|
| ML «gano» / «fondo» | 0,19 | 0,11 | 0,19-0,21 | 0,09-0,10 | 40 % / 35 % |
| Capitulación M5 (CAP) | 0,15 | 0,16 | 0,09 | 0,15 | 58 % / 54 % |
| Bollinger / Keltner | 0,16 | 0,13 | 0,13-0,15 | 0,13-0,14 | 51 % / 52 % |
| Divergencia RSI | 0,17 | 0,13 | 0,14 | 0,12 | 54 % / 49 % |
| Secretaria (SEC) | 0,16 | 0,15 | 0,12 | 0,15 | 59 % / 62 % |
| Escalera de ganadoras (LAD) | 0,22 | 0,14 | 0,21 | 0,15 | 57 % / 60 % |

- **Ninguna familia entra cerca del mínimo de forma sistemática.** Solo un 25-45 % de las recargas quedan a ≤ 0,1 ATR_D del mínimo.
- Los modelos de ML eligen días algo mejores (35-40 % perdedores, frente a 45-60 % de las reglas). A cambio, entran **antes** del fondo: unas 0,2 ATR_D por encima del mínimo, el doble de lejos que el azar.
- Las reglas de giro (CAP, DIV, BB) entran un poco más cerca del fondo, pero sobre todo en **días malos**: es la trampa del estudio anterior.

## 5. Resultados de las recargas

### 5.1 Conteo (90 variantes por pata; BH q = 0,10)

| Pata | Pasan alfa contra lote mayor, IS | Pasan alfa, OOS | Pasan nulo al azar mismo día, OOS | Pasan **las dos** en OOS |
|---|---|---|---|---|
| Big One | 0 | 0 | 20 | **0** |
| Momentum | 0 | 2 | 7 | **0** |

En promedio, las recargas **empeoran** el retorno/caída. Mediana de variantes:
- Big One: −15 % en IS y −23 % en OOS.
- Momentum: −13 % en IS y +3 % en OOS.

Solo el 13-27 % de las variantes le ganan al lote mayor en IS.

Por familia, en OOS (mediana del cambio en retorno/caída):

| Familia | Big One | Momentum |
|---|---|---|
| ML «gano» (GBDT) | −25 % | +28 % |
| ML «gano» (logística) | −26 % | +1 % |
| ML «fondo» (GBDT) | −27 % | +18 % |
| Escalera de ganadoras | −38 % | +2 % |
| Escalera + filtro de día malo | −42 % | +2 % |
| Capitulación M5 | +6 % | +3 % |
| Bollinger / Keltner | −26 % / −20 % | −16 % / +17 % |
| Divergencia RSI | −20 % | +35 % |
| Secretaria | −23 % | −4 % |
| Ventana horaria | +4 % | −7 % |
| M15 + M5 | −37 % | −28 % |

### 5.2 Las que salieron «bien» fuera de muestra, revisadas a fondo

Se eligieron **mirando el OOS**, así que hay que leerlas con desconfianza. `minimo_profundo.py`:

**Momentum, ML «fondo» GBDT, umbral 98 %, salida por hora**

| | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|
| R que añade la recarga | +2,0 | +0,5 | +0,4 | **+7,8** | +3,8 |

| Cartera | IS 2022-24: retorno/caída | IS: peor día | OOS 2025-26: retorno/caída | OOS: peor día | OOS: beneficio/mes |
|---|---|---|---|---|---|
| Base | 7,0 | −9,7 % | 3,9 | −12,0 % | 6,8 % |
| + recarga | **6,1** (peor) | **−16,8 %** | **6,3** | −12,0 % | 11,0 % |
| Lote mayor, mismo beneficio | 6,7 | −11,5 % | 3,8 | −24,9 % | 11,0 % |

- Nulo al azar, **mismo día**: p = 1,00. Recargar en un momento cualquiera de esos días gana casi el doble (+20 R frente a +11,6 R): el «momento» elegido es **peor** que el azar.
- Nulo al azar, **día al azar**: p = 0,70. Recargar en días y momentos al azar da lo mismo (+13 R).
- **Conclusión:** en 2025-26 el Momentum fue un buen período y cualquier exposición extra ganó. En 2022-24 la misma regla empeoró la cartera. No hay detector del fondo.

**Momentum, ML «gano», umbral 90 %:** el mismo patrón. OOS retorno/caída 5,6 contra 3,9 de la base, pero el peor día pasa a −19,9 %. Nulos: p = 1,00 y p = 1,00.

**Big One, capitulación M5 (k = 2-3 ATR15, rango ≥ 2,5 × media)**
- Le gana al nulo del mismo día (p ≈ 0,001-0,006), tanto en IS como en OOS.
- **No** le gana al nulo de días al azar (p = 0,33-1,00). En IS añade −1,2 R y +0,5 R; en OOS, +3,7 R y +1,5 R.
- Es la misma ilusión explicada en el estudio anterior. La regla solo dispara en días que ya bajaron mucho. En esos días, el azar compra también *antes* de la caída, a peor precio. Eso hace que la regla «le gane al azar» sin tener habilidad real.

### 5.3 Inverso: cortar la base si el detector dice «día malo»

Cerrar lo que quede abierto a los 30/60/120/180 min si la probabilidad de día malo supera el cuantil 70 % o 90 % de IS:
- **Big One:** empeora en casi todos los casos, en IS y en OOS. Entre −0,009 y +0,001 R por operación. Cortar pronto te saca de días que se recuperan.
- **Momentum:** en IS empeora en **todas** las combinaciones (−0,006 a −0,018 R/op). En OOS mejora (+0,004 a +0,009 R/op; p = 0,008-0,03 contra cortar al azar). Ese signo opuesto entre períodos indica ruido o un cambio de régimen, no una habilidad. Con 16 pruebas OOS, ninguna pasa BH.

### 5.4 M1 y ticks del broker (solo 2026: 198 Big One, 103 Momentum)

Probamos 11 reglas por pata y las evaluamos en todo 2026 y en sus dos mitades: pico de ticks con mecha, agotamiento de ticks, desequilibrio de subidas y bajadas, y rechazo M15 con disparo M1.
- Ninguna le gana al azar del mismo día en todo 2026. La mejor p es 0,20 en la Big One y 0,11 en el Momentum.
- Lo único con p < 0,05 contra el lote mayor: desequilibrio de ticks en el Momentum. Son 10 disparos, +0,17 R por disparo, alfa p = 0,02. Con 18 pruebas y 10 disparos es **anecdótico**.
- El conteo de ticks del broker se satura en unos 1 000 por minuto, así que los picos de «pánico» casi no se ven. Las reglas de capitulación por ticks entran en días perdedores (55-100 %).

## 6. Respuesta honesta a «¿por qué no puede ver el mínimo?»

1. **El mínimo no se puede distinguir de «la mitad de la caída» con lo que hay hasta ese momento.** Con 28 rasgos y dos tipos de modelo, la separación es de AUC 0,57-0,61. Eso es apenas mejor que una moneda, y el error se paga caro: si recargas en una caída que sigue, la pérdida de ese día se duplica y queda congelada en el candado.
2. **Lo poco que los modelos «ven» es el tipo de día, no el momento.** Y en cuanto al día, no le ganan a elegir días al azar (nulo de días al azar, p = 0,45-1,0).
3. **En la Big One no hay información temprana.** Durante las primeras 2 horas, un día bueno y uno malo se ven iguales (AUC 0,53-0,57).
4. **Las mejoras de 2025-26 en el Momentum son exposición extra en un buen período.** Lo prueba que el mismo modelo, validado igual, empeoró la cartera en 2022-24.

## 7. Veredicto y qué haría falta para cambiarlo

- **No implementar** ninguna recarga «en el mínimo» en el bot e2: ni con ML, ni con capitulación, ni con ticks.
- **No cortar** la base con el detector de día malo.
- **En vigilancia** (no es candidata):
  - el clasificador «fondo» GBDT al 98 % en el Momentum;
  - el desequilibrio de ticks en el Momentum.

  Para confirmarlos haría falta:
  1. **Al menos 12 meses más** de operaciones Momentum en demo (unas 120-150), con la señal registrada pero sin operarla.
  2. Que su R añadido le gane **a la vez** a una recarga en días al azar y a un lote mayor, con p < 0,01 sobre esas operaciones nuevas.
  3. Que **no** empeore el peor día.
  4. Para los ticks: un año de ticks del broker (hoy solo hay 10 meses) y un conteo de ticks que no se sature.
- Si el objetivo es ganar más en el Momentum, sigue valiendo lo del estudio anterior: subir su peso a conciencia. Los modelos de este estudio no lo hacen mejor que eso de forma estable.

## 8. Limitaciones

| Limitación | Efecto |
|---|---|
| 2022-2025 en velas M5 Dukascopy ajustadas al broker | Sin volumen ni ticks antes de 2026. Las reglas de microestructura solo se pudieron probar en 10 meses. |
| Resolución de 5 min en el lab principal | Una entrada en M1 podría quedar algo más cerca del fondo. Pero las reglas M1 de 2026 no mejoraron. |
| Pocas operaciones Momentum (228 en IS) | Los modelos para el Momentum tienen poca muestra. Las p de una sola variante son frágiles. |
| Modelos propios en numpy (no hay sklearn instalado) | GBDT sencillo, sin ajuste fino de hiperparámetros. Se fijaron de antemano para no sobreajustar. |
| La primera corrida de la logística tuvo un fallo (NaN en la tendencia s) | Se corrigió y se volvió a correr. Los resultados que se muestran son los corregidos. |
