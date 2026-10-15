# Diseño: freno a la re-entrada lejana + suelo del hedge

**Estado:** PROPUESTA, pendiente de aprobación del usuario. No se toca código hasta aprobarla.
**Rama:** `experimento-2-rediseno`.
**Datos de origen:** `docs/experimento-2/analisis-notas-usuario-2026-10-15.md` (segunda ronda, secciones "Re-entradas" e "Hedge con confirmación").

## 1. Por qué

**Re-entradas.** La OP1 entra cuando la última vela M15 cerrada rompe el último fractal confirmado (`indicators.check_m15_breakout`). Esa señal sigue viva mientras la vela cerrada siga más allá del nivel.

Cuando un ciclo se cierra (Basket Profit Trail, por ejemplo), a los 10 s (`cooldown_seconds`) el bot vuelve a abrir OP1 sobre **la misma ruptura**, cada vez con el precio más lejos del nivel. En el historial:
- hubo 237 re-entradas sobre 156 rupturas, hasta 13 en una misma;
- el ritmo no cambió tras los fixes de agosto.

| Entrada | % ciclos positivos | P&L |
|---|---|---|
| Re-entradas a < 1 ATR del nivel | 96 % | +6,1 k$ |
| Re-entradas a > 1 ATR del nivel | 85 % | −7,4 k$ |

Las tres mayores pérdidas de la historia (−10,6 k$, −4,5 k$ y −3,5 k$) fueron re-entradas lejanas (9.ª, 4.ª y 3.ª sobre su señal).

**Suelo del hedge.** `hedge_dist = 350` puntos (3,50 $ de precio). Nunca fue la distancia que mandó: siempre ganó 2×ATR(M15), con mediana de 16 $. Como suelo es demasiado bajo: en una sesión anormalmente quieta cubriría por ruido.

## 2. Objetivos y no-objetivos

**Objetivos:**
- No abrir una OP1 de **re-entrada** cuando el precio ya se alejó más de N×ATR del nivel roto.
- Subir el suelo de la distancia del hedge.

**No-objetivos (descartados con datos):**
- Filtros sobre la vela de ruptura.
- Entrada por retesteo u order blocks.
- Hedge condicionado a confirmación de giro.
- Ensanchar el multiplicador 2×ATR.

**Anti-objetivos:**
- Tocar la **primera** entrada de cada ruptura: su mediana ya está a ~0,95 ATR del nivel y es el grupo más sano (93 % positivos).
- Bloquear el hedge, la gestión o los cierres. Esto solo frena aperturas OP1.

## 3. Comportamiento

### 3.1 Freno a la re-entrada (solo M15, ESTADO 0)

**Identidad de una ruptura (señal):** `(dirección, nivel del fractal roto)`.

Se añade `indicators.m15_breakout_level(df_m15) -> (signal, level)`, con la misma búsqueda de fractales que `check_m15_breakout`. Esta última sigue igual y la llaman el motor M15 (para la señal), el M5 y los tests, que la sustituyen por un mock. El motor M15 llama a `m15_breakout_level` solo en ESTADO 0, para obtener el nivel. Es solo lectura y no cambia la señal.

**Registro en memoria del motor.** Al abrir una OP1 confirmada se guarda `_last_entry_signal = (dirección, nivel)`.

**Regla en ESTADO 0**, justo antes de `_open_additive` de OP1, después de todos los gates existentes:
- **Re-entrada:** la señal actual tiene la misma `(dirección, nivel)` que `_last_entry_signal`. El nivel se compara con tolerancia de medio punto (`point/2`).
- Si es re-entrada y `reentry_max_atr > 0`, la distancia se mide como:
  - BUY: `ask − nivel`;
  - SELL: `nivel − bid`.
- Si `distancia > reentry_max_atr × _effective_atr()`, **no se abre**.
- Una señal nueva (otro nivel u otra dirección) es primera entrada y no se frena.

**Log:** una línea `SYSTEM` por señal frenada, sin repetirse cada tick:
`Re-entrada frenada: precio a X.X ATR del nivel roto N (max R ATR).`
El HUD muestra el gate "Re-entrada" con la distancia actual y el máximo.

**Reinicio del bot.** `_last_entry_signal` vive en memoria: tras un reinicio, la primera OP1 cuenta como primera entrada.

*Decisión mía:* aceptarlo por simplicidad, porque los reinicios son raros. El coste si es un error es, como mucho, una re-entrada lejana extra tras cada reinicio.

### 3.2 Suelo del hedge

- `hedge_dist` pasa de **350 a 800** puntos (8 $ de precio).
- La regla sigue siendo `max(hedge_dist, 2×ATR)`, así que hoy no cambia nada mientras 2×ATR > 8 $ (ATR > 4 $).
- *Decisión mía:* 800 en vez de 1 000, para tocar lo mínimo posible el comportamiento validado.

## 4. Configuración (bot_config)

- **Columna nueva** `reentry_max_atr` DOUBLE PRECISION, DEFAULT **1.0**. El valor 0 desactiva el freno (vuelta atrás sin desplegar código).
- **`hedge_dist`:** default 800 en `DEFAULTS` (`bot/strategy.py`), en `schema.sql` y en `supabase_schema.sql`.

**Migración `migrations/011_reentrada_suelo_hedge.sql`** (idempotente, mismo estilo que 010):
1. `ADD COLUMN IF NOT EXISTS reentry_max_atr`.
2. `UPDATE bot_config SET hedge_dist = 800 WHERE bot_id = 'm15' AND hedge_dist = 350`. No pisa valores personalizados.
3. Bloque ROLLBACK comentado: `hedge_dist` vuelve a 350 y `reentry_max_atr` a 0.

## 5. Tests (script-style, `python -m tests.test_reentrada`)

1. **Primera entrada lejana:** una señal nueva con el precio a 2 ATR del nivel abre OP1.
2. **Re-entrada cercana:** misma señal, a 0,5 ATR, abre.
3. **Re-entrada lejana:** misma señal, a 1,5 ATR, **no** abre y loguea una sola vez aunque pasen varios ticks.
4. **Ruptura nueva:** con otro nivel o con la dirección contraria, abre aunque esté lejos.
5. **Interruptor:** `reentry_max_atr = 0` desactiva el freno.
6. **Estado de la señal:** `_last_entry_signal` solo se actualiza con una apertura confirmada; un rechazo del broker no cuenta.
7. **Suelo del hedge:** con ATR pequeño (2×ATR < 8 $) el hedge salta a 800 puntos y no a 350; con ATR normal, salta a 2×ATR.
8. **Coherencia:** la señal de `m15_breakout_level` coincide con `check_m15_breakout` en varios dataframes sintéticos, y el nivel es el fractal roto.
9. Las suites existentes (`test_supervivencia`, `test_ledger`, `test_m5_and_budget`, `test_mt5_prep`) siguen en verde.

## 6. Despliegue y evaluación

Según el ciclo acordado:
1. implementar;
2. commit y push;
3. el usuario aplica la migración 011;
4. `restart_all`, solo con la aprobación del usuario; carga también el fix de inactividad a2f07d7;
5. dejar correr unos días.

**Qué revisar después:**
- re-entradas frenadas por día;
- P&L de los ciclos de primera entrada frente a re-entradas cercanas;
- que no haya hedges a 8 $ por ruido.

**Vuelta atrás:**
- sin código: `reentry_max_atr = 0` y `hedge_dist = 350` en `bot_config`;
- completa: checkout de `experimento-1-grinder` + `restart_all`.

## 7. Riesgos y lo que no sabemos

- **Muestra pequeña.** El −7,4 k$ del grupo lejano sale de 3 ciclos; sin ellos, ese grupo daría +7,4 k$. El freno puede costar ganancias en mercados de tendencia limpia. Por eso es un experimento con interruptor, no una mejora probada.
- **Umbral de 1 ATR elegido a mano** con los datos: 0,5–1 ATR sano y > 1 ATR con la cola mala. No se optimizó.
- **ATR en vivo vs. histórico.** Se mide con `_effective_atr()` en el momento de la re-entrada; el análisis usó el ATR en la entrada. Es lo mismo en la práctica.
