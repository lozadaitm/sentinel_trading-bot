# Prompt de arranque — experimento-2-rediseno (2026-10-13)

Copiar y pegar en una sesión nueva de Claude Code abierta en
`C:\Users\Administrator\Documents\sentinel_trading_exp2`.

---

Estamos en la rama `experimento-2-rediseno`, en el worktree `sentinel_trading_exp2`. La carpeta hermana `sentinel_trading` es PRODUCCIÓN (rama `experimento-1-grinder`, 3 bots M15 + 2 M5 corriendo en Lite, tarea `SentinelRestart` apunta allí): no la edites, no cambies su rama, no reinicies bots. Cualquier lectura de MT5 se hace en modo solo lectura contra los terminales ya abiertos, como hace `scripts/news_exporter.py`.

Antes de nada lee `docs/memory/MEMORY.md` y en detalle `docs/memory/pendientes-pre-experimento-2.md` y `docs/memory/ideas-experimento-2.md`. Ahí está todo el contexto y el backlog de ideas. Ninguna idea está verificada; el objetivo de esta sesión es medir, analizar y decidir, no implementar.

Usa el skill `brainstorming` del plugin Superpowers para conducir la sesión, y cierra cada bloque de diseño aprobado con `writing-plans`. Hazme preguntas de una en una cuando necesites decisiones mías; soy vibecoder, explícame los trade-offs en lenguaje llano.

## Fase 0 — Auditoría de las 3 cuentas (agosto a octubre 2026)

Sospecho que, con la misma lógica, cada instancia se comportó distinto: cantidad de operaciones por ciclo, puntos de entrada y salida, y cálculo del lotaje respecto al equity de cada cuenta.

1. Exporta el historial completo de deals de cada instancia MT5 (los clones 25924397, 25912766 y 34087418 más la base) a CSV en `docs/experimento-2/audit/`, conectando en solo lectura a los terminales que ya corren. Usa `config.mt5_init_kwargs()` y los `.env` de `instances/` para saber qué terminal es cada cuenta.
2. Cruza con `bot_logs` de Supabase (ver memoria `logging-taxonomy-and-ticket`) y con los `cycle_ledger_m15_*.json` de producción (léelos, no los modifiques).
3. Compara entre cuentas: número de ciclos, ciclos que llegaron a OP3/OP4/rescate, deals por ciclo, timestamps y precios de entrada y salida de OP1 por ciclo (deberían coincidir casi al minuto si la lógica es la misma), lotaje real vs lotaje esperado por `equity_weight` y la fórmula de riesgo del bot, Healer y Unwind por cuenta, resultado neto por cuenta.
4. Entrega un informe en `docs/experimento-2/audit/informe-3-cuentas.md` con tablas y una lista de discrepancias confirmadas, cada una con su causa raíz en el código (archivo:línea) o marcada como "no explicada". Si encuentras un bug de lotaje o de entradas, no lo arregles todavía: anótalo con severidad y lo decidimos.

## Fase 1 — Investigación de ideas (web, repos, papers)

Para cada idea del backlog (B a G), investiga y devuélveme un veredicto: descartada / investigar más / diseño aprobado, con 3 a 5 líneas de por qué y qué costaría integrarla en el bot de ciclos con hedge que ya tenemos. En concreto:

- **B. Kronos** (https://github.com/shiyu-coder/Kronos): qué es, licencia, si corre en CPU en el VPS, qué evidencia hay de que predice mejor que azar en XAUUSD, y cómo se usaría (filtro de dirección de OP1, veto de ruptura, otra cosa). Busca alternativas open source comparables.
- **C. Alpha decay**: diseña, sin implementar, un monitor de salud de la estrategia con racha de ciclos que llegan a OP4 y Sharpe rodante, respetando que no quiero emergency-stops duros (memoria `bot-design-constraints`). ¿Qué haría el bot cuando la salud se degrada?
- **D. Sesiones** (Asia rango, Londres rompe, Nueva York confirma): verifícalo con nuestros propios datos de XAUUSD antes de proponer nada (hay CSV M5/M15 en producción y `bot_backtesting/data/`). ¿Se cumplen los rangos de pips que dice el video?
- **E. APILayer**: ¿tiene alguna API útil para nosotros (calendario, sentimiento, precios)? Precio y límites.
- **F. MiroFish**: qué es realmente, y si sirve como agente del arnés de IA.
- **G. AMD / Power of 3** (Acumulación, Manipulación, Distribución): ¿encaja con el grid de ciclos o solo como filtro de entrada de OP1?

## Fase 2 — Arnés de agentes de IA (solo diseño)

Con el esqueleto del carrusel que está en `ideas-experimento-2` (escáner → señales → plan → riesgo → monitoreo → memo con aprobación humana), propón cómo sería un arnés de agentes para nuestro bot, qué partes del bot actual cubren ya cada bloque, y qué modelos de Claude usarías en cada agente. Guárdalo como diseño en `docs/experimento-2/arnes-agentes.md`. Nada de código todavía.

## Reglas

- No tocar código del bot hasta que yo apruebe un diseño por escrito. Los hallazgos van a `docs/experimento-2/` y las decisiones firmes a `docs/memory/` siguiendo la convención del CLAUDE.md (archivo + pointer en MEMORY.md + commit).
- No correr backtests salvo que lo pida.
- Commitea y pushea cada entregable en esta rama en cuanto esté listo.
- Si entra un hotfix en `experimento-1-grinder`, mergéalo aquí el mismo día.
