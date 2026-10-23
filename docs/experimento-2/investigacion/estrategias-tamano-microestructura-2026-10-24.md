# Investigación: estrategias complementarias a la "Big One", gestión de tamaño, microestructura y techo realista

Fecha: 2026-10-24. Alcance: búsqueda web y lectura de literatura (no se tocó el repo). Contexto: bot MT5 XAUUSD CFD, cuenta 1k-10k USD, servidor GMT+2/+3, sin stop catastrófico ni cierre de emergencia (sí "candado"). La ventaja propia validada es comprar en la reapertura diaria (01:00 servidor = 18:00 NY) con tendencia diaria alcista: ~15 operaciones/mes, +0,2 R/operación, ~6-7 %/mes compuesto a 3 % de riesgo.

Las cifras marcadas "(cálculo propio)" son mías; el resto cita la fuente. Cuando solo leí un resumen secundario, lo indico.

---

## 0. Conclusión en una página

1. **Techo teórico de la Big One sola.** Con tus números (3 % de riesgo → 6-7 %/mes), la desviación por operación sale ≈ 2 R. Con eso, el Kelly completo es ≈ 5 % de riesgo por operación y el crecimiento máximo ≈ 7,8 %/mes (cálculo propio, §4). **Con 3 % ya estás en ~0,6 Kelly y capturas ~84 % del máximo.** Subir el riesgo apenas suma crecimiento y dispara la probabilidad de ruina. Si la ventaja real fuera la mitad (0,1 R, algo plausible tras probar muchas ideas), 3 % ya sería sobreapostar.
2. **La única palanca real es añadir flujos poco correlacionados.** Con N flujos independientes del mismo Sharpe, el crecimiento máximo se multiplica por N (g = S²/2 y S crece con √N). Llegar a 2x/mes (ln 2 = 0,69/mes) exige un Sharpe mensual ≥ 1,18 (≈ 4,1 anual) a Kelly completo, es decir, unas 9 Big One independientes. **2x/mes no es alcanzable sin riesgo de ruina.** Una meta realista y agresiva es 8-15 %/mes con 2-3 flujos.
3. **Candidatos a probar ya, ordenados por evidencia × costo × facilidad con tu arnés:**
   - (a) El **mismo patrón de reapertura en otros símbolos**: XAGUSD, US500/NAS100 y pares FX según Breedon-Ranaldo. Reutiliza tu código y entra después del rollover, así que no paga swap.
   - (b) **Intraday momentum de la última media hora** en US500/NAS100 y en el settlement del oro COMEX. Tiene evidencia publicada en 60+ futuros 1974-2020 (JFE 2021) y cierra antes del rollover.
   - (c) **Control de drawdown tipo Grossman-Zhou**: el tamaño es proporcional al colchón sobre un piso del pico. Reemplaza el "stop de emergencia" sin cerrar posiciones.
   - (d) **Trend following multi-activo en cartera chica**, como diversificador de baja frecuencia.
4. **Descartados o débiles:** la deriva nocturna de índices (la ventana 2-3 a.m. NY lleva ≈ 0 desde 2021 según sus propios autores), el pre-FOMC (desaparecido post-2015), el carry FX en CFD retail (el swap del broker se come el diferencial), el par XAU/XAG (sin evidencia OOS), vender volatilidad (incompatible con "no quemar la cuenta") y el meta-labeling con 15 operaciones/mes (muestra insuficiente).
5. **Microestructura.** Comprar exactamente a la 01:00 servidor es comprar en la ventana de spread más ancho del día. Mide el spread por minuto con `copy_ticks_range` y retrasa la entrada 5-15 min o usa una orden límite. El "candado" (cobertura) equivale económicamente a un stop, más costos: paga spread al abrir y al deshacer, y swap de las dos patas.

---

## 1. Estrategias candidatas (evidencia, tamaño, costos CFD, OOS)

### 1.1 Deriva nocturna / overnight en índices (US500, NAS100, GER40)

- **Evidencia original.** Boyarchenko, Larsen y Whelan, "The Overnight Drift" (NY Fed Staff Report 917; RFS 2023): en E-mini S&P 1998-2020, la ventana 2:00-3:00 a.m. NY rindió ≈ 3,7 %/año, más del 60 % del retorno close-to-close de 5,9 %/año. La atribuyen al riesgo de inventario de los intermediarios tras desequilibrios de cierre.
  - https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr917.pdf
- **Evidencia OOS, la clave.** Los mismos autores, "The Disappearing Overnight Drift" (Liberty Street, julio 2026): **desde 2021 la ventana promedia ≈ 0** (1.245 días). Igual en NQ y YM. La causa es que la dispersión del desequilibrio de cierre cayó de 6,5 % a 2,9 %. El efecto podría volver si se ensancha esa dispersión, pero eso no está probado.
  - https://libertystreeteconomics.newyorkfed.org/2026/07/the-disappearing-overnight-drift/
- **Costos.** CXO Advisory (resumen secundario) reporta que, ya con datos 1998-2018, la ventana 2-3 a.m. se vuelve negativa tras el bid-ask. https://www.cxoadvisory.com/?p=33743
- **ETFs overnight reales** (NSPY/NIWM, 2022-2023): cerraron en ~1 año. El retorno overnight de SPY fue negativo en ese periodo. https://efalken.substack.com/p/the-equity-overnight-anomaly-etfs
- **CFD y swap.** El rollover de los CFD de índices es a las 17:00 NY (00:00 servidor). Una posición close-to-open (16:00 → 09:30 NY) cruza el rollover y paga un día de financiación: (SOFR ≈ 4 % + markup 2,5-3 %)/360 ≈ 0,018 %/noche ≈ 4,5 %/año (cálculo propio con la fórmula de IG). Eso es del mismo orden que todo el premio overnight histórico.
  - https://www.ig.com/en/help-and-support/cfds/fees-and-charges/why-is-overnight-funding-charged-and-how-is-it-calculated-
  - https://help.capital.com/hc/en-us/articles/360016641939-Overnight-Fee-Premium
- **Variante interesante (no publicada; la propongo para probar):** usar la misma estructura que tu Big One en US500/NAS100, **compra a la reapertura de las 18:00 NY y salida antes de las 17:00 NY del día siguiente**. Esa ventana **no paga swap** e incluye todo el tramo nocturno. Riesgo: la parte "jugosa" (2-3 a.m.) está plana desde 2021. Tu arnés ya lo hace, así que el costo de probarlo es bajo. La correlación diaria oro-S&P es baja (≈ 0-0,2, variable).
- **Veredicto:** prioridad media. Pruébalo solo con la estructura sin swap y exige OOS 2021-2026.

### 1.2 Reapertura/rollover en FX y metales (patrones por hora del día)

- **Breedon y Ranaldo**, "Intraday patterns in FX returns and order flow" (SNB WP 2011-04; JMCB 2013): con 10 años de datos de alta frecuencia, **las monedas tienden a depreciarse durante su propio horario local**. El patrón aparece en varias divisas y husos, y en EUR/USD permite una estrategia simple rentable. El mecanismo es que los locales son compradores netos de divisa extranjera en su horario.
  - https://www.snb.ch/en/mmr/papers/id/working_paper_2011_04
  - https://qmul.ac.uk/sef/research/workingpapers/2012/items/694.html
  - Aplicación: el USD tendería a debilitarse en horario NY y a fortalecerse fuera. Eso es coherente con que el oro (precio en USD) suba en Asia, es decir, con tu Big One. Implica **riesgo de correlación**: un "long EURUSD/AUDUSD en Asia" podría ser en parte el mismo factor USD. Mide la correlación antes de sumar.
- **Oro "hat-shaped":** Donati y Jung (tesis CBS 2019). El oro sube en horario oriental y cae el resto del día, con caídas alrededor del London Fix en los años de manipulación. Las estrategias dan Sharpe de hasta 1,61 antes de costos, pero **tras costos rinden por debajo del mercado aunque siguen algo rentables**. Es una tesis de máster: evidencia débil, aunque **confirma que tu Big One captura un patrón documentado**.
  - https://research.cbs.dk/en/studentProjects/gold-price-dynamics-around-the-clock/
- **"Night effect" en futuros de oro y plata chinos** (J. Global Finance/IRFA 2025): https://ideas.repec.org/a/eee/glofin/v64y2025ics1044028325000110.html (solo leí el resumen).
- **London Fix:** Caminschi y Heaney (J. Futures Markets 2014) muestran retornos informados en los 4 min tras el inicio del PM fix y nada tras la publicación. Desde 2015 el fix es la subasta electrónica LBMA (10:30/15:00 Londres), así que el efecto histórico probablemente desapareció.
  - https://ideas.repec.org/a/wly/jfutmk/v34y2014i11p1003-1039.html
- **Veredicto:** prioridad alta, pero como **réplica de la Big One en XAGUSD, EURUSD, AUDUSD, USDJPY y US500**, midiendo la correlación con la Big One. Si XAGUSD replica con correlación 0,7, aporta poco. Si un par FX replica con ρ < 0,3, vale casi una segunda Big One.

### 1.3 Momentum intradía de la última media hora (intraday momentum)

- **Gao, Han, Li y Zhou**, "Market Intraday Momentum" (JFE 2018): en SPY 1993-2013, el retorno de la primera media hora (desde el cierre previo) predice el de la última media hora. Es más fuerte en días volátiles, de alto volumen y con noticias macro. Hay evidencia OOS en la versión de trabajo (R² OOS ≈ 1,8 % según CXO) y efecto también en otros 10 ETFs.
  - https://profiles.wustl.edu/en/publications/market-intraday-momentum/
  - https://www.cxoadvisory.com/?p=25481
- **Baltussen, Da, Lammers y Martens**, "Hedging Demand and Market Intraday Momentum" (JFE 2021): **más de 60 futuros (acciones, bonos, commodities y divisas), 1974-2020**. El retorno del resto del día predice el de los últimos 30 min antes del cierre en **todas** las clases de activo. El mecanismo es la cobertura de gamma de market makers de opciones y ETFs apalancados. Revierte en días siguientes.
  - https://www3.nd.edu/~zda/intramom.pdf
  - https://pure.eur.nl/en/publications/hedging-demand-and-market-intraday-momentum/
- **Tamaño y costos CFD (cálculo propio, orientativo):**
  - US500: el |retorno| típico de la última media hora es ~0,15-0,25 % y la ventaja esperada por operación ~0,02-0,05 %. Un spread de 0,4-0,6 pt sobre ~6.000 ≈ 0,01 % ida y vuelta, o sea 20-50 % de la ventaja. Cierra antes del rollover, así que no paga swap.
  - Hay ~21 operaciones/mes y la señal está **poco correlacionada con la Big One**: horario distinto (15:30-16:00 NY) y activo distinto.
- **Oro:** el "cierre" relevante es el settlement COMEX (13:30 NY = 20:30 servidor). Baltussen incluye commodities. Probar "retorno 18:00 NY → 13:00 NY predice 13:00-13:30 NY". Tú probaste "momentum intradía", pero quizá no esta especificación concreta ligada al settlement.
- **Advertencia:** varias réplicas recientes reportan debilitamiento post-2014 (no lo verifiqué con datos). Exige OOS 2021-2026.
- **Veredicto:** prioridad alta (es el segundo flujo con mejor respaldo académico multi-activo).

### 1.4 Trend following / momentum de series temporales (TSMOM) multi-activo

- **Moskowitz, Ooi y Pedersen** (JFE 2012): 58 futuros, señal = signo del retorno de 12 meses y pesos por volatilidad. Es positivo en **todos** los contratos.
  - https://papers.ssrn.com/abstract=2089463
  - Datos AQR: https://www.aqr.com/Insights/Datasets/Time-Series-Momentum-Factors-Monthly
- **Hurst, Ooi y Pedersen**, "A Century of Evidence on Trend-Following" (1880-2016, 67 mercados, objetivo 10 % de vol): positivo en todas las décadas y casi sin correlación con acciones y bonos. Sharpe neto de comisiones 2/20 entre ~0,4 y 0,76 según el resumen consultado.
  - https://www.TrendFollowing.com/whitepaper/Century_Evidence_Trend_Following.pdf
- **Realidad reciente (SG Trend Index):** 2022 +27,3 % (récord); 2023 el CTA Index ≈ −3 %; 2024 tuvo gran dispersión entre gestores (~15 pp).
  - https://www.hedgeweek.com/trend-followers-turn-leaders-ctas-deliver-record-returns-2022/
- **Cartera chica en CFD (cálculo propio):**
  - Un solo activo tiene Sharpe ~0,3-0,4. Con 6-10 CFD diversificados (US500, GER40, XAU, XAG, WTI, EURUSD, USDJPY, AUDUSD, bund/UST si los hay) se puede esperar ~0,5-0,7 bruto.
  - Costos: swaps de mantener posiciones semanas o meses (índices largos ≈ SOFR + 2,5-3 %/año; FX con markup). Restan ~1-3 %/año a 10 % de vol.
  - Con 1k USD, el lote mínimo de 0,01 impide igualar el riesgo entre activos (granularidad). Necesitas ≥ 5-10k.
  - A Kelly completo con S = 0,6 anual, g = 0,18/año ≈ 1,5 %/mes. **Es un diversificador, no un motor de crecimiento.**
- **Veredicto:** prioridad media-baja para el objetivo mensual. Su valor está en la correlación ≈ 0 y la convexidad en crisis (2022, 2008).

### 1.5 Estacionalidad de calendario en índices

- **Turn-of-the-month:** el Atlanta Fed (Maberly y Waggoner 2000) lo encuentra desaparecido post-1990 en futuros S&P. Carchano y Pardo (2011) lo encuentran entre los 3 de 188 efectos que sobreviven en ambos sub-periodos (1991-2008). No hay prueba OOS en los 2020.
  - https://www.atlantafed.org/research/publications/wp/2000/11.aspx
  - https://quantpedia.com/strategies/turn-of-the-month-in-equity-indexes
  - Son ~4 días/mes con exposición. Barato de probar como satélite, pero con evidencia mixta.
- **Pre-FOMC drift** (Lucca y Moench): según Kurov, Wolfe y Gilbert, desapareció tras 2015, con y sin conferencia de prensa. Según el BIS, se desplazó y se redujo a ~22 pb. **Descartar.**
  - https://www.skidmore.edu/economics/documents/KurovWolfeGilbert-TheDisappearingPre-FOMC-Announce-Drift-200914.pdf
  - https://www.bis.org/publ/work1079.pdf

### 1.6 Carry en FX

- Brunnermeier, Nagel y Pedersen: el carry tiene asimetría negativa y crashes ligados al VIX y la liquidez. Jurek (G10 1990-2008): tras cubrir el riesgo de crash con opciones, el exceso de retorno no es distinguible de cero.
  - https://www.nber.org/papers/w14473.pdf
  - https://www.johnhcochrane.com/s/jurek_currency.pdf
- **En CFD retail** el broker paga y cobra el swap con un markup (típicamente ~1-3 %/año por pata). El diferencial G10 neto se reduce a muy poco y conservas todo el riesgo de crash, justo el perfil "quemar la cuenta". **Descartar** salvo un broker con swaps cercanos a interbancario, y aun así sería de baja prioridad.

### 1.7 Pares / relativos (XAU vs XAG, XAUUSD vs XAUEUR)

- **XAU/XAG:** no encontré ninguna prueba OOS publicada con estadística. Quantified Strategies reporta resultados pobres o planos. El ratio pasó de 45 a 115 con regímenes de años: la reversión a la media existe a escala de años, no de días.
  - https://quantifiedstrategies.substack.com/p/gold-silver-chart-ratio-strategy
- **XAUUSD vs XAUEUR:** el spread entre ambos es esencialmente EURUSD. No es un relativo, es una apuesta de divisa con doble costo. **Descartar.**

### 1.8 Estrategias de volatilidad

- En MT5 retail no hay opciones. Las "estrategias de volatilidad" se reducen a CFD de VIX (vender contango), con crash conocido (feb-2018, XIV −90 % en un día). Eso es **incompatible con "sin stop y sin quemar la cuenta"**. **Descartar.**
- El uso correcto de la volatilidad es **dimensionar** (HAR ya predice bien; ver §2.1), no operarla.

---

## 2. Gestión de tamaño y riesgo

### 2.1 Vol targeting

- Harvey et al., "The Impact of Volatility Targeting" (JPM 2018, Man AHL, 60 activos desde 1926): **mejora el Sharpe solo en activos "de riesgo"** (acciones y crédito, por el efecto apalancamiento). En US equities pasa de 0,40 a 0,48-0,51. **En commodities y divisas el efecto en el Sharpe es despreciable**, pero **reduce las colas y el máximo drawdown en todas las clases**.
  - https://people.duke.edu/~charvey/Research/Published_Papers/P135_The_impact_of.pdf
- Cederburg et al. (JFE 2020, 103 estrategias): en tiempo real, los portafolios con gestión de vol **no superan sistemáticamente** a los no gestionados (72 de 103 pierden OOS).
  - https://www.lehigh.edu/~xuy219/research/COWY.pdf
- **Implicación para el oro (cálculo/criterio propio):** no esperes más Sharpe del vol targeting con HAR. Úsalo para **igualar el riesgo por operación** (riesgo en USD constante = lote ∝ 1/σ_HAR). Eso reduce la varianza de los resultados en R. Como el crecimiento depende de μ/σ² por operación, igualar σ sube el crecimiento compuesto aunque no cambie el Sharpe medio, solo si antes había dispersión grande del tamaño efectivo.

### 2.2 Kelly fraccional con incertidumbre

- Fórmulas (difusión continua):
  - f* = μ/σ²
  - g_max = S²/2 por periodo
  - con fracción k de Kelly: g(k) = k·(2 − k)·S²/2
  - k = ½ da 75 % del crecimiento con ¼ de la varianza.
  - Wikipedia: https://en.wikipedia.org/wiki/Kelly_criterion
- **Probabilidad de tocar alguna vez un drawdown hasta la fracción α del pico** (difusión, apostando k·Kelly): P = α^(2/k − 1). Para un drawdown del 50 % (α = 0,5):

  | Fracción de Kelly | P(DD ≥ 50 % alguna vez) | P(DD ≥ 30 %) | Crecimiento vs máximo |
  |---|---|---|---|
  | 1,0 | 50 % | 70 % | 100 % |
  | 0,5 | 12,5 % | 34 % | 75 % |
  | 0,33 | 3 % | 17 % | 56 % |
  | 0,25 | 0,8 % | 8 % | 44 % |

  (cálculo propio con la fórmula anterior; en la realidad, con saltos y colas gruesas, los números son peores.)
- **Incertidumbre del parámetro:** sobreapostar cuesta mucho más que infra-apostar. Con 2× Kelly, g = 0. Si μ real = μ_est/2, entonces "Kelly completo estimado" = 2× Kelly real, y el crecimiento es cero o negativo. **Por eso, tras probar muchas estrategias (sesgo de selección), lo prudente es ¼-½ del Kelly estimado.**
- **Risk-constrained Kelly** (Busseti, Ryu y Boyd 2016): maximiza el crecimiento sujeto a P(caer a α) ≤ β, con una cota convexa y un solo parámetro λ = log β / log α. Domina al Kelly fraccional a igual riesgo de drawdown.
  - https://arxiv.org/pdf/1603.06183
  - https://web.stanford.edu/~boyd/papers/kelly.html

### 2.3 Control de drawdown (Grossman-Zhou) y CPPI/TIPP

- Grossman y Zhou (Math. Finance 1993): exposición ∝ **colchón** (W − α·M), con M el máximo histórico de la equity. Así se garantiza W ≥ α·M en tiempo continuo. Con utilidad log, la exposición es Kelly × colchón y el crecimiento asintótico es ≈ (1 − α) × el de Kelly sin restricción. Esta proporción viene del resultado clásico de Grossman-Zhou y Cvitanić-Karatzas; no la verifiqué con el texto completo.
  - https://ideas.repec.org/a/bla/mathfi/v3y1993i3p241-276.html
  - Klass y Nowicki (2005): en tiempo discreto pierde la optimalidad exacta (los gaps rompen la garantía). https://lup.lub.lu.se/record/223851
- **CPPI:** exposición = m × (W − piso). **TIPP:** el piso sube con el pico (equivale a Grossman-Zhou). Los gaps (fin de semana en oro) pueden perforar el piso si m es grande.
- **Encaje con tus reglas:** es la forma "matemática" de no quemar la cuenta **sin stop de emergencia**. Las posiciones no se cierran; las **nuevas** entradas se hacen más pequeñas a medida que crece el drawdown. Ejemplo (cálculo propio): piso α = 0,7 (DD máx. 30 %) y riesgo por operación = 5 % × (W − 0,7·M)/W. En el pico arriesgas 1,5 %; con 15 % de DD arriesgas ≈ 0,9 %; con 25 % de DD ≈ 0,3 %.
- **Anti-martingala (subir tamaño tras ganar):** solo añade valor si los resultados tienen autocorrelación positiva. Si no, el tamaño fluctuante reduce el crecimiento geométrico frente al fraccional constante (desigualdad de Jensen). La versión que sí tiene fundamento es precisamente Grossman-Zhou/TIPP: el tamaño ∝ colchón sube tras ganar y baja tras perder, como regla de riesgo y no como apuesta a rachas.

### 2.4 Diversificación entre estrategias poco correlacionadas (lo que más mueve la aguja)

- Dos estrategias con Sharpe S y correlación ρ, a igual riesgo: S_comb = S·√(2/(1+ρ)). Como g_max = S²/2:

  | ρ | Multiplicador del Sharpe | Multiplicador del crecimiento máximo |
  |---|---|---|
  | 0 | 1,41 | 2,0 |
  | 0,3 | 1,24 | 1,54 |
  | 0,5 | 1,15 | 1,33 |
  | 0,8 | 1,05 | 1,11 |

  (cálculo propio.) Con N flujos independientes de igual Sharpe, el crecimiento máximo escala ×N. Ojo: el "rebalancing bonus" no es una fuente de valor esperado adicional sin reversión a la media (Chambers 2014). El beneficio viene del menor drag de varianza a igual exposición.
  - https://arxiv.org/pdf/1109.1256
  - https://www.hec.ca/finance/Fichier/Chambers2014.pdf
- **Implicación:** un segundo flujo con Sharpe mensual ~0,3 y ρ ≈ 0 con la Big One vale más que cualquier refinamiento de la Big One.

### 2.5 Meta-labeling

- No hay estudio independiente y OOS que aísle la mejora de Sharpe. Lo que existe es una tesis UZH 2022 positiva con una muestra chica y material de Hudson & Thames, que vende la herramienta.
  - https://www.merlin.uzh.ch/publication/show/22343
  - https://en.wikipedia.org/wiki/Meta-Labeling
- Con ~180 operaciones/año, un clasificador secundario tiene muy pocos datos y alto riesgo de sobreajuste. Tu experiencia con ML de dirección apunta igual. **Baja prioridad.** Una alternativa barata: 1-2 filtros monotónicos con sentido económico (vol HAR alta/baja, día de la semana, noticias), validados walk-forward.

---

## 3. Microestructura del broker retail

### 3.1 Spread en el rollover y comprar a la 01:00 servidor

- El rollover diario es a las 17:00 NY = 00:00 servidor (GMT+2/+3). Los brokers reportan que el spread del oro se multiplica en esa ventana (anecdótico: "se triplica"). Algunos deshabilitaron históricamente los metales minutos alrededor del rollover; por ejemplo, IC Markets en 2014 hasta las 01:00 de plataforma.
  - https://www.mql5.com/en/blogs/post/772036
  - https://www.icmarkets.com/blog/?p=5983
- COMEX para 60 min diarios (17:00-18:00 NY). **La reapertura de las 01:00 servidor es el primer minuto de liquidez tras la pausa**: spread ancho, saltos y cotizaciones escalonadas.
- **Efecto en la Big One (cálculo propio):** si R ≈ 1 ATR diario del oro (hoy ~40-80 USD/oz) y el spread a las 01:00 es 1-2 USD frente a 0,15-0,30 normal, el costo extra es ≈ 0,01-0,04 R por operación. **Eso es hasta 20 % de la ventaja de 0,2 R.** Tu arnés de barras usa precios bid de cierre de barra, así que probablemente **no** lo descuenta.
- **Qué hacer:** (1) medir el spread por minuto entre 00:00 y 01:30 servidor; (2) probar la entrada a las 01:05, 01:10 y 01:15, o una orden **límite** en el mid o en bid + x; (3) comparar la pérdida de ventaja frente al ahorro de spread.

### 3.2 Medirlo con MT5 (Python)

- Usa `mt5.copy_ticks_range(symbol, desde, hasta, mt5.COPY_TICKS_INFO)` (ticks con cambio de bid/ask) y calcula spread = ask − bid. Luego agrupa por minuto servidor y día de la semana, y obtén la mediana y el p90. El terminal solo devuelve los ticks que tiene en su historial: descarga los ticks del símbolo antes, o graba tú mismo en vivo.
  - https://www.mql5.com/en/docs/series/copyticks
  - https://mql5.com/de/book/advanced/python/python_copyticks
- Haz lo mismo para el **deslizamiento real**: registra el precio pedido frente al ejecutado (`order_send` → `result.price`) en cada entrada de la demo. Ojo: **la ejecución demo suele ser más benigna que la real**.
- Swap: `mt5.symbol_info(sym).swap_long`, `swap_mode` y `swap_rollover3days` (día del triple swap). Para la Big One, que compra a la 01:00 y sale antes de las 00:00, el swap es 0 si la salida es antes del rollover. Verifica que **ninguna** operación cruce la medianoche servidor, o cuantifica el costo cuando lo haga.

### 3.3 Cuentas raw spread y límite vs mercado

- Raw/ECN: spread interbancario + comisión ~6-7 USD por lote round-turn (IC Markets 3,5 por lado; Vantage 6 RT). En oro (1 lote = 100 oz), 7 USD/lote = 0,07 USD/oz. Suele salir más barato que una cuenta estándar con markup **fuera** del rollover, pero en el rollover el spread raw también se ensancha.
  - https://www.icmarkets.eu/en/trading-accounts/overview
  - https://www.fxempire.com/news/article/which-gold-xau-usd-trading-platforms-offer-low-spreads-and-low-trading-costs-top-5-brokers-compared-2026-1622410
- **Límite vs mercado:**
  - Una orden límite ahorra medio spread o más, pero tiene **selección adversa**: se llena más cuando el precio va en tu contra y falla en las que salen disparadas. Hay que medir la tasa de llenado y el retorno condicional de las no llenadas.
  - Para una entrada con ventana amplia como la Big One (el edge es de horas), una límite en el mid con expiración a 15-30 min suele ser buena relación.

### 3.4 Sobre el "candado" (cobertura)

- En una cuenta hedging, abrir la pata opuesta del mismo volumen deja la exposición neta en 0. **Económicamente es idéntico a cerrar** (congela la pérdida), pero:
  - paga spread y comisión de la cobertura y otra vez al deshacerla;
  - paga **swap de ambas patas** (el broker cobra el markup dos veces) si cruza el rollover;
  - mantiene margen bloqueado.
- No hay ventaja matemática frente a un stop. Su "ventaja" es psicológica u operativa: permite decidir después. Si se usa, conviene que la regla de deshacer el candado sea explícita y probada, porque si no reintroduce exposición discrecional.

---

## 4. Realismo: techo de crecimiento y por qué 2x/mes implica ruina

### 4.1 Qué ganan los mejores

- **Medallion (Renaissance):** ≈ 66 % anual bruto y 39 % neto, 1988-2018 (Zuckerman). Son estimaciones, no auditadas. Equivale a ≈ 4,3 %/mes bruto y 2,8 %/mes neto (cálculo propio). Es el mejor historial conocido.
  - https://www.cnbc.com/2020/04/17/renaissance-hedge-fund-reportedly-having-one-of-its-best-years-ever.html
- **Trend following / CTAs:** el mejor año del SG Trend Index fue 2022 con +27 % (≈ 2 %/mes). Hay años negativos frecuentes.
- **2x/mes** = 4.096x/año. Ningún fondo sistemático documentado se acerca ni a 2x/año sostenido.

### 4.2 Techo teórico con Kelly para tu ventaja (cálculo propio)

- Datos: μ = 0,2 R/operación, n = 15/mes. Tu reporte de 3 % → 6-7 %/mes compuesto implica:
  - log-growth = n·(f·μ − f²σ²/2) = 15·(0,006 − 0,00045·σ²) ≈ 0,063
  - de ahí **σ ≈ 2 R por operación**.
- De ahí salen:
  - Sharpe por operación = 0,1
  - Sharpe mensual = 0,1·√15 ≈ 0,39; Sharpe anual ≈ 1,34 (muy bueno si es real)
  - Kelly completo: f* = μ/σ² = 0,2/4 = **5 % de riesgo por operación**
  - Crecimiento máximo: g* = S_m²/2 = 0,075/mes → **≈ 7,8 %/mes**
  - A 3 % (0,6 Kelly) obtienes g ≈ 0,063 → 6,5 %/mes = **84 % del máximo**
  - A 5 % (Kelly completo): 7,8 %/mes, pero **50 % de probabilidad de tocar un DD del 50 %** y ~70 % de tocar uno del 30 %.
- **Sensibilidad a sobreestimar la ventaja:** si la μ real es 0,1 R, f* real = 2,5 %, y entonces:
  - a 3 % (1,2× Kelly real): g = 15·(0,003 − 0,0018) = 0,018 → **≈ 1,8 %/mes**, con drawdowns de Kelly completo o peor;
  - a 5 %: g = 15·(0,005 − 0,005) = 0 → **crecimiento cero** con riesgo de ruina alto.
- Es decir, **subir el riesgo solo tiene sentido si estás seguro de μ**. Con ~900 operaciones de backtest, el error estándar de μ ≈ 2/√900 ≈ 0,067 R. El intervalo al 95 % es [0,07; 0,33] R, antes de ajustar por las muchas estrategias probadas.

### 4.3 Qué Sharpe haría falta para 2x/mes

- Se necesita g = ln 2 = 0,693/mes. A Kelly completo, S_m ≥ √(2·0,693) = **1,18 mensual ≈ 4,1 anual**. A ½ Kelly, S_m ≥ 1,36 (≈ 4,7 anual).
- Con flujos independientes del Sharpe de la Big One (0,39/mes), harían falta (1,18/0,39)² ≈ **9 flujos independientes** a Kelly completo, con 50 % de probabilidad de un DD del 50 %.
- **Metas realistas (cálculo propio):**

  | Flujos indep. (S_m≈0,39 c/u) | g máx Kelly | ½ Kelly | ⅓ Kelly |
  |---|---|---|---|
  | 1 (Big One) | 7,8 %/mes | 5,8 % | 4,3 % |
  | 2 | 16 % | 12 % | 8,8 % |
  | 3 | 25 % | 18 % | 13 % |

  Con flujos más débiles (S_m ≈ 0,2, lo típico de un satélite como la última media hora), cada uno añade ≈ 0,02 a S² → +1-2 %/mes a Kelly fraccional.
- **Recomendación de riesgo:** ½-⅓ Kelly agregado sobre la cartera, con un piso tipo Grossman-Zhou (por ejemplo α = 0,7) para que el drawdown máximo quede acotado sin stops.

---

## 5. Plan de pruebas sugerido (ordenado)

1. **Medir el spread y el deslizamiento a la 01:00** con `copy_ticks_range` y probar las entradas a las 01:05/01:10/01:15 o con límite en el mid. Puede recuperar hasta ~0,02-0,04 R por operación, y es la mejora más barata.
2. **Replicar la Big One en otros símbolos** (XAGUSD, US500, NAS100, GER40, EURUSD, AUDUSD, USDJPY), con la misma lógica de reapertura más tendencia diaria y salida antes del rollover. Criterio: ventaja ≥ 0,1 R tras spread, OOS 2021-2026 positivo y **ρ diaria con la Big One < 0,3**.
3. **Intraday momentum de la última media hora:**
   - US500/NAS100: retorno desde el cierre previo hasta las 15:30 NY → posición 15:30-16:00 NY.
   - Oro: retorno 18:00 NY → 13:00 NY → posición 13:00-13:30 NY (settlement COMEX).
   - Sin swap. Exigir OOS post-2014 y post-2021.
4. **Dimensionamiento:** riesgo por operación = k·f*·(colchón Grossman-Zhou), con k = 0,4-0,5 y f* estimado con la μ **reducida a la mitad** (shrinkage por sesgo de selección). Lote ∝ 1/σ_HAR.
5. **Trend following de baja frecuencia** en 6-10 CFD (12 meses + 3 meses, vol target), solo si el capital es ≥ 5-10k. Es un diversificador de crisis.
6. **Descartar:** la deriva overnight close-to-open con swap, el pre-FOMC, el carry FX en CFD, el par XAU/XAG, XAUUSD vs XAUEUR, vender VIX, y el meta-labeling con ML (por ahora).
