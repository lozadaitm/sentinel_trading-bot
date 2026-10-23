# Literatura sobre anomalías y predictibilidad del oro (XAUUSD): revisión para HyperGrinder v20

Fecha: 2026-10-24. Solo investigación; no se tocó código.

## 0. Conversión de horas (hora servidor = Nueva York + 7 h, con el mismo horario de verano que EE. UU.)

| Evento | Hora local | Hora servidor (aprox.) |
|---|---|---|
| Reapertura CME/Globex y del broker | 18:00 NY | 01:00 |
| Fixing de Tokio USDJPY | 09:55 JST | 02:55 en invierno / 03:55 en verano |
| Apertura del día en la SGE (Shanghai Gold Exchange) | 09:00 Pekín | 03:00 en invierno / 04:00 en verano (China no cambia de hora) |
| Subastas Shanghai Gold Benchmark | 10:15 y 14:15 Pekín | 04:15 y 08:15 en invierno (+1 h en verano) |
| Apertura de MCX India | 09:00 IST | ~05:30 en invierno / 06:30 en verano |
| Apertura de Europa (ventana de la "deriva nocturna" del S&P) | 02:00-03:00 NY | 09:00-10:00 |
| Subasta LBMA Gold AM | 10:30 Londres | ~12:30 (con desfases de 1 h en las semanas en que EE. UU. y Europa no coinciden en el cambio de hora) |
| Sesión nocturna de la SHFE/SGE | 20:00-02:30 Pekín | 14:00-20:30 en invierno / 15:00-21:30 en verano |
| Datos macro de EE. UU. | 08:30 NY | 15:30 |
| Horario "pit" COMEX oro | 08:20-13:30 NY | 15:20-20:30 |
| Subasta LBMA Gold PM | 15:00 Londres | ~17:00 |
| Cierre del día y swap | 17:00 NY | 00:00 |

**Observación clave:** la ventaja que ya validamos (comprar a la 01:00 y mantener hasta ~10:00) coincide exactamente con el tramo "Asia + preapertura europea". Es el patrón mejor documentado de toda la literatura que se revisa abajo.

---

## 1. PROMETEDORES (vale la pena probarlos ya)

### P1. Asimetría horaria del oro: sube en horas asiáticas y nocturnas, cae en horas de EE. UU./pit

Explica y amplía la ventaja de la reapertura.

- **Efecto (1):** el rendimiento overnight del oro (cierre de EE. UU. → apertura) es significativamente positivo y el diurno (apertura → cierre) significativamente negativo. Se observa en futuros COMEX, en el fixing de Londres, en mineras y en ETFs. Ocurre tanto en mercados alcistas como bajistas. Una tesis de la CBS encuentra una forma de "sombrero": el oro sube de forma robusta en horas orientales (China/India) y baja el resto del día, con caídas concentradas alrededor de los fixings de Londres en los años de supuesta manipulación. Los autores lo atribuyen a la demanda de importación de Asia.
- **Tamaño (2):**
  - Morgan Stanley (Perzov, webinar de la FIA, febrero 2026): en los últimos 12 meses (≈2025), ir largo solo en horas "pit" de COMEX habría dado **−7 %**, y solo fuera de esas horas **+61 %**. Dicen que el patrón destaca frente a 25 años de historia propia y que se mantiene en ventanas móviles de 1 y 12 meses.
  - Caixin/WGC (S1 2026): horas asiáticas **+13 %**, horas de EE. UU. **−15 %** y Europa −1,3 %.
  - GLD (Quantified Strategies): ≈+0,04 % por noche, frente a un intradía plano.
  - Con el oro en niveles de miles de $/oz, una deriva de 0,05-0,1 % por sesión equivale a varios $/oz. Supera con holgura los 0,32 $/oz, siempre que el spread real a la hora de entrada se parezca al supuesto (ver advertencia).
- **Evidencia y robustez (3):**
  - Blose et al. (2018) dicen que es económicamente relevante después de costes.
  - La tesis de la CBS: Sharpe de hasta 1,61 antes de costes, aunque "después de costes queda por debajo del mercado". Ojo: con costes de 2019 y sobre un mercado de referencia.
  - La evidencia de 2025-26 es muy fuerte pero está contaminada por un mercado alcista extremo, con compras de bancos centrales y de Asia. **Riesgo:** el efecto puede depender del régimen (demanda asiática fuerte) y debilitarse. En EE. UU. ya pasó: la deriva overnight del S&P desapareció en 2021-25.
- **Fuentes (4):**
  - Blose, Gondhalekar y Kort (2018), "Overnight versus day returns in gold and gold related assets", *J. of Economics and Finance* 42(3): https://ideas.repec.org/a/spr/jecfin/v42y2018i3d10.1007_s12197-017-9403-0.html
  - Donati y Jung (2019), "Gold Price Dynamics Around the Clock", tesis de máster de la CBS: https://research.cbs.dk/en/studentProjects/gold-price-dynamics-around-the-clock/
  - FIA/Morgan Stanley (2026): https://www.fia.org/marketvoice/articles/retail-focused-precious-metals-derivatives-trading-surges-outpacing
  - Caixin (2026): https://www.caixinglobal.com/2026-07-03/analysis-gold-caught-in-a-tug-of-war-between-asian-bulls-and-a-hawkish-fed-102460438.html
  - Money Metals (2026): https://www.moneymetals.com/news/2026/07/12/a-strange-dichotomy-gold-up-on-the-year-in-asian-markets-down-big-in-the-west-005059
  - Quantified Strategies (GLD): https://quantifiedstrategies.substack.com/p/a-quantitative-look-at-the-gold-overnight
- **Datos (5):** solo precio M5/M1 de XAUUSD. Gratuitos y disponibles en tiempo real en el MT5.
- **Pruebas en la simulación (6):**
  - (a) **Pata corta en horas de EE. UU.:** vender a las 15:20 (o 16:30, apertura del NYSE) y cerrar a las 20:30 o 23:55. Probar solo los días en que la tendencia diaria NO es alcista, y también todos los días.
  - (b) **Optimizar la salida del largo de la 01:00** con un mapa de rendimiento acumulado medio por bloque de 15 min entre la 01:00 y las 15:00. La salida natural está entre las 09:00 y las 12:30 (antes del LBMA AM). Evitar optimizar en exceso: elegir en train 2021-23 y validar en 2024-26.
  - (c) **Medir la "forma de sombrero" por año** para ver si el efecto se está debilitando o reforzando.
- **Advertencia crítica sobre la ejecución:**
  - Quantpedia mostró que la deriva overnight del GDX era en parte un artefacto de los precios OHLC de apertura. Al ejecutar a las 09:31 con datos de 1 minuto, el efecto cayó mucho.
  - Equivalente para nosotros: a la 01:00 servidor (rollover) el spread del CFD se ensancha muchísimo, a menudo varios $/oz.
  - Hay que verificar que el backtest use el bid/ask real de M1 de la 01:00-01:15 y no 0,32 $ fijos. Si no, conviene entrar a las 01:15 o más tarde.
  - Fuente: https://quantpedia.com/dangers-of-relying-on-ohlc-prices-the-case-of-overnight-drift-in-gdx-etf/
- **Clasificación: PROMETEDOR** (es la familia de nuestra ventaja actual). La extensión con mejor relación coste/beneficio es la pata corta en horas de EE. UU.

### P2. Días festivos en China (SGE cerrada) como experimento natural y filtro

- **Efecto (1):**
  - Si la deriva asiática se debe a la demanda física china, debería desaparecer cuando la SGE está cerrada: Golden Week del 1 al 7 de octubre, Año Nuevo chino, 1 de mayo y otros festivos.
  - Hay testimonios de mercado (Saxo, mayo 2025) de caídas de ~2 % cuando "desaparece la oferta compradora china".
  - Rösch, Schmidbauer y Jiang (2013) encuentran un rendimiento esperado más alto alrededor del Año Nuevo chino, que se mantiene varios días después (fixing de Londres, GARCH con dummies), detectable desde el año 2000.
- **Tamaño (2):** sin estimación formal reciente.
- **Evidencia (3):** débil y en su mayoría anecdótica. Su valor es **validar el mecanismo** de nuestra ventaja y servir como filtro: no operar la reapertura en días de cierre de la SGE.
- **Fuentes (4):**
  - Rösch et al. (2013), "Gold and China", ECOMOD: https://ecomod.net/system/files/gold_and_china_ecomod2013.pdf
  - Kitco (2025): https://www.kitco.com/news/article/2025-05-01/gold-prices-drop-2-after-key-bid-evaporates-when-chinese-investors-go
  - WGC sobre la Golden Week: https://www.gold.org/download/file/21176/WMM_28_September_2026_Golden_Week_in_China.pdf
- **Datos (5):** calendario de festivos de la SGE, público y gratuito. Se codifica a mano una vez al año.
- **Prueba (6):** comparar el rendimiento medio del largo de la 01:00-10:00 en días con la SGE abierta frente a cerrada (2021-26). Si en días cerrados es ≤0, añadir un filtro "no operar". Son pocas observaciones (~15-20 días al año), así que se trata de una prueba de mecanismo más que de optimización.
- **Clasificación: PROMETEDOR como filtro y validación.** Es barato de probar.

### P3. Momentum intradía de "última media hora" (cobertura gamma)

- **Efecto (1):** el rendimiento del resto del día predice positivamente el rendimiento de los últimos 30 minutos antes del cierre, en más de 60 futuros: renta variable, bonos, materias primas y divisas. Sharpe de 0,87-1,73 por clase de activo. Se revierte en los días siguientes. Mecanismo: cobertura gamma de creadores de mercado y ETFs apalancados.
- **Efecto en China:** en futuros chinos de oro y plata, tras la introducción de la sesión nocturna, la **primera media hora de la sesión nocturna** predice el resto del día. En términos del servidor sería ~14:00-14:30 en invierno o 15:00-15:30 en verano.
- **Tamaño (2):** en el S&P, unos pocos puntos básicos por día. Para el oro con precio de miles de $, 3-5 pb son 1-2 $/oz, por encima del coste. No hay desglose específico del oro.
- **Evidencia (3):** Baltussen et al. (JFE 2021) cubre 1974-2020 con muchos mercados, lo que la hace robusta. Gao et al. (JFE 2018) lo hace en el SPY. El estudio chino es de 2025 y es una única fuente.
- **Fuentes (4):**
  - Baltussen, Da, Lammers y Martens (2021), "Hedging demand and market intraday momentum", *JFE* 142: https://ideas.repec.org/a/eee/jfinec/v142y2021i1p377-403.html (PDF: https://www3.nd.edu/~zda/intramom.pdf)
  - Gao, Han, Li y Zhou (2018), "Market intraday momentum", *JFE*: https://profiles.wustl.edu/en/publications/market-intraday-momentum/
  - Ma, Bouri, Xu y Zhou (2025), "The 'night effect' of intraday trading: Evidence from Chinese gold and silver futures markets", *Global Finance Journal* 64: https://ideas.repec.org/a/eee/glofin/v64y2025ics1044028325000110.html
- **Datos (5):** solo precio. Gratuito.
- **Prueba (6):**
  - (a) Señal = rendimiento de XAUUSD desde la 01:00 (o desde las 15:20, apertura del pit) hasta las 20:00 servidor. Si es > 0, comprar a las 20:00 y cerrar a las 20:30 (cierre del pit de COMEX); si es < 0, vender. Probar la variante "solo si |señal| > umbral de volatilidad HAR".
  - (b) Señal = rendimiento entre las 14:00 y las 14:30 (inicio de la sesión nocturna china; 15:00-15:30 en verano). Operar en la misma dirección hasta las 20:30.
  - **Escepticismo:** no hemos probado exactamente esta configuración ("momentum intradía" genérico ya fracasó), pero es una hipótesis concreta con mecanismo y no una búsqueda abierta. Probarlo en train/test solo con las dos variantes predefinidas.
- **Clasificación: PROMETEDOR** (moderado).

### P4. Prima de riesgo de varianza del oro (implícita GVZ − realizada prevista) como predictor de rendimiento a 1-24 meses

- **Efecto (1):** la prima de riesgo del oro varía en el tiempo y se puede predecir dentro y fuera de muestra con dos variables: la prima de riesgo de varianza (VI² − RV esperada) y la prima de riesgo de saltos a la baja. Una VRP alta implica un rendimiento esperado mayor.
- **Tamaño (2):** horizonte mensual. Sirve para ajustar el **tamaño y la dirección del sesgo**, no para una operación individual. Su valor está en ponderar el riesgo de nuestra estrategia de reapertura.
- **Evidencia (3):** OOS según los autores (JIMF 2019). No sabemos si se mantiene después de 2019.
- **Fuente (4):** Nguyen, Prokopczuk y Wese Simen (2019), "The risk premium of gold", *J. of International Money and Finance* 94: https://centaur.reading.ac.uk/82170/ y el resumen de Macrosynergy: https://macrosynergy.com/?p=40616
- **Datos (5):**
  - GVZ (CBOE Gold ETF Volatility Index), diario y gratuito en FRED (serie GVZCLS), con un día de retraso. No sirve en tiempo real intradía, pero basta para un filtro diario.
  - Nuestra previsión HAR ya proporciona la varianza realizada esperada.
- **Prueba (6):** VRP_t = (GVZ_t/100)²/12 − RV_HAR_prevista_mes. Para el largo de la reapertura: multiplicador de riesgo 1,5× si la VRP está en el tercil superior (calculado en train) y 0,5× si está en el inferior. Comparar el Sharpe en el período de test. Encaja con el motor de "riesgo dinámico" que ya existe.
- **Clasificación: PROMETEDOR como modulador de tamaño.** Tiene base académica y se aprovecha el HAR que ya tenemos.

---

## 2. POSIBLES

### Q1. Deriva previa al FOMC
- **Efecto (1):** el S&P sube ≈49 pb en las 24 h previas al FOMC (1994-2011), sobre todo cuando la volatilidad implícita es alta. Lucca y Moench afirman que **no** hay deriva similar en otras clases de activos. No se encontró ningún estudio específico sobre el oro.
- **Debilitamiento (3):** después de 2011 la deriva se debilitó y solo persiste en reuniones con rueda de prensa.
- **Fuente (4):** Lucca y Moench (2015), NY Fed SR512: https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr512.html
- **Prueba (6):** largo de oro entre las 21:00 servidor del día anterior y las 20:45 del día del FOMC (el anuncio es a las 14:00 NY = 21:00 servidor). Son pocas muestras (8 al año), así que hay mucho riesgo de ruido.
- **Clasificación: POSIBLE** (barato de probar, pero con baja expectativa). Ya hay deriva posterior al FOMC en nuestro estudio, lo que la complementa.

### Q2. Efecto hora del día en divisas (para replicar en otros símbolos del broker)
- **Efecto (1):** cada divisa tiende a **depreciarse en su propio horario local** y a apreciarse en el horario extranjero, por el sesgo doméstico y el inventario de los dealers. Ejemplo: el EURUSD cae en la mañana europea y se recupera en horas de EE. UU. Según los autores, es rentable como estrategia simple en EURUSD.
- **Evidencia (3):** dos artículos (Ranaldo 2007; Breedon y Ranaldo 2013, *JMCB*), con datos hasta ~2010. No hay evidencia OOS reciente.
- **Fuentes (4):**
  - Ranaldo, "Segmentation and Time-of-Day Patterns in Foreign Exchange Markets", SNB WP 2007-03: https://www.snb.ch/en/mmr/papers/id/working_paper_2007_03
  - Breedon y Ranaldo, "Intraday patterns in FX returns and order flow", SNB WP 2011-04 y *JMCB* 2013: https://www.snb.ch/en/mmr/papers/id/working_paper_2011_04
- **Prueba (6):**
  - EURUSD: corto desde ~09:00 hasta ~13:00 servidor (mañana europea) y largo desde ~15:00 hasta ~23:00.
  - USDJPY: efecto "gotobi". En días 5/10/15/20/25/fin de mes, largo antes del fixing de Tokio (02:55/03:55 servidor) y salida en el fix. Las fuentes son solo de practicantes y no tienen papers verificados.
  - Coste del FX ≈0,5-1 pip. El efecto es de pocos pb, así que el margen es estrecho.
- **Clasificación: POSIBLE.** Es una diversificación que reutiliza la misma infraestructura de "ventana horaria".

### Q3. Alrededor de las subastas LBMA (12:30 y 17:00 servidor)
- **Efecto (1):** antes de 2015 hubo filtración de información en el fixing PM: el volumen subía un 50 % al minuto del inicio y la dirección de los futuros predecía el fix con un acierto de hasta 80-90 %. Además, el oro caía alrededor de los fixings en los años de manipulación.
- **Situación actual (3):** desde marzo de 2015 hay una subasta electrónica de ICE con supervisión, así que es probable que el efecto se haya atenuado. No se encontró un estudio posterior a 2015.
- **Fuentes (4):**
  - Caminschi y Heaney (2014), "Fixing a leaky fixing", *J. Futures Markets* 34(11): https://ideas.repec.org/a/wly/jfutmk/v34y2014i11p1003-1039.html
  - Donati y Jung (2019), tesis de la CBS (enlace en P1).
- **Prueba (6):**
  - Rendimiento medio en las ventanas 12:15-13:00 y 16:45-17:30 servidor (2021-26). Comprobar si son negativas de forma sistemática.
  - Como regla de salida: cerrar el largo de la reapertura antes de las 12:30.
  - No se busca una estrategia propia.
- **Clasificación: POSIBLE** (como refinamiento de la salida de P1).

### Q4. Prima de Shanghai (SGE frente a LBMA) como filtro de demanda
- **Efecto (1):** una prima alta indica demanda china fuerte. La correlación diaria con el precio internacional es **negativa** en muestras largas (el LBMA Alchemist sugiere causalidad inversa: un precio alto reduce la prima). Como predictor de rendimiento no está probado.
- **Fuentes (4):**
  - LBMA Alchemist n.º 83: https://www.lbma.org.uk/alchemist/issue-83/links-between-the-chinese-and-international-gold-prices
  - CME Group (2024): https://www.cmegroup.com/openmarkets/metals/2024/The-Rise-and-Fall-of-Chinas-Gold-Premium.html
- **Datos (5):**
  - Precio Au9999 de la SGE, en CNY/gramo, frente a XAUUSD × USDCNY. Se puede obtener gratis de metalcharts.org o de la web de la SGE, con algo de raspado. Es difícil de conseguir en tiempo real de forma fiable.
  - El USDCNH sí puede estar disponible en el broker.
- **Prueba (6):** prima_t calculada al cierre de la SGE (09:30 servidor) y usada para filtrar el largo de la reapertura del día siguiente (prima en el tercil alto → operar o ampliar el tamaño).
- **Clasificación: POSIBLE.** Tiene lógica para nuestro mecanismo (demanda asiática), pero la evidencia formal es nula y el coste de obtener los datos es alto.

### Q5. Momentum de serie temporal del oro a largo plazo
- **Efecto (1):** reglas de tendencia a largo plazo en el oro. Según la CXO, la más robusta es el momentum de 24 meses, que sirve sobre todo para evitar caídas prolongadas. El TSMOM en materias primas se ha debilitado después de 2009.
- **Fuentes (4):**
  - Moskowitz, Ooi y Pedersen / Hurst, Ooi y Pedersen (siglo de evidencia): https://fairmodel.econ.yale.edu/ec439/hurst.pdf
  - CXO Advisory: https://www.cxoadvisory.com/?p=31400
- **Prueba (6):** filtro de régimen. Desactivar los largos (o reducirlos a 0,5×) si el precio está por debajo de su valor de hace 12 o 24 meses. Ya usamos la tendencia diaria; esto añade un régimen lento.
- **Clasificación: POSIBLE** (como filtro). No es una fuente de alfa independiente.

---

## 3. DESCARTAR (para nuestro horizonte y coste) y por qué

| Tema | Motivo |
|---|---|
| **Deriva overnight de índices de EE. UU.** (S&P, Nasdaq y Dow, 02:00-03:00 NY = 09:00-10:00 servidor) | Boyarchenko, Larsen y Whelan (*RFS* 2023): era ~3,7 % anual entre 1998 y 2020, pero los mismos autores informan que es **≈0 en 2021-2025** (Liberty Street, julio 2026). Además, los spreads eliminaban la ganancia bruta. https://libertystreeteconomics.newyorkfed.org/?p=43261 |
| Estacionalidad anual (septiembre, noviembre, enero, festivales indios) | Baur (2012): septiembre +2,2 % y noviembre +1,8 % (1981-2010), pero otras fuentes dicen que septiembre es el peor mes. Son 12 observaciones por año y probablemente minería de datos. https://cxoadvisory.com/calendar-effects/gold-seasonality-drivers |
| Efecto lunes / fin de semana | Resultados contradictorios: Blose (2011) lo ve negativo; Yu y Shih (2011) dicen que desapareció; otro estudio de 2016 encuentra viernes + y martes −. Además ya probamos el día de la semana. https://businessperspectives.org/journals/banks-and-bank-systems/issue-190/weekday-effects-on-gold-tokyo-london-and-new-york-markets |
| Índice GPR (Caldara-Iacoviello) | En el modelo GRAM del WGC es significativo pero solo sube el R² de 0,635 a 0,645. Es contemporáneo, no predictivo, y no hay ganancia OOS demostrada. https://www.gold.org/goldhub/gold-focus/2023/10/you-asked-we-answered-whats-impact-of-geopolitics-on-gold |
| Flujos de ETFs (tenencias de GLD) | Solo hay correlación contemporánea y causalidad inversa. No hay ningún test OOS predictivo. |
| Compras de bancos centrales (PBOC) | Datos mensuales, compras subdeclaradas y sin estudio predictivo. Sirven para la narrativa del régimen, no para operar. |
| Google Trends | Tesis y estudios pequeños, con dirección inconsistente: las búsquedas siguen a las caídas. Es contemporáneo. |
| Tasas de arrendamiento / GOFO | El GOFO dejó de publicarse (era LIBOR); las lease rates se comportan casi como un paseo aleatorio. La evidencia es anecdótica (2013-14). |
| Índice de sorpresas económicas de Citi | Notas de practicantes con n≈15 señales, propietario y de pago. Lo que sí está documentado (Elder, Miao y Ramchander, *JBF* 2011: las sorpresas positivas de EE. UU. hunden el oro, sobre todo NFP y bienes duraderos) ya está cubierto en nuestro estudio de noticias. |
| Vencimiento de opciones de COMEX, pinning, roll | No hay estudios específicos del oro. El pinning es "real pero modesto" y está diluido por las opciones semanales. |
| Ciclo FOMC de semanas pares (Cieslak et al.) | Solo documentado en acciones; no hay evidencia en oro. |
| Bitcoin overnight (Quantpedia) | Se sale de nuestro foco. Existe un efecto de fin de semana, pero con evidencia de blog. |

---

## 4. Lectura global y prioridades

1. **Nuestra ventaja de la reapertura es la cara visible de un fenómeno bien documentado:** el oro sube en horas asiáticas y cae en horas occidentales (Blose 2018, CBS 2019, Morgan Stanley 2026, Caixin 2026). Esto aumenta la confianza en que no es minería de datos. También advierte de que depende del régimen de demanda asiática y que podría debilitarse, como ya ocurrió con la deriva overnight del S&P.
2. **Siguientes pasos, por orden:**
   - (i) Verificar el coste real del spread a la 01:00-01:15.
   - (ii) Pata corta en horas pit de EE. UU. (P1a).
   - (iii) Filtro de festivos de la SGE (P2).
   - (iv) Salida óptima antes del LBMA AM (P1b / Q3).
   - (v) Momentum de la última media hora y de la sesión nocturna china (P3).
   - (vi) VRP del GVZ como modulador de tamaño (P4).
3. **Disciplina:** cada prueba debe tener una sola regla predefinida, train 2021-23 y test 2024-26, y una corrección mental por comparaciones múltiples. Con ~6 pruebas, exigir t > 2,5 en test.
