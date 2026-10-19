# Reglas de entrada para oro (XAUUSD): qué tiene evidencia independiente

Fecha: 2026-10-20 · Tipo: investigación web (no se ejecutó código de trading).

## 0. Resumen ejecutivo

- **No hay ningún estudio revisado por pares que demuestre una regla intradía de oro rentable después de costes y fuera de muestra.** La literatura específica de oro intradía es escasa. Casi todo lo que hay es: (a) efectos documentados en *otros* futuros (índices, commodities chinos, FX) que pueden o no trasladarse al oro; (b) estudios de oro diario/mensual; (c) backtests de vendedores o blogs.
- **La palanca más fuerte que tenemos no es la señal, sino el horizonte.** Nuestro coste de ida y vuelta (0,32 USD/oz) es ~0,8 pb con oro a 4000. Es ~5-10 % de un ATR de M15 (3-6 USD), pero <1 % de un rango diario típico (~40-60 USD). Una ventaja direccional de 0,1-0,3 USD por operación en M15 es imposible de rentabilizar; esa misma "calidad" de señal sobre un movimiento de horas/días sí podría serlo. Por eso las mejores candidatas de abajo mantienen la posición horas o días.
- Los efectos con mejor respaldo (en orden): **momentum de serie temporal diario** (fuerte en general, más débil tras 2009 y en oro aislado), **momentum intradía "resto del día → última media hora"** (fuerte en 60+ futuros, sin desglose de oro), y **asimetría horaria del oro (sube en horas asiáticas, cae en horas de EE. UU.)** (evidencia sugerente pero no peer-reviewed).
- **Aviso metodológico importante sobre nuestro tester:** si el benchmark son "entradas aleatorias con el mismo timing y lado", un efecto que sea *puramente horario* (p. ej. "comprar a las 03:00 servidor") queda anulado por el propio benchmark, porque la entrada aleatoria comparte hora y lado. Para las reglas de tipo calendario/sesión hay que usar además un benchmark de hora aleatoria (mismo lado, misma duración, hora sorteada) y/o restar la deriva incondicional de todas las horas. Para las reglas condicionales (momentum, ruptura) el benchmark actual sí es correcto.

### Mapa horario (servidor UTC+2/+3 alineado al cierre de NY ⇒ servidor = hora NY + 7 h todo el año)

| Evento | Hora local | Servidor |
|---|---|---|
| Cierre/reapertura CME Globex (diario) | 17:00 NY | 00:00 / 01:00 (reapertura 18:00 NY) |
| Apertura Shanghai Gold Exchange (sesión día) | 09:00 Pekín | ~03:00-04:00 (según DST de EE. UU.) |
| Apertura Londres | 08:00 Londres | 10:00 |
| LBMA Gold Price AM | 10:30 Londres | 12:30 |
| Datos macro EE. UU. (NFP, CPI) | 08:30 NY | 15:30 |
| Apertura pit COMEX / "NY open" metales | 08:20 NY | 15:20 |
| LBMA Gold Price PM | 15:00 Londres | 17:00 |
| Settlement COMEX GC | 13:30 NY | 20:30 |
| FOMC (comunicado) | 14:00 NY | 21:00 |

(Londres y NY cambian de horario en fechas distintas: 2-3 semanas al año la diferencia es 4 h, no 5; el servidor sigue a NY, así que eventos de Londres se desplazan 1 h esas semanas.)

---

## 1. Momentum de serie temporal / seguimiento de tendencia (D1, H4)

**Qué dice la evidencia**
- **Moskowitz, Ooi y Pedersen (2012, JFE), "Time Series Momentum".** 58 futuros (incluye oro), 1985-2009. Regla: signo del retorno de los últimos 12 meses (también 1, 3, 6 meses), mantener 1 mes, posición escalada por volatilidad. Persistencia de 1 a 12 meses, reversión parcial después. Muy significativo en cartera diversificada. <https://papers.ssrn.com/abstract=2089463>
- **Hurst, Ooi y Pedersen (2017, JPM), "A Century of Evidence on Trend-Following".** Combinación de lookbacks 1, 3 y 12 meses, 1880-2016, rentable en todas las décadas (cartera). <https://fairmodel.econ.yale.edu/ec439/hurst.pdf>
- **Crítica: Kim, Tse y Wald (2016, J. Financial Markets).** Gran parte del resultado viene del escalado por volatilidad, no del momentum; y el rendimiento superior desaparece en 2009-2013. Tesis de replicación 2025 también ve debilitamiento post-2009 en commodities. <https://run.unl.pt/bitstreams/3a74d44e-542e-440d-83b5-b5f44247f18f/download>
- **Específico de oro: Bartsch, Baur, Dichtl y Drobetz, "Investing in the Gold Market: Market Timing or Buy-and-Hold?"** 1990-2015, >4000 reglas (estacionales, técnicas, fundamentales), corrección por *data snooping* (SPA de Hansen). Sólo **algunas reglas técnicas** sobreviven; las ganadoras son las que salen del oro tras rachas negativas prolongadas (MA de 1-3 meses vs 9-12 meses, momentum 1-12 meses). Horizonte mensual, long/cash. <https://quantpedia.com/an-extensive-test-of-market-timing-strategies-in-the-gold-market/>
- **Intradía (5 min) oro: Batten, Lucey, McGroarty, Peat y Urquhart (2018, J. Int. Fin. Markets, Inst. & Money).** Oro spot 5 min (~2008-2014), reglas de medias móviles con IS/OOS. Con parámetros estándar **no hay poder predictivo**; con parámetros más largos algunas combinaciones son significativas en oro (no en plata). Resultados brutos, sin costes. <https://ideas.repec.org/a/eee/intfin/v52y2018icp102-113.html>
- Preprint arXiv 2025 (Singha et al.) con Sharpe OOS 2,88 en futuros de oro 2015-2025: **no fiable** (no revisado, mezcla Kelly, salidas ATR, cifras inverosímiles). <https://arxiv.org/abs/2511.08571>

**Valoración:** evidencia sólida *como fenómeno de cartera a horizonte de semanas-meses*; en oro aislado es positiva pero modesta y frágil post-2009. Útil para nosotros sobre todo como **filtro de dirección** (operar sólo a favor de la tendencia D1) y para alargar la tenencia. Coste irrelevante a ese horizonte.

## 2. Momentum intradía (primera/resto del día → última media hora)

- **Gao, Han, Li y Zhou (2018, JFE), "Market Intraday Momentum".** SPY 1993-2013: el retorno de la primera media hora (incluye el gap overnight) predice el de la última media hora. R² ~1,6 %, significativo dentro y fuera de muestra; más fuerte en días volátiles, de alto volumen y de noticias macro. Rentabilidad de estrategia del orden de 6-7 % anual (no es neta de costes realistas). <https://c.mql5.com/forextsd/forum/173/intraday_momentum_-_the_first_half-hour_return_predicts_the_last_half-hour_return.pdf>
- **Baltussen, Da, Lammers y Martens (2021, JFE), "Hedging Demand and Market Intraday Momentum".** >60 futuros (renta variable, bonos, **commodities**, divisas), 1974-2020. El retorno "resto del día" (cierre previo → 30 min antes del cierre) predice los últimos 30 min **en todas las clases de activo**. Mecanismo: cobertura gamma de creadores de mercado de opciones y ETFs apalancados. El efecto **revierte en los días siguientes** (commodities: ~2 días). No encontré desglose publicado para oro. <https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3760365>
- **Jin, Kearney, Li y Yang (2020, J. Futures Markets).** Futuros chinos de cobre, acero, soja y harina de soja: la primera media hora predice la última en los cuatro; más fuerte en metales con alto volumen/volatilidad. <https://ideas.repec.org/a/wly/jfutmk/v40y2020i4p632-650.html>
- **Ma, Bouri, Xu y Zhou (2025, Global Finance Journal), "night effect" en oro y plata chinos (SHFE).** Existen **momentum y reversión intradía**; tras la introducción de la sesión nocturna, la primera media hora *nocturna* pasó a ser el predictor. Una estrategia de *market timing* supera a buy-and-hold. Es la evidencia más directa de momentum intradía en oro, pero en SHFE, no en el mercado de Londres/COMEX. <https://ideas.repec.org/a/eee/glofin/v64y2025ics1044028325000110.html>
- Crudo (ETF USO, 2006-2018): momentum intradía IS y OOS (Wen et al.).

**Valoración:** el efecto es de los más replicados en microestructura, pero (1) el "cierre" relevante para oro no es obvio en un mercado 23 h — lo razonable es el **settlement de COMEX (13:30 NY = 20:30 servidor)**, que es donde se cubren las opciones y se concentra el flujo; (2) la magnitud por operación es pequeña (fracción de la volatilidad de 30 min): con oro, la última media hora antes del settlement mueve típicamente 2-5 USD, así que una ventaja del 5-10 % de eso es ~0,2-0,5 USD — **en el filo de nuestros costes**. Hay que condicionarlo a días de |retorno| grande (donde el efecto es más fuerte) para que tenga opciones.

## 3. Sesiones, rupturas de rango y asimetría horaria

**Asimetría horaria (el hallazgo más interesante para oro)**
- **Tesis CBS (2019), "Gold Price Dynamics Around the Clock".** Patrón en forma de sombrero: el oro **se aprecia durante horas orientales (China/India) de forma robusta y se deprecia el resto del día**; caídas en la ventana del fixing de Londres en años de manipulación alegada. Estrategias: Sharpe hasta 1,61 sin costes; **con costes rinden menos que el mercado** aunque siguen algo rentables. Sin OOS reportado. Tesis de máster (no peer-reviewed). <https://research.cbs.dk/en/studentProjects/gold-price-dynamics-around-the-clock/>
- **WGC / Ed Steer (vía FXStreet, 2026):** en el 1S el oro subió +12,9 % en horas asiáticas, −1,3 % en europeas y −15 % en norteamericanas. "Comprar en PM fix y vender en el AM fix siguiente" vs "AM→PM" desde 1970: el tramo nocturno acumula casi toda la subida. Sin metodología verificable; anecdótico, pero coincide con lo anterior. <https://www.fxstreet.com/analysis/a-strange-dichotomy-gold-up-on-the-year-in-asian-markets-down-big-in-the-west-202607131959>
- **GLD overnight vs intradía (Quantpedia; Quantified Strategies):** prácticamente toda la rentabilidad de GLD en 20 años ocurre de cierre a apertura NY (16:00→09:30 NY, que incluye Asia y Londres); el tramo 09:30-16:00 NY ≈ 0. Quantpedia advierte que los precios de apertura OHLC de Yahoo inflan estos efectos. <https://quantpedia.com/dangers-of-relying-on-ohlc-prices-the-case-of-overnight-drift-in-gdx-etf/> · <https://quantifiedstrategies.substack.com/p/a-quantitative-look-at-the-gold-overnight>
- **Caminschi y Heaney (2014, J. Futures Markets), "Fixing a leaky fixing".** Alrededor del PM fix (pre-2015) había volumen/volatilidad anómalos y el flujo en los primeros minutos predecía la dirección del fix >90 % de las veces; tras publicarse el resultado, **sin retornos aprovechables**. El fix se sustituyó por subasta electrónica (LBMA Gold Price) en 2015, así que este efecto concreto probablemente ya no existe. <https://ideas.repec.org/a/wly/jfutmk/v34y2014i11p1003-1039.html>
- **Batten et al. (2017, PLoS ONE)**, oro 5 min 2000-2015: periodicidad intradía clara en volatilidad y volumen (pico 11-17 GMT, solape Londres-NY), pero no publica medias por hora de los retornos. <https://pmc.ncbi.nlm.nih.gov/articles/PMC5407636/>

**Valoración:** la asimetría "Asia sube / EE. UU. cae" es el efecto horario con más indicios específicos del oro y tiene una explicación económica (demanda física asiática, ventas/cobertura occidental, noticias macro de EE. UU. que caen en horario NY). Pero: (a) ninguna fuente es peer-reviewed; (b) 2021-2026 es un mercado alcista fuerte, así que "comprar en Asia" incluye mucha beta; (c) el coste por día (0,8 pb) es pequeño frente a la deriva reportada. Es **barato de probar** y tiene mucho mayor ratio movimiento/coste que nuestro M15.

**Rupturas de rango de apertura (ORB) y rango asiático → Londres**
- **Zarattini y Aziz (SSRN 4416622), ORB 5 min en acciones "in play"/QQQ:** comisiones sí, spread/slippage no, sin OOS. Una réplica independiente sobre CFDs de 5 índices 2015-2026: **bruto se reproduce, neto ≈ 0**, 4 de 5 negativos tras costes. <https://www.mql5.com/en/blogs/post/776235>
- **Zarattini, Aziz y Barbon (2024), "Beat the Market" (SPY), banda de ruido intradía:** banda = apertura ± media de 14 días del movimiento absoluto apertura→misma hora; long si precio > banda, short si < banda, sólo en HH:00/HH:30, stop dinámico. Sólo SPY; sin validación en otros símbolos.
- **Ruptura Asia→Londres en XAUUSD (blog de vendedor en MQL5, 2023-09/2026):** rango 03:00-08:00 servidor, OCO a las 08:00, filtro de rango 0,30-1,60 % del precio, SL lado opuesto (máx 0,6 %), TP 2,5R, BE a 1,5R, cierre 21:00. PF 1,37-1,38 en dos brokers (715 operaciones), PF 1,61 en 157 operaciones 2026 "no vistas". **Evidencia débil**: autor vende el producto, costes no especificados, parámetros elegidos sobre 2023-2025. <https://www.mql5.com/en/blogs/post/777540>

**Valoración:** ORB en índices no sobrevive costes en réplicas independientes; para oro sólo hay backtests de vendedor. Vale la pena probarlo porque es barato y nuestro tester tiene 5 años y OOS limpio, pero con expectativas bajas.

## 4. Reversión a la media de corto plazo

- **Ma et al. (2025)** (ver §2): en oro/plata chinos hay también **reversión intradía**, atribuida a liquidez excesiva de operadores desinformados.
- **Baltussen et al. (2021):** el momentum intradía **revierte en 1-2 días** en commodities ⇒ fade al día siguiente de días extremos.
- **Honarvar (AEA 2017, acciones):** la reversión de corto plazo es la compensación por proveer liquidez y **es más intensa cuando el VIX es alto**. <https://aeaweb.org/conference/2017/preliminary/paper/rSfnzi9z>
- Estudio 2003 (Global Business & Finance Review) sobre futuros de oro y plata: reversiones diarias mayores tras movimientos negativos. Antiguo.
- **Sobti (2024, working paper)**: saltos intradía en GC y GLD 2010-2018; más saltos negativos que positivos; las noticias macro programadas son el principal predictor de saltos. No mide reversión posterior.
- Practicantes (Unger Academy): fade de rupturas del máximo/mínimo de la sesión previa en futuros de oro, ~650 operaciones, sin rigor estadístico ni costes. RSI(2) de Connors: documentado en índices de acciones, **no encontré evidencia seria en oro**.

**Valoración:** evidencia general (acciones, China) de que los movimientos grandes *sin noticia* tienden a revertir parcialmente y de que los movimientos *con noticia* tienden a continuar. Es la intuición más defendible, pero no hay estudio de oro que la cuantifique a H1/M15.

## 5. Régimen de volatilidad y eventos macro

- **Gestión por volatilidad (Moreira y Muir 2017; Kim-Tse-Wald 2016):** el escalado por volatilidad mejora el Sharpe de factores y explica gran parte del TSMOM. Para nosotros: es una regla de **tamaño**, no de entrada.
- **Compresión → ruptura (NR4/NR7, "squeeze"):** la compresión predice *expansión* de volatilidad (agrupamiento de volatilidad, bien establecido), **no la dirección**. No encontré ningún estudio académico de NR7 en futuros. La dirección sólo la da la propia ruptura.
- **Momentum intradía más fuerte en días volátiles / con noticias** (Gao et al.; Jin et al.) ⇒ la volatilidad sirve como *condicionante* de las reglas de momentum.
- **FOMC:** Awartani, Hussain y Virk (2024, Int. Rev. Financial Analysis): con datos de alta frecuencia, el ajuste de precio y volatilidad del oro **continúa más allá de 5 minutos** tras la sorpresa del FOMC (más sensible a sorpresas dovish) ⇒ posible ineficiencia de corto plazo. Malhotra (Yale, tesis 2023): +1,09 % por punto de sorpresa a 2 días, p=0,083 (débil). El *pre-FOMC drift* de Lucca-Moench es de acciones; los autores **no lo encuentran en otras clases de activo**. <https://pure.kfupm.edu.sa/en/publications/how-do-the-gold-intra-day-returns-and-volatility-react-to-monetar/> · <https://www.bostonfed.org/economic/conf/Macro-Finance-2012/presentations/lucca.pdf>
- **NFP/CPI:** Elder, Miao y Ramchander (2012, J. Banking & Finance), futuros de oro/plata/cobre 2002-2008: reacción rápida y significativa, NFP y 8:30 NY las más fuertes; sorpresas positivas de actividad bajan el oro. Cai, Cheung y Wong (2001, JFM): empleo, PIB, CPI dominan la volatilidad de GC. Análisis de FXStreet (2022): a 4 h del NFP ya no hay relación con la sorpresa (es decir, la deriva post-noticia, si existe, es corta). <https://mountainscholar.org/handle/10217/206884>

**Valoración:** hay evidencia de que la reacción del oro a FOMC no es instantánea; para NFP/CPI la reacción es rápida y la continuación a horas es dudosa. Requiere calendario económico externo (fechas/horas; idealmente consenso para medir sorpresa, que no tenemos — usar el propio movimiento de los primeros minutos como proxy de sorpresa).

## 6. Predictores cruzados intradía

- **Futuros lideran el descubrimiento de precio del oro** frente a spot OTC y ETF (J. Futures Markets 2021, datos 1997-2014). Para nosotros no es explotable: el CFD del broker ya replica el futuro con latencia de milisegundos. <https://ideas.repec.org/a/wly/jfutmk/v41y2021i7p1092-1123.html>
- **Plata:** en datos de 15 min, la plata soporta la mayor parte del ajuste del spread oro/plata (es el oro el que "lidera"). No hay evidencia de que la plata anticipe al oro a minutos-horas. 
- **USD (DXY) y rendimientos reales (TIPS):** relación contemporánea fuerte y bien conocida a horizontes diarios o más, pero **no encontré ningún estudio de lead-lag a minutos-horas**; en mercados tan líquidos cualquier adelanto sería de segundos. Útil como *contexto de régimen* (p. ej. tendencia diaria del real yield), no como disparador intradía.
- **Risk-off en renta variable:** sin evidencia intradía específica.

**Valoración:** ningún predictor cruzado tiene evidencia suficiente para entrar en el shortlist. No merece la pena conseguir datos externos para esto por ahora.

---

## 7. Shortlist: 8 reglas concretas para el tester (ordenadas por prometedoras)

Convenciones: horas en **servidor**; barras M5 salvo que se diga; `ATRd` = ATR(14) en D1; `C_t` = cierre de la barra a la hora t. Coste 0,32 USD por ida y vuelta. Para todas, reportar ventaja media por operación (USD/oz) vs benchmark, IS 2021-2023 y OOS 2024-2026, y la ventaja *neta de coste*.

### R1. Deriva horaria "Asia sube / EE. UU. no" (efecto de sesión)
- **Long** a la apertura de la barra de **01:05** (tras la reapertura de Globex y el ensanchamiento de spread del rollover); salida a las **10:00** (apertura Londres). Variante B: entrada 03:00 (≈ apertura Shanghai), salida 10:00. Variante C (corto): short 16:30→23:00.
- Horizonte: ~9 h. Datos: sólo OHLC.
- **Benchmark obligatorio:** long de igual duración a hora aleatoria del mismo día (no el benchmark de "misma hora"), y además restar la deriva media por hora de toda la muestra.
- Evidencia: tesis CBS + WGC/Steer + GLD overnight. Débil-media; probable sesgo alcista 2021-2026. Prometedora por la relación movimiento/coste.

### R2. Filtro de tendencia D1 (TSMOM) con tenencia de días
- Señal a las 01:05: `s = sign(C_D1[-1] − C_D1[-21]) + sign(C_D1[-1] − C_D1[-63])` (cierres diarios a 00:00). Long si `s = +2`, short si `s = −2`, nada en otro caso.
- Salida: a 1, 3 y 5 días (probar los tres), o cuando cambie `s`.
- Uso doble: como regla propia y como **filtro** de lado para cualquier entrada M15 (sólo operar en el lado de `s`).
- Evidencia: MOP 2012, Hurst et al. 2017, Bartsch et al. (sobrevive SPA en oro). Debilitada post-2009. Coste despreciable.

### R3. Momentum intradía hacia el settlement de COMEX
- `ROD = C_20:00 / C_00:00(día) − 1` (desde el cierre NY previo hasta 30 min antes del settlement).
- Si `|ROD| > p70` de los últimos 60 días: entrar en la barra de 20:00 en el sentido de `ROD`, salir a las **20:30**. Variante: salida 21:00.
- Variante Gao: predictor = `C_15:50 / C_00:00 − 1` (incluye la apertura NY 15:20-15:50).
- Evidencia: Baltussen et al. 2021 (60+ futuros, incluye commodities), Gao et al. 2018, Ma et al. 2025 (oro SHFE). Fuerte en general, sin cifra para oro; ventaja esperada pequeña ⇒ el filtro de |ROD| grande es clave.

### R4. Fade del día siguiente tras día extremo (reversión de Baltussen)
- Si el movimiento del día previo (00:00→00:00) cumple `|C_D1[-1] − C_D1[-2]| > 1,5·ATRd`: entrar a las 03:00 en **contra** de ese día, salir a las 23:00 (o a 2 días). Excluir si el día previo tuvo FOMC/NFP/CPI (los movimientos con noticia tienden a persistir).
- Evidencia: Baltussen (reversión en ~2 días), Ma et al. (reversión por liquidez desinformada). Media-débil.

### R5. Continuación post-evento macro (FOMC, NFP, CPI)
- **Requiere calendario externo** (fecha y hora de FOMC 21:00, NFP/CPI 15:30 servidor).
- `m = C_{t0+15min} − O_{t0}` (t0 = barra de la publicación). Si `|m| > 1,0·ATR(14,M15)`: entrar en el sentido de `m` al cierre de la barra t0+15min, salir a t0+2 h y a t0+4 h (probar ambos). Para FOMC, salir también al día siguiente 03:00.
- Evidencia: Awartani et al. 2024 (ajuste del oro al FOMC dura >5 min), Elder et al. 2012. La continuación a horas de NFP es dudosa (FXStreet: nula a 4 h). Media-débil.

### R6. Ruptura del rango asiático en la apertura de Londres
- Rango: máx/mín de **03:00-09:59**. Desde 10:00 hasta 13:00, orden stop en `máx + 0,1·ATR(14,M15)` y `mín − 0,1·ATR(14,M15)` (OCO, 1 operación/día).
- Filtro: operar sólo si `0,30 % ≤ (máx−mín)/precio ≤ 1,60 %`. SL lado opuesto (tope 0,6 %), TP 2,5R, cierre forzado 23:00.
- Para el tester de entradas: evaluar la *entrada* con salida temporal fija (fin de día) además de la geometría SL/TP.
- Evidencia: sólo backtest de vendedor (PF ~1,37, 2023-2026). Débil.

### R7. Banda de ruido intradía (Zarattini "Beat the Market") adaptada
- Apertura de día `O = Open(01:00)`. Para cada barra a la hora τ: `σ(τ) = media de 14 días de |C_τ/O − 1|`. Banda superior `O·(1+σ)`, inferior `O·(1−σ)`.
- Sólo evaluar a HH:00 y HH:30 entre 10:00 y 22:00: long si `C > banda sup.`, short si `C < banda inf.`; salida cuando el precio vuelve dentro de la banda (o a VWAP diario si se aproxima con volumen de ticks) o a las 23:00.
- Evidencia: sólo SPY; réplicas de ORB en índices pierden la ventaja tras costes. Débil para oro, pero es la versión "sistematizada" de nuestra entrada actual de ruptura y es útil como comparación.

### R8. Fade de barra extrema sin noticia en régimen de alta volatilidad
- En H1: si `|C − O| > 2,5·ATR(14,H1)` de la barra recién cerrada, **y** no hay evento macro programado en ±1 h (calendario externo; sin calendario, excluir 15:00-16:00 y 21:00-22:00), **y** `ATR(14,H1) > mediana de 60 días`: entrar en contra al cierre de la barra, salir a +4 h.
- Variante RSI(2): long si RSI(2,H1) < 5 y R2 = +2 (tendencia D1 alcista), salir cuando RSI(2) > 50 o a +8 h. Simétrico para short.
- Evidencia: Honarvar (reversión más fuerte con alta volatilidad, acciones), Ma et al. (reversión en oro chino), practicantes. Débil.

### Recomendaciones de prueba
1. Probar primero **R1, R2 y R3**: son las de mejor evidencia/explicación económica y no requieren datos externos.
2. Medir siempre en USD/oz por operación *y* en múltiplos del coste (0,32). Descartar cualquier regla con ventaja neta OOS < 0,3 USD/oz o con signo distinto entre IS y OOS.
3. Con ~8 reglas × variantes hay riesgo de *data snooping*: fijar las variantes **antes** de mirar OOS y aplicar al menos una corrección de Bonferroni o un White's Reality Check/SPA sobre el conjunto (como hicieron Bartsch et al.).
4. Controlar la beta alcista de 2021-2026: reportar cada regla también en su versión long-only vs short-only y vs deriva incondicional.
