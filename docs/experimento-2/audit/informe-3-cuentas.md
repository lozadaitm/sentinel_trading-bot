# Informe Fase 0 — Auditoría de las 3 cuentas (ago–oct 2026)

Fecha: 2026-10-13 · Rama: `experimento-2-rediseno` · Código auditado: idéntico a
`experimento-1-grinder` en `bot/` (sin diff).

## Resumen en 5 líneas

1. **Las 3 cuentas solo operaron juntas 6 días (13 → 19 de agosto).** Desde el 21 de
   agosto ninguna abre ciclos: dos quebraron por stop-out y la tercera quedó en
   close-only por objetivo de ganancia. Los bots siguen "RUNNING" con heartbeat sobre
   cuentas sin dinero.
2. **El lotaje se calcula bien** (0 desviaciones contra la fórmula), pero el redondeo hacia
   abajo castiga a la cuenta chica (lote real = 51–99 % del teórico, media 80 %).
3. **La causa principal de que "la misma lógica se comporte distinto" son umbrales fijos en
   dólares** (piso verde 3 $, armado mínimo 2 $, Unwind 30 $, retroceso 1–50 $). Con
   lotes distintos, el mismo movimiento de precio cruza esos umbrales en una cuenta y no en
   otra. Eso explica el caso que viste: una cierra la OP1 en verde y otra cae en OP2.
4. Hay **diferencias de configuración** entre la cuenta base y los clones (sobre todo en el M5).
5. La conexión Python→MT5 desde un proceso nuevo **falla en los 3 terminales** (`-6
   Authorization failed`). Riesgo operativo: no sabemos si un `restart_all` reconectaría.

## Fuentes y limitaciones

| Fuente | Estado |
|---|---|
| Historial de deals MT5 (vía `config.mt5_init_kwargs()`) | **No disponible.** Los 3 terminales vivos (base, 25924397, 25912766) devuelven `(-6, 'Terminal: Authorization failed')`, tanto con las credenciales del `.env` como sin ellas, y con o sin sandbox. El terminal 34087418 no está corriendo y no se lanzó. |
| `bot_logs` Supabase (desde 01-ago, sin `SYSTEM`) | 661 313 filas. Es la fuente principal: aperturas logueadas en el broker con ticket, lote, precio y balance. |
| `bot_positions` Supabase | 2 067 filas, **incompletas**: del 50 al 87 % de las filas no tienen `lots`/`open_time` (solo upsert de cierre). |
| `bot_config`, `bot_state`, `bot_instances`, `account_settings` | Completas. |
| `instances/cycle_ledger_m15_*.json` | Los 3 de usuarios reales están vacíos (planos). `81118671…` es un residuo de pruebas del 13-ago (ticket `1`). |

Datos crudos en `docs/experimento-2/audit/supabase/` (locales, no versionados: el repo es
público y `bot_logs.csv` pesa 131 MB).

## Mapa de cuentas

| Usuario (uuid) | Cuenta MT5 | Servidor | Terminal | Estado hoy |
|---|---|---|---|---|
| e8d840ab (base) | 25556247 | Demo | `Program Files\MetaTrader 5` | Balance **349 $** (inicio 11 687 $). Stop-out 21-ago. |
| 593747e4 | 25912766 | Demo | clon portable | Balance **−38,73 $** (inicio 5 000 $). Stop-outs 19-ago (x2) y 1-sep. |
| 39358e52 | 25924397 | Demo | clon portable | Balance **4 892 $** (inicio 1 000 $). Close-only desde 11-sep por objetivo 100 %. |
| ce26a49c | 34087418 | **Live** | clon portable | Nunca operó (`STOPPED`, `.env` deshabilitado con `_`, terminal apagado). |

## Comparativa en la ventana común (13-ago 00:00 → 19-ago 11:00 UTC, M15)

| Cuenta | Ciclos (OP1) | Llegaron a OP2 | OP3 | OP4 | Healer | Unwind |
|---|---|---|---|---|---|---|
| 25924397 (1 000 $, lote 0,01) | 22 | 3 | 3 | 2 | 4 | 3 |
| 25912766 (5 000 $, lote 0,09) | 36 | 3 | 3 | 2 | 11 | 11 |
| base (11 700 $, lote 0,22) | 23 | 2 | 2 | 2 | 35 | 26 |

**Sincronía de entradas OP1** (misma señal ⇒ deberían coincidir al minuto):

| Par | OP1 con pareja ≤ 60 s | ≤ 5 min |
|---|---|---|
| 25924397 vs 25912766 | 13 / 22 | 15 / 22 |
| 25924397 vs base | 4 / 22 | 5 / 22 |
| 25912766 vs base | 14 / 36 | 17 / 36 |

Ejemplo del arranque (13-ago 09:30:02): las 3 entran a la vez en 4380,27. La base cierra a los
69 s (+8,36 $) y reentra. 25912766 cierra 6 min después. A partir de ahí cada cuenta va
desfasada y solo se resincroniza cuando todas coinciden planas.

**Lotaje real vs esperado.** Fórmula: `floor(equity·0,8/5000·0,12)` con mínimo 0,01
(`bot/strategy.py:218-240`).

| Cuenta | OP1 analizadas | Desvío vs fórmula | Lote real / lote teórico sin redondear |
|---|---|---|---|
| 25924397 | 50 | 0 | media 80 %, mín 51 % |
| 25912766 | 36 | 0 | media 94 %, mín 90 % |
| base | 89 | 1 caso de −0,02 (11-ago, explicable por equity < balance) | media 97 %, mín 90 % |

## Discrepancias confirmadas

| # | Severidad | Discrepancia | Causa raíz |
|---|---|---|---|
| D1 | **ALTA** | 2 de 3 cuentas quemadas. 25912766: stop-out 19-ago 01:02 UTC (margin level 16 %, 6 010 → 1 200 $) con cesta OP3/OP4 larga + 3 amputaciones del Healer + spike en la apertura de Asia (VCB activado a las 01:02). Base: stop-out 21-ago ~07-08 UTC (12 538 → 349 $) tras 4 amputaciones del Healer el 19-ago sobre una Recovery Sell con 14 OP4 SELL. | Mismo patrón que [[healer-unwind-hedge-cascade]]: cesta profunda sin stop que el Healer va desarmando. El detalle tick a tick requiere el historial MT5 (bloqueado, ver D9). **Causa parcial.** |
| D2 | **ALTA** | Después del stop-out, el bot **sigue el ciclo con el residuo**. 25912766 abre Recovery Sell + 5 OP4 SELL con 1 234 $ (19-ago 11:09) → segundo stop-out el mismo día (→ 358 $) → tercero el 1-sep (→ −38,73 $), con **12 970 ERROR "Hedge Lock FALLIDO retcode 10019"** en minutos. | El ledger trata las patas supervivientes del stop-out como un ciclo vivo. No hay ningún gate "cuenta quebrada / sin margen" que pare los reintentos del Hedge Lock (spam de 10019). **Por localizar archivo:línea** en `bot/ledger.py` / Hedge Monitor (`strategy.py:1090+`). |
| D3 | **MEDIA** | Mismo precio, distinto destino: en una cuenta la OP1 cierra verde y en otra cae a OP2. Los Unwind van de 3 a 26 según el tamaño de la cuenta. | **Umbrales fijos en $ con lotes distintos**: `min_green_profit=3 $` (`strategy.py:1073`); con 0,01 lotes exige ~300 pts y con 0,22 ~14 pts, así que la cuenta chica desarma a hedge mucho más. Armado mínimo `2 $` (`:1039-1040`; en 1 000 $ el 0,15 % = 1,5 $ queda subido a 2 $). Retroceso acotado `1–50 $` (`:1059-1060`). `unwind_money_floor=30 $` (`:756/767`); para 0,44 lotes son ~70 pts, mucho antes que 2 ATR. |
| D4 | **MEDIA** | La cuenta chica opera con menos riesgo relativo (lote al 51–99 % del teórico). | `math.floor` al `volume_step` (`strategy.py:228-229`). Con 1 000 $, 0,019 → 0,01. |
| D5 | **MEDIA** | "Tenían capital y no abrían." | Objetivo de ganancia → close-only (`strategy.py:1143`, `:1166`, `:815`). 25924397: TARGET 14-ago 12:20 (+10 %), 25-ago 15:22 (+100 %) y 11-sep 08:24 (+100 %). Base: 12-ago 19:14 (+137 %). Cada reactivación fue un reset manual de baseline. Funciona según diseño. |
| D6 | **MEDIA** | Desde el 21-ago **ninguna cuenta opera**, pero `bot_instances` muestra RUNNING con heartbeat fresco. 50 días sin datos útiles. | Nadie vigila "cuenta quemada". Relacionado con la idea C (salud de la estrategia). |
| D7 | **BAJA** | Config distinta entre la base y los clones. | `bot_config`. Base M5: `margin_cap_pct 10` (clones 60), `ml_flatten 250` (clones 0), `ml_no_add 400` (clones 200). Base M15: `inp_max_spread 300` (clones 350). Los clones tienen además `status=INACTIVE` (columna legacy, sin efecto aparente). |
| D8 | **BAJA** | Calidad de datos: `bot_positions` sin lote ni apertura en el 50–87 % de las filas. Los logs HEALER guardan el P&L en la columna `price` y otro valor en `lots`. | Upsert de cierre sin datos de apertura (`bot/db.py::upsert_positions`). Healer: semántica de columnas reutilizada. **Por localizar.** |
| D9 | **ALTA (operativa)** | `mt5.initialize()` desde un proceso nuevo falla con `-6 Authorization failed` en los 3 terminales vivos, aunque los bots ya conectados siguen funcionando. Si un `restart_all` reproduce el fallo, los bots no reconectarían. | **No explicada.** Mismo build (5.0.6090) en paquete y terminal, misma sesión y usuario. |
| D10 | INFO | La cuenta 34087418 es **LIVE** (no demo) y está apagada. | Provisionada el 13-ago, nunca arrancó. |

## Lo que NO se pudo verificar

- Precios exactos de los deals de cierre y comisiones/swap por deal (requiere el historial MT5, D9).
- El resultado neto puro por trading de cada cuenta: hubo resets de baseline y posibles depósitos
  (`last_flow_ticket`); los balances de arriba son brutos.

## Preguntas abiertas para decidir (no implementar todavía)

1. ¿Escalar los umbrales en $ (D3) por lote o por balance, para que todas las cuentas se
   comporten igual?
2. ¿Qué debe hacer el bot tras un stop-out parcial (D2)? Choca con "no stops duros"; aquí la
   cuenta ya está liquidada.
3. ¿Investigamos D9 antes de cualquier `restart_all`?
