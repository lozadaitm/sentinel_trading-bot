# Fase 1: Kronos (y alternativas) como filtro para HyperGrinder en XAUUSD

Investigación web del 2026-10-13. No se tocó código, no se instaló nada y no se ejecutó nada.
Convención: **[paper]** = lo que dicen los autores; **[independiente]** = alguien ajeno; **[estimación]** = cálculo mío, sin medir.

---

## 1. Qué es Kronos

- **Qué es.** Un modelo de IA "pre-entrenado" solo con velas (OHLCV), en lugar de con texto. Funciona como un "ChatGPT de velas": convierte cada vela en un "token" y predice la vela siguiente, luego la siguiente, y así hasta cubrir el horizonte pedido (modo autoregresivo, decoder-only). Fuente: https://github.com/shiyu-coder/Kronos
- **Tokenizer.** Un autoencoder pequeño con cuantizador BSQ convierte cada vela (open, high, low, close, volume, amount) en un código de 20 bits. Ese código se parte en un sub-token "grueso" de 10 bits y otro "fino" de 10 bits. El tokenizer tiene 3+3 capas, dimensión 256 y 4 cabezas. Fuente: https://arxiv.org/html/2508.02739
- **Datos de entrenamiento [paper].** "Más de 12.000 millones de velas" de más de 45 bolsas, que incluyen acciones, cripto, futuros y forex, con frecuencias de 1 minuto a semanal. El propio paper se contradice en algún detalle: "45 exchanges" frente a "40+ exchanges en 30+ países", y "7 granularidades" frente a una tabla con 13. Los datos llegan hasta **junio de 2024** y el test empieza en julio de 2024. Fuentes: https://arxiv.org/html/2508.02739 y https://huggingface.co/papers/2508.02739
- **Tamaños.** Fuente: https://github.com/shiyu-coder/Kronos

| Modelo | Parámetros | Contexto máx. | ¿Pesos públicos? |
|---|---|---|---|
| Kronos-mini | 4,1 M | 2048 velas | Sí |
| Kronos-small | 24,7 M | 512 velas | Sí |
| Kronos-base | 102,3 M | 512 velas | Sí |
| Kronos-large | 499,2 M | 512 velas | **No** |

- **Paper.** arXiv **2508.02739**, "Kronos: A Foundation Model for the Language of Financial Markets", de Yu Shi, Zongliang Fu et al. (Tsinghua). Se publicó el 2 de agosto de 2025 y fue aceptado en **AAAI 2026** (anuncio del 10 de noviembre de 2025; aparece en ojs.aaai.org). Fuentes: https://arxiv.org/abs/2508.02739, https://ojs.aaai.org/index.php/AAAI/article/view/39730/43691 y https://github.com/shiyu-coder/Kronos
- **Popularidad.** Kronos-small tuvo unas 1 M de descargas el último mes en Hugging Face: https://huggingface.co/NeoQuasar/Kronos-small

## 2. Licencia

- **Código:** MIT. https://github.com/shiyu-coder/Kronos
- **Pesos:** las model cards de Hugging Face dicen "license: mit". https://huggingface.co/NeoQuasar/Kronos-small
- **Matiz:** los repos de pesos en HF no traen un archivo LICENSE propio. Un usuario lo preguntó formalmente y, en lo visible, nadie del equipo respondió: https://huggingface.co/NeoQuasar/Kronos-small/discussions/3. Para uso privado en nuestra cuenta, el riesgo práctico es bajo. MIT permite uso comercial.

## 3. ¿Corre en CPU? Latencia, memoria, dependencias

- **Dependencias.** `numpy`, `pandas`, `torch>=2.0`, `einops`, `huggingface_hub`, `matplotlib`, `tqdm` y `safetensors`, con Python 3.10 o superior. El ajuste fino (fine-tuning) además usa `pyqlib`. Fuentes: https://raw.githubusercontent.com/shiyu-coder/Kronos/master/requirements.txt y https://github.com/shiyu-coder/Kronos
- **CPU.** El README no promete nada sobre CPU, aunque PyTorch corre en CPU sin problema. Hay evidencia indirecta de uso en CPU:
  - El issue #403 reproduce el problema con `device='cpu'`: https://github.com/shiyu-coder/Kronos/issues/403
  - Hay un port a .NET que corre en CPU: https://www.nuget.org/packages/Tsfm.Forecasting.Kronos
  - Un PR (no aceptado) con un puente a **MetaTrader 5** usaba Kronos-mini en CPU sobre **XAUUSD, EURUSD y GBPUSD**: https://github.com/shiyu-coder/Kronos/pull/292
- **Latencia: el único dato encontrado.** Ese PR #292 dice **~800 a 2000 ms por inferencia con Kronos-mini en CPU** [independiente, no verificado]. https://github.com/shiyu-coder/Kronos/pull/292
- **Mi estimación para nuestro caso** [estimación]: 400 velas de contexto, 4 a 16 velas de horizonte, CPU del VPS.
  - Kronos genera cada vela futura en **2 pasos secuenciales**, uno por sub-token (https://arxiv.org/html/2508.02739, Tabla 12).
  - El paper promedia **10 trayectorias** por predicción (https://arxiv.org/html/2508.02739, Tabla 6), así que una predicción "como en el paper" cuesta unas 10 veces más que una sola trayectoria.
  - Resultado esperado: entre 1 y 10 segundos por predicción con small, y algo menos con mini. RAM de unos 0,5 a 1,5 GB, casi todo por PyTorch (los pesos de small ocupan ~100 MB en float32).
  - En M15 hay 15 minutos entre velas, así que la latencia **no es el problema**.
- **Riesgos operativos reales en Windows:**
  - **Issue #403 (abierto, sin respuesta):** `predict()` **se cuelga** tras unas 20 a 40 llamadas en bucle en Windows, tanto en CPU como en GPU. El proceso queda al 0 % y solo se puede matar con `taskkill`. https://github.com/shiyu-coder/Kronos/issues/403. Para un bot 24/5 en Windows Server, esto es grave. Habría que aislarlo en un subproceso con watchdog y timeout.
  - **Issue #184:** CPU y GPU dan resultados distintos. https://github.com/shiyu-coder/Kronos/issues/184
  - **La salida es aleatoria por diseño:** usa muestreo con temperatura y top-p (https://github.com/shiyu-coder/Kronos). Dos llamadas con los mismos datos pueden dar direcciones distintas, así que habría que fijar la semilla y promediar muchas muestras.

## 4. ¿Predice mejor que el azar? (con escepticismo)

### Lo que afirma el paper [paper]
- **Titular:** "+93 % de RankIC frente al mejor modelo fundacional y +87 % frente al mejor modelo no pre-entrenado" en predicción de precios; un 9 % menos de error (MAE) en volatilidad. https://arxiv.org/abs/2508.02739
- **Cómo de pequeños son los números en realidad.**
  - En **Forex** (más de 1000 pares, solo OHLC, promedio de todas las frecuencias de 5 min a diario), Kronos-small saca IC 0,0279 y RankIC 0,0177 en precio. El mejor modelo clásico entrenado saca 0,0228 y 0,0175, y Chronos-S 0,0176 y 0,0168. https://arxiv.org/html/2508.02739 (Apéndice F, Tablas 14 y 15)
  - Un "+93 %" sobre una correlación de 0,01 sigue siendo una correlación de 0,02. Son señales **muy débiles**.
- **Qué mide el "IC" de precio.** Es la correlación entre la *forma* de la serie predicha y la real dentro del horizonte, por muestra y promediando O, H, L y C. **No es** "acertar si sube o baja". El IC de *retornos* sí se calcula, pero de forma *transversal*: compara qué activos suben más que otros en el mismo momento, lo que sirve para elegir una cartera, no para operar un solo símbolo. https://arxiv.org/html/2508.02739
- **El paper no reporta "% de acierto de dirección"** en ninguna parte que yo haya visto.
- **Volatilidad en Forex.** MAE de 0,0097 (small) frente a 0,0185 de GARCH; R² de 0,13 frente a 0,11. Mejora en el error, con un R² que sigue siendo bajo. https://arxiv.org/html/2508.02739 (Tabla 18)
- **Backtest del paper.** Es solo de **acciones chinas diarias** (CSI300 y CSI800), con estrategia top-k y un coste del 0,15 %. Kronos-small obtiene un exceso anual de ~17,9 % e IR 1,42, frente a Moment-L con 16,8 % e IR 1,37. **No hay backtest de forex ni de oro.** https://arxiv.org/html/2508.02739
- **Oro, materias primas y futuros:** no se evalúan. Solo aparecen en el entrenamiento. https://arxiv.org/html/2508.02739
- **Fuga de datos (leakage).** El paper corta el entrenamiento en junio de 2024 y testea desde julio de 2024. Es correcto en el tiempo, pero los datos de test salen de las *mismas bolsas* que el entrenamiento. No vi que comprobaran solapamiento de activos. https://arxiv.org/html/2508.02739
- **Los rivales.** La comparación la eligieron los autores (25 modelos). Algunos son rivales flojos en datos financieros, como Moirai, que en Forex da IC ≈ 0. No compararon contra un **paseo aleatorio** ni contra "la vela siguiente igual a la actual" en dirección.

### Evidencia independiente
- **Test en Forex y CFDs, incluido oro** (Florin Elchis, Medium): 25 mercados de Oanda en H4, fuera de muestra, 749 predicciones. **50,2 % de acierto de dirección**, es decir, una moneda al aire, y peor que apostar siempre a "sube". Operar las señales **perdía dinero antes de costes**, y la "confianza" del modelo no servía para filtrar. https://florinelchis.medium.com/testing-kronos-price-prediction-model-on-forex-and-cfds-b9d4d0e76e3c (no pude abrirlo directamente, porque Medium devuelve 403; el resumen sale del buscador. Es un blog, no un paper.)
- **PR #292 (XAUUSD M15):** un mensaje de commit afirma 54 % de "win rate" con un filtro de acuerdo direccional ≥70 % y 58 % con ≥80 %. **No hay backtest ni datos**, el PR no se aceptó y no se puede verificar. https://github.com/shiyu-coder/Kronos/pull/292
- **KiT (arXiv 2609.34507):** compara contra Kronos-base en acciones chinas, acciones de EE. UU. y cripto, intradía y diario, con test de enero a abril de 2026.
  - Kronos queda por encima de Chronos-2 y TimesFM 3 en RankIC de retornos, pero por debajo del modelo propuesto.
  - Hacer fine-tuning de Kronos empeora su RankIC de retornos.
  - Es una sola ventana de unos 3 meses, con el pipeline de los propios autores de KiT.
  - https://arxiv.org/html/2609.34507v1
- **Cuantiles de velas (arXiv 2607.26792):** 12 acciones europeas y de EE. UU., diario, test de enero de 2025 a julio de 2026. Kronos tiene el menor error cuantil del grupo (6,55), pero empata con una red neuronal simple entrenada (ANN, 6,56). No incluye paseo aleatorio, FX ni oro. https://arxiv.org/html/2607.26792
- **Contexto general sobre modelos fundacionales en finanzas:**
  - Rahimikia et al. (arXiv 2511.18578): con retornos diarios de 94 países, los modelos fundacionales listos para usar rinden **mal**, tanto sin ajuste (zero-shot) como con fine-tuning, frente a CatBoost y LightGBM. https://arxiv.org/abs/2511.18578
  - arXiv 2606.27100 (5 acciones de EE. UU., diario): las mejoras frente al paseo aleatorio son del orden de **10⁻³** y casi nunca significativas. Los autores concluyen que **no son fuente fiable de alpha**. https://arxiv.org/html/2606.27100
  - arXiv 2607.05291 (volatilidad realizada en 50 activos, incluido FX): la ventaja sobre HAR se concentra en pocos activos y casi desaparece al recalibrar. https://arxiv.org/abs/2607.05291
- **Críticas de practicantes.** Kinlay dice que un IC tan bajo puede reflejar *volatilidad agrupada* (riesgo) en vez de capacidad de predecir la dirección, y pide "un backtest con costes reales antes de llamarlo señal". Ojo: ese mismo blog afirma erróneamente que Kronos no es público. https://jonathankinlay.com/2026/02/time-series-foundation-models-for-financial-markets-kronos-and-the-rise-of-pre-trained-market-models/

**Resumen honesto:**
- Hay evidencia del paper de una señal débil en la *forma* del precio y algo más útil en *volatilidad*.
- **No hay evidencia independiente sólida de que acierte la dirección del oro intradía.** El único test independiente en FX y oro da azar.
- Lo único que parece más defendible es el uso en **volatilidad**, y ahí un GARCH o HAR barato es el rival a batir.

## 5. Cómo podría usarse en el bot y cómo validarlo honestamente

### Usos posibles, de más a menos plausible
1. **Veto de volatilidad o breakout.** Antes de abrir OP1, se pide a Kronos que genere N trayectorias de 4 a 16 velas M15. Si el rango previsto (high–low) o la dispersión entre trayectorias supera un umbral, por ejemplo k×ATR, **no se abre ciclo**. Encaja con el riesgo real de una grid con cobertura (hedge): que el precio se escape en tendencia y obligue a usar OP3 y OP4. Es la forma de uso con menos exigencia de "adivinar" la dirección.
2. **Régimen (rango o tendencia).** Se usa el acuerdo entre trayectorias como medida de si el mercado lleva una dirección. Si el 80 % de las trayectorias van al mismo lado, se considera tendencia y se evita una entrada contra ella.
3. **Filtro de dirección para OP1.** Es el uso más tentador y el **menos respaldado**: la evidencia independiente en FX y oro da ~50 %.

### Protocolo de validación (antes de tocar el bot)
- **Datos.** XAUUSD M15 de nuestro broker, **solo desde julio de 2024** en adelante, porque es lo que Kronos no vio al entrenar. Se reserva el último tramo (por ejemplo, 3 meses) como prueba final que solo se mira una vez.
- **Walk-forward.** En cada vela de decisión se usan solo datos anteriores (las 400 velas previas), se fija la semilla y se generan N≥10 muestras. El umbral del veto se elige en una ventana y se prueba en la siguiente.
- **Rivales obligatorios, todos baratos:**
  - Moneda al aire.
  - "Siempre a favor de la última vela o de la EMA".
  - ATR y rango de las N velas previas, para el veto.
  - GARCH(1,1) o HAR, para la volatilidad.
  - Chronos-Bolt como modelo fundacional general.
- **Métrica que importa: el bot entero, no la correlación.**
  - La pregunta es si, con el veto, bajan los ciclos que llegan a OP3/OP4 y el drawdown, y si sube el PnL neto, *con spread y comisiones reales*.
  - El veto también tiene coste: cada ciclo bueno que se veta es dinero que se deja de ganar. Hay que medir los "vetos falsos" frente a los "breakouts evitados".
  - Hay que probar la significancia, por ejemplo con bootstrap de ciclos o comparando contra un veto aleatorio con la misma tasa de veto.
- **Advertencia del arnés.** Nuestro backtest es bar-close y no ve los picos dentro de la vela. Para el veto de breakout, eso puede sobreestimar o subestimar el beneficio. Lo ideal es validar después en las cuentas demo de experimento-2.
- **Criterio de éxito sugerido.** El veto de Kronos tiene que batir con claridad a un veto "tonto" por ATR o rango con la misma tasa de veto. Si no lo consigue, no merece su complejidad.

## 6. Alternativas open source

| Modelo | Licencia (pesos) | Tamaño | ¿CPU? | ¿Evidencia de retornos financieros? |
|---|---|---|---|---|
| **Chronos-Bolt** (Amazon) | Apache-2.0 ([HF](https://huggingface.co/amazon/chronos-bolt-small)) | small 48 M | Sí; según la model card, hasta 250× más rápido que Chronos y desplegable en CPU ([HF](https://huggingface.co/amazon/chronos-bolt-small)) | Débil o negativa: [2511.18578](https://arxiv.org/abs/2511.18578) y [2606.27100](https://arxiv.org/html/2606.27100). En el paper de Kronos, Chronos-S en FX da IC 0,018 ([paper](https://arxiv.org/html/2508.02739)) |
| **Chronos-2** (Amazon, oct. 2025) | Apache-2.0 ([HF](https://huggingface.co/amazon/chronos-2)) | 120 M | Sí, según la card ([HF](https://huggingface.co/amazon/chronos-2)) | Mejora marginal sobre el paseo aleatorio ([2606.27100](https://arxiv.org/html/2606.27100)); RankIC de retornos ≈ 0 ([KiT](https://arxiv.org/html/2609.34507v1)) |
| **TimesFM 2.5** (Google) | Apache-2.0 ([HF](https://huggingface.co/google/timesfm-2.5-200m-pytorch)). TimesFM 3: pesos no comerciales, según un tercero ([beri.net](https://www.beri.net/article/timesfm-vs-chronos-vs-moirai-time-series-foundation-model-licence-bigquery-sagemaker-cost-2026)) | 200 M | Probable (PyTorch), sin cifras oficiales | Mejor rango medio en 5 acciones, pero con ganancia ~10⁻³ ([2606.27100](https://arxiv.org/html/2606.27100)) |
| **Moirai 2.0** (Salesforce) | **CC-BY-NC 4.0, solo investigación** ([HF](https://huggingface.co/Salesforce/moirai-2.0-R-small)) | small 11,4 M | Probable | IC ≈ 0 en FX dentro del paper de Kronos ([paper](https://arxiv.org/html/2508.02739)). La licencia no permite uso comercial |
| **Lag-Llama** | Apache-2.0 ([HF](https://huggingface.co/time-series-foundation-models/Lag-Llama)) | 2,45 M | Sí (muy pequeño) | Ninguna seria encontrada; modelo de 2023-2024, superado |
| **Toto** (Datadog) | Apache-2.0 ([HF](https://huggingface.co/Datadog/Toto-Open-Base-1.0)) | ~151 M | Sin guía de CPU; recomienda GPU con xFormers | Ninguna. Entrenado sobre todo con métricas de observabilidad, no de mercados |
| **TiRex / TiRex-2** (NXAI) | TiRex 1: NXAI Community License; TiRex-2: Apache-2.0 ([GitHub](https://github.com/NX-AI/tirex-2), [HF](https://huggingface.co/NX-AI/TiRex)) | 38 M (univariante) | Sí; hay imagen Docker de CPU, pero el paquete solo está probado en Linux y macOS ([GitHub](https://github.com/NX-AI/tirex-2)) | Ninguna específica encontrada |
| **TimeGPT** (Nixtla) | Cerrado (API de pago) | n/a | n/a (nube) | Evaluado en [2606.27100](https://arxiv.org/html/2606.27100) sin ventaja clara |

Conclusión de la tabla: **Kronos es el único entrenado específicamente con velas, incluidas de FX.** Los demás son generalistas, y la literatura independiente sobre ellos en retornos financieros es mayormente negativa o marginal. Si se prueba algo, Chronos-Bolt es el "rival generalista" más barato en CPU y con licencia limpia.

---

## Veredicto propuesto: **INVESTIGAR MÁS** (no aprobar diseño; solo un experimento offline acotado)

- **Por qué no se descarta.** Licencia MIT, corre en CPU, el modelo mini/small es pequeño y es el único entrenado con velas de FX. Además, su punto más defendible (volatilidad y dispersión de trayectorias) encaja justo con nuestro riesgo principal: un breakout que arrastra la grid hacia OP3/OP4.
- **Por qué no se aprueba.** No hay evidencia independiente de que acierte la dirección del oro: el único test FX/oro da 50,2 %. Los IC del paper son ~0,02. No hay backtest en FX ni oro con costes. Y hay un bug abierto de cuelgue en Windows (#403), que es crítico para un bot 24/5.
- **Coste de integración.** Bajo para un experimento offline: un script aparte con torch en CPU (~1 a 2 días de trabajo), que corre walk-forward sobre XAUUSD M15 desde julio de 2024 y compara el veto Kronos con un veto por ATR o rango y con GARCH. Medio-alto para producción: un subproceso aislado con watchdog y timeout contra cuelgues, semilla fija, N muestras (segundos de CPU por vela), PyTorch en el VPS (~1 GB de RAM) y monitorización.
- **Siguiente paso.** Solo pasar a "diseño aprobado" si el veto Kronos **bate con claridad** a un veto ingenuo por ATR o rango con la misma tasa de veto, medido en ciclos que llegan a OP3/OP4 y en PnL neto fuera de muestra.
