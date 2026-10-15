# Diseño: observación de re-entradas lejanas + suelo del hedge

**Estado:** PROPUESTA v2, pendiente de aprobación del usuario. No se toca código hasta aprobarla.
- v1: freno activo.
- v2, acordada en conversación el 2026-10-15: el freno nace **en modo observación** y el suelo del hedge sube a 800.

**Rama:** `experimento-2-rediseno`.

**Datos de origen:** `docs/experimento-2/analisis-notas-usuario-2026-10-15.md`, secciones "Re-entradas", "Hedge con confirmación" y "Variantes del freno".

## 1. Por qué

### Re-entradas

La OP1 entra cuando la última vela M15 cerrada rompe el último fractal confirmado (`indicators.check_m15_breakout`). Cuando un ciclo se cierra (Basket Profit Trail, por ejemplo), a los 10 s (`cooldown_seconds`) el bot vuelve a abrir OP1 sobre **la misma ruptura**, y siempre dentro de la misma vela M15.

En el historial:
- hubo 237 re-entradas sobre 156 rupturas, hasta 13 en una misma;
- las re-entradas a > 1 ATR del nivel roto suman −7,4 k$;
- ese −7,4 k$ viene de los tres peores ciclos (jun, jul y ago); sin ellos, ese grupo daría +7,4 k$;
- ningún filtro de tendencia probado separa las buenas de las malas: ADX, H4, pendiente de la EMA, anclaje al último mínimo creciente o distancia a la EMA.

Los tres desastres son anteriores al candado de supervivencia, que hoy acota esa cola. Frenar ya costaría ganancias normales seguras a cambio de una protección que el candado quizá ya da.

**Decisión:** primero **medir** con la versión actual. El bot anota qué re-entradas habría frenado, pero las abre igual.

### Suelo del hedge

`hedge_dist = 350` puntos (3,50 $ de precio). Nunca fue la distancia que mandó: siempre ganó 2×ATR(M15), con mediana de 16 $. Como suelo es demasiado bajo, porque en una sesión anormalmente quieta cubriría por ruido.

## 2. Objetivos y no-objetivos

**Objetivos:**
- Registrar cada re-entrada lejana (> N×ATR del nivel roto) con su ticket, para evaluarla después contra el resultado de su ciclo.
- Dejar el freno listo para activarse por configuración, sin desplegar código.
- Subir el suelo de la distancia del hedge a 800 puntos (8 $).

**No-objetivos (descartados con datos):**
- Filtros sobre la vela de ruptura.
- Entrada por retesteo u order blocks.
- Hedge condicionado a confirmación de giro.
- Ensanchar el multiplicador 2×ATR.
- Excepciones por ADX u otros filtros de tendencia.

**Anti-objetivos:**
- Cambiar qué OP1 se abren mientras el modo observación esté activo.
- Tocar el hedge, la gestión o los cierres.

## 3. Comportamiento

### 3.1 Observación y freno de re-entrada (solo M15, ESTADO 0)

**Nivel roto.** Se añade `indicators.m15_breakout_level(df_m15) -> (signal, level)`, con la misma búsqueda de fractales que `check_m15_breakout`.

`check_m15_breakout` no cambia. La siguen llamando el motor M15 (para la señal), el M5 y los tests, que la sustituyen por un mock. El motor M15 llama a `m15_breakout_level` solo en ESTADO 0, para obtener el nivel. Es solo lectura.

**Identidad de una ruptura:** `(dirección, nivel)`, con el nivel comparado con tolerancia de `point/2`.

Al abrir una OP1 **confirmada** se guarda `_last_entry_signal = (dirección, nivel)`. Un rechazo del broker no la actualiza.

**Re-entrada:** la señal actual coincide con `_last_entry_signal`. La distancia se mide como:
- BUY: `ask − nivel`;
- SELL: `nivel − bid`.

En unidades de `_effective_atr()`.

**Re-entrada lejana:** `reentry_max_atr > 0` y `distancia > reentry_max_atr × ATR`.

| `reentry_enforce` | Qué hace con una re-entrada lejana |
|---|---|
| **false (default)** | Abre la OP1 como hoy y, tras la apertura confirmada, escribe `SYSTEM` con `ticket=<OP1>`: `Re-entrada lejana (observacion): N.ª entrada sobre el nivel L, a X.XX ATR (umbral R). Se abre igual.` |
| true | No abre. Escribe `SYSTEM` una sola vez por señal: `Re-entrada frenada: precio a X.XX ATR del nivel L (max R ATR).` |

**Registro para el análisis posterior:** el ordinal N (cuántas OP1 van sobre esa señal) también se anota en las re-entradas cercanas, en una línea `SYSTEM` del mismo formato con `(cercana)`. Así se podrán comparar los dos grupos.

**HUD:** muestra el gate "Re-entrada" con la distancia actual, el umbral y el modo (OBS/ACTIVO).

**Reinicio del bot.** `_last_entry_signal` vive en memoria: tras un reinicio, la primera OP1 cuenta como primera entrada.

*Decisión mía:* lo acepto, porque los reinicios son raros. El coste si es un error es una re-entrada mal clasificada por reinicio.

### 3.2 Suelo del hedge

- `hedge_dist` pasa de **350 a 800** puntos (8 $ de precio).
- La regla sigue siendo `max(hedge_dist, 2×ATR)`, así que hoy no cambia nada mientras ATR(M15) > 4 $.
- El watchdog de huérfanos usa la misma distancia.

## 4. Configuración (bot_config)

**Columnas nuevas:**
- `reentry_max_atr` DOUBLE PRECISION, DEFAULT **1.0**. El valor 0 apaga la regla (ni observa ni frena).
- `reentry_enforce` BOOLEAN, DEFAULT **false**.

**`hedge_dist`:** default 800 en `DEFAULTS` (`bot/strategy.py`), en `schema.sql` y en `supabase_schema.sql`.

**Migración `migrations/011_reentrada_suelo_hedge.sql`** (idempotente, mismo estilo que 010):
1. `ADD COLUMN IF NOT EXISTS` de las dos columnas.
2. `UPDATE bot_config SET hedge_dist = 800 WHERE bot_id = 'm15' AND hedge_dist = 350`. No pisa valores personalizados.
3. Bloque ROLLBACK comentado.

**Activar el freno más adelante** = `reentry_enforce = true` en `bot_config`. No hace falta reiniciar: `main.py` recarga `bot_config` en caliente (`engine.cfg = cfg`).

## 5. Tests (script-style, `python -m tests.test_reentrada`)

1. **Primera entrada lejana:** una señal nueva a 2 ATR del nivel abre y no escribe log de re-entrada.
2. **Re-entrada cercana:** misma señal a 0,5 ATR. Abre y loguea `(cercana)` con N=2.
3. **Observación:** con `reentry_enforce=false`, la re-entrada a 1,5 ATR **abre** y loguea la observación con el ticket.
4. **Freno:** con `reentry_enforce=true`, la misma re-entrada **no** abre y loguea una sola vez aunque pasen varios ticks.
5. **Ruptura nueva:** con otro nivel o con la dirección contraria cuenta como primera entrada (N=1).
6. **Interruptor:** con `reentry_max_atr = 0` no hay observación ni freno.
7. **Rechazo del broker:** no actualiza `_last_entry_signal`.
8. **Suelo del hedge:** con 2×ATR < 8 $, el hedge salta a 800 puntos y no a 350; con ATR normal, a 2×ATR.
9. **Coherencia:** la señal de `m15_breakout_level` coincide con `check_m15_breakout` en dataframes sintéticos, y el nivel es el fractal roto.
10. Las suites existentes siguen en verde: `test_supervivencia`, `test_ledger`, `test_m5_and_budget` y `test_mt5_prep`.

## 6. Despliegue y evaluación

Según el ciclo acordado:
1. implementar;
2. commit y push;
3. el usuario aplica la migración 011;
4. `restart_all`, solo con la aprobación del usuario; carga también el fix de inactividad a2f07d7;
5. dejar correr.

**Evaluación en unas semanas:** P&L de los ciclos según su origen (primera entrada, re-entrada cercana, re-entrada lejana), uniendo los logs con `bot_positions` por ticket. Si las lejanas siguen siendo la cola mala con el candado activo, se propone `reentry_enforce = true`.

**Vuelta atrás:**
- sin código: `reentry_max_atr = 0` y `hedge_dist = 350`;
- completa: checkout de `experimento-1-grinder` + `restart_all`.

## 7. Riesgos

- **Muestra:** con pocas cuentas, las semanas de observación pueden no traer ningún evento de cola. La decisión de activar el freno puede tardar.
- **Coste del modo observación:** nulo en trading; solo añade líneas de log.
