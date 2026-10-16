# Diseño: trailing del M5 proporcional al ATR

**Estado:** APROBADO por el usuario el 2026-10-16. Implementado (código, tests, migración 013).

**Rama:** `experimento-2-rediseno`.

**Origen:** `docs/experimento-2/auditoria-m5-2026-10-16.md`, secciones 1, 2, 6 y 7.

## 1. Por qué

**El M5 no tiene ventaja hoy.**
- En 944 operaciones reales quedó en −185 $.
- Acierta el 85–89 %, pero cada pérdida (≈ 8,5 $/oz) borra 6–7 ganancias (≈ 1,3 $/oz).

**La causa es el trailing en puntos fijos** (`_manage_exits`):
- arranca a +1 $ y sigue a 0,5 $;
- desde +3 $ se separa a 1,5 $.

Con un ATR(M5) mediano de 4,9 $, eso equivale a arrancar a 0,2 ATR y seguir a 0,1 ATR. Cualquier retroceso normal cierra la operación, aunque las ganadoras recorren de mediana 2,5 $/oz a favor.

**Backtest tick a tick sobre las 944 entradas reales** (sección 6 de la auditoría). Con el trailing proporcional al ATR:

| | Hoy (simulado) | Con ATR |
|---|---|---|
| Resultado por 0,01 lote | −30 | **+147,5** |
| Semanas que mejoran | — | 5 de 5 |
| Pérdida / ganancia | 6–7× | ≈ 2× |
| Acierto | 85–89 % | 73–74 % |

**Por qué el resultado es fiable:**
- Las 72 combinaciones vecinas probadas superan la configuración actual.
- Se probó una proyección del objetivo por estructura (sección 7.1) y no aporta nada: la segunda fase de este trailing ya actúa como proyección por ATR.

## 2. Objetivos y no-objetivos

**Objetivo:** que el trailing del M5 arranque, siga y se apriete en múltiplos del ATR del M5, con los valores del backtest.

**No-objetivos de este cambio:**
- **Stop inicial:** 2 × ATR con suelo de 10 $.
- **TimeStop:** 45 min.
- **Entradas, régimen, filtros y tamaño:** sin cambios.
- **El M15:** sección 8 de la auditoría; no se toca.

Las mejoras secundarias (stop de 2 ATR sin suelo y TimeStop de 90 min) se aplicarán **después**, solo por configuración (`m5_hard_sl_points`, `m5_max_trade_min`) y con decisión aparte. Así se puede atribuir cada efecto.

## 3. Comportamiento

### 3.1 Modos

- **Nuevo parámetro:** `m5_trail_mode`, con los valores `atr` (nuevo, DEFAULT) o `points` (el actual, intacto).
- **En modo `atr`,** para cada posición propia:

```
A        = ATR(14) M5 de la ultima vela CERRADA antes de la apertura de la posicion
avance   = movimiento a favor, en $ (precio actual vs apertura)
si avance <  m5_trail_start_atr * A                     -> nada
si avance >= m5_turbo_trigger_atr * A                   -> dist = m5_turbo_dist_atr * A
si no                                                   -> dist = m5_trail_dist_atr * A
dist     = max(dist, stops_level + 20 pt)               (igual que hoy)
nuevo_sl = precio_actual -/+ dist
se aplica solo si mejora el SL actual en mas de m5_trail_step pt y queda en verde (igual que hoy)
```

**Valores por defecto (los del backtest):**

| Parámetro | Valor |
|---|---|
| `m5_trail_start_atr` | 0,50 |
| `m5_trail_dist_atr` | 0,30 |
| `m5_turbo_trigger_atr` | 1,25 |
| `m5_turbo_dist_atr` | 0,15 |

**Ejemplo con un ATR de 4,9 $:**
1. Arranca cuando la operación va +2,45 $ a favor.
2. Sigue a 1,47 $ del precio. El primer stop queda en unos +1 $.
3. Desde +6,1 $ sigue a 0,73 $.

### 3.2 Qué ATR se usa: el de la apertura, fijo durante toda la operación

*Decisión mía:*
- El backtest usó el ATR de la entrada. Si el ATR cambia mientras la operación sigue abierta, el comportamiento no sería el probado.
- No necesita estado: se calcula del `df_m5` que el motor ya tiene (200 velas; la operación más larga dura 45 min, unas 9 velas).
- Funciona igual tras un reinicio.

**Respaldo:** si no se encuentra la vela de apertura, se usa `self.atr1`. Ese caso no debería darse.

### 3.3 Lo que no cambia

- El TimeStop (cierra en rojo pasados `m5_max_trade_min`).
- El histéresis `m5_trail_step`.
- El respeto del `stops_level`.
- La regla de que el stop solo se mueve a favor y queda en verde.
- `m5_use_trailing = false` sigue apagando todo el trailing.

### 3.4 Log

- **Una línea `GRINDER` por posición, la primera vez que se arma el trailing:**
  `Trailing ATR armado: ticket #T, ATR X $, avance Y $, SL Z.`
- **Por qué:** hoy no se registra cuándo se arma el trailing, y esa línea permite revisar el comportamiento en vivo.
- **Movimientos posteriores del stop:** sin log, como hoy, para evitar el ruido de cada modificación.

## 4. Configuración

- **Migración `migrations/013_m5_trailing_atr.sql`,** idempotente:
  - añade las columnas `m5_trail_mode` (TEXT, DEFAULT 'atr') y las cuatro `*_atr` (DOUBLE PRECISION, con sus DEFAULT);
  - las inicializa en las filas del M5.
- **ROLLBACK** comentado en la migración: `UPDATE bot_config SET m5_trail_mode = 'points' WHERE bot_id = 'm5';`.
- **Sin la migración,** el bot usa los DEFAULT del código. Como `bot_config` se recarga en caliente, los cambios de valores no requieren reinicio.
- **Los parámetros en puntos** (`m5_trail_start`, `m5_trail_dist`, `m5_turbo_*`) se conservan para el modo `points`.

## 5. Tests (script-style, `python -m tests.test_m5_trailing`)

1. **Arranque:** con ATR 4,0, sin stop a +1,9 $ (por debajo de 0,5 ATR = 2,0); con stop a +2,1 $.
2. **Distancia normal:** con avance de 3,0 $ y ATR 4,0, el stop queda a 1,2 $ del precio (0,3 ATR).
3. **Turbo:** con avance de 5,5 $ (más de 1,25 ATR = 5,0), el stop queda a 0,6 $ (0,15 ATR).
4. **ATR de la apertura:** si `atr1` cambia mientras la operación sigue abierta, la distancia no cambia. Se usa la vela anterior a la apertura.
5. **Respaldo:** si la vela de apertura no está en `df_m5`, se usa `atr1`.
6. **Suelo del broker:** con ATR 1,0, la distancia del turbo (0,15 $) sube a `stops_level + 20 pt`.
7. **Venta:** los casos 1–3 en espejo.
8. **Histéresis y verde:** no se modifica el stop si la mejora es menor que `m5_trail_step` ni si el stop quedaría en rojo.
9. **Log:** una sola línea «Trailing ATR armado» por ticket, aunque el stop se mueva varias veces.
10. **Interruptor:** con `m5_trail_mode = 'points'`, el comportamiento es idéntico al de hoy (mismos casos que la sección [4] de `test_m5_and_budget`).
11. **Suites existentes en verde:** `test_m5_and_budget`, `test_supervivencia`, `test_ledger`, `test_mt5_prep`, `test_reentrada` y `test_healer`.
    - La sección [4] de `test_m5_and_budget` asume el modo `points`: se fija `m5_trail_mode = 'points'` en ese test y se explica en el commit.

## 6. Despliegue y evaluación

**Ciclo acordado:**
1. implementar, commit y push;
2. el usuario aplica la migración 013;
3. `restart_all`, solo con su aprobación;
4. dejar correr.

**Qué mirar** en la revisión, con el historial de MT5 en solo lectura y los logs:
- las líneas «Trailing ATR armado»;
- la duración de las operaciones (se espera una mediana de unos 10 min, frente a 2 hoy);
- acierto, ganancia y pérdida medias en $/oz.

**Criterio** tras al menos 2 semanas o 100 operaciones del M5:
- la relación pérdida/ganancia baja de 6–7× a unas 3× o menos;
- el resultado por 0,01 lote no es peor que el de las semanas previas.

Si no se cumple, se vuelve atrás.

**Vuelta atrás:**
- sin código: `m5_trail_mode = 'points'`;
- completa: revertir el commit + `restart_all`.

## 7. Riesgos

- **Acierta menos** (≈ 73 %): habrá más operaciones perdedoras seguidas que hoy, aunque cada ganancia valga más del doble.
- **La peor racha del experimento 1** salió más profunda en la simulación: −377 $ frente a −245 $ en la cuenta base. La de las cuentas actuales mejoró.
- **El backtest tiene límites:**
  - entradas fijas;
  - 5 semanas de datos;
  - no puede simular las entradas que el bot no tomó por tener una posición abierta.
- **Cuenta de 1 000 $:** su M5 solo opera a la contra del M15 (hallazgo 2 de la revisión del 16-oct). El cambio le aplica igual.
- **Operaciones más largas** (unos 10 min frente a 2): coinciden más tiempo con el M15 abierto. El gobierno de margen y el tope de supervivencia no cambian.
