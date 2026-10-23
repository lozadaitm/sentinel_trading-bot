# Banco de ideas de scalping / operaciones cortas para XAUUSD (CFD retail)

Fecha: 2026-10-24. Alcance: horizontes de segundos a unas 2 horas. Contexto: oro CFD en MT5, spread mediano 0,11 $/oz (0,17 en la reapertura de las 01:00 del servidor), comisión de 0,12 $/oz ida y vuelta, costo total de 0,23-0,29 $/oz, apalancamiento 1:500 y servidor en hora de Nueva York + 7 h. Datos disponibles: ticks bid/ask del broker desde 2026-01, M5 desde 2025-05 y M15 desde 2022-08.

Nota sobre las fuentes: las URL se comprobaron por búsqueda web el 2026-10-24, salvo las marcadas como «(ref. bibliográfica)», que son referencias clásicas citadas de memoria con revista y año, y conviene confirmarlas antes de citarlas formalmente. Cuando solo se leyó el resumen o un resumen secundario se indica en el texto.

---

## 0. La aritmética que manda: umbral de ventaja frente al costo

Con el oro a ~4000 $, un costo de 0,25 $/oz equivale a **0,625 pb (0,00625 %)**. Lo que importa es comparar ese costo con la volatilidad del horizonte de la operación:

- Volatilidad diaria realizada del oro en 2025-26 de ~1,5-2,5 % → 60-100 $/día. Si se reparte sobre unos 1.380 minutos de negociación (más concentrada en horario de EE. UU.), sale una σ de **≈1,5-2,5 $ por minuto** de media, **≈3,5-5,5 $ cada 5 min** y **≈8-12 $ por hora**. Calibren esto con sus propios ticks por franja horaria: en Asia puede ser la mitad y en noticias, diez veces más.
- Si la señal tiene un coeficiente de información IC = corr(señal, retorno futuro), la ganancia bruta esperada por operación es ≈ IC · σ_h · √(2/π) cuando se opera solo el signo. Para cubrir 0,25 $:
  - h = 1 min (σ≈2 $): hace falta IC ≳ 0,16. **Prácticamente imposible** para una señal pública.
  - h = 5 min (σ≈4,5 $): IC ≳ 0,07. Muy difícil, y solo plausible en eventos.
  - h = 30 min (σ≈11 $): IC ≳ 0,03. Factible si hay un mecanismo económico.
  - h = 2 h (σ≈20 $): IC ≳ 0,015. Es el terreno donde ya encontraron cosas (momentum Asia→EE. UU., deriva post-FOMC/NFP).
- **Conclusión estructural:** con un costo de taker retail de ~0,6 pb, el «scalping» de segundos solo es viable si se captura algo informativo que el broker todavía no ha incorporado (latencia, que el broker prohíbe y detecta) o si se provee liquidez (imposible en un CFD B-book). Las ideas viables viven en **5-120 min y condicionadas a eventos**, donde σ_h es grande y la señal tiene un mecanismo detrás.

Regla práctica de cribado: antes de simular cualquier idea, mídase el **retorno bruto medio por evento en $/oz y en unidades de σ_h**. Si el bruto es < 0,5 $/oz, descártese sin más trabajo, porque el deslizamiento real se comerá el margen.

---

## 1. Resumen de la clasificación

| # | Idea | Horizonte | Clasificación |
|---|------|-----------|---------------|
| 1 | Continuación tras noticias macro programadas (ampliar FOMC/NFP a CPI, PCE, ISM, ventas minoristas, peticiones de subsidio, JOLTS); entrada tras 1-3 min | 15-120 min | **PROMETEDOR** |
| 2 | Compuerta de volatilidad/costo (HAR + estacionalidad + spread) como filtro de todas las estrategias | — (filtro) | **PROMETEDOR (filtro)** |
| 3 | Continuación tras saltos exógenos no programados con actividad de ticks anómala | 5-60 min | **PROMETEDOR (a validar; muestra pequeña)** |
| 4 | Números redondos y cascadas de stops (Osler) en niveles de 10/25/50/100 $ | 1-30 min | POSIBLE (alto; probar primero entre los POSIBLE) |
| 5 | Ventanas de fixing LBMA (12:30 y 17:00 servidor) | 1-15 min | POSIBLE (probablemente debilitado tras 2015) |
| 6 | Refinar la entrada del momentum Asia→EE. UU. alrededor de la apertura del COMEX (15:20 servidor) y de las acciones de NY (16:30 servidor) | 30-360 min | POSIBLE (mejora de algo ya validado) |
| 7 | Anclaje en strikes en el vencimiento de opciones del COMEX (OG) | 1-4 h | POSIBLE (necesita interés abierto por strike de CME) |
| 8 | Reversión tras saltos endógenos o de liquidez (sin noticia, con spread anómalo) | 1-15 min | POSIBLE (bajo; riesgo de fill) |
| 9 | Estacionalidad direccional por minuto en aperturas (Tokio, Shanghái/SGE, Londres) | 15-60 min | POSIBLE (bajo; minería de datos) |
| 10 | Hawkes / agrupamiento de actividad como filtro de intensidad | — (filtro) | POSIBLE (como filtro) |
| 11 | Gap de reapertura diaria o semanal (relleno) | 15-120 min | POSIBLE (bajo; sesgo de datos) |
| 12 | Flujos de fin de mes o de fixing (rebalanceo) | 5-30 min | POSIBLE (bajo) |
| 13 | OFI top-of-book sin tamaños / tick rule / Lee-Ready | seg-min | DESCARTAR como señal |
| 14 | Autocorrelación / razón de varianzas a escala de segundos | seg-min | DESCARTAR como señal (útil como diagnóstico) |
| 15 | «Fading» del primer minuto de la noticia | 1-15 min | DESCARTAR |
| 16 | Ruptura tras compresión de volatilidad (sin evento) | 5-60 min | DESCARTAR |
| 17 | Kyle lambda / impacto de precio / VPIN | — | DESCARTAR (requiere volumen real) |
| 18 | Lead-lag de sub-segundo con los futuros GC (arbitraje de latencia) | ms-seg | DESCARTAR (contractual y operativo) |
| 19 | Ensanchamiento del spread como señal direccional | seg-min | DESCARTAR como señal (útil como filtro) |
| 20 | ML de microestructura (LOB/DeepLOB, árboles sobre ticks) | seg-min | DESCARTAR |
| 21 | Pares oro/plata intradía (cointegración) | min-h | DESCARTAR |

---

## 2. Ideas en detalle

### 2.1 [PROMETEDOR] Continuación tras noticias macro programadas (ampliación de la deriva post-FOMC/NFP)

- **Mecanismo:** las sorpresas macro producen un salto en la media condicional del tipo de cambio y del oro. Tras ese salto, el ajuste de carteras (coberturas, CTA, fondos que reequilibran por riesgo) continúa durante decenas de minutos. Ederington y Lee (1993) hallaron que la mayor parte del ajuste ocurre en el primer minuto, que la volatilidad sigue elevada unos 15 minutos y que **el movimiento posterior es casi independiente del primer minuto**; es decir, no hay reversión sistemática. Andersen, Bollerslev, Diebold y Vega (2003) documentan saltos de la media condicional en FX ante sorpresas, con asimetría: las malas noticias pesan más. En el oro, Sobti (2025) encuentra que las noticias macro de EE. UU. explican ~34 % de los saltos intradía de los futuros del COMEX, con el FOMC como evento dominante. Cai, Cheung y Wong (2001) señalan como los anuncios más relevantes para el oro el empleo, el PIB, el IPC y la renta personal.
- **Horizonte:** de 15 a 120 minutos.
- **Tamaño del efecto:** en el oro, el movimiento de los primeros 5 minutos tras NFP, CPI o FOMC suele ser de 5-30 $, muy por encima del costo. Para que la estrategia funcione, la continuación posterior debe superar ~0,5 $ netos de spread ensanchado. Ustedes ya validaron la deriva post-FOMC/NFP. La extensión natural es el IPC (CPI), el PCE, el ISM manufacturero y de servicios, las ventas minoristas, las peticiones semanales de subsidio y las JOLTS.
- **Evidencia fuera de muestra y debilitamiento:** el salto inicial es robusto desde los años 90. La deriva posterior es más frágil; con la algoritmización, el ajuste se concentra cada vez más en los primeros segundos (Scholtus, van Dijk y Frijns, 2014, para el SPY). Un estudio sectorial de LMAX con Macro Hive indica que ~60 % del movimiento de una hora ocurre en el primer minuto, lo que deja el ~40 % restante como deriva potencial.
- **Datos que requiere:** ticks bid/ask del broker (suficientes) y un calendario con hora exacta y, de ser posible, el consenso para calcular la sorpresa. Sin consenso, el signo del movimiento inicial sirve como proxy de la sorpresa. No hace falta volumen.
- **Regla concreta comprobable:**
  - Eventos: CPI, PCE subyacente, ISM, ventas minoristas, peticiones semanales de subsidio (ojo: muy frecuentes y de menor impacto) y JOLTS, a las 08:30 o 10:00 NY = **15:30 o 17:00 del servidor**. El FOMC es a las 14:00 NY = 21:00 del servidor.
  - En T+Δ, con Δ ∈ {1, 2, 3, 5} min, calcular r0 = mid(T+Δ) − mid(T−1 min).
  - Si |r0| > k · σ_pre, donde σ_pre es la desviación típica de los retornos de Δ minutos de los 60 minutos previos y k ∈ {2, 3}, comprar si r0 > 0 o vender si r0 < 0. Ejecutar al ask o bid del **primer tick posterior a T+Δ + latencia (300 ms)**.
  - Salida por tiempo en T+{30, 60, 120} min, sin stop o con un stop catastrófico de 3 · |r0|.
  - Variante: entrar solo si el spread en T+Δ es ≤ 2 × la mediana de la hora, para no pagar el ensanchamiento.
  - Placebo: la misma regla en los mismos minutos de días sin noticia.
  - Prueba: media neta por evento, t con errores robustos y bootstrap por evento. Con ~12 eventos/año por tipo (salvo los subsidios, ~50), en 2022-2026 hay ~50 eventos por tipo en M15 y ~20 en M5. **Agrupar tipos** y no optimizar Δ, k ni el horizonte por separado para cada tipo.
- **Fuentes:**
  - Ederington y Lee (1993), *Journal of Finance* (ref. bibliográfica, resumido vía búsqueda).
  - Andersen, Bollerslev, Diebold y Vega (2003), AER: https://papers.ssrn.com/abstract=313660 · NBER: https://www.nber.org/system/files/working_papers/w8959/w8959.pdf
  - Sobti (2025), IRFA: https://ideas.repec.org/a/eee/finana/v105y2025ics1057521925004673.html · versión de trabajo: https://www.iima.ac.in/sites/default/files/2024-03/Neharika%20Sobti%20-%20Intraday%20price%20jumps.pdf
  - Cai, Cheung y Wong (2001), *J. Futures Markets*, «What moves the gold market?»: https://ideas.repec.org/a/wly/jfutmk/v21y2001i3p257-278.html
  - Smales, O'Grady y Yang, sobre anuncios y oro del COMEX: https://espace.curtin.edu.au/handle/20.500.11937/28039
  - Scholtus, van Dijk y Frijns (2014): https://tinbergen.nl/publication/166789/speed-algorithmic-trading-and-market-quality-around-u-s-macroeconomic-news-announcements
  - LMAX y Macro Hive (sectorial): https://financemagnates.com/forex/fx-market-reactions-to-events-millisecond-data-helps-traders-capture-90-of-movements/amp
- **Escepticismo:** el riesgo principal es el **deslizamiento en la entrada**: en T+1 min el spread del broker puede estar en 0,5-1,5 $ y puede haber last-look o recotizaciones. Por eso entrar en T+3 o T+5 suele ser mejor aunque se pierda parte del movimiento. Con ticks, midan el spread real del broker en cada evento de 2026.

### 2.2 [PROMETEDOR como filtro] Compuerta de volatilidad/costo: HAR + estacionalidad + spread

- **Mecanismo:** la volatilidad es persistente y muy predecible (memoria larga; modelo HAR de Corsi), y la estacionalidad intradía de la volatilidad del oro es fuerte (Cai et al., 2001; Iwatsubo, Watkins y Xu, 2017). La rentabilidad de una regla a horizonte h escala con σ_h, mientras que el costo es fijo. **Operar solo cuando la σ esperada es grande respecto al costo** sube mecánicamente la ventaja neta de cualquier señal con IC > 0 y elimina las horas muertas, donde el costo se come todo. No es alfa direccional, pero es el filtro con más respaldo teórico.
- **Horizonte:** se aplica a cualquier estrategia de 5-120 min.
- **Efecto:** el ratio σ_h/costo varía de 5× a 50× según la hora y el régimen. Dada una IC fija, filtrar el tercil de σ esperada más bajo puede convertir una estrategia de neto ≈ 0 en positiva, *si* la IC no cae en alta volatilidad (hay que comprobarlo).
- **Evidencia fuera de muestra:** HAR-RV es un benchmark robusto desde 2009. La estacionalidad intradía de la volatilidad es estable.
- **Datos:** ticks o M5 del broker (suficientes) para la RV de 5 min y la estacionalidad por minuto del día.
- **Regla:**
  - Cada 5 min: σ̂_h = f(minuto del día) × HAR(RV_1h, RV_día, RV_semana) (o, más simple, el ATR de 5 min de las últimas 2 h por un factor estacional).
  - Operar una señal solo si σ̂_h / costo_esperado ≥ U, con costo_esperado = spread actual + 0,12 de comisión + deslizamiento medido, y U ∈ {15, 25}.
  - No operar si spread_actual > 2 × la mediana de esa hora (cubre la reapertura de las 01:00, el rollover de las 00:00 del servidor y los minutos de noticias).
  - Prueba: aplicarla a las estrategias ya validadas (momentum Asia→EE. UU., post-FOMC/NFP) y a la regla 2.1, y comparar el neto con y sin filtro **fijando U antes de mirar el resultado**.
- **Fuentes:**
  - Corsi (2009), «A simple approximate long-memory model of realized volatility», *J. Financial Econometrics* (ref. bibliográfica).
  - Cai et al. (2001), arriba.
  - Iwatsubo, Watkins y Xu (2017), RIETI DP 17-E-120: https://www.rieti.go.jp/jp/publications/dp/17e120.pdf
  - Andersen y Bollerslev (1997), «Intraday periodicity and volatility persistence», *J. Empirical Finance* (ref. bibliográfica).

### 2.3 [PROMETEDOR, a validar] Continuación tras saltos exógenos no programados con actividad anómala

- **Mecanismo:** los saltos asociados a información (noticias no programadas, titulares geopolíticos, comentarios de la Fed) inducen un **cambio persistente de precio** y la actividad sigue elevada. Scaillet, Treccani y Trevisan (*J. Financial Econometrics*) encuentran que los saltos van precedidos de desequilibrio de órdenes, agresividad y ensanchamiento del spread, y que **inducen un cambio de precio persistente**. Bouchaud y coautores (Joulin et al., 2008; Marcaccioli, Bouchaud y Benzaquen, 2022) distinguen los saltos exógenos (noticia), cuya volatilidad posterior se relaja sin reversión, de los endógenos (liquidez), con dinámica distinta y más reversión. La evidencia de momentum intradía de Gao, Han, Li y Zhou (JFE, 2018), más fuerte en días de alto volumen y de noticias, apunta en la misma dirección. Ustedes descartaron la *reversión* tras shocks de M15/H1, lo cual es coherente con que, en promedio, los shocks no revierten. Lo que queda por probar es la *continuación* condicionada a la actividad.
- **Horizonte:** de 5 a 60 min.
- **Efecto:** desconocido para el oro. Un salto de 5σ en 1 min equivale a ~10 $; con una continuación de solo el 10 %, son 1 $ brutos frente a 0,25-0,5 $ de costo con spread ensanchado. Es marginal pero plausible.
- **Evidencia fuera de muestra:** débil y específica de cada mercado. **Muestra pequeña**: los saltos del oro son raros (Sobti: probabilidad ~0,43 % por intervalo).
- **Datos:** ticks bid/ask (suficientes). La «actividad» se mide como número de cambios de cotización por segundo; el volumen de ticks es un proxy razonable del volumen real en horizontes ≥ 1 h y mucho más ruidoso a alta frecuencia (FMG DP265).
- **Regla:**
  - Detector de Lee y Mykland sobre retornos mid de 1 min: L = r_t / σ̂_bipower(ventana de 60-120 min previos, ajustada por estacionalidad). Salto si |L| > umbral(α = 1 %, Bonferroni diario) ≈ 4-4,5.
  - Excluir ±10 min alrededor de noticias programadas (esos saltos corresponden a 2.1).
  - Condición de exogeneidad: tasa de ticks en el minuto del salto > 3 × la mediana estacional *y* actividad que se mantiene alta (> 2×) en el minuto siguiente. Condición de spread: si el spread se ensanchó > 3× *antes* del salto, se trata como endógeno o de liquidez y se descarta (ver 8).
  - Entrar en la dirección del salto en t+1 min (primer tick + 300 ms) y salir a los 15, 30 o 60 min.
  - Contraste: el mismo análisis con los saltos «endógenos» (spread previo ancho, actividad que se apaga) en dirección contraria; véase 2.8.
- **Fuentes:**
  - Lee y Mykland (2008), RFS: https://galton.uchicago.edu/%7Emykland/paperlinks/LeeMykland-2535.pdf
  - Comparativa Monte Carlo de pruebas de saltos (Dumitru y Urga, 2012, JBES): https://openaccess.city.ac.uk/id/eprint/6962
  - Sesgo de los tests hacia demasiados saltos cuando la volatilidad intradía cambia (tesis de Rognlie, Duke): https://sites.duke.edu/djepapers/files/2016/10/rognlie.thesis.pdf → **ajustar siempre por estacionalidad**.
  - Barndorff-Nielsen y Shephard (2004/2006), variación bipotencia (ref. bibliográfica, *J. Financial Econometrics*).
  - Scaillet, Treccani y Trevisan: https://arxiv.org/pdf/1704.08175
  - Gao, Han, Li y Zhou (2018): https://eranraviv.com/market-intraday-momentum (resumen) · DOI 10.1016/j.jfineco.2018.05.009
  - Marcaccioli, Bouchaud y Benzaquen (2022), «Exogenous and endogenous price jumps belong to different dynamical classes» (ref. bibliográfica, arXiv 2106.07040; verificar).
- **Escepticismo:** la clasificación exógeno/endógeno con ticks retail es ruidosa. Con ~1 año de ticks habrá quizá 50-150 saltos limpios: el poder estadístico es bajo y **no conviene optimizar umbrales**. Puede ampliarse la muestra con M5 desde 2025-05, perdiendo el detalle de la tasa de ticks.

### 2.4 [POSIBLE, alto] Números redondos y cascadas de stops (Osler)

- **Mecanismo:** Osler (2000, 2003, 2005), con datos de órdenes de un banco, muestra que las órdenes take-profit se agrupan *en* los números redondos, lo que produce rebotes, y que las stop-loss se agrupan *justo después* de ellos (stops de venta justo por debajo, stops de compra justo por encima), lo que produce cascadas: cuando el precio atraviesa el redondo, la tendencia se acelera. En FX (1996-98, datos por minuto) las tendencias fueron inusualmente rápidas al alcanzar niveles con stops agrupados. Para el XAUUSD hay un test de bloguero, no revisado por pares, sobre ~8,5 años de H1: el precio que llega a un múltiplo de 20 $ con impulso tiende a **rechazarse** más que a atravesarlo, en una zona de ~1 $ de ancho; en los pares de FX no encontró nada.
- **Horizonte:** de 1 a 30 min.
- **Efecto:** las reacciones típicas en un redondo son de 1-3 $, de 4 a 12 veces el costo. El problema es la tasa de acierto y la definición de «toque».
- **Evidencia fuera de muestra:** la de Osler es de los 90. Con la algoritmización es probable que se haya debilitado, aunque los stops retail siguen agrupándose. El oro, con mucho flujo retail en CFD, es candidato natural.
- **Datos:** ticks bid/ask (suficientes). No hace falta volumen.
- **Reglas (probar ambas, fijadas de antemano):**
  - **Rebote (take-profit):** primer toque del día de un nivel L múltiplo de 25 $ (y por separado de 50 $ y 100 $), definido como mid a ≤ 0,30 $ de L, cuando el precio estuvo a > 5 $ de L durante los 30 min previos. Operar en contra con stop en L ± 1,5 $ y objetivo de 2 $, o salida por tiempo a 15 min.
  - **Cascada (stops):** si el mid atraviesa L en > 0,5 $ (tras el toque) dentro de los 5 min siguientes, operar a favor de la ruptura con stop en L ∓ 0,5 $ y salida a los 15 o 30 min.
  - Placebo obligatorio: repetir con niveles «no redondos» desplazados (L + 7, L + 13 $). El efecto debe ser específico de los redondos; si no, es solo dinámica de rupturas, que ya descartaron (ORB).
  - Mismo esquema para máximos y mínimos de la sesión previa (stops alrededor de extremos recientes). Ustedes descartaron «barridas» como concepto de smart money; la versión Osler es distinta porque **predice continuación tras atravesar, no reversión**.
- **Fuentes:**
  - Osler (2003/2005), «Stop-loss orders and price cascades in currency markets», NY Fed SR150: https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr150.pdf
  - Osler (2000), «Support for resistance: technical analysis and intraday exchange rates», FRBNY Economic Policy Review (ref. bibliográfica).
  - Test sobre XAUUSD en niveles de 20 $ (blog, no revisado): https://www.mql5.com/en/blogs/post/775454
- **Escepticismo:** es muy fácil minar datos eligiendo el paso del redondo (10, 20, 25, 50) y las distancias. Hay que fijar la parrilla de antemano y aplicar SPA (que ya usan) sobre todas las variantes.

### 2.5 [POSIBLE] Ventanas del fixing LBMA (AM 10:30 Londres, PM 15:00 Londres)

- **Mecanismo:** Caminschi y Heaney (2014, JFM) observaron en los futuros GC y en el GLD un volumen y una volatilidad elevados al **inicio** del fixing PM. Las operaciones de los primeros minutos predecían la dirección del fixing (en algunos casos > 90 %) y había rentabilidad en los 4 minutos siguientes al inicio, sin efecto tras la publicación: una fuga de información del fixing telefónico. Una tesis de la CBS y Batten et al. (2017) describen caídas del precio alrededor de los fixings en los años de manipulación alegada.
- **Debilitamiento:** desde marzo de 2015 el fixing es una subasta electrónica (LBMA Gold Price, administrada por ICE/IBA) con rondas y transparencia. **Lo esperable es que el efecto se haya reducido mucho.**
- **Horas en el servidor:** 10:30 Londres = 05:30 NY = **12:30 del servidor**; 15:00 Londres = 10:00 NY = **17:00 del servidor**. Ojo con las 2-3 semanas al año de desfase de horario de verano entre EE. UU. y el Reino Unido, en marzo y en octubre-noviembre, en las que Londres queda a NY+4 y estas horas se adelantan una hora en el servidor.
- **Datos:** ticks (suficientes).
- **Regla:** r_inicio = mid(17:02) − mid(17:00). Si |r_inicio| > 1,5 σ_2min, entrar en su dirección en 17:02 y salir en 17:05, 17:10 o 17:15. Lo mismo a las 12:30. Placebo: 16:30 y 17:30. Prueba adicional: el retorno medio 16:55-17:15 por día de la semana y por fin de mes.
- **Fuentes:**
  - Caminschi y Heaney (2014): https://ideas.repec.org/a/wly/jfutmk/v34y2014i11p1003-1039.html · nota de prensa de la UWA: https://www.news.uwa.edu.au/201410067021/research/uwa-research-finds-gold-and-silver-price-setting-open-exploitation
  - Batten, Lucey, McGroarty, Peat y Urquhart (2017): https://reading-clone.eprints-hosting.org/79175/1/BattenLuceyMcGroartyPeatUrquhart2017.pdf
  - Tesis de la CBS: https://research-api.cbs.dk/ws/portalfiles/portal/59803241/651553_Thesis_Contract_13383.pdf
- **Escepticismo:** con 4 minutos de horizonte, σ_4min ≈ 3-4 $ y haría falta IC > 0,08. Solo merece una prueba rápida.

### 2.6 [POSIBLE] Refinar la entrada del momentum Asia→EE. UU. (apertura del COMEX y de NY)

- **Mecanismo:** el momentum intradía de mercado (Gao et al., 2018; Baltussen, Da, Lammers y Martens, 2021, sobre más de 60 futuros, incluidas materias primas y divisas) se explica por coberturas de gamma corta y por reequilibrios tardíos. Ustedes ya validaron que lo de 01:00-15:00 continúa de 15:00 a 21:00 en el servidor (08:00-14:00 NY). Las aperturas del COMEX (08:20 NY = **15:20 servidor**) y de las acciones de NY (09:30 = **16:30 servidor**), junto con los datos de las 08:30 (15:30), concentran volatilidad. Entrar *después* del choque de apertura (15:35-15:45) o tras un retroceso puede mejorar el precio medio de entrada.
- **Datos:** M5 o ticks.
- **Regla:**
  - Señal = signo de r(01:00→15:00).
  - Variante A: entrada en 15:00 (base actual).
  - Variante B: entrada en 15:40.
  - Variante C: entrada en el primer retroceso ≥ 0,25 · ATR_5m desde 15:20 (límite virtual, ejecutado al tocar el bid o el ask), con caducidad a las 16:30.
  - Salida común a las 21:00 (o 20:30, cierre del COMEX). Comparar con SPA solo estas 3 variantes.
- **Fuentes:**
  - Baltussen et al. (2021), JFE: https://pure.eur.nl/en/publications/hedging-demand-and-market-intraday-momentum/ · PDF: https://www3.nd.edu/~zda/intramom.pdf
  - Gao et al. (2018), arriba.
- **Escepticismo:** es una mejora de ejecución, no una señal nueva. El efecto es de segundo orden y se pierde fácilmente en el ruido.

### 2.7 [POSIBLE] Anclaje en strikes en el vencimiento de opciones de oro del COMEX (OG)

- **Mecanismo:** en el vencimiento, la cobertura delta de los creadores de mercado con gamma larga ancla el precio a strikes con mucho interés abierto (pinning: Ni, Pearson y Poteshman, 2005, en acciones). Las opciones mensuales de oro vencen 4 días hábiles antes del fin de mes del contrato a las 13:30 NY (20:30 servidor). En el oro, el efecto podría verse en strikes múltiplos de 25 o 50 $ con interés abierto alto.
- **Datos:** **no basta con los ticks del broker**; hace falta el interés abierto por strike que CME publica cada día (descargable gratis de los informes diarios). Las semanales OG también vencen; empiecen por las mensuales.
- **Regla:** el día del vencimiento, a las 17:00 del servidor, sea K* el strike con más interés abierto a menos de 15 $ del precio. Si |mid − K*| > 5 $, operar hacia K* con objetivo K* ± 1 $, stop de 8 $ y salida a las 20:30.
- **Fuente:** Ni, Pearson y Poteshman (2005), «Stock price clustering on option expiration dates», JFE (ref. bibliográfica). Mecanismo de gamma: Baltussen et al., arriba.
- **Escepticismo:** solo hay ~12 eventos/año. Sirve para una exploración, no para validar nada con potencia.

### 2.8 [POSIBLE, bajo] Reversión tras saltos endógenos o de liquidez

- **Mecanismo:** los saltos sin noticia, causados por agotamiento momentáneo de liquidez, se revierten en parte (Joulin et al., 2008; Marcaccioli et al., 2022). En un feed retail se suman los «picos» por recotización de un proveedor de liquidez o por agregación de cotizaciones.
- **Problema central:** muchos de esos picos **no son ejecutables** (la cotización dura milisegundos, el broker aplica last-look o los filtra en el servidor). Simular el fill al bid o ask del pico sobreestima mucho. Además, ustedes ya descartaron la reversión a M15/H1.
- **Regla:** salto según Lee-Mykland con retornos de 10 s, sin noticia en ±10 min, con un spread > 3 × la mediana en los 30 s previos y una tasa de ticks que se apaga en el minuto siguiente. Esperar a que el spread vuelva a < 1,5 × la mediana, entrar en contra del salto *al precio de ese momento* (no al del pico) y salir a los 5 o 15 min o al recuperar el 50 % del salto.
- **Fuentes:** véase 2.3. Joulin, Lefevre, Grunberg y Bouchaud (2008), «Stock price jumps: news and volume play a minor role», arXiv 0803.1769 (ref. bibliográfica).

### 2.9 [POSIBLE, bajo] Estacionalidad direccional por minuto en aperturas asiáticas y de Londres

- **Mecanismo y evidencia:** la tesis de la CBS describe una estacionalidad «en forma de sombrero»: el oro se aprecia de forma robusta en horario oriental y se deprecia el resto del día. Se atribuye a la demanda física asiática y, en parte, a la manipulación del fixing. Es coherente con el sesgo comprador asiático que ya validaron. La apertura de la SGE y del SHFE es a las 09:00 de China: **04:00 del servidor en el horario de verano de EE. UU. y 03:00 en el de invierno** (el servidor sigue el horario de verano de NY y China no lo usa). Tokio abre a las 09:00 JST: 03:00 o 02:00 del servidor según la estación. Londres, a las 08:00: 10:00 del servidor (salvo en las semanas de desfase).
- **Debilidad:** la direccionalidad por minuto es el caldo de cultivo de la minería de datos, y los costos a 15-60 min exigen IC > 0,03-0,05. El sesgo asiático ya lo explotan a horizonte largo; refinarlo al minuto añade poco.
- **Regla:** una sola prueba, fijada de antemano. Retorno 03:55-05:00 del servidor (verano) o 02:55-04:00 (invierno), es decir, la apertura de Shanghái alineada por hora local china y no por hora del servidor, comparado con la misma ventana desalineada (placebo). Si el efecto aparece *solo* al alinear por hora de China, hay mecanismo; si no, es ruido.
- **Fuentes:**
  - Tesis de la CBS, arriba: https://research.cbs.dk/en/studentProjects/gold-price-dynamics-around-the-clock/
  - Tully y Lucey (2005), IIIS DP 57 (estacionalidad diaria: débil en la media y fuerte en la varianza): https://www.tcd.ie/triss/assets/PDFs/iiis/iiisdp57.pdf

### 2.10 [POSIBLE como filtro] Procesos de Hawkes / agrupamiento de actividad

- **Mecanismo:** los eventos de mercado (cambios de cotización, saltos) se autoexcitan: un evento aumenta la probabilidad de otro en el corto plazo. Hawkes predice bien la **intensidad**, es decir, la volatilidad y la actividad, no la dirección. Aït-Sahalia, Cacho-Diaz y Laeven (2015) modelan saltos mutuamente excitantes entre mercados.
- **Uso:** como alternativa más fina que el ATR en la compuerta de 2.2, y para ajustar el time stop: si la intensidad decae, la volatilidad futura cae y conviene salir antes.
- **Datos:** timestamps de ticks (suficientes). El ajuste exponencial univariante es trivial; existe la librería `tick` en Python.
- **Regla:** λ(t) = μ_estacional + Σ α · e^{−β(t − t_i)} sobre cambios de mid > 0,05 $. Operar señales de 2.1 o 2.3 solo si λ(t) > percentil 70, y cerrar si λ cae por debajo del percentil 30 durante 5 min.
- **Fuentes:**
  - Bacry, Mastromatteo y Muzy (2015), «Hawkes processes in finance»: https://arxiv.org/pdf/1502.04592v1
  - Aplicación a USD/JPY: https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8871091/
  - Aït-Sahalia, Cacho-Diaz y Laeven (2015), JFE (ref. bibliográfica).

### 2.11 [POSIBLE, bajo] Gap de reapertura diaria (01:00 servidor) y semanal

- **Mecanismo:** en la reapertura tras el rollover hay poca liquidez, spreads anchos y un precio que puede «saltar» y luego volver.
- **Problema:** ustedes ya detectaron un artefacto de Dukascopy en la reapertura. El spread del broker es de 0,17 de mediana a esa hora y sus colas son mucho más anchas. Es el ejemplo de manual de una ganancia de backtest falsa por fills al mid.
- **Regla:** solo con ticks reales del broker. Si |mid(01:05) − mid(23:55 del día previo)| > 2 $, operar hacia el cierre previo con salida a las 02:00 o al cerrar el 50 % del gap. Exigir spread < 0,25 en la entrada. Los lunes, por separado.

### 2.12 [POSIBLE, bajo] Flujos de fin de mes y de fixing (rebalanceo)

- **Mecanismo:** en FX, el fixing WM/R de las 16:00 de Londres en fin de mes muestra presión sistemática por el rebalanceo de coberturas de cartera (Melvin y Prins, 2015, *J. Financial Markets*; ref. bibliográfica). En el oro, los ETF (GLD, IAU) crean y reembolsan acciones, y los fondos indexados ruedan los futuros GC (ventana del «Goldman roll» en los días hábiles 5-9).
- **Regla:** en el último día hábil del mes, retorno 17:30-18:00 del servidor (16:00 Londres = 11:00 NY = 18:00 servidor) en función del signo del retorno del dólar o del oro en el mes. Muestra mínima: 12 eventos/año. Solo como curiosidad.

### 2.13 [DESCARTAR como señal] OFI top-of-book, tick rule y Lee-Ready con ticks sin volumen

- **Evidencia:** Cont, Kukanov y Stoikov (2014) muestran que, en intervalos cortos, los cambios de precio son lineales en el OFI (desequilibrio en el mejor bid/ask, ponderado por tamaños), con pendiente inversamente proporcional a la profundidad. **Pero la relación es contemporánea, no predictiva**: el OFI explica el movimiento del mismo intervalo. Chordia, Roll y Subrahmanyam (2005) hallan que los desequilibrios de órdenes persisten, pero el precio converge a la eficiencia en 5-60 min porque los participantes sofisticados arbitran la dependencia; replicado en 5-15 min para acciones grandes por Chung y Hrazdil (2012). Evans y Lyons (2002) explican > 50-60 % de la variación diaria de un tipo de cambio con el flujo interdealer, pero un estudio desde la mesa de un dealer encontró que el flujo de clientes «no es fácilmente explotable para especulación de corto plazo».
- **Por qué no sirve aquí:**
  1. El broker **no da tamaños**, así que el OFI se degenera en un conteo de subidas y bajadas del bid y del ask, una versión de la tick rule sobre cotizaciones.
  2. No hay operaciones, así que Lee-Ready no es aplicable: no hay trade price que clasificar.
  3. El feed del broker es un agregado de proveedores de liquidez *retrasado* respecto al COMEX y a los mercados interbancarios principales, de modo que el «OFI» del broker refleja con retraso un flujo que ya está en el precio.
  4. El horizonte en que el OFI tiene algo de poder predictivo (segundos) exige una IC > 0,2, imposible con un costo de taker de 0,25 $.
- **Prueba barata para cerrar el tema:** qOFI_t = Σ (Δbid > 0) − (Δbid < 0) + (Δask > 0) − (Δask < 0) en ventanas de 10 s, 30 s y 1 min. Calcular la correlación con el retorno mid de los 1, 5 y 15 min *siguientes*. Si IC(5 min) < 0,05, descartar.
- **Fuentes:**
  - Cont, Kukanov y Stoikov: https://arxiv.org/abs/1011.6402
  - Chordia, Roll y Subrahmanyam (2005): https://rpc.cfainstitute.org/en/research/cfa-digest/2005/11/evidence-on-the-speed-of-convergence-to-market-efficiency-digest-summary
  - Chung y Hrazdil (2012): https://ideas.repec.org/a/eee/empfin/v19y2012i5p702-720.html
  - Evans y Lyons (2002), JPE: https://www.nber.org/papers/w7317.pdf
  - Lee y Ready (1991), *J. Finance* (ref. bibliográfica).

### 2.14 [DESCARTAR como señal] Autocorrelación / razón de varianzas a escala de segundos

- **Mecanismo:** a escala de segundos, los retornos de cotización tienen autocorrelación negativa por ruido de microestructura (rebote bid-ask, recotizaciones), que desaparece a 1-5 min. Esa reversión vive **dentro del spread**: solo la captura quien provee liquidez, nunca un taker retail.
- **Uso legítimo:** como diagnóstico de régimen. La razón de varianzas de Lo y MacKinlay, VR(q) = Var(r_q)/(q · Var(r_1)), con r_1 = 1 min y q = 15, 30, 60, calculada por día o por sesión: VR > 1 indica tendencia y VR < 1, reversión. Puede probarse si la VR de Asia predice la VR de EE. UU., es decir, si mejora el filtro del momentum. También sirve para escoger la frecuencia de muestreo de la RV (gráfico de firma de volatilidad), evitando el sesgo por ruido.
- **Fuente:** Lo y MacKinlay (1988), RFS (ref. bibliográfica). Bouchaud, Bonart, Donier y Gould (2018), *Trades, Quotes and Prices*, Cambridge UP (ref. bibliográfica).

### 2.15 [DESCARTAR] «Fading» del primer minuto tras la noticia

- **Evidencia:** Ederington y Lee (1993) encuentran que el movimiento posterior es casi independiente del primer minuto. ABDV (2003) y Almeida, Goodhart y Payne no hallan reversión clara. La evidencia propia de deriva post-FOMC/NFP apunta a la continuación. Hacer «fade» a un salto informativo implica entrar contra el flujo con spread ancho y el máximo de deslizamiento: el peor escenario retail. Véase 2.1.

### 2.16 [DESCARTAR] Ruptura tras compresión de volatilidad sin evento

- **Razón:** la volatilidad se agrupa (GARCH, HAR), así que una compresión predice **más compresión** y no una ruptura inminente. La dirección de una ruptura no es predecible por la compresión. Solo hay indicadores comerciales sin pruebas fuera de muestra. Los ORB, que ya descartaron, son el caso concreto. La única variante con lógica es la compresión **antes de una noticia programada**, pero ahí la volatilidad la explica el evento y no la compresión, y es mejor la regla 2.1, que entra *después* sin necesidad de órdenes stop de straddle que se ejecutan con deslizamiento máximo.

### 2.17 [DESCARTAR] Kyle lambda, impacto de precio y VPIN

- **Razón:** todos requieren volumen firmado real. Con conteos de ticks del CFD, «lambda» se reduce a |Δp|/n_ticks, que es básicamente la volatilidad por tick, ya cubierta por 2.2 y 2.10. VPIN además fue muy criticado por su escaso poder predictivo (Andersen y Bondarenko, 2014; ref. bibliográfica). El volumen de ticks del FX se correlaciona razonablemente con el volumen real a horizontes de 1 h o más, pero de forma inestable a alta frecuencia: https://www.fmg.ac.uk/sites/default/files/2020-10/dp265.pdf
- **Alternativa:** si algún día se quiere volumen real, el GC del COMEX vía CME DataMine o un proveedor de datos de futuros, pero entonces el instrumento operado debería ser el futuro, no el CFD.

### 2.18 [DESCARTAR] Lead-lag de sub-segundo con los futuros GC (arbitraje de latencia)

- **Razón:** el efecto existe porque el feed del broker se retrasa respecto al COMEX y es el clásico «flujo tóxico» contra un B-book. Los brokers lo detectan con tiempos de mantenimiento mínimos, análisis de markouts por cliente, last-look y recotizaciones, y lo prohíben en sus términos. Exige además un feed de CME de baja latencia y coubicación. Ustedes ya descartaron el lead-lag en M5 con DXY, plata y bonos, coherente con lo anterior a escalas más largas.
- **Fuente sobre last-look:** Oomen (2017), «Last look», *Quantitative Finance*: https://ideas.repec.org/a/taf/quantf/v17y2017i7p1057-1070.html

### 2.19 [DESCARTAR como señal, útil como filtro] Ensanchamiento del spread

- **Evidencia:** en el Bitcoin de Mt. Gox, el ensanchamiento del spread, junto con el OFI y la agresividad, predice *saltos* (Scaillet et al.), pero no su dirección. En un CFD retail, además, el spread lo fija en parte el broker (márgenes en noticias y en el rollover), así que lleva información sobre la política de riesgo del broker más que sobre el mercado.
- **Uso:** no operar cuando spread > 2× la mediana de la hora (ya incluido en 2.2) y como condición de «endogeneidad» en 2.3 y 2.8.

### 2.20 [DESCARTAR] ML de microestructura

- **Evidencia:** DeepLOB y similares logran buena *exactitud* en la clasificación del mid a pocos eventos vista sobre libros completos (LSE, NASDAQ). Pero Briola, Bartolucci y Aste (2024, LOBFrame) muestran que una alta capacidad predictiva **no se traduce en señales operables** y que las métricas estándar de ML no sirven en este contexto. Lee (2024) muestra que una mala definición del objetivo hace inútiles las predicciones. La ventaja suele estar en horizontes de unos pocos eventos, donde el movimiento esperado es menor que el spread.
- **Además:** ustedes no tienen libro, solo top-of-book sin tamaños, y su LightGBM de dirección ya falló. Los fallos típicos son la fuga de información por etiquetas solapadas (resolver con *purging* y *embargo*), objetivos medidos al mid y no al bid/ask, desequilibrio de clases y selección de hiperparámetros sobre el período de test.
- **Fuentes:**
  - Briola et al.: https://arxiv.org/html/2403.09267v2
  - Lee (2024): https://arxiv.org/html/2409.14157v1
  - DeepLOB: https://arxiv.org/pdf/1808.03668.pdf

### 2.21 [DESCARTAR] Pares oro/plata intradía

- **Razón:** se pagan dos costos (el de la plata es relativamente mayor), la relación se rompe en regímenes de noticias y la reversión del ratio en horizontes intradía es lenta frente al costo. Su lead-lag con la plata en M5 ya falló.

---

## 3. Cómo evaluar honestamente scalping con ticks del broker

### 3.1 Ejecución

1. **Fill al lado correcto:** compras al **ask**, ventas al **bid**, tanto al abrir como al cerrar. Nunca al mid ni al cierre de la vela (en MT5, las velas M1/M5 se construyen con el *bid*).
2. **Latencia:** señal en el tick t, orden enviada en t + δ_cálculo y ejecutada en el **primer tick con timestamp ≥ t + δ**, con δ = ping al servidor del broker + tiempo de proceso. Midan el ping real desde el VPS (típicamente 2-50 ms si están en el mismo centro de datos, 100-300 ms si no) y simulen δ ∈ {100, 300, 1000} ms. **Si el resultado se derrumba entre 100 y 1000 ms, no es robusto.**
3. **Deslizamiento y last-look:**
   - En las noticias, añadir un deslizamiento adverso aleatorio tomado de la distribución empírica. Mídanla con su propia cuenta: envíen órdenes mínimas (0,01 lotes) en momentos aleatorios y en noticias, y comparen el precio solicitado con el ejecutado. Es el dato más valioso y barato que pueden recolectar.
   - Muchos brokers retail aplican **deslizamiento asimétrico** (lo negativo se traslada y lo positivo no; ESMA lo considera un conflicto de interés) y last-look con tiempos de retención. Simulen fills con deslizamiento solo en contra como escenario base conservador.
   - Fuentes: Oomen (2017), arriba; resumen de las preguntas y respuestas de ESMA: https://www.cappitech.com/?p=1364 ; documento de XTX sobre tiempos de retención: https://thefullfx.com/xtx-paper-takes-aim-at-invisible-tax-from-hold-times/
4. **Stops:** un stop se ejecuta en el *primer tick que lo cruza*, no al precio del stop. En gaps y noticias, al precio del tick siguiente. Los take-profit pueden ejecutarse al precio exacto o mejor, según el broker. Verifíquenlo con la cuenta real.
5. **Políticas del broker contra el scalping:** las cláusulas de tiempo mínimo de mantenimiento (por ejemplo, operaciones < 1-3 min marcadas como «abusivas»), la reclasificación a A-book con peor ejecución o la cancelación de beneficios por «arbitraje». **Las reglas de 5-120 min de este informe evitan ese riesgo; el scalping de segundos no.**

### 3.2 Sesgos de los datos

1. **Rollover y reapertura (00:00-01:00 del servidor):** spreads de 5-20×, cotizaciones indicativas y huecos. Excluir esa franja o simularla con el spread real tick a tick. Ya vieron el artefacto de Dukascopy; con los ticks del broker revisen también los **picos de una sola cotización** (off-market) que el broker luego no ejecuta.
2. **Historial de ticks de MT5:** el servidor puede almacenar el historial «filtrado» o comprimido, que difiere de lo que vio el terminal en vivo. Comparen el colector propio (ticks en vivo) con el historial descargado del servidor para los mismos días. Si difieren, solo el colector en vivo representa lo ejecutable.
3. **Cambios horarios:** el servidor está en NY+7 y sigue el horario de verano de EE. UU.; Londres y Asia no lo siguen igual. Alinear cada evento por la **hora local del mercado que lo origina** (el fixing por Londres, la SGE por China, los datos macro por NY).
4. **Calendario de noticias:** usar horas exactas de publicación con fuente histórica, sin reconstruirlas «de memoria»; los datos reprogramados (cierres de gobierno, festivos) cambian de día.
5. **Barras ya cerradas:** una señal calculada con el cierre de M5 solo es ejecutable en el siguiente tick, no al precio de cierre. Su arnés es bar-close: para estas ideas hace falta un **simulador por eventos sobre ticks**.
6. **Supervivencia y régimen:** los ticks de 2026 cubren un solo régimen (oro en máximos y muy volátil). σ alta favorece el ratio σ/costo; si la volatilidad vuelve a niveles de 2019, el mismo costo pesa el triple en σ.

### 3.3 Estadística

1. **Pre-registro:** escribir cada regla, su parrilla de parámetros (pequeña) y el criterio de éxito *antes* de mirar los datos, y versionarlo en git.
2. **Inferencia por evento:** en estrategias de eventos, la unidad es el evento, no la vela. Usar bootstrap por bloques o por evento y errores Newey-West si las operaciones se solapan.
3. **Múltiples pruebas:** contar *todas* las variantes probadas, también las de este banco. Aplicar SPA de Hansen o el Reality Check de White (que ya usan), el Sharpe deflactado y la PBO por CSCV (Bailey y López de Prado). Como regla de bolsillo, Harvey, Liu y Zhu (2016) exigen t > 3 para un factor nuevo.
4. **Placebos:** las mismas reglas en horas o niveles desplazados (sección 2). Si el placebo «gana» parecido, no hay efecto.
5. **Curva de costo de equilibrio:** reportar el neto en función del costo (0, 0,25, 0,5, 0,75 $/oz) y de la latencia. Una idea robusta tiene un costo de equilibrio ≥ 2 × el costo real.
6. **Walk-forward y fuera de muestra real:** reservar los últimos 3-4 meses de ticks sin tocar y, después, **operar en paper o con lote mínimo en real durante 1-2 meses** comparando los fills reales con los simulados. Esa diferencia es el «impuesto retail» verdadero.
7. **Métricas:** la media neta en $/oz por operación (con IC del 95 %), el porcentaje de días positivos, el peor mes y la sensibilidad a δ y al deslizamiento. No el beneficio total.

---

## 4. Plan sugerido (orden de ejecución)

1. Instrumentar la **medición del deslizamiento y la latencia reales** con órdenes mínimas (3.1). Sin este dato, todo lo demás es optimista.
2. **2.2 (compuerta de volatilidad/costo)** sobre las estrategias ya validadas: es barato y su mecanismo es sólido.
3. **2.1 (continuación post-noticia ampliada)** con entrada en T+3 o T+5 min, con M15/M5 desde 2022-2025 y ticks de 2026 para los costos reales.
4. **2.3 (saltos exógenos)** con detector Lee-Mykland ajustado por estacionalidad.
5. **2.4 (números redondos, Osler)** con placebo de niveles desplazados.
6. Pruebas rápidas de cierre (≤ 1 h cada una): 2.5 (fixing), 2.13 (IC del qOFI) y 2.14 (VR como diagnóstico).

---

## 5. Otras fuentes consultadas

- Andersen, Bollerslev y Dobrev (2007), pruebas de saltos intradía (ref. bibliográfica).
- Harvey, Liu y Zhu (2016), «...and the cross-section of expected returns», RFS (ref. bibliográfica).
- Bailey y López de Prado (2014), «The deflated Sharpe ratio» (ref. bibliográfica); Bailey, Borwein, López de Prado y Zhu (2017), «The probability of backtest overfitting» (ref. bibliográfica).
- Price discovery entre Londres, el COMEX y Tokio (tesis de Kobe): https://da.lib.kobe-u.ac.jp/da/kernel/D1007097/D1007097.pdf
- Estudio sobre el volumen de ticks frente al volumen real en FX (Marney, citado de segunda mano): https://c.mql5.com/forextsd/forum/145/fxvolume_tick_volume_vs_real_volume_study_1.pdf
