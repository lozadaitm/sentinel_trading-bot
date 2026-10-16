# Auditoría del M5: gana poco muchas veces, pierde mucho pocas veces (2026-10-16)

**Pregunta del usuario:** las pocas operaciones perdedoras del M5 pesan más que las muchas ganadoras; ¿la suma da negativo?

**Alcance:**
- **Experimento 1:** 764 operaciones M5 de la cuenta base y los dos clones, del 6-ago al 11-sep. Fuente: `audit/mt5_positions_*.csv`.
- **Cuentas actuales:** 180 operaciones M5 de las cuentas de 1 000 $, 5 000 $ y 10 000 $, del 14 al 16-oct. Fuente: MT5 en modo solo lectura.
- Cada operación se cruzó con:
  - sus velas M1, para medir cuánto fue en contra (MAE) y a favor (MFE);
  - su línea «Entrada M5» del log, para leer el ADX y el RSI al entrar.

No es un backtest. Las «estimaciones» de la sección 4 son aritmética sobre las operaciones reales, con la precisión de una vela M1.

## 1. Resultado: la intuición es correcta, la suma es ≈ 0 o negativa

| | Operaciones | Acierto | Ganancia media | Pérdida media | Pérdida / ganancia | Acierto necesario para empatar | Neto |
|---|---|---|---|---|---|---|---|
| Experimento 1 | 764 | 85,1 % | +3,29 $ | −20,31 $ | 6,2× | 86,1 % | **−179,8 $** |
| Ahora | 180 | 88,3 % | +2,21 $ | −17,02 $ | 7,7× | 88,5 % | **−5,3 $** |

- **En movimiento de precio:** la ganadora media cobra **1,3 $/oz** y la perdedora media pierde **8,4–8,8 $/oz**.
- **El M5 necesita acertar 86–89 % solo para empatar,** y acierta 85–88 %. Vive en el filo: unas pocas pérdidas más o menos deciden el signo del mes.
- **Concentración:** en el experimento 1, las 10 peores operaciones (−463 $) borraron el 22 % de todo lo ganado (+2 135 $). Ahora, las 10 peores (−269 $) se comieron el 76 % de lo ganado (+352 $).
- **Costes:** comisión y swap suman −118 $ en el experimento 1, unos 0,15 $ por operación. Pesan, pero no son la causa.

## 2. Por qué: la asimetría está en la configuración de salida

| Pieza | Valor | Efecto |
|---|---|---|
| Stop inicial | `m5_sl_atr` 2 × ATR, con suelo `m5_hard_sl_points` 1 000 pt | Casi siempre manda el suelo: **10–11,4 $/oz** (mediana 10,5). |
| Trailing | arranca a +1 $ (`m5_trail_start` 100), distancia 0,5 $ (`m5_trail_dist` 50) | La ganadora se cierra entre +0,5 y +1,6 $/oz (mediana **1,0**). |
| TimeStop | 45 min, solo si va en rojo | Las perdedoras llegan a los 45 min ya hundidas, a −8,3 $/oz de mediana ahora. |

**Ganar 1 $ arriesgando 10 $** obliga a acertar más del 90 % antes de costes.

**Qué dicen las velas:**
- **Las ganadoras se cortan pronto.**
  - A favor llegan a **2,5 $/oz** de mediana, pero cobran **1,0**: el trailing devuelve más de la mitad del recorrido.
  - Duración: mediana 1,7 min; el 90 % cierra antes de 11 min.
- **Las perdedoras casi nunca van a favor.**
  - Su mejor momento es +0,6 $/oz de mediana, y solo 24 de 135 tocan +1 $.
  - Se hunden directamente: 10,6 $/oz en contra de mediana.
  - Una hora después de la entrada, el precio sigue en contra en 111 de 130 casos (mediana −7,7 $/oz). **Esperar más no las habría salvado.**
- **Por dónde salen las pérdidas:**
  - Experimento 1: stop −1 888 $ (73 operaciones) y TimeStop −427 $ (40).
  - Ahora: TimeStop −264 $ (16 operaciones) y stop −94 $ (5).

## 3. Lo que NO explica las pérdidas

- **El ADX y el RSI de entrada no separan ganadoras de perdedoras.**
  - Medianas de ganadoras: ADX 36,7 y RSI a favor 64,9.
  - Medianas de perdedoras: ADX 34,2 y RSI a favor 65,0.
  - La franja ADX 30–35, justo al entrar en régimen Surfer, sale peor (acierto 80 %, −178 $ por 0,01 lote, n = 265). Pero las franjas vecinas no siguen un patrón: lo trato como ruido hasta tener más datos.
- **Ni la dirección ni la racha.**
  - Compras y ventas cambian de signo entre los dos periodos.
  - Tras una pérdida se reabre en el mismo minuto, pero esa operación siguiente acierta igual que la media (85 % y 100 %).
- **La hora, con poca seguridad.**
  - En el experimento 1, las franjas de 14–16 h (−278 $) y 20–21 h de servidor (−164 $) fueron las peores.
  - En las cuentas actuales casi no hay operaciones en esas horas para confirmarlo.

**Dato aparte:** el M5 es en la práctica solo el **Surfer**: 939 de 944 operaciones. La reversión de rango (la mejora v2 de [[m5-range-regime-v2]]) casi nunca dispara.

## 4. Estimaciones (aritmética sobre operaciones reales, no backtest)

**Stop más corto: no ayuda.**

| Stop | Experimento 1 | Ahora |
|---|---|---|
| 10 $ (actual) | −180 | −5 |
| 4 $ | −256 | −30 |
| 6 $ | −195 | +6 |
| 8 $ | −349 | −35 |

El 25 % de las ganadoras va 3 $/oz o más en contra antes de ganar. Un stop corto las convierte en pérdidas.

**TimeStop más corto: ayuda algo, sin dar la vuelta.** La regla estimada: cerrar si a los T minutos va en rojo y el trailing aún no se armó.

| Regla | Experimento 1 | Ahora |
|---|---|---|
| Actual (45 min) | −180 | −5 |
| 10 min | −13 | +24 |
| 15 min | −100 | +54 |
| 30 min | −188 | +84 |

Con 10 minutos mejora en los dos periodos. A partir de 15 minutos, los dos periodos se contradicen.

**Trailing más holgado** (dejar correr hacia los 2,5 $/oz que sí alcanzan las ganadoras): es la palanca con más margen. No se puede estimar con esta aritmética porque depende del camino del precio. Medirlo exigiría reproducir las operaciones vela a vela, es decir, un backtest, que solo se hace si el usuario lo pide.

## 5. Conclusión

1. **El M5 no tiene ventaja.** En 944 operaciones queda en ≈ 0 o algo negativo: −185 $ en total, con un lote de 0,01–0,04.
2. **El problema es la proporción entre salidas,** no las entradas:
   - un trailing que cobra 1 $/oz;
   - un stop o TimeStop que pierde 8–10 $/oz.
3. **No hay un parámetro único que lo arregle con seguridad** con los datos de hoy. Las palancas, de más a menos prometedora:
   - **(a) trailing más holgado:** requiere medición vela a vela;
   - **(b) TimeStop corto,** de unos 10 min, si no se armó el trailing;
   - **(c) apagar o reducir el M5:** su aporte al resultado de la cuenta es marginal frente al M15.
4. **Ningún cambio se aplica sin diseño aprobado por el usuario.**

## 6. Backtest de salidas sobre las entradas reales (pedido por el usuario el 2026-10-16)

### Qué es el trailing hoy

**Puntos fijos, no dinámico.** Está en `bot/strategy_m5.py::_manage_exits`, y los valores en vivo son los mismos en todas las filas de `bot_config`:
- arranca a **+100 pt (1 $)** y sigue a **50 pt (0,5 $)**;
- desde +300 pt (3 $) se separa a 150 pt (1,5 $);
- solo el stop inicial usa el ATR (2 × ATR, con suelo de 10 $).

**Escala:** el ATR(14) del M5 en la entrada vale 3,3 / **4,9** / 7,2 $ (percentiles 10, 50 y 90). El trailing actual arranca a unos 0,2 ATR y sigue a unos 0,1 ATR.

### Método

1. **Entradas:** las 944 reales (hora, precio, lote, comisión).
2. **Precio:** ticks reales del broker, leídos del terminal en solo lectura y resumidos por segundo (bid y ask: mínimo, máximo y último).
3. **Salida:** se repite el `_manage_exits` actual, cambiando solo los parámetros de salida:
   - stop inicial de siempre;
   - TimeStop de 45 min si va en rojo;
   - `stops_level` 20 + 20 pt;
   - paso de 10 pt.
4. **Una posición viva por cuenta:** si la salida simulada dura más, se saltan las entradas reales que caen mientras sigue abierta.
5. **Calibración:** con la configuración actual, el simulador reproduce el 85–89 % de las salidas reales con un margen de ±0,30 $/oz.
   - Las diferencias son casos frontera: el precio toca +1,0–1,1 $ y el bot real no llega a armar el trailing.
   - El error absoluto es de unos ±100 $ en el experimento 1, así que **se compara cada variante contra la base simulada con el mismo motor**.
   - Se repitió con un retraso del bucle de 1, 2 y 5 s.

**Límites:**
- No se pueden inventar las entradas que el bot no tomó por tener una posición abierta.
- Se ignoran la memoria de racha del Surfer y el swap.
- Son 5 semanas y 6 cuentas: s32–s34 de agosto, s37 de septiembre y s42 de octubre.

### Resultado: el trailing holgado y proporcional al ATR gana con claridad

Cifras en $ por cada 0,01 lote, para que las cuentas de tamaños distintos pesen igual:

| Variante (múltiplos del ATR del M5) | s32 | s33 | s34 | s37 | s42 | Total |
|---|---|---|---|---|---|---|
| **Actual** (1 $ / 0,5 $; turbo 3 $ / 1,5 $) | −11,9 | −11,1 | +5,6 | −40,8 | +28,3 | **−30,0** |
| **Propuesta:** arranca a 0,5 ATR, sigue a 0,3 ATR; desde +1,25 ATR se aprieta a 0,15 ATR | −5,6 | +55,3 | +55,2 | −35,2 | +77,8 | **+147,5** |

**No es un pico de casualidad:**
- Se probaron las 72 combinaciones vecinas:
  - arranque 0,4 / 0,5 / 0,6 ATR;
  - distancia 0,25 / 0,30 / 0,35 ATR;
  - turbo desde 0,8 / 1,0 / 1,25 ATR;
  - turbo a 0,15 / 0,20 / 0,25 ATR.
- **Las 72 superan a la configuración actual:** entre +7,5 y +171 por 0,01 lote, con mediana +85.
- La propuesta es la única de las mejores que mejora **las 5 semanas**.

**Trailing fijo más ancho:**
- 5 $ / 2,5 $ también mejora, hasta +102.
- Pero empeora la cuenta de 1 000 $ y es peor que la versión por ATR.

**Cierre a los 10 min si no se armó el trailing:** casi siempre empeora con el trailing holgado. Se descarta.

### Ficha de la propuesta (en $ reales, retraso del bucle de 2 s)

| | Actual: experimento 1 | Propuesta: experimento 1 | Actual: ahora | Propuesta: ahora |
|---|---|---|---|---|
| Operaciones | 703 | 411 | 160 | 93 |
| Acierto | 85 % | 73 % | 89 % | 74 % |
| Ganancia media | 3,33 $ (1,39 $/oz) | 7,78 $ (3,17 $/oz) | 2,19 $ (1,31 $/oz) | 5,84 $ (3,42 $/oz) |
| Pérdida media | −19,91 $ (−8,34 $/oz) | −17,79 $ (−7,53 $/oz) | −15,92 $ (−8,80 $/oz) | −11,26 $ (−6,35 $/oz) |
| Pérdida / ganancia | 6,0× | 2,4× | 6,7× | 1,9× |
| **Neto** | −28 $ | **+307 $** | +43 $ | **+133 $** |
| Caída máxima | −245 $ | −377 $ | −90 $ | −70 $ |
| Duración mediana | 3 min | 9 min | 2 min | 11 min |

- **Con retraso de 1 s y 5 s,** la propuesta queda entre +277 y +345 $ en el experimento 1 y entre +86 y +182 $ ahora. La base queda entre −72 y −11 $, y entre +31 y +58 $.
- **Cambia el carácter del M5:**
  - acierta menos (73 % frente a 85 %);
  - cada ganancia vale más del doble;
  - hace la mitad de operaciones y paga menos comisión.
- **La caída máxima del experimento 1 empeora** (−377 $ frente a −245 $). La de ahora mejora.
- **El stop inicial no cambia.** Las pérdidas siguen siendo de unos 6–8 $/oz, pero ahora las paga una ganancia de 3+ $/oz en vez de 1,3.

### Qué haría falta para aplicarlo

Esto es solo una propuesta: **no se toca código sin diseño aprobado**.

- **Parámetros nuevos** en `bot_config`, con su migración:
  - `m5_trail_mode` (`points` | `atr`);
  - `m5_trail_start_atr` 0,5;
  - `m5_trail_dist_atr` 0,3;
  - el turbo, en ATR: 1,25 → 0,15.
- **El ATR en vivo** sería el mismo `self.atr1` que ya calcula el M5 (vela cerrada).
- **Volver atrás** es poner `m5_trail_mode = points`, sin tocar código.

## 7. Segunda pasada sobre el M5 (pedida por el usuario el 2026-10-16)

Mismo motor de la sección 6. Todo se compara contra la **propuesta** (trailing ATR 0,5 / 0,3, turbo 1,25 → 0,15). Cifras en $ por cada 0,01 lote.

### 7.1 Proyectar un precio objetivo según la entrada

Se calculó, para cada entrada, el siguiente techo o suelo confirmado en la dirección de la operación (fractales de M5, M15 y H1), y además objetivos por volatilidad (1, 1,5, 2 y 3 ATR del M15).

| Uso del objetivo | Total | Semanas ≥ propuesta |
|---|---|---|
| Propuesta, sin objetivo | **147,5** | — |
| Techo/suelo M15: apretar al llegar | 19 a 31 | 0–1 de 5 |
| Techo/suelo M15: cerrar en el objetivo | −33 | 0 de 5 |
| Techo/suelo H1: apretar al llegar | 32 a 60 | 1–3 de 5 |
| Techo/suelo H1: cerrar en el objetivo | −2 | 1 de 5 |
| 1 ATR(M15): apretar al llegar | 158 | 5 de 5 |
| 1,5–3 ATR(M15): apretar o cerrar | 134 a 151 | 2–5 de 5 |

- **El objetivo por estructura empeora.** El M5 opera casi siempre en modo tendencia (Surfer), y en tendencia el precio atraviesa esos niveles. Cortar ahí recorta justo las mejores operaciones.
- **El objetivo por volatilidad empata.** La propuesta ya proyecta: su segunda fase («desde +1,25 ATR, aprieta a 0,15 ATR») es una proyección por ATR. Usar 1 ATR del M15 da +10, que es ruido.
- **Como filtro de entrada tampoco sirve.** Saltarse entradas con poco recorrido hasta el siguiente nivel no ayuda: los resultados por tramo de recorrido no siguen ningún patrón. En H1, incluso salen peor las que tienen más recorrido.

**Conclusión:** proyectar el objetivo no aporta nada sobre la propuesta.

### 7.2 Otras palancas probadas

| Variante, sobre la propuesta | Total | Semanas ≥ propuesta | Comentario |
|---|---|---|---|
| Stop 2 ATR **sin** el suelo de 10 $ | 179,9 | 4/5 | Mejora o empata en las 6 cuentas y con retraso de 1, 2 y 5 s. Peor racha −102 frente a −119. |
| Stop 1,5 ATR | 77 | 1/5 | Peor. |
| Stop 2,5–3 ATR | 132–135 | 2/5 | Peor. |
| Stop en la estructura M15 | 136 | 3/5 | Peor. |
| TimeStop 20 min | 94 | 2/5 | Peor. |
| TimeStop 30 / 60 min | 184 / 177 | 3/5 | Irregular. |
| **TimeStop 90 min** | 222,7 | 4/5 | Mejora en las 6 cuentas y con los 3 retrasos. Peor racha −94. La pérdida media sube de 7,3 a 9,6 $/oz. |
| Sin TimeStop | 230,6 | 4/5 | Parecido a 90 min, con pérdidas aún más grandes. |
| **Stop 2 ATR + TimeStop 90** | 224,1 | — | Mejora o empata en las 6 cuentas. Peor racha **−80**. Pérdida media 8,4 $/oz. |
| Sin las horas 14–16 y 20–21 | 129 | 3/5 | Peor. Se descarta. |
| Sin ADX 30–35 | 205 | 3/5 | Solo 373 operaciones; irregular. Sospecha de sobreajuste. |
| Filtros de RSI o de ATR | 27–160 | 2–4/5 | Sin mejora estable. |

**Lectura:**
- La palanca principal sigue siendo el **trailing por ATR**.
- El stop en 2 ATR sin suelo y el TimeStop de 90 min son mejoras **secundarias**.
  - Ya existen como configuración (`m5_hard_sl_points` y `m5_max_trade_min`), así que se aplican sin tocar código.
  - Conviene aplicarlas **después** del trailing, una cosa cada vez, para poder atribuir cada efecto.
- **El TimeStop largo hace cada pérdida algo más grande,** aunque haya menos pérdidas.

## 8. ¿Aplica al M15? (Op1 y vigilancia de la Op2)

**Medición, no backtest del ciclo.** Son 190 Op1 reales, del 6-jul al 14-oct, con velas M1. Las otras 212 Op1 del historial no tienen velas M1 en el terminal.

### 8.1 La Op1 sola tiene la misma asimetría que el M5

- **Cómo sale hoy:** la cesta se arma a **+0,83 $/oz** (`basket_arm_move_usd`) y cierra al retroceder **0,1 ATR** (`retrace_atr_mult`, mínimo 0,11 $). Los valores en vivo son los mismos en todas las filas.
- **El smart trail de la Op1** (arranca a 1 ATR y sigue a 1,5 ATR) solo pone stop por encima de la entrada a partir de +1,5 ATR. Casi nunca actúa antes que la cesta.
- **Cobro real de las Op1 en verde** (396 cerradas, experimento 1): mediana **1,5 $/oz**, a los **3 minutos**.
- **Recorrido a favor antes de llegar a la cobertura:** mediana **1,45 ATR(M15)**, unos 11 $.
  - El 63 % llega a +1 ATR;
  - el 50 % llega a +1,5 ATR;
  - el 25 % llega a +3 ATR.

### 8.2 Un trailing más holgado en la Op1 tiene un precio: más ciclos

Simulación de la Op1 sola hasta que cierra en verde o hasta que salta la Op2. Velas M1, con orden pesimista: dentro de cada vela, primero lo adverso.

| Salida de la Op1 | Cierra en verde | Cobro medio | Total cobrado | Termina en Op2 (ciclo) |
|---|---|---|---|---|
| Actual (cesta) | 88 % | 3,5 $/oz | 589 $/oz | **12 %** |
| ATR(M15) 0,5 / 0,3 | 77 % | 6,6 | 972 | 23 % |
| ATR(M15) 1,0 / 0,5 | 61 % | 11,2 | 1 284 | 39 % |
| ATR(M15) 1,5 / 0,75 | 47 % | 14,9 | 1 328 | 53 % |

- El trailing holgado **duplica lo cobrado**, pero también **duplica o triplica las Op1 que acaban en ciclo** (Op2, recoveries y candado).
- El ciclo es la parte cara: el del 14-oct lleva unos −2 000 $ flotantes en la cuenta de 10 000 $.
- **Para saber si compensa** hay que conocer el coste medio de un ciclo, y eso solo lo da un backtest del ciclo completo. El arnés existente cierra por vela.
- **Cuenta orientativa:**
  - la variante 0,5 / 0,3 gana +383 $/oz a cambio de 20 ciclos más;
  - compensa solo si cada ciclo cuesta menos de unos 19 $/oz;
  - la Op2 sola ya congela unos 15,6 $/oz (mediana de `hedge_dist`).
- **No hay evidencia suficiente para el M15.** No se propone cambio.

### 8.3 Vigilancia de la Op2: ¿salta antes de tiempo?

Regla actual: la cobertura salta a **max(8 $, 2 × ATR(M15))**; mediana 15,6 $.

- El 97 % de las Op1 que no se cierran antes llega a esa distancia, tras unos 194 min de mediana.
- **Tras saltar la cobertura, el precio sigue en contra de mediana 3,8 veces esa distancia** en las 24 h siguientes (p90: 6 veces).
- Aun así, en el 72 % de los casos el precio vuelve a la entrada dentro de esas 24 h.

**¿Ayuda esperar a que se rompa la estructura** (el suelo o techo M15 que invalida la entrada)?

| Al tocar la cobertura | Casos | Vuelve a la entrada en 24 h | Peor recorrido en contra después |
|---|---|---|---|
| Estructura ya rota | 93 | 67 % | 4,3 veces la distancia |
| Estructura intacta | 92 | 77 % | 3,3 veces la distancia |

- La estructura apenas distingue los casos.
- **Con la estructura intacta, el precio sigue yendo 3,3 veces la distancia en contra.** Retrasar la Op2 hasta que se rompa la estructura habría dejado la Op1 desnuda en recorridos muy grandes.

**Conclusión:** con estos datos, la Op2 no salta antes de tiempo. Congela pérdidas que de otro modo se multiplicarían por 3–4 antes de volver. El problema del ciclo está en lo que pasa después de la Op2 (recoveries y cola), no en el disparo.
