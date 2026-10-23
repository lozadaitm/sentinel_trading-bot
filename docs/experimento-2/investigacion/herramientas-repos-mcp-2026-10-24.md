# Herramientas para HyperGrinder (XAUUSD / MT5): investigación y recomendación

Fecha: 2026-10-24. Restricciones: Python + paquete MetaTrader5, numpy/pandas (sin statsmodels), Windows Server, 4 núcleos y 8 GB de RAM. Datos actuales: Dukascopy M5, broker, FRED, COT.

Nota de rigor: verifiqué en la web lo marcado con [V]. Lo marcado con [C] sale de conocimiento previo (hasta 2026) y conviene confirmarlo en la URL antes de instalar. No di cifras de estrellas cuando no pude verificarlas.

---

## 0. Resumen ejecutivo

El cuello de botella del proyecto no es la falta de motor de backtest (ya tenemos simuladores propios). Es la falta de **pruebas formales contra el data-snooping** y la falta de una **medición del costo real** (spread o slippage por hora). La mayor ganancia de certeza por unidad de esfuerzo sale de:

1. `arch`: GARCH/HAR, bootstrap estacionario o circular (Politis-Romano), **SPA de Hansen, StepM de Romano-Wolf y Model Confidence Set**.
2. Una implementación de **PBO/CSCV + Deflated Sharpe + PSR/MinTRL** (`pypbo`, o mejor, unas 150 líneas propias en numpy siguiendo los papers).
3. **Ticks de Dukascopy con bid/ask** y, sobre todo, **ticks propios del broker con `mt5.copy_ticks_range`**, para medir el spread a la 01:00 servidor.
4. `statsmodels`: regresiones con errores HAC (Newey-West), tests de raíz unitaria y Markov-switching.
5. GVZ (vol implícita del oro, en FRED) como regresor de la vol prevista.

Todo esto es gratis y cabe sin problema en 8 GB.

---

## 1. Librerías Python

### 1.1 Backtesting e investigación

| Herramienta | Licencia | Madurez y mantenimiento | Qué nos aporta | Veredicto |
|---|---|---|---|---|
| **vectorbt** (OSS) — https://github.com/polakowo/vectorbt | Apache-2.0 + Commons Clause [C] | Muy popular. La versión OSS recibe poco desarrollo nuevo: el esfuerzo está en PRO [V] | Barridos masivos de parámetros vectorizados con numba. Útil para generar la **matriz de N variantes × T retornos** que piden SPA y PBO | Opcional. Nuestros simuladores ya hacen esto. Numba pesa, pero funciona en Windows |
| **vectorbt PRO** — https://vectorbt.pro | Comercial, por membresía (mensual, anual o vitalicia). Uso comercial requiere acuerdo aparte [V] | Activo | Simulación con datos tick/OHLC más rica, *portfolio optimization* y *splitters* (purged CV) | No vale el costo para nosotros |
| **backtesting.py** — https://github.com/kernc/backtesting.py | AGPL-3.0 [C] | Maduro y estable | Backtest de barra simple con optimizador. Es bar-close, el mismo límite que nuestro arnés | No aporta |
| **nautilus_trader** — https://github.com/nautechsystems/nautilus_trader | LGPL-3.0 [C] | Muy activo (núcleo en Rust) [C] | Simulación **event-driven a nivel tick, con libro y latencias**. Es lo único de la lista que resolvería nuestro punto ciego intra-vela (spikes) | A medio plazo, para estudiar spikes con ticks de Dukascopy. Curva de aprendizaje alta. No tiene adaptador MT5 oficial |
| **zipline-reloaded** — https://github.com/stefan-jansen/zipline-reloaded | Apache-2.0 | Mantenido por la comunidad | Orientado a acciones de EE. UU. y datos diarios | No |
| **bt** — https://github.com/pmorissette/bt | MIT | Estable | Asignación de cartera | No |
| **Lean / QuantConnect** — https://github.com/QuantConnect/Lean | Apache-2.0 | Muy activo | Motor C#. La nube tiene datos de CFD/oro de OANDA | No: es otro ecosistema |
| **qlib** (Microsoft) — https://github.com/microsoft/qlib | MIT | Activo | ML de alfa cross-sectional en acciones | No aplica a un solo instrumento |
| **FinRL** — https://github.com/AI4Finance-Foundation/FinRL | MIT | Activo pero académico | Aprendizaje por refuerzo. Alto riesgo de sobreajuste | No |

### 1.2 Econometría y series de tiempo

| Herramienta | Licencia | Qué nos aporta concretamente |
|---|---|---|
| **arch** — https://github.com/bashtage/arch · docs https://arch.readthedocs.io | NCSA (tipo BSD) | v8.0.0 (oct-2025): wheels para Py 3.14, soporte de NumPy 2.4 y pandas 3 [V]. Ofrece: **GARCH/EGARCH/GJR/FIGARCH**, media **HAR** (`HARX`), distribuciones t y skew-t, pronóstico de varianza multi-paso; **bootstraps** IID, Stationary (Politis-Romano), Circular Block y Moving Block, con selección óptima del bloque (`optimal_block_length`); **comparación múltiple: `SPA` (Hansen 2005, que incluye el Reality Check de White como caso), `StepM` (Romano-Wolf) y `MCS` (Hansen-Lunde-Nason)**; tests de raíz unitaria y cointegración. **Es la pieza número uno.** No depende de statsmodels para lo esencial [C]. Mantenedor: Kevin Sheppard |
| **statsmodels** — https://github.com/statsmodels/statsmodels | BSD-3 | OLS/GLM con **errores HAC/Newey-West**, ARIMA, **MarkovRegression/MarkovAutoregression** (régimen), VAR, Ljung-Box, tests de Diebold-Mariano (vía extensiones). Instalarlo sustituye código casero que hoy no está validado |
| **linearmodels** — https://github.com/bashtage/linearmodels | NCSA | IV, panel y Fama-MacBeth. Poco útil para un solo activo |
| **hmmlearn** — https://github.com/hmmlearn/hmmlearn | BSD | HMM gaussianos (ya hicimos un HMM casero). Sirve para validar el nuestro. Mantenimiento lento [C] |
| **ruptures** — https://github.com/deepcharles/ruptures | BSD-2 | Detección de **cambios estructurales** (PELT, Binseg) sobre vol y spread. Útil para fechar regímenes sin mirar adelante (usarlo solo de forma *rolling*) |
| **tsfresh** | MIT | Extracción masiva de features. Riesgo de minería de datos sin control; si se usa, va con PBO |
| **sktime** — https://github.com/sktime/sktime | BSD-3 | Framework unificado. Incluye splitters temporales |
| **darts** — https://github.com/unit8co/darts | Apache-2.0 | Pronóstico con DL. Pesado (torch) |
| **Nixtla statsforecast** — https://github.com/Nixtla/statsforecast | Apache-2.0 | ARIMA/ETS/GARCH rápidos con numba. **TimeGPT es SaaS de pago**; **neuralforecast** requiere torch. Para la vol, HAR en `arch` basta |

### 1.3 López de Prado: purged CV, DSR, PSR, triple barrera y meta-labeling

- **mlfinlab** (Hudson & Thames): **hoy es propietario, "all rights reserved", con uso comercial prohibido sin licencia** [V]. Las versiones antiguas (0.0.x) eran BSD-3 [V]. Los forks (p. ej. `famlafl`) arrastran la misma licencia [V]. **Evitar.**
- **mlfinpy** — https://pypi.org/project/mlfinpy/ — MIT, reescritura desde cero inspirada en mlfinlab [V]. Hay que confirmar qué módulos trae (barras, triple barrera, CV).
- **pypbo** — https://github.com/esvhd/pypbo — PBO (CSCV), PSR, MinTRL, MinBTL y **Deflated Sharpe**. Unas 138★ [V]. **Riesgos:** sin tests (su propio TODO lo dice), depende de statsmodels y seaborn, y tiene poca actividad [V]. Sirve como **referencia** para contrastar una implementación propia.
- **oos-lab** — https://github.com/OutOfSampleLab/oos-lab — dice incluir PSR, DSR, PBO-CSCV y el *haircut* de Harvey-Liu [V, solo por la descripción].
- **fynance** (módulo `research.overfit`), con CSCV — https://fynance.readthedocs.io [V].
- **R `pbo`** (CRAN), la implementación de referencia de CSCV [V], útil para validar resultados.
- **skfolio** — https://github.com/skfolio/skfolio — BSD-3. Incluye `CombinatorialPurgedCV` y `WalkForward` con estilo scikit-learn. Es la fuente abierta y mantenida más limpia para **purged / combinatorial CV** [C].
- **timeseriescv** (Sam Arnesen): purged k-fold mínimo. Abandonado [C].

**Recomendación:** implementar en numpy (sin dependencias) PSR, DSR, MinTRL y PBO-CSCV. Son fórmulas cerradas de Bailey y López de Prado (2012, 2014) y Bailey, Borwein, López de Prado y Zhu (2015/2017). Después se validan contra `pypbo` y R `pbo` con los mismos datos. El **número de ensayos N** para el DSR debe salir del registro real de variantes probadas: los barridos de la carpeta `bot_backtesting/results/`.

### 1.4 Riesgo y cartera

| Herramienta | Licencia | Aporte |
|---|---|---|
| **quantstats** — https://github.com/ranaroussi/quantstats | Apache-2.0 | Tearsheet HTML (drawdowns, Sharpe/Sortino, retornos mensuales) en una línea. Útil para reportes |
| **pyfolio-reloaded** — https://github.com/stefan-jansen/pyfolio-reloaded | Apache-2.0 | Tearsheets más académicos. Arrastra empyrical |
| **Riskfolio-Lib** — https://github.com/dcajasn/Riskfolio-Lib | BSD-3 | Optimización de cartera (CVaR, risk parity). Útil solo si combinamos varias estrategias o satélites |
| **skfolio** | BSD-3 | Cartera más CV purgada (ver arriba) |

---

## 2. Datos gratis o baratos para el oro

| Fuente | Acceso | Utilidad para nosotros |
|---|---|---|
| **Dukascopy ticks (bid/ask, volumen)** | Gratis. Feed binario por hora (`.bi5`, LZMA, registros de 20 bytes; **el mes del URL empieza en 0**) [V]. Historia del oro desde mayo de 2003 [V]. Herramientas: `dukascopy-node` (npm), **tickterial** (Python, devuelve ask/bid por tick) https://github.com/drui9/tickterial [V], **TickVault** https://github.com/keyhankamyar/TickVault [V], `theorycraft-trading/dukascopy` [V] | **Historia del spread por hora del día**, incluida la ventana de rollover y la 01:00 servidor. **Atención:** el spread ECN de Dukascopy es más estrecho que el de un broker retail (en un caso documentado, ~0,2 frente a ~0,47) [V]. Sirve como **piso** y como **perfil horario relativo**, no como costo absoluto |
| **Ticks del propio broker vía MT5** | Gratis: `mt5.copy_ticks_range(symbol, from, to, mt5.COPY_TICKS_ALL)` devuelve bid/ask/last/flags. La profundidad depende del servidor del broker (a menudo semanas o meses) [C] | **La fuente de verdad del costo.** Recomiendo un **colector propio** que guarde ticks diarios en parquet (unos MB por día). En pocas semanas tendremos la distribución de spread y slippage a la 01:00 servidor, en noticias y en rollover. Además, `symbol_info().spread` y las barras M1 de MT5 traen una columna `spread` (el mínimo de la barra) |
| **CBOE GVZ** | FRED `GVZCLS`, diario desde 2008-06-03 [V] — https://fred.stlouisfed.org/series/GVZCLS | Vol implícita a 30 días del oro (opciones sobre GLD). **El mejor regresor exógeno para HAR-X** y para el "freno" de riesgo. Ya tenemos el cliente de FRED |
| **GLD / IAU holdings** | SPDR publica un histórico diario de toneladas (descarga XLSX/CSV en spdrgoldshares.com) [C]. iShares publica las tenencias de IAU [C] | Flujo de ETF. Señal lenta (días o semanas); como contexto de régimen |
| **SGE (Shanghai)** | Precio de referencia *Shanghai Gold Benchmark* diario en sge.com.cn [C]. La **prima** se calcula como SGE (CNY/g) frente a XAUUSD × USDCNY | Demanda china. Lenta. Scraping frágil |
| **LBMA Gold Price AM/PM** | JSON público en prices.lbma.org.uk [C]. Histórico gratis con uso restringido por licencia (ICE/LBMA) | Referencia de fixing. Útil para estudiar el efecto horario de las 10:30 y 15:00 de Londres |
| **Índice GPR (Caldara-Iacoviello)** | Gratis, diario y mensual, XLS en https://www.matteoiacoviello.com/gpr.htm [C] | Riesgo geopolítico. Régimen "refugio" |
| **Sorpresas económicas** | El Citi ESI es propietario (Bloomberg). Alternativas abiertas: construir un índice propio **(dato real − consenso)/σ** a partir del calendario; o usar el **Atlanta Fed GDPNow** o el NY Fed Nowcast; o los *Economic Policy Uncertainty* en FRED | Sustituto razonable del ESI |
| **Calendario con consenso y dato real** | **Trading Economics API**: consenso = promedio de economistas; exporta JSON/CSV; **de pago** para el uso serio [V]. **Finnhub** `/calendar/economic`: premium [C]. **FMP** `economic_calendar`: plan gratis con límites [C]. **ForexFactory**: sin API oficial; existe el feed semanal JSON `nfs.faireconomy.media/ff_calendar_thisweek.json` [C] y scrapers de Apify, **algunos sin el campo "actual"** [V]. TradingView: scraper sobre JSON público [V] | Hoy usamos calendario para los satélites. Para medir la **sorpresa** se necesita el dato real en el minuto exacto: FF en JSON más una verificación posterior con FRED (los datos de EE. UU. de BLS y BEA quedan en FRED/ALFRED con su fecha de publicación) |
| **Sentimiento de noticias** | **GDELT** (gratis, cada 15 min, DOC/GEO API) https://www.gdeltproject.org. **Alpha Vantage NEWS_SENTIMENT** (clave gratis con unas 25 peticiones al día según terceros [V]) | Ruido alto. Útil como **detector de estrés** (picos de volumen de noticias sobre guerra o la Fed), no como dirección |
| **Posicionamiento retail** | **IG Client Sentiment**: API de IG con cuenta (demo gratis) [C]. **Myfxbook Community Outlook**: API con login gratuito [C]. **OANDA orderBook/positionBook**: API v20 con cuenta; históricamente limitada a ciertos instrumentos y cuentas [C] | Contrarian débil. Prioridad baja |
| **COT CFTC** | Ya lo tenemos | — |

---

## 3. Servidores MCP

Para el **arnés de agentes de vigilancia** (vol prevista, calendario y sorpresas, riesgo; **no dirección**):

| MCP | Qué hace | Confiabilidad | Uso propuesto |
|---|---|---|---|
| **Qoyyuum/mcp-metatrader5-server** (`mt5mcp`) — https://github.com/Qoyyuum/mcp-metatrader5-server | Datos de mercado, órdenes e historial vía el paquete MetaTrader5. FastMCP, Python 3.11+, requiere el terminal en Windows. ~136★ y 53 forks [V] | Comunitario. **Expone herramientas de trading:** si se usa, hay que **quitar o deshabilitar las tools de envío de órdenes** o correrlo contra una cuenta demo | Lectura de ticks, spread actual y posiciones abiertas para el agente vigía |
| **ariadng/metatrader-mcp-server** — https://github.com/ariadng/metatrader-mcp-server | Cliente MT5 más un servidor WebSocket de cotizaciones y REST. v0.5.1; **algunas tools devuelven valores demo** [V] | Inmaduro | No |
| **amirkhonov/metatrader5-mcp**, **meta-trader-mcp** (PyPI, "risk interceptor"; Windows no probado por el mantenedor) [V] | Similares | Inmaduros | No |
| **Alternativa recomendada:** un **MCP propio de solo lectura** (unas 100 líneas con FastMCP) que envuelva nuestras funciones: `spread_now`, `vol_forecast_har`, `next_events`, `exposure` | Control total, cero riesgo de órdenes | — | **Sí** |
| **FRED MCP** (stefanoamorelli) — https://github.com/stefanoamorelli/fred-mcp-server | Búsqueda y descarga de series FRED. AGPL-3.0. No oficial [V] | Bueno para consultas ad-hoc | GVZ, tasas reales, DXY proxy |
| **Alpha Vantage MCP (oficial)** — https://mcp.alphavantage.co | Remoto (`/mcp?apikey=`) o `uvx alphavantage-mcp`. Incluye news sentiment, FX y commodities [V] | Oficial del proveedor. El límite gratis es muy bajo | Sentimiento de noticias puntual |
| **Massive (antes Polygon) MCP** — https://github.com/massive-com/mcp_massive (antes polygon-io/mcp_polygon, MIT) [V] | API completa de Massive (acciones, opciones, FX). Experimental [V]. Requiere plan de pago para datos útiles | Oficial | Bajo valor para el oro spot |
| **Financial Datasets MCP** — https://github.com/financial-datasets/mcp-server [C] | Fundamentales y precios de acciones | — | No aplica |
| **Yahoo Finance MCP** (varios comunitarios) [C] | Precios de GC=F, GLD y ^GVZ con retraso | Scraping no oficial | Respaldo de GVZ intradía |
| **TradingView MCP** (comunitarios) [C] | Screener e indicadores, no oficial | Frágil (ToS) | No |
| **Dukascopy MCP** (listado en glama) [V] | Descarga de ticks e históricos | Comunitario | Prescindible: mejor un script |

**Diseño sugerido del arnés:** agentes **sin herramientas de orden**. (1) *Vol-watch*: HAR-X con GVZ, alerta si la vol prevista supera el percentil 90. (2) *News-watch*: calendario de FF/TE, ventana ±N minutos y cálculo de la sorpresa cuando sale el dato. (3) *Risk-watch*: spread actual frente a su percentil horario histórico (colector de ticks) y exposición abierta. Su salida es solo un **flag de freno** que el bot ya consume, nunca una dirección.

---

## 4. Conjunto mínimo recomendado (orden de instalación)

1. **`arch`** (`pip install arch`): HAR/GARCH de vol, bootstrap estacionario con bloque óptimo y **SPA/StepM/MCS** para decidir si la mejor variante de un barrido le gana a la referencia (p. ej. no operar, o la configuración actual) después de corregir por data-snooping. **Es la prueba de certeza que hoy nos falta.**
2. **`statsmodels`**: HAC/Newey-West en las regresiones de eventos y del estudio econométrico, Markov-switching y diagnósticos. Valida nuestro código casero.
3. **PBO/CSCV + DSR + PSR + MinTRL**: módulo propio en numpy dentro de `bot_backtesting/` (sin dependencias), validado contra **`pypbo`** (https://github.com/esvhd/pypbo) o R `pbo`. Aplicar el DSR con N igual al número real de variantes probadas.
4. **Colector de ticks del broker** con `mt5.copy_ticks_range`, a parquet diario. Más **ticks de Dukascopy** (tickterial o dukascopy-node) para la historia del perfil horario del spread. Responde: ¿cuánto cuesta realmente entrar a la 01:00 servidor?
5. **GVZ desde FRED** (`GVZCLS`) como regresor en el HAR-X y en el freno de riesgo. Costo cero: ya tenemos FRED.
6. **`skfolio`**, solo por `CombinatorialPurgedCV` y `WalkForward` (o `ruptures` si se priorizan los regímenes).
7. **`quantstats`**: tearsheets estandarizados para comparar variantes.
8. (Opcional, a medio plazo) **nautilus_trader**, para un backtest tick a tick con los ticks de Dukascopy y el spread real. Es lo único que ataca el punto ciego intra-vela del arnés bar-close.

**Recursos:** todo cabe en 4 núcleos y 8 GB. `arch` y `statsmodels` son ligeros. Los ticks de Dukascopy del oro ocupan unos 1-3 GB por año en parquet comprimido [C], así que hay que procesarlos por mes. Evitar torch, darts, neuralforecast y FinRL en este servidor.

**No recomendado:** mlfinlab (licencia propietaria), vectorbt PRO (costo y poco valor adicional), FinRL, qlib y TimeGPT (SaaS), y MCPs MT5 comunitarios con permisos de orden.

---

## Fuentes principales
- arch v8.0.0 (Zenodo): https://zenodo.org/records/1344905/latest · repo: https://github.com/bashtage/arch
- pypbo: https://github.com/esvhd/pypbo · fynance overfit: https://fynance.readthedocs.io/en/master/_modules/fynance/research/overfit.html · R pbo: https://cran.r-project.org/package=pbo
- mlfinlab (licencia): https://github.com/closedloop/mlfinlab · mlfinpy: https://pypi.org/p/mlfinpy · famlafl: https://pypi.org/project/famlafl/
- vectorbt PRO FAQ: https://vectorbt.pro/faq
- Dukascopy: tickterial https://github.com/drui9/tickterial · TickVault https://github.com/keyhankamyar/TickVault · formato bi5: https://support.tickstory.com/viewtopic.php?p=4913 · nota de spread: https://forge.mql5.io/aron3/Warrior_EA/src/branch/main/research/dukas.py
- GVZ: https://fred.stlouisfed.org/series/GVZCLS
- Calendario: https://tradingeconomics.com/calendar · https://apify.com/xtracto/forexfactory-calendar
- MCP MT5: https://www.typingmind.com/mcp/qoyyuum-mcp-metatrader5-server · https://docsearch.algolia.com/mcp/docs/repo/ariadng/metatrader-mcp-server · https://www.pypi.org/project/meta-trader-mcp/
- FRED MCP: https://glama.ai/mcp/servers/@stefanoamorelli/fred-mcp-server/blob/41a5270f604aef6d81d0c33a9f2054be0d43a4dd/README.md
- Alpha Vantage MCP: https://mcp.alphavantage.co/
- Massive/Polygon MCP: https://glama.ai/mcp/servers/polygon-io/mcp_massive · https://mcpservers.org/servers/polygon-io/mcp_polygon
