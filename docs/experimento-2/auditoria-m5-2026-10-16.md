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

- **Tres parámetros nuevos** en `bot_config`, con su migración:
  - `m5_trail_mode` (`points` | `atr`);
  - `m5_trail_start_atr` 0,5;
  - `m5_trail_dist_atr` 0,3;
  - el turbo, en ATR: 1,25 → 0,15.
- **El ATR en vivo** sería el mismo `self.atr1` que ya calcula el M5 (vela cerrada).
- **Volver atrás** es poner `m5_trail_mode = points`, sin tocar código.
