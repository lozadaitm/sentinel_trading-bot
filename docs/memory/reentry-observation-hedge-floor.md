---
name: reentry-observation-hedge-floor
description: Decisiones del 2026-10-15 — re-entradas sobre la misma ruptura en modo observación, suelo del hedge a 800 pt, horas de riesgo NY que siguen el DST; qué se descartó con datos
metadata:
  type: project
---

Decisión del usuario (2026-10-15), migración `011_reentrada_suelo_hedge.sql`, spec `docs/superpowers/specs/2026-10-15-reentrada-y-suelo-hedge-design.md`.

**1. Re-entradas en modo observación.**
- El M15 reabre OP1 sobre la misma ruptura M15 (mismo lado y nivel) a los 10 s de cerrar un ciclo, siempre dentro de la misma vela.
- `reentry_max_atr` (1.0) marca la re-entrada "lejana"; con `reentry_enforce=false` se abre igual y se loguea `Re-entrada lejana/cercana (observacion)` con el ticket.
- Activar el freno = `reentry_enforce=true` en `bot_config` (recarga en caliente). `reentry_max_atr=0` apaga todo.

**2. Suelo del hedge.** `hedge_dist` pasa de 350 a 800 pt. Manda `max(hedge_dist, 2×ATR)` y en el historial siempre mandó 2×ATR.

**3. Horas de riesgo.**
- `risk_hours_utc='1'` (Asia).
- `risk_hours_ny='9,10,11'` en hora de Nueva York, calculada como servidor − 7 h, así que sigue el DST de EE. UU. sin intervención.

**Descartado con datos (no re-proponer sin datos nuevos):**
- filtros de vela de ruptura;
- retesteo;
- order blocks;
- hedge condicionado a CHoCH;
- ensanchar 2×ATR;
- cerrar el hedge en verde cuando el precio gira;
- excepciones por ADX, H4 o EMA al freno.

**Why:**
- Las re-entradas lejanas sumaron −7,4 k$, pero por 3 ciclos anteriores al candado; sin ellos darían +7,4 k$.
- Ningún criterio separa las buenas de las malas.
- Se mide con el candado activo antes de frenar.

**How to apply:**
- En la revisión de semanas, unir los logs `Re-entrada ...` con `bot_positions` por ticket.
- Si las lejanas siguen siendo la cola mala, proponer `reentry_enforce=true`.
- Análisis completo en `docs/experimento-2/analisis-notas-usuario-2026-10-15.md`.
- Ver [[survival-cap-basket-lock]].

**Despliegue:** migración 011 aplicada y `restart_all` hecho el 2026-10-15 ~20:55 UTC (con un ciclo abierto en las 3 cuentas; el ledger lo retomó sin problemas). La observación cuenta desde esa fecha.
