# Prompt de arranque — optimización de rentabilidad e2 (2026-10-27)

Copiar y pegar en una sesión nueva de Claude Code abierta en
`C:\Users\Administrator\Documents\sentinel_trading`.

---

Estamos en la rama `experimento-2-rediseno`. En esta máquina corren **en vivo** 3 bots e2 (`bot.lite_e2`, magic 100300) sobre cuentas DEMO de 3 000, 10 000 y 25 000 USD, más el `news_exporter`. Soy vibecoder: háblame en español y en lenguaje llano, con tablas cortas y una recomendación clara.

## Reglas que no se rompen

- **No reinicies bots ni lances `restart_all`** hasta que yo apruebe un cambio de código, y el permiso es para cada ocasión.
- **MT5 solo en lectura**, contra los terminales ya abiertos, y solo lecturas ligeras con el mercado abierto. Para investigar usa los datos ya descargados; si hace falta descargar más del broker, pregúntame antes.
- **Sin stop loss, sin cierre de emergencia y sin freno por caída de la cesta.**
  - Permitido: el **Hedge Lock (candado)**, las salidas por hora y las salidas en ganancia, como TP o trailing que solo cierra en positivo.
  - Si una idea necesita cerrar en pérdida de otra forma, propónmela aparte y explícame por qué; no la asumas.
- **Repositorio público.**
  - Nada de datos crudos, emails, números de cuenta, UUIDs ni secretos en lo que se commitea.
  - Nunca imprimas valores de `.env`.
  - No commitees CSV de logs, `instances/*`, `.env` ni pickles.
  - Haz stage solo de tus archivos; nunca `git add -A` ni `commit -a`.
  - Trailer de commit: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Simulaciones a prioridad baja** (BELOW_NORMAL), con **3 procesos pesados como máximo a la vez**, porque los bots en vivo comparten la máquina.
- **Dónde se guarda cada cosa.**
  - Hallazgos: `docs/experimento-2/`.
  - Decisiones: `docs/memory/` (archivo, más su pointer en `MEMORY.md`, más commit).
  - Scripts: `bot_backtesting/fullsim/`.
- **Autorizaciones.** Te autorizo a usar un workflow multiagente o subagentes en paralelo para esta investigación, a instalar con `pip` los frameworks que hagan falta y a darte de alta en APIs gratuitas o de prueba. Si una API es de pago, pregúntame antes, con el precio.

## Lee primero

1. `docs/memory/MEMORY.md`, entero, y las memorias que enlaza. En especial:
   - `e2-recargas-descartadas`;
   - `broker-sesion-trading-0101`;
   - `pendientes-e2`;
   - `bot-design-constraints`.
2. El diseño vigente: `docs/experimento-2/diseno-bot-tres-patas-2026-10-25.md`.
   - **Big One:** compra a las 01:01 y sale a las 10:00.
   - **Momentum:** opera de 15:00 a 21:00 en la dirección del movimiento 01:00→15:00.
   - **NFP.**
   - **Gestión:** escalera de 3 tercios con TP a 2 y 3 × ATR15, candado a −1 × ATR_D y riesgo del 8 %.
3. Lo que ya se probó y **no pasó**. No lo repitas igual; si vuelves a algo, di qué cambia.
   - `docs/experimento-2/banco-patrones-velas-2026-10-26.md` y `investigacion/patrones-*`: patrones de velas, geométricos y formas sin nombre (más de 330 000 variantes).
   - `investigacion/recargas-minimo-2026-10-27.md`, `deteccion-minimo-2026-10-27.md` y `reentrada-confirmacion-2026-10-27.md`: recargar en el mínimo, ML del fondo y reentrar al volver a la entrada. Nada le gana a un lote mayor ni al azar.
   - `investigacion/riesgo-maximo-2026-10-27.md`: el margen aguanta ~20 %, pero lo sensato es 8 %. Al 8 % la proyección es ×26–35 en 4 años, con caída máxima del 33 %.
   - Los `entry_*` de `bot_backtesting/fullsim/results/`: ORB, drift, Donchian, RSI2, squeeze, VWAP fade, lead-lag con DXY, EURUSD y bonos, y ML de dirección.
   - `banco-modelos-econometricos-2026-10-23.md`, `investigacion/literatura-anomalias-oro-2026-10-24.md`, `investigacion/kronos-y-alternativas.md`, `investigacion/scalping-microestructura-2026-10-24.md` y `cartera-broker-2026-10-24.md`.

## Datos disponibles (en `bot_backtesting/fullsim/data/`)

- **XAUUSD+ del broker:** `broker_m15_full.pkl` y `broker_m5_full.pkl` (2022→2026) y `broker_m1_ticks.pkl` (M1 desde 2026-01).
- **Ticks:** `ticks_5s.pkl` y `ticks/spread_*.csv`. Para entre 2022 y 2025 existe `frames_duka.pkl`, de Dukascopy ajustado al broker.
- **Otros activos:** `broker_multi/*.pkl` (37 símbolos del broker: índices, FX, plata, platino, petróleo, VIX, USDX, cripto) y `cross_*.pkl`.
- **Simuladores de referencia, para reutilizar sus costos y su señal:** `broker_rule.py`, `broker_legs.py`, `broker_accounts.py`, `broker_final.py`, `recargas_*.py`, `minimo_*.py` y `riesgo_max_e2.py`.
- **Calendario de noticias:** lo genera `scripts/news_exporter.py`.

## Objetivo

Quiero que el bot gane **claramente más por unidad de riesgo** que el e2 actual, mirando el gráfico en tiempo real y adaptándose al mercado. No me sirve «más ganancia con más riesgo»: eso ya sé que se logra subiendo el lote.

**Métrica principal.** Retorno anual dividido entre la caída máxima (MAR), con la cartera completa al 8 % y costos reales. Se compara contra el e2 actual y contra el e2 con un lote mayor al mismo riesgo.

**Una idea gana si cumple las tres condiciones:**
- mejora el MAR al menos un 25 %;
- no empeora el peor día ni el peor mes;
- se mantiene en el periodo de prueba que no se usó para elegirla.

No acepto «es imposible» sin haber agotado las líneas de abajo. Tampoco acepto un resultado bonito que sea sobreajuste: prefiero un «no» honesto a una curva falsa.

## Líneas de trabajo (exhaustivo, pero pragmático)

Para cada línea:
1. Haz primero una lluvia de ideas amplia.
2. Ordénalas por «ganancia esperada ÷ costo de probar».
3. Prueba las mejores.

Empieza por **A y B**, que actúan sobre una ventaja que ya existe y son las más baratas.

### A. Mejores salidas sobre la ventaja que ya tenemos

- **Proyectar el TP.** Predecir el rango probable del resto de la sesión (por ejemplo, regresión por cuantiles del máximo y el mínimo hasta la hora de salida) y fijar el TP según eso, en lugar de 2 y 3 × ATR15 fijos.
- **Trailing inteligente que solo cierre en ganancia**, por ejemplo:
  - Chandelier o ATR;
  - un trailing que se aprieta con el tiempo;
  - un trailing que se activa a +x;
  - un parabólico;
  - la salida por agotamiento.
- **Salidas parciales y hora de salida adaptativa**, por ejemplo extender la operación si va a favor en un régimen de tendencia.
- **Qué hacer con el candado.** Dónde ponerlo y cómo deshacerlo, siempre sin cerrar en pérdida antes de la hora.
- Simula las salidas con datos **dentro de la vela** (M1 y ticks donde existan). El arnés por cierre de vela no ve los picos.

### B. Tamaño inteligente (meta-labeling)

- Un modelo que, con la información disponible en el momento de entrar, prediga la probabilidad de que esa Big One o ese Momentum gane. Con esa probabilidad se sube o baja el peso (0, 0.5, 1, 1.5) sin cambiar la dirección. Es la técnica de López de Prado.
- Características a probar:
  - el régimen;
  - la volatilidad implícita (VIX o GVZ);
  - DXY y las tasas reales;
  - el gap de apertura;
  - el rango de Asia;
  - el día de la semana y las noticias;
  - el COT y los flujos del ETF.
- Prueba también la volatilidad objetivo (vol targeting) y el riesgo por régimen.

### C. Regímenes y cambio de estrategia según régimen

- **Detectar el régimen:** tendencia o rango, volatilidad alta o baja, risk-on o risk-off. Prueba HMM, clustering y reglas sencillas.
- Medir cómo rinde cada pata del e2 en cada régimen.
- Buscar o adaptar una estrategia para los regímenes donde el e2 no rinde, y alternar entre ellas.
- Cuidado con el **sesgo de mirar adelante**: el régimen se tiene que poder calcular en tiempo real.

### D. Proyectar entradas: órdenes límite y stop de entrada

- Predecir el precio de entrada probable, por ejemplo el mínimo de la primera hora tras la apertura, y colocar órdenes límite o stop de entrada.
- La idea es mejorar el precio sin cambiar la señal. Esto es distinto de las recargas que ya se descartaron, que eran órdenes adicionales.

### E. Más patas no correlacionadas (cartera)

- Otras ventanas horarias del oro.
- Otros símbolos del broker (`broker_multi`).
- Relaciones lead-lag y spreads entre activos: oro/plata, oro/DXY, oro/tasas.
- Varias ventajas pequeñas que no se muevan juntas bajan la caída más que una sola grande.

### F. IA y datos externos

- **Modelos fundacionales de series temporales** (Kronos, Chronos, TimesFM, Moirai, Lag-Llama), probados *zero-shot* y *fine-tuned*. Sirven como filtro o como característica, no como oráculo.
- **Aprendizaje por refuerzo** solo para la gestión de salidas y el tamaño, con validación muy estricta.
- **Sentimiento de noticias con LLM**: Claude API, GDELT, Finnhub, Alpha Vantage News.
- **APIs que aporten información:**
  - FRED: tasas reales (DFII10), breakevens, GVZCLS y DXY;
  - CFTC COT;
  - tenencias de GLD;
  - el calendario económico;
  - datos de opciones si hay algo gratuito.
- Comprueba el **retraso real de publicación** de cada dato antes de usarlo; si no, metes información del futuro.
- **Frameworks recomendados:** vectorbt, lightgbm o xgboost, optuna, hmmlearn, statsmodels, scikit-learn, skfolio o riskfolio y mlfinlab (o sus equivalentes abiertos). Para RL, gymnasium y stable-baselines3. Instálalos si los necesitas.

### G. Lo que se te ocurra

Cualquier otra vía creíble que no esté arriba, justificada en 3 líneas.

## Protocolo de validación (obligatorio)

- **Costos reales del broker:** spread de los datos, comisión de 3 USD por lote y lado, deslizamiento de 0.05 y swap si la posición pasa la noche. La Big One entra a las 01:01, no a las 01:00.
- **Periodos.**
  - Para elegir: 2022-10 → 2024-12.
  - Para validar: 2025.
  - **2026 queda guardado y no se mira** hasta la evaluación final de los 3 mejores candidatos.
  - Además, walk-forward rodante y validación cruzada con purga y embargo en los modelos de ML.
- **Corrección por pruebas múltiples:** Benjamini-Hochberg sobre todas las variantes probadas y Deflated Sharpe. Lleva la cuenta de **cuántas variantes probaste en total** y repórtala.
- **Nulos obligatorios:**
  - el mismo número de operaciones en momentos al azar;
  - días al azar;
  - el e2 con un lote mayor al mismo riesgo.
- **Estabilidad:** que el resultado no dependa de un solo parámetro exacto (mostrar el vecindario) ni de un solo año.
- **Bootstrap** por bloques de días para el peor día, el peor mes y la probabilidad de caer más del 30 o el 40 %.

## Entregables

1. `docs/experimento-2/banco-ideas-optimizacion-2026-10-27.md` (o con la fecha del día): todas las ideas, cada una con su veredicto (pasa / vigilancia / descartada), números y archivo de script.
2. Un informe final con los **3 mejores candidatos**: tabla contra la base, contra el lote mayor y contra el azar, el resultado en 2026 y el riesgo.
3. Para cada candidato que pase, un **plan de prueba en sombra**: el bot registra en la demo lo que habría hecho, sin operar, durante N semanas. Fija el criterio de aprobación antes de empezar.
4. No implementes nada en `bot/` sin mi aprobación. Cuando apruebe, sigue `docs/memory/workflow-implement-then-commit.md`.

Al terminar cada línea (A, B, C…) dame un resumen de 5 líneas y sigue con la siguiente sin esperar. Para solo si necesitas una decisión mía, como pagar una API o cerrar en pérdida.
