# Fase 1 — Investigación E, F, G (APILayer, MiroFish, AMD / Power of 3)

Fecha de la investigación: 2026-10-13. Solo investigación web: no se tocó código, MT5 ni scripts del bot.
Nota: los precios y límites cambian a menudo. Se tomaron de las páginas oficiales de precios en esta fecha.

---

## E. APILayer: ¿nos sirve alguna de sus APIs?

### Qué es APILayer
Es un "supermercado" de APIs de pago con más de 40 productos propios (marketstack, mediastack, coinlayer, ipstack, weatherstack, etc.) y un marketplace de terceros.
Fuente: https://apilayer.com/

En su marketplace, la categoría Finanzas solo tiene 14 APIs: 4 de divisas, 4 de banca, 1 de contabilidad, 1 de inversión y 4 en "otros". **No existe ninguna categoría de calendario económico, metales, materias primas ni sentimiento.**
Fuente: https://marketplace.apilayer.com/

### APIs revisadas

| API | Qué da | Frecuencia de actualización | Gratis | De pago (mensual) | ¿Mejora lo que ya tenemos? |
|---|---|---|---|---|---|
| **currencylayer** | Tipos de cambio de 168 monedas, incluido oro "XAU" | Gratis: diaria u horaria (la propia página se contradice). Basic: horaria. Enterprise: cada 10 min. Enterprise+: cada 60 s | 100 peticiones/mes | Basic $14.99 (10k), Enterprise $59.99 (100k), Enterprise+ $99.99 (500k, 60 s) | **No.** El precio de MT5 es tick a tick y es el precio real al que opera el broker. Un dato de referencia que en el mejor caso llega cada 60 s no sirve para operar. |
| **Fixer** | Tipos de cambio de 170 monedas (la página no confirma XAU) | Gratis y Basic: horaria. Professional: 10 min. Professional Plus: 60 s | 100 peticiones/mes | Basic $14.99, Professional $59.99, Professional Plus $99.99 | **No**, por la misma razón. |
| **marketstack** | Acciones: fin de día, intradía (IEX, EE. UU.) y "commodity prices" solo desde el plan Professional. No menciona forex ni oro por nombre | Tiempo real (<15 min) solo desde Professional | 100 peticiones/mes | Basic $9.99, Professional $49.99, Business $149.99 | **No.** Está orientado a acciones de EE. UU. |
| **mediastack** | Noticias generales en JSON | Gratis: noticias "con retraso" (no dice cuánto). De pago: en vivo | 100 peticiones/mes | Standard $24.99 (10k), Professional $99.99, Business $249.99 | **Solo como insumo crudo.** No incluye análisis de sentimiento ni filtro financiero, así que habría que añadir un LLM que lo procese. |
| **Calendario económico** | No existe en APILayer | — | — | — | **Forex Factory sigue siendo la mejor opción** dentro de este análisis. |

Fuentes:
- currencylayer: https://currencylayer.com/product
- Fixer: https://fixer.io/product
- marketstack: https://marketstack.com/product
- mediastack: https://mediastack.com/product
- marketplace (sin calendario): https://marketplace.apilayer.com/

### ¿Metals-API se vendió o salió de APILayer?
- Metals-API **no aparece hoy en APILayer**. Su web dice "Made by Zyla Labs" y enlaza a zylalabs.com como su "API Hub". Fuente: https://metals-api.com/pricing
- **No encontré evidencia publicada de que APILayer lo vendiera.** No hay nota de prensa ni noticia que lo confirme, así que no lo afirmo. Lo que sí está verificado es que hoy lo opera o lo publica Zyla Labs, no APILayer.
- Precios actuales de Metals-API: desde $19.99/mes (2.500 llamadas, cada 10 min) hasta $149.99/mes (100k llamadas, cada 60 s). No hay un plan gratis claro. Fuente: https://metals-api.com/pricing
- Zyla API Hub también lista APIs de metales y de noticias con "sentimiento", pero son de terceros y de calidad desigual. Fuente: https://zylalabs.com/api-marketplace/top-search/Real%20Time%20Financial%20News%20and%20Sentiments%20API?page=6

### Veredicto E: **descartada** (con una nota sobre mediastack)
- Para precios: MT5 ya nos da el precio real del broker, tick a tick y gratis. Ninguna API de APILayer o Metals-API lo mejora, y en el mejor caso llegan con 60 s de retraso.
- Para el calendario: APILayer no tiene. Forex Factory se queda.
- Para noticias: mediastack sería una fuente cruda más. Requiere pagar al menos $24.99/mes por noticias en vivo y además un LLM que calcule el sentimiento. Solo valdría la pena si el futuro "agente scanner" del harness necesitara titulares, y hay alternativas especializadas en finanzas que convendría comparar antes.
- Costo de integración: bajo técnicamente (REST + JSON, un día), pero el beneficio es casi nulo. **No recomendado ahora.**

---

## F. MiroFish: qué es en realidad

### Datos verificables
- **Repo oficial:** https://github.com/666ghj/MiroFish. Hay forks y copias, como Grandlulu/MiroFish y mahi80/mirofish, que no son el original. Fuente: https://github.com/666ghj/MiroFish
- **Qué hace:** "motor de predicción por inteligencia de enjambre". Recibe material semilla (noticias, borradores de políticas, "señales financieras") y crea un mundo digital simulado con miles de agentes LLM que tienen personalidad y memoria propias. Esos agentes "conversan" como en una red social, y al final un agente redacta un informe de "predicción". Fuente: https://github.com/666ghj/MiroFish
- **Motor de fondo:** no es propio. Usa **OASIS** de CAMEL-AI, un simulador de redes sociales (tipo X o Reddit) con hasta 1 millón de agentes LLM, publicado en arXiv como "OASIS: Open Agent Social Interaction Simulations with One Million Agents". Ese paper reproduce fenómenos sociales como la difusión de información, la polarización y el efecto manada. **No trata de predecir precios.**
  - Repo de MiroFish: https://github.com/666ghj/MiroFish
  - Paper de OASIS: https://arxiv.org/abs/2411.11581
- **Dependencias:** necesita un LLM compatible con OpenAI (recomiendan qwen-plus de Alibaba, y el README advierte de su "alto consumo") y Zep Cloud para la memoria de los agentes. Fuente: https://github.com/666ghj/MiroFish
- **Licencia:** AGPL-3.0. Es copyleft fuerte: si se modifica y se ofrece como servicio en red, hay que liberar el código. Fuente: https://github.com/666ghj/MiroFish
- **Popularidad:** ~78,5k estrellas, ~12k forks, 322 commits y 63 issues abiertos al consultarlo. Fuente: https://github.com/666ghj/MiroFish
- **Respaldo:** el README dice que tiene "apoyo estratégico e incubación de Shanda Group" y el contacto es mirofish@shanda.com. Fuente: https://github.com/666ghj/MiroFish
  - Fuentes secundarias atribuyen la autoría a Guo Hangjiang ("BaiFu") y una financiación de unos 30 M de yuanes de Chen Tianqiao, fundador de Shanda. Esto **no lo pude verificar en fuente primaria**. Fuente: https://pasqualepillitteri.it/nl/news/21454/werkt-mirofish-echt-agentenzwerm-alternatieven
  - Otras notas hablan de "$4M en 24 horas". Fuente: https://emelia.io/hub/mirofish-ai-swarm-prediction
- **Paper propio:** no hay. **Benchmark de precisión:** no hay.
  - Las únicas demos son una simulación de opinión pública sobre la Universidad de Wuhan y un "final perdido" de la novela *Sueño en el pabellón rojo*. Los ejemplos financieros figuran como "próximamente". Fuente: https://github.com/666ghj/MiroFish

### Evidencia sobre su uso en mercados (escasa y débil)
- En un caso anecdótico, un desarrollador hizo 338 operaciones en Polymarket con +$4.266. El mismo artículo concluye que MiroFish **"no tiene ventaja en la microestructura financiera"** y que falla en mercados de menos de 15 minutos y en mercados poco líquidos. Fuente: https://www.abhs.in/blog/mirofish-1m-agents-why-trading-fails-public-opinion-wins-2026
- Según un resumen secundario, una prueba pequeña de un laboratorio de WPP sobre acciones acertó mal la dirección y ninguna de las 5 acciones elegidas estuvo entre las 5 mejores reales. **No pude abrir la fuente original**, así que es un dato no verificado. Fuente del resumen: https://pasqualepillitteri.it/tr/news/21447/mirofish-gercekten-ise-yariyor-mu-ajan-surusu-alternatifleri

### ¿Es creíble para predecir el precio del oro?
No. La "predicción" de MiroFish es un **escenario narrativo**: cómo reaccionaría una sociedad simulada a una noticia. No es un modelo entrenado con precios ni ha sido validado contra resultados reales del mercado. Las estrellas de GitHub miden el interés que despierta, no si acierta. Además, nuestro bot trabaja en M5/M15, un horizonte en el que hasta los artículos favorables admiten que la herramienta no tiene ventaja.

### ¿Podría ser un agente del harness?
Como mucho, sería un generador opcional de "escenarios de narrativa macro" que alimente el memo de decisión humana, con una etiqueta clara de "no es señal". Su costo es alto en tokens de LLM, depende de Zep Cloud y la licencia AGPL obliga a revisar cómo se distribuye. No debe intervenir en la entrada de OP1 ni en el riesgo.

### Veredicto F: **descartada** (para señales). Como mucho, un "investigar más" muy bajo en la lista para usarlo como generador de narrativas.
- No hay ni una sola medición pública de precisión, y su motor (OASIS) es un simulador social, no un modelo de precios.
- Las pruebas de terceros en trading son anecdóticas o negativas.
- Costo de integración: medio-alto (LLM caro, Zep, AGPL, mantenimiento) para un beneficio que no está demostrado.

---

## G. AMD / Power of 3 (ICT / Smart Money Concepts)

### Explicado en sencillo
La idea de ICT es que el día de trading tiene tres fases:
1. **Acumulación (A):** el precio se mueve de lado en un rango estrecho, típicamente durante la sesión asiática.
2. **Manipulación (M):** al abrir Londres, el precio rompe el rango asiático por un lado para "barrer" los stops que hay acumulados ahí. A esto lo llaman el "Judas swing", un movimiento falso.
3. **Distribución (D):** el precio se da la vuelta y hace el movimiento "real" en la dirección contraria, muchas veces hasta Nueva York.

La regla práctica que suele derivarse es esta: esperar a que el precio barra el máximo o el mínimo asiático, que vuelva a cerrar dentro del rango, y entrar en contra del barrido.
- Fuente: https://completetradersedge.com/ict-power-of-3-accumulation-manipulation-distribution/
- Fuente: https://takeprofitapp.com/en/learn/ict-asian-range-trading

### Evidencia: qué es serio y qué es anécdota
**Base académica indirecta (seria, pero no prueba AMD):**
- Osler (Fed de Nueva York, Staff Report 150, 2002) halló que en divisas los stop-loss se agrupan en ciertos niveles. Cuando el precio llega a esos niveles se producen "cascadas" de precio rápidas que se refuerzan a sí mismas. El efecto es estadísticamente significativo durante horas, pero no durante días. Es decir, el "barrido de liquidez" existe como fenómeno. Pero **la cascada empuja en la dirección de la ruptura**, no necesariamente hacia una reversión. Fuente: https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr150.pdf
- Osler (Staff Report 125) también halló que las órdenes se concentran en números redondos. Fuente: https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr125.pdf
- En oro existe estacionalidad intradía: en la sesión de Tokio domina el flujo "no informado" y en Nueva York el "informado" (Iwatsubo, Watkins y Xu, *Journal of Commodity Markets*, 2018, con datos de futuros). Esto encaja con la idea de que Asia es más tranquila, pero no prueba el patrón AMD. Fuente: https://www.rieti.go.jp/en/publications/summary/17110007.html

**Pruebas directas de ICT/SMC:**
- **No encontré ningún estudio revisado por pares** que valide ICT/SMC.
- Una página de revisión cita un preprint de SSRN de 2026: "Smart Money or Costly Folklore? A Systematic Evaluation of ICT/SMC Trading Rules in G10 FX" (S. Mahadzva). Según esa reseña, concluye "no evidence that ICT/SMC concepts work as literally taught". También dice que tres reglas de barrido distintas coincidieron en que **tras un barrido el precio tiende a seguir en la misma dirección, no a revertir**.
  - **Advertencia:** SSRN devolvió error 403 y no pude leer el abstract directamente, así que esto queda por verificar.
  - Reseña: https://thortradecopier.com/blog/does-ict-smart-money-concepts-work
  - DOI citado: https://doi.org/10.2139/ssrn.7430998
- La misma página simuló un paseo aleatorio y vio que los "fair value gaps" se rellenan igual de a menudo que niveles elegidos al azar (83,4% frente a 83,5%). Eso sugiere que la tasa de relleno por sí sola no demuestra ninguna ventaja. Fuente: https://thortradecopier.com/blog/does-ict-smart-money-concepts-work

**Backtests de vendedores (anecdóticos y con conflicto de interés):**
- Take Profit App dice que en XAUUSD obtuvo 175 setups, 68% de aciertos y un profit factor de 2,34 (2024–2025, M15/H1). No declara costos ni drawdown, no publica la lista de operaciones y sus números no cuadran entre sí: con 68% de aciertos y un R:R de 1,8 el profit factor debería rondar 3,8. Además vende señales y usa enlaces de afiliado de un broker. Fuente: https://takeprofitapp.com/en/learn/ict-asian-range-trading
- Backtrex dice que en EURUSD + XAUUSD (2019–2024, 1.247 operaciones) obtuvo un profit factor de 1,68. Es una página comercial. Fuente: https://backtrex.com/en/blog/liquidity-sweep-strategy-backtest-results

**Conclusión de la evidencia:** el fenómeno del barrido de stops es real, pero **no está demostrado que el barrido prediga una reversión**. La única prueba sistemática encontrada, aún sin verificar, apunta a lo contrario: continuación.

### ¿Encaja con un bot de grid/cobertura?
- **Como filtro de entrada de OP1:** es el uso más natural. La regla sería "no abrir OP1 hasta que haya ocurrido un barrido del rango asiático y el precio haya vuelto a cerrar dentro, y abrir en la dirección de la reversión". Si funcionara, reduciría la cantidad de ciclos que acaban en OP2 (el bloqueo de la pérdida), porque se entraría después del movimiento falso y no durante él.
  - **Riesgo:** si en el oro lo que domina es la continuación (como sugiere el preprint), este filtro haría entrar justo **en contra** del movimiento fuerte, que es el peor caso para un ciclo sin stop-loss.
  - Por eso hay que **medir ambas direcciones** (reversión y continuación), sin dar por buena la regla de ICT.
- **Como filtro de "no operar":** usar el estado del día (rango asiático todavía intacto, o barrido ya ocurrido) para **pausar** las entradas nuevas en la ventana de manipulación de Londres (aprox. 07:00–09:00 GMT). Encaja bien con la regla de no usar stops duros, porque no cierra nada: solo evita abrir ciclos en el tramo más violento.
- **Para OP3/OP4 y el Healer:** el máximo y mínimo asiático podrían servir como niveles de referencia para las piernas de recuperación. Sería una idea secundaria que habría que probar después.

### Definición medible propuesta (para probar con nuestros datos M5/M15 de XAUUSD)
Todas las horas en UTC. Hay que convertir desde la hora del servidor del broker, que suele ser GMT+2/+3, y cuidar los cambios de horario de verano.
1. **Rango asiático (A):** máximo AH y mínimo AL de las velas M5 entre 00:00 y 06:00 UTC. Tamaño R = AH − AL. Se descartan los días con R mayor que el percentil 80 de los últimos 60 días (Asia no estuvo "acumulando").
2. **Barrido (M):** entre 06:00 y 10:00 UTC, una vela M5 hace un máximo ≥ AH + k·R (o un mínimo ≤ AL − k·R), con k ∈ {0,05; 0,10; 0,20}. También puede medirse en ATR(14) de M15.
3. **Confirmación de reversión:** después del barrido, en las siguientes N velas M5 (N ∈ {3, 6, 12}), una vela **cierra** de nuevo dentro de [AL, AH].
4. **Señal OP1:** vender si el barrido fue por arriba y comprar si fue por abajo, entrando al cierre de la vela de confirmación.
5. **Qué medir (por día y por señal):**
   - Excursión favorable y adversa máximas (MFE y MAE) a 1, 2, 4 y 8 horas, en múltiplos de R y de ATR.
   - Probabilidad de alcanzar el punto medio del rango y el lado opuesto antes de que el precio se aleje X en contra.
   - **Comparación con controles:** (a) la entrada contraria (continuación), (b) entradas a la misma hora en días sin barrido y (c) entradas aleatorias a la misma hora.
   - **Métrica específica para nuestro bot:** porcentaje de ciclos que habrían llegado a OP2 y duración media de los ciclos, con el filtro y sin él.
6. **Validación:** separar los datos en un periodo de desarrollo y otro reservado (por ejemplo, el último 30%), incluir el spread real del broker y fijar los parámetros antes de mirar el periodo reservado.

Nota: el arnés del proyecto evalúa al cierre de cada vela. Esta definición también funciona así, porque solo usa cierres y extremos de velas M5. Aun así, el resultado será una aproximación.

### Veredicto G: **investigar más** (prueba estadística barata, sin tocar el bot)
- La idea tiene una base real (los stops se agrupan y provocan cascadas), pero la parte de "reversión" no está demostrada y hay indicios de lo contrario.
- Es fácil de definir y medir con los CSV M5/M15 que ya tenemos. Un script de análisis aislado, sin cambiar el bot, llevaría entre 1 y 2 días.
- Si el análisis muestra una ventaja clara fuera de muestra (en cualquiera de las dos direcciones) o una reducción de ciclos que llegan a OP2, se pasa a diseñar el filtro de OP1 o la pausa en la ventana de Londres. Si no la muestra, se descarta.
- Costo de integración posterior: bajo. Es un filtro de estado diario (rango y barrido) antes de abrir OP1 y no requiere stops.
