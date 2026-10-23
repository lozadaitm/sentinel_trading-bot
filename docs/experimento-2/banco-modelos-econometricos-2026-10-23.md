# Banco de modelos econométricos por aspecto del bot (23-oct)

Idea del usuario: no buscar un solo modelo que prediga el precio, sino un modelo por cada
aspecto del bot. Cada modelo responde una pregunta concreta y alimenta una decisión
concreta: lote, distancias, horario, régimen o salida.

**Criterio para aprobar un modelo:** lo que encuentra en 2021–23 tiene que repetirse en
2024–26, con el mismo signo y con |t| > 2 (o un R² positivo fuera de muestra).

**Estado:**
- ✅ = tiene poder y sirve.
- ❌ = no tiene poder.
- ⏳ = pendiente.
- 🔬 = en curso.

## A. Dirección (¿hacia dónde va?)

| # | Modelo | Pregunta | Alimenta | Estado |
|---|---|---|---|---|
| A1 | Regresión macro (MCO + Newey-West): dólar, tasas reales, inflación esperada, VIX, petróleo, Fed | ¿Qué mueve al oro el mismo día y qué predice el siguiente? | Filtro de dirección | ❌ Explica el 20–39 % del mismo día; 0 de 175 predictores se sostienen |
| A2 | Ridge con todo (macro, COT, cruzados, técnico) | ¿Combinados predicen? | Filtro de dirección | ❌ R² fuera de muestra < 0 en los 5 horizontes |
| A3 | Corrección de error oro-plata (cointegración) | ¿Un desvío del oro frente a la plata se corrige? | Señal de reversión | ❌ Desvío casi sin reversión (vida media ~4 años); sin poder a 1 ni a 5 días |
| A4 | Estacionalidad de calendario (hora, día, reapertura) | ¿Hay horas con deriva? | Big One | ✅ Reapertura 01:00 compradora en todos los estados |
| A5 | Momentum de serie temporal (1–3 meses) | ¿La tendencia mensual continúa? | Tamaño según tendencia | ⏳ Positivo pero t ≤ 1,3 (ronda 2) |
| A6 | Granger intradía con DXY, bono y plata (M5) | ¿Algún mercado se adelanta al oro? | Entrada | ❌ Reglas leadlag sin ventaja (ronda 5) |

## B. Volatilidad (¿cuánto se va a mover?)

| # | Modelo | Pregunta | Alimenta | Estado |
|---|---|---|---|---|
| B1 | HAR (volatilidad realizada de 1, 5 y 22 días) | ¿Cuánto se moverá hoy? | Lote, candado, distancia de cobertura | ✅ R² fuera de muestra 0,54 (ATR: 0,28) |
| B2 | Perfil horario de la volatilidad | ¿A qué hora se mueve más? | Lote/distancia por hora, horario del M5 | ✅ Perfil estable (correlación 0,94 entre tramos) |
| B3 | Estudio de eventos (NFP, IPC, FOMC) | ¿Cuánto dura el golpe de la noticia? | Ventanas de bloqueo del NewsGuard | ✅ Golpe ×5–8 en el minuto 0; dura 30–60 min (IPC/NFP) y ~3 h (FOMC) |
| B4 | HAR horario + estacionalidad | ¿Volatilidad de la próxima hora? | Trailing y distancias del M5 y de las Op | ✅ R² fuera de muestra 0,55 (tipo ATR: 0,37) |

## C. Riesgo de cola (¿cuánto puede ir en contra sin stop?)

| # | Modelo | Pregunta | Alimenta | Estado |
|---|---|---|---|---|
| C1 | Cuantiles extremos e índice de cola (Hill) de la excursión en contra | ¿Cuánto puede ir en contra en 4 h a 10 días, en ATR? | **Lote máximo sin quemar** con un diseño sin stop | ✅ Tabla de cuantiles: sin stop, el lote alto es inviable |
| C2 | Teoría de valores extremos condicionada a la volatilidad prevista | ¿Se ensancha la cola en régimen agitado? | Lote dinámico | ❌ La cola medida con volatilidad prevista no es más fina que con el ATR diario |

## D. Geometría de salida (¿dónde poner objetivo y cobertura?)

| # | Modelo | Pregunta | Alimenta | Estado |
|---|---|---|---|---|
| D1 | Probabilidad de tocar +a antes que −b frente al azar b/(a+b) | ¿Alguna relación objetivo/cobertura le gana al azar? | TP de la Op1 y distancia de la Op2 | ❌ Igual al azar ±2 puntos en todas las geometrías |
| D2 | Modelo de duración (riesgo por tiempo) de las operaciones | ¿Cuándo deja de convenir mantener una operación abierta? | TimeStop del M5 (su mayor pérdida) | ❌ Frente al azar emparejado, la ventaja diaria es negativa o nula a 1–12 h. El «indicio» era deriva del oro |

## E. Régimen (¿qué lógica usar hoy?)

| # | Modelo | Pregunta | Alimenta | Estado |
|---|---|---|---|---|
| E1 | Razón de varianzas por horizonte, sesión, tendencia y volatilidad | ¿El oro sigue tendencia o revierte a 15 min / 1 h / 4 h / 1 día? | Lógica del M5 (surfer o scalper) y de la Op1 | ❌ Paseo al azar en 15 min–1 día (VR ≈ 1). Única señal estable: los días de volatilidad baja siguen un poco la tendencia (VR 1,06–1,07, z ≈ 2) |
| E2 | Markov de dos estados (calma/agitado) | ¿El régimen es persistente y cambia la lógica ganadora? | Interruptor de modo | ❌ Persistente (calma ~30 d, agitado ~18 d), pero no cambia la lógica ganadora de forma estable |

## F. Ejecución y costos

| # | Modelo | Pregunta | Alimenta | Estado |
|---|---|---|---|---|
| F1 | Spread y deslizamiento por hora (ticks reales del demo) | ¿Cuánto cuesta entrar a la 01:00? | Viabilidad de la Big One | ⏳ Requiere medir en demo: las velas no traen spread |
| F2 | Swap y noches mantenidas | ¿Cuánto cuesta aguantar un ciclo congelado? | Op2 Hedge Lock | ✅ Ya incluido en las simulaciones |

## G. Cartera

| # | Modelo | Pregunta | Alimenta | Estado |
|---|---|---|---|---|
| G1 | Remuestreo por bloques mensuales (P de duplicar / P de caída) | ¿Qué riesgo por operación es «agresivo pero estable»? | % de riesgo | ✅ (`kelly_bigone`, `bigone_plus`) |
| G2 | Kelly con incertidumbre del estimador | ¿Cuánto recortar el riesgo porque el R medio es incierto? | % de riesgo | ✅ Kelly ≈ 10,5 % (p10 6 %); un cuarto de Kelly ≈ 2,6–3 % |

Scripts: `bot_backtesting/fullsim/econ_build.py`, `econ_model.py`, `econ_bank.py`.

## Resultados

**M1: razón de varianzas.** VR(q) de Lo-MacKinlay sobre retornos M5. VR > 1 = tendencia; VR < 1 = reversión.

| Horizonte | VR 2021–23 (z) | VR 2024–26 (z) |
|---|---|---|
| 15 min | 0,98 (−1,5) | 1,01 (+1,3) |
| 1 h | 0,97 (−1,0) | 1,02 (+0,6) |
| 4 h | 0,95 (−1,2) | 0,98 (−0,5) |
| 1 día | 0,96 (−0,7) | 1,06 (+0,6) |

- Por sesión, tendencia y volatilidad, solo se repite en los dos tramos el grupo de **volatilidad prevista baja**: VR(1 h) de 1,06 y 1,07, con z de 1,9 y 2,3.
- La reversión de Londres (z −3,5) y la de días agitados (z −3,4) aparecen solo en 2021–23.
- **Para el M5:** la lógica de tendencia (surfer) tiene un pequeño fundamento solo en días tranquilos, y la de reversión (scalper) no tiene ninguno estable. El efecto (~3 % de autocorrelación) es chico frente al costo.

**M2: volatilidad por hora** (|retorno de 5 min| relativo al promedio del día, 2024–26):
- Máxima de 15 a 17 h servidor (×1,45–1,67).
- Mínima a las 23 h (×0,59) y entre las 06 y 07 h (×0,70–0,74).
- Las horas 01–02 están en ×0,77–0,82.
- Correlación del perfil entre tramos: 0,94.
- Sirve para escalar distancias y lote por hora.

**M3: excursión en contra máxima**, en múltiplos del ATR diario previo (entradas cada hora):

| Horizonte | p50 | p99 | p99,9 | Máximo |
|---|---|---|---|---|
| 4 h | 0,14 | 0,96–1,04 | 1,6–1,9 | 4,6 |
| 1 día | 0,40 | 2,0–2,2 | 3,1–3,8 | 6,3 |
| 3 días | 0,7–0,8 | 4,0 | 5,8–8,8 | 10,5 |
| 10 días | 1,2–1,6 | 7,6–9,2 | 9,2–11,0 | 11,9 |

Ejemplo: con un ATR diario de 60 $, una posición sin stop mantenida 10 días puede ir hasta ~660 $/oz en contra (p99,9). Eso son 660 $ por cada 0,01 lote, es decir, el 13 % de una cuenta de 5 000 $ por cada 0,01. **El lote alto solo es posible con un límite de pérdida o un candado.** Con un candado a 1–3 ATR M15, el riesgo queda acotado y el lote puede crecer.

**M4: geometría.** La probabilidad de tocar +a antes que −b es igual a la del azar b/(a+b), con ±2 puntos, para todas las relaciones probadas (1:1, 1:2, 1:3, 2:1, 3:1, 0,5:2,5, 2:2), en compra y en venta. En 2024–26 la compra lleva ~+1,5 puntos por la subida del oro. **No hay relación objetivo/cobertura que gane por sí sola.**

**M8: eventos.** |Retorno de 5 min| frente a la misma hora sin evento:
- IPC y NFP: ×4,6–5,0 en el minuto 0 y ×1,5–2,5 hasta ~30–60 min.
- FOMC: ×7,8 en el minuto 0, y entre ×2 y ×4,6 hasta ~3 h.
- Ventanas sugeridas: IPC/NFP de −15 a +60 min; FOMC de −5 a +180 min.

**D2: duración del M5.**
- Las entradas reales del M5 cerradas a tiempo fijo dan ≈ 0 de 5 a 120 min.
- A 4–8 h dan +0,13/+0,25 $/oz bruto (t 1,6–2,3). Todavía no se comparó con entradas al azar.
- En el bot, el TimeStop (63 min de media) deja −2,30 $/oz y el Trail +1,45.
- **Pista:** el TimeStop corta demasiado pronto. Falta compararlo con el azar antes de creerlo.

**C2: colas en unidades de volatilidad prevista.** El p99 a 1 y 5 días no es más estable medido con HAR que con el ATR diario, y la relación con el tercil de volatilidad tiene forma de U. Para el lote máximo sin quemar, se usa la tabla de M3.

### Big One mejorada (`bigone_plus.py`)

**Método:**
- Validación móvil 2023–2026, salida elegida con los dos años anteriores.
- Remuestreo de meses: 12 meses, 2 000 caminos.
- **Corrección:** la escala del candado usa ahora el ATR de la vela **anterior**. Antes incluía la vela de entrada, lo que era mirar adelante. Con eso la base baja de +0,178 a +0,145 R.

| Variante | Riesgo | Ops/mes | R/op | Mes mediano | P(mes ≥ 30 %) | P(2x en 12 m) | P(caída ≥ 50 %) | Real 2023–26 (×, caída) |
|---|---|---|---|---|---|---|---|---|
| base (ATR) | 2 % | 14,6 | 0,145 | +3,8 % | 3 % | 24 % | 1 % | ×4,4, 39 % |
| base (ATR) | 3 % | 14,6 | 0,145 | +5,5 % | 8 % | 46 % | 6 % | ×8,3, 52 % |
| **HAR** | 2 % | 14,6 | **0,202** | +4,5 % | 3 % | **41 %** | 0,3 % | ×7,4, 37 % |
| **HAR** | 3 % | 14,6 | 0,202 | +6,8 % | 18 % | **57 %** | 8 % | ×16,5, 50 % |
| HAR + eventos ×0,5 | 3 % | 14,6 | 0,202 | +5,8 % | 13 % | 60 % | 6 % | ×17,5, 48 % |
| HAR + eventos ×0,5 | 5 % | 14,6 | 0,202 | +9,8 % | 28 % | 69 % | 47 % | ×64, 68 % |
| + días neutros ×0,5 | 3 % | 19,1 | 0,157 | +3,8 % | 16 % | 58 % | 5 % | ×21,5, 48 % |
| + todos los días ×0,5 | 3 % | 21,3 | 0,140 | +4,8 % | 13 % | 57 % | 6 % | ×22,5, 48 % |
| + pirámide a +1 escala | 3 % | 19,1 | 0,193 | +3,2 % | 23 % | 58 % | **46 %** | ×28,9, 79 % |
| + pirámide a +1,5 | 3 % | 19,1 | 0,171 | +0,5 % | 23 % | 57 % | 30 % | ×24,8, 64 % |

**Lectura:**
1. **La volatilidad prevista (HAR) es la mejora real.** Sube el R por operación de 0,145 a 0,202 (+39 %). A 2 % de riesgo, P(duplicar en 12 meses) pasa de 24 % a 41 % sin más riesgo de caída.
2. **Reducir el riesgo en días de evento** recorta un poco la caída y apenas cambia la ganancia. Conviene.
3. **Días neutros y bajistas a medio riesgo:**
   - suman ~5–7 operaciones al mes, pero con menos R por operación;
   - el total histórico mejora (×21 frente a ×17) y la probabilidad a 12 meses queda igual;
   - aporte marginal.
4. **La pirámide (Op2 como segunda entrada a favor) empeora:** más meses de +30 %, pero la probabilidad de caer a la mitad se multiplica (46 % frente a 5 % a 3 %). Se descarta.
5. **Punto óptimo «agresivo pero estable»: HAR + eventos ×0,5 al 3 %.** Mes mediano +6 %, 13 % de meses ≥ +30 %, 60 % de duplicar en 12 meses y 6 % de caer a la mitad. En la historia real 2023–26 la caída máxima, contando el flotante, fue del 48 %. Esos años fueron alcistas y la ejecución a la 01:00 no está medida.

### Segunda tanda (`econ_bank2.py`)

**B4: volatilidad de la próxima hora.** R² fuera de muestra 2024–26:

| Predictor | R² |
|---|---|
| media de 3 h (como un ATR) | 0,37 |
| media de 3 h ajustada por la hora del día | 0,47 |
| HAR horario (1 h, 3 h, 24 h, 120 h) | 0,50 |
| **HAR horario + perfil por hora** | **0,55** |
| + HAR diario | 0,55 |

Para el trailing, las distancias de las Op y el M5, conviene usar «HAR horario × perfil por hora» en vez del ATR. Predice un 50 % mejor.

**D2b: el TimeStop del M5 contra el azar** (entradas reales del M5 mantenidas k min frente a 3 entradas al azar a la misma hora y del mismo lado):
- La ventaja media por operación es de +0,01 a +0,42 $/oz.
- Agrupada por día, la t es negativa o ≈ 0 (de −3,7 a +0,1).
- La mejora a 4–8 h de D2 era la deriva del oro, no las entradas. **Alargar el TimeStop no arregla el M5.**

**E2: régimen calma/agitado** (HMM de 2 estados sobre la volatilidad diaria, entrenado en 2021–23 y filtrado sin mirar adelante):
- Calma: 0,71 % diario, dura ~30 días en promedio. Agitado: 1,00 % diario, dura ~18 días.
- **Big One (HAR):** gana en los dos regímenes.

  | Régimen | 2023 | 2024 | 2025 | 2026 |
  |---|---|---|---|---|
  | Agitado | +0,22 | −0,10 | +0,32 | +0,04 |
  | Calma | +0,18 | +0,32 | +0,17 | — |

  No hace falta filtro.
- **M5:** el surfer pierde bruto en los dos regímenes. El scalper tiene muy pocas operaciones.
- **VR(1 h):** en calma hay tendencia solo en 2024–26 (z +2,5); en agitado hay reversión solo en 2021–23 (z −3,0). **No es estable.** Cambiar de modo según el régimen no tiene base.

**G2: Kelly con incertidumbre** (Big One, crecimiento logarítmico, remuestreo por meses):

| Variante | R medio | Kelly | p10 / p25 del remuestreo | Kelly por año (2023 / 2024 / 2025 / 2026) |
|---|---|---|---|---|
| base | +0,145 | 11,5 % | 5,5 / 8,5 % | 39,5 / 20,0 / 9,5 / 0,5 % |
| HAR + eventos | +0,203 | 10,5 % | 6,0 / 7,5 % | 39,5 / 6,5 / 11,5 / 3,0 % |

**3 % de riesgo ≈ un cuarto de Kelly ≈ el Kelly completo del peor año (2026).** Es el techo prudente. Pasar del 5 % ya sería superar a la mitad del Kelly del remuestreo pesimista.

### Hallazgos acumulados para el diseño completo

1. **Dirección:** solo la reapertura asiática (01:00) tiene ventaja. Nada macro, técnico, SMC, de régimen ni de geometría predice la dirección.
2. **Volatilidad:**
   - el HAR diario predice el día;
   - el HAR horario × perfil por hora predice la próxima hora;
   - los dos sustituyen al ATR para el lote, el candado, el trailing y las distancias.
3. **Noticias:** riesgo reducido; ventanas de IPC/NFP de −15 a +60 min y de FOMC de −5 a +180 min.
4. **Riesgo de cola:** sin candado, el lote tiene que ser mínimo (p99,9 ≈ 11 ATR diarios en 10 días). Con candado, el lote sale del % de riesgo.
5. **Tamaño:** 3 % por operación en la Big One (un cuarto de Kelly).
6. **M15/M5:** sin ventaja en ningún régimen, horizonte ni geometría. Su papel posible es secundario (lote mínimo) o ninguno.
