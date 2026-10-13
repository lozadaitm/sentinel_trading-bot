# Correcciones de menores del candado (2026-10-14)

Aprobado por el usuario en chat el 2026-10-14: grupo A (comportamiento), pruebas del grupo B y
limpieza del grupo C, salvo lo que se excluye abajo. Origen: menores diferidos de
[`registro-implementacion-candado.md`](registro-implementacion-candado.md).

Reglas para quien implemente:

- No reiniciar bots, no `restart_all`, no backtests, no tocar Supabase.
- Tests script-style: `python -m tests.<mod>` con `check()`; nada de pytest.
- Las tres suites deben quedar verdes:
  - `python -m tests.test_supervivencia`
  - `python -m tests.test_ledger`
  - `python -m tests.test_m5_and_budget`
- Stage solo los archivos propios (nunca `git add -A`). El repo es público: sin datos crudos, correos, UUID ni secretos.
- Trailer del commit: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Lote 1 — lecturas fallidas, avisos y relojes (A1, A5, A6, A7)

**A1. Margen desconocido no es 0 %.**
- `Broker.margin_level()` (`bot/broker.py`) devuelve 0.0 si `account_info` falla. Debe devolver `None`, igual que `account_equity` / `account_margin`.
- Cada llamador trata `None` como desconocido:
  - `budget.posture()` nunca entra en FLATTEN por `None`. Bloquea lo aditivo (NO_ADD) mientras sea desconocido.
  - `budget.py:~172`: revisar y decidir de forma coherente (desconocido nunca libera ni liquida).
  - El gate de apertura del M5 (`strategy_m5.py:~718`) no abre con `None`.
  - El panel de gates (`strategy_m5.py:~600`) muestra `n/a`.
- Además, el default de código `ml_flatten` del M5 (`strategy_m5.py:129`, 250.0) pasa a 0.0, alineado con la migración 010. Así una lectura mala nunca liquida, aunque la migración no se haya aplicado.

**A5. Aviso que falla al enviarse no consume la espera de 6 h.**
- En `AlertManager.notify` (`bot/alerts.py`), si el envío falla (excepción o `sender` que devuelve `False`), se restaura el `_last[kind]` previo para que el siguiente intento pueda enviarse.
- Comprobar qué devuelve el sender real ante fallo SMTP.

**A6. Equidad 0 pasajera no manda CRÍTICA.**
- `account_dead` / su llamador (`bot/alerts.py:~75`) declaran la cuenta muerta por `equity <= 0` solo tras 2 lecturas consecutivas confirmadas, en ticks distintos, igual que el guard `_empty_reads`.
- `trade_allowed` falso se mantiene como está.

**A7. Relojes en hora del servidor.**
- `strategy.py:~179` (`init_history_cursor`) y `strategy_m5.py:~255` (`_refresh_last_trade_result`) usan `datetime.now()` / `utcnow()`.
- Deben usar la misma base de hora del servidor que las ventanas de historial de R9 (ver cómo lo hacen `_check_stop_out` / `_check_idle` y `_server_dt`).

**Pruebas del lote:**
- `margin_level` `None` → M5 no liquida ni abre, posture NO_ADD;
- fallo de envío → reintento permitido;
- equity 0 una vez → sin CRÍTICA, dos veces → CRÍTICA;
- dead-gate del M5 (faltaba).

## Lote 2 — candado y disolución (A2, A3, A4)

**A2. Una sola pareja por día UTC.**
- En `_maybe_dissolve` / `_retry_dissolve_pending` (`bot/strategy.py`), `last_dissolve_day` se marca en cuanto se cierra cualquier volumen ≥ step de la pareja. Incluye:
  - primer miembro parcial (rama "PARCIAL");
  - deuda descartada (ambas ramas "descartada");
  - ruta R15 recortada.
- El resto espera al día siguiente. La deuda R14 sí se sigue reintentando dentro y fuera de la ventana, porque es exposición desnuda.
- La ruta R15 recortada también debe registrar el motivo correcto y limpiar la meta del candado si ya no quedan patas LOCK. Reusar `_dissolve_done` o separar "marcar día" de "log y limpieza".

**A3. Volumen inicial del candado = volumen realmente abierto.**
- En la apertura del candado (`strategy.py:~535`), si el fill es parcial (IOC), sumar a `lock_initial_volume` el volumen realmente llenado (`res.volume` o relectura), no el pedido.

**A4. Ganancias del aflojado parcial.**
- En `_maybe_unlock`, un cierre DONE_PARTIAL suma a `cycle_realized` lo realmente cerrado, como ya hace `_dissolve_close` (F6).
- Si el resultado es mixto, no mover la referencia de precio por el volumen no cerrado.

**Pruebas del lote:**
- disolución parcial → no hay segunda pareja el mismo día, sí al siguiente;
- R15 recortada marca el día y limpia la meta;
- fill parcial del candado SELL y BUY → `lock_initial_volume` real;
- aflojado DONE_PARTIAL → `cycle_realized` correcto.

## Lote 3 — pruebas que faltaban (grupo B)

Añadir a `tests/test_supervivencia.py` (o `test_m5_and_budget.py` si es M5).

**Supervivencia y apertura:**
- `fit`:
  - por la ruta de margen (`_mpl`);
  - en la rama "S de otro bot";
  - relog de dedupe BUDGET;
  - por debajo de `volume_min` → 0.
- Llamada a `surv.fit` desde el M5.
- `reset_meta` cuando `core_count == 0`.
- Rescate bloqueado por supervivencia (positivo) en la fixture [16]. El test `test_rescue_cooldown_only_when_sent` debe afirmar el evento BUDGET para no pasar en vacío.
- Afirmaciones más estrictas en `test_no_fixed_lot_caps` (valores, no `> 1.0`).

**Umbrales y horas:**
- El trailing usa los nuevos umbrales en pips: armado, clamp del retroceso, `min_green`.
- Fallback de `_ref_lot` sin meta.
- Gate de hora de riesgo en la rama de recuperación (`strategy.py:~1199`).
- El test de churn no debe depender de la identidad de FakePos.

**Candado y disolución:**
- `order_check` ok pero el envío es rechazado en el candado.
- Partición por `volume_max`.
- Fallback de `lock_initial_volume` en la disolución.
- Afirmar el log de degradación LOCK→ORPHAN.

Solo pruebas. Si una prueba destapa un fallo real, no lo arregla el lote: se reporta.

## Lote 4 — limpieza (grupo C)

**Comentarios y textos:**
- Comentarios obsoletos: `strategy.py:~1005` (y `:~496` si aplica) dicen `news_enforce=False (default)`.
- Docstring roto de `_news_note` ("solo no deberia").
- Líneas largas 1090–1091 de `strategy.py`.
- Comentario de la búsqueda binaria del aflojado: asume que el neto no-LOCK no se opone a `dir_orig`.

**Código:**
- `_hedge_fail_next`: purgar tickets que ya no existen.
- `parse_hours`: tokens con espacios o vacíos no rompen.
- `survival.DEFAULTS`: quitar las claves §5.9 sin uso, si de verdad no se usan.

**Otros archivos:**
- `migrations/010_supervivencia.sql`: el bloque ROLLBACK comentado no debe mezclar prosa que daría error de sintaxis al descomentarlo. La prosa va en líneas `--` aparte, claramente marcadas.
- `bot_backtesting/sim_broker.py`: añadir los métodos nuevos del bróker con semántica simulada coherente:
  - `account_margin`, `contract_size`, `order_check`, `account_snapshot`;
  - `positions_checked`, `positions_all_checked`, `trade_allowed`.
  - Sin correr backtests: solo verificar que importa y que una instancia responde.

**Excluido a propósito:**
- `set_meta` escribe el archivo en cada cambio. Es lo más seguro ante cortes.
- El Healer cuenta las ganancias de la disolución (decisión consciente).
- El filtro del magic de `[so`: se verifica en demo.
