# Tope de supervivencia + candado de cesta — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que ninguna cuenta pueda liquidarse por exposición que añade el bot. Para ello:
- un tope de supervivencia medido en movimiento del oro;
- un candado de cesta que congela en vez de cortar;
- umbrales en movimiento, para que todas las cuentas decidan igual;
- alertas por correo.

**Architecture:** Un módulo nuevo `bot/survival.py` calcula el "aguante" S de la cuenta y el
lote que cabe. Lo comparten el M15 y el M5. El candado vive en `bot/strategy.py` como una
máquina de tres estados (LIBRE / CONGELADO / AFLOJADO) sobre un rol nuevo `ROLE_LOCK` del
`CycleLedger`, que además gana un dict `meta` persistido para el estado del ciclo. Las alertas
van en `bot/alerts.py`, sobre `bot/notify.py`.

**Tech Stack:** Python 3.14, paquete `MetaTrader5`, Supabase/Postgres (`bot_config` en
columnas), tests como scripts `python -m tests.<modulo>` con `check()` (no hay pytest).

**Spec:** `docs/superpowers/specs/2026-10-13-candado-supervivencia-design.md`. Los dos se leen
juntos; el plan argumenta desde el spec.

## Global Constraints

- Sin stop de cesta, sin cierre de emergencia y sin SL catastrófico. Nada cierra en pérdida para
  frenar, salvo amputaciones del Healer, el cierre total en positivo y la disolución por parejas.
- Las órdenes protectoras (`"Hedge Lock"`, `"Basket Lock"`) nunca pasan por `SurvivalGuard.fit`,
  `MarginGovernor.can_open` ni ningún filtro. Se envían y decide el bróker.
- Valores (spec §5): `survival_move_usd` = 350.0, `lock_trigger_usd` = 150.0,
  `unlock_rebound_usd` = 50.0, `risk_hours_utc` = "1,13,14,15",
  `lock_dissolve_after_h` = 24, `lock_dissolve_fraction` = 0.34,
  `lock_dissolve_hours_utc` = "3,4".
- Umbrales en movimiento (spec §5.9): `basket_arm_move_usd` 0.83, `rescue_arm_move_usd` 0.56,
  `min_green_move_usd` 0.33, `retrace_min_move_usd` 0.11, `retrace_max_move_usd` 5.6,
  `fixed_retrace_move_usd` 0.22, `unwind_floor_move_usd` 3.33, `rescue_l2_move_usd` 16.7,
  `rescue_l3_move_usd` 44.4.
- Para `max_net_lots`, `max_entry_lots`, `max_recovery_lots` y `m5_max_lot_cap`, **0 =
  desactivado**. Las claves viejas (`basket_percent`, `min_green_profit`, etc.) se conservan en
  `DEFAULTS` y en la DB (rollback), pero el código nuevo ya no las lee.
- Comment del candado: `"Basket Lock"`. Rol: `"LOCK"`.
- Logs según `docs/memory/logging-taxonomy-and-ticket.md`:
  - `PROTECCION` → candado puesto / aflojado / fallido;
  - `BUDGET` → recortes y bloqueos del tope;
  - `HEALER` → disolución;
  - `ERROR` → fallos.
- Tests: `python -m tests.test_ledger`, `python -m tests.test_m5_and_budget` y el nuevo
  `python -m tests.test_supervivencia` deben terminar en "TODO OK".
- No correr backtests. No reiniciar bots ni lanzar `restart_all` sin OK explícito del usuario.
- Commits con `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Push a
  `experimento-2-rediseno` al final de cada tarea.
- Repo público: nada de credenciales, emails ni datos crudos.

## Review Focus

1. **Restart con candado vivo.** Tras reiniciar, la pata `"Basket Lock"` se rehidrata como
   `LOCK` y el estado (CONGELADO/AFLOJADO, precio de referencia, `lock_since`) se recupera de
   `meta`. No se abre un segundo candado ni un Hedge Lock encima. → test en la Tarea 2 y en la
   Tarea 7.
2. **SL de trailing previo al candado.** Si una Op3 tenía SL del trailing en verde cuando entra
   el candado, ese SL podría saltar y cambiar el neto con la cesta congelada. Al poner el
   candado se quitan los SL de las patas M15. → test en la Tarea 7.
3. **Bróker que rechaza el candado (sin margen).** Un ERROR al primer fallo y luego como mucho
   uno cada 600 s, más una alerta crítica. Nunca miles de líneas. → test en la Tarea 7.
4. **Hora de servidor vs UTC en el cambio de horario de EE. UU.** Las horas de riesgo y de
   disolución deben caer en la hora UTC correcta en verano (servidor = UTC+3) y en invierno
   (UTC+2). → test en la Tarea 1.
5. **Cuenta con lote mínimo (≈1 000 $).** El tope puede bloquear toda Op3/Op4. El bot debe
   seguir gestionando (hedge, trail, cierres) y loguear el bloqueo una sola vez por motivo.
   → test en la Tarea 3.

---

## Mapa de archivos

| Archivo | Responsabilidad |
|---|---|
| `bot/survival.py` (nuevo) | Cálculo de S, lote que cabe, reparto por `equity_weight`, hora UTC desde la hora del servidor |
| `bot/alerts.py` (nuevo) | Correos de alerta con dedupe por tipo; detección de cuenta muerta |
| `bot/broker.py` | `account_margin()`, `contract_size()`, `order_check()` |
| `bot/ledger.py` | `ROLE_LOCK`, `lock_legs()`, `meta` persistido |
| `bot/strategy.py` | `_open_additive`, umbrales en movimiento, gates de Op3/Op4, máquina del candado, disolución |
| `bot/strategy_m5.py` | tope compartido, `m5_max_lot_cap` 0 = off, cuenta muerta |
| `bot/config.py` | `ALERT_EMAIL_TO` |
| `bot/main.py` | log de `margin_hedged` al arrancar |
| `migrations/010_supervivencia.sql`, `schema.sql` | columnas nuevas y valores |
| `tests/test_supervivencia.py` (nuevo) | tests de este plan |
| `tests/test_ledger.py`, `tests/test_m5_and_budget.py` | extensiones y ajuste del test de la excepción L3 |

---

### Task 1: Núcleo de supervivencia (S, lote que cabe, hora UTC)

**Files:**
- Create: `bot/survival.py`
- Modify: `bot/broker.py` (añadir tras `margin_free`, ~línea 96)
- Test: `tests/test_supervivencia.py`

**Interfaces:**
- Produces:
  - `Broker.account_margin() -> float` (`account_info().margin`, 0.0 si None).
  - `Broker.contract_size() -> float` (`symbol_info().trade_contract_size`, 100.0 si None).
  - `survival.DEFAULTS: dict`, con todas las claves de Global Constraints más
    `equity_weight` 1.0.
  - `survival.net_lots(positions) -> float`: compras − ventas.
  - `survival.survival_usd(equity, margin, so_pct, net, contract) -> float`:
    - `inf` si `|net| < 1e-9`;
    - `max(0.0, equity − so_pct*margin/100) / (|net|*contract)` en otro caso.
  - `survival.utc_hour_from_server(ts: int) -> int`: hora del servidor = NY + 7 h; regla de DST
    de EE. UU. (2.º domingo de marzo 02:00 → 1.er domingo de noviembre 02:00, hora NY),
    implementada a mano, sin `zoneinfo`.
  - `survival.parse_hours(s: str) -> set[int]`.
  - `class SurvivalGuard(broker, cfg_provider, logger, own_magic)`:
    - `s_with_delta(delta_net: float, delta_margin: float) -> float`: usa
      `positions_all()`, `account_equity()`, `account_margin()`, `stop_out_levels()[1]` y
      `contract_size()`;
    - `s_now() -> float`;
    - `n_max() -> float`: `max(0, E − so*M/100) / (survival_move_usd*contract)`;
    - `fit(order_type, requested: float, label: str) -> float`: devuelve 0.0 si no cabe;
    - `s_after_close(position) -> float`: delta_net = −contribución de la posición,
      delta_margin = −`order_margin` de su volumen.
- Algoritmo de `fit`:
  1. Si la orden reduce `|net de cuenta|`, devuelve `requested` tal cual.
  2. Si no, prueba `v` desde `floor(requested/step)*step` hacia abajo en pasos de `step` hasta
     `volume_min`. Acepta el primero que cumpla las dos condiciones:
     - `s_with_delta(±v, order_margin(type, v)) >= survival_move_usd`;
     - y, si agranda el `|neto propio|` (magic `own_magic`),
       `|neto_propio ± v| <= equity_weight * n_max()`.
  3. Recorte → `BUDGET`: `"{label} reducida {req:.2f} → {v:.2f} por tope de supervivencia
     (S={S:.0f} $)"`.
  4. Nada cabe → `BUDGET`: `"{label} bloqueada por tope de supervivencia: no cabe {vmin:.2f}
     (S={S:.0f} $)"`.
  5. Dedupe: solo se loguea si cambia `(label, tipo)` respecto del último log.

- [ ] **Step 1: Write the failing tests** en `tests/test_supervivencia.py`.

  Estilo de `tests/test_ledger.py`: `check()` + `main()`, con `"test_supervivencia: TODO OK"`
  al final. Reutiliza `FakePos`/`FakeLogger`/`FakeBroker` de `tests.test_m5_and_budget` y
  define `SurvBroker(FakeBroker)`:
  - `positions()` filtra por `self.magic` y `positions_all()` devuelve todo;
  - `account_equity()` devuelve `self._equity`;
  - `account_margin()` devuelve `self._margin` (default 0.0);
  - `order_margin` devuelve 0.0 salvo que se configure `self._mpl` (margen por lote);
  - `stop_out_levels()` devuelve (100.0, 50.0);
  - `contract_size()` devuelve 100.0.

  ```python
  def test_survival_math():
      check(survival.survival_usd(5000, 0, 50, 0.0, 100) == float("inf"), "neto 0 => S infinito")
      check(abs(survival.survival_usd(6000, 2000, 50, 0.5, 100) - 100.0) < 1e-9, "(6000-1000)/(0.5*100)=100")
      check(survival.survival_usd(500, 2000, 50, 0.1, 100) == 0.0, "equity bajo el stop-out => 0")

  def test_fit_dynamic():   # E=7000, sin margen, equity_weight=1.0 => n_max=0.20
      # neto propio BUY 0.05 => pide 0.20 BUY => 0.15 ; neto 0.01 => 0.19 ;
      # neto SELL 0.15 => pide 0.20 BUY => 0.20 (nunca mas de lo pedido) ; neto BUY 0.196 => 0.0
      # + el log BUDGET "reducida 0.20 → 0.15" aparece una sola vez si se llama dos veces seguidas

  def test_fit_share_between_bots():   # E=7000, equity_weight 0.8 (M15) / 0.2 (M5)
      # M15 sin posiciones: fit(BUY, 0.50) == 0.16 ; M5 con equity_weight 0.2: fit(BUY, 0.50) == 0.04

  def test_s_after_close():   # BUY 0.10 + SELL 0.04 (neto 0.06), E=5000
      # s_after_close(SELL 0.04) == 5000/(0.10*100) == 500.0

  def test_utc_hour():
      # servidor 2026-08-19 16:00 (verano, UTC+3) -> 13 ; servidor 2026-01-15 15:00 (invierno, UTC+2) -> 13
      # servidor 2026-03-09 04:00 (dia siguiente al cambio de EE. UU.) -> 1
  ```

- [ ] **Step 2: Run** `python -m tests.test_supervivencia`. Expected: falla con
  `ModuleNotFoundError: bot.survival`.
- [ ] **Step 3: Implement** `bot/survival.py` y los dos métodos de broker según Interfaces.
- [ ] **Step 4: Run** `python -m tests.test_supervivencia`. Expected: `test_supervivencia: TODO OK`.
- [ ] **Step 5: Commit + push**:
  `feat(survival): aguante S de la cuenta, lote que cabe y hora UTC desde servidor`.

---

### Task 2: Ledger — rol `LOCK` y `meta` persistido

**Files:**
- Modify: `bot/ledger.py`
- Test: `tests/test_ledger.py`

**Interfaces:**
- Produces:
  - `ledger.ROLE_LOCK = "LOCK"`. En `_COMMENT_ROLES` se añade `("Basket Lock", ROLE_LOCK)`.
  - `CycleLedger.lock_legs(positions) -> list`: patas vivas con rol LOCK.
  - `cycle_legs()` **excluye** `ROLE_LOCK` (el candado no es profundidad del ciclo).
  - `CycleLedger.meta: dict`, persistido en el JSON bajo la clave `"meta"` (si falta, `{}`).
    Métodos: `get_meta(key, default=None)`, `set_meta(key, value)` (guarda) y
    `reset_meta()` (guarda).
  - Claves que usarán tareas posteriores: `ref_lot`, `rescue_opened`, `lock_since`,
    `lock_initial_volume`, `unlock_ref_price`, `last_unlock_ts`, `last_dissolve_day`.

- [ ] **Step 1: Write the failing tests**:
  - `test_lock_role`: `"Basket Lock"` se rehidrata como LOCK y no entra en `cycle_legs`, ni en
    `pairs`, ni en la promoción a ENTRY. Con ENTRY + HEDGE + RECOVERY + LOCK vivos,
    `cycle_legs` tiene 3 elementos y `lock_legs` tiene 1.
  - `test_meta_persists`: `set_meta("lock_since", 123)` y luego un `CycleLedger` nuevo sobre
    el mismo path devuelve 123. `reset_meta()` lo borra.

  Registrar los dos en `main()`.
- [ ] **Step 2: Run** `python -m tests.test_ledger`. Expected: FAIL (`ROLE_LOCK` no existe).
- [ ] **Step 3: Implement** según Interfaces.
- [ ] **Step 4: Run** `python -m tests.test_ledger`. Expected: `test_ledger: TODO OK`.
- [ ] **Step 5: Commit + push**: `feat(ledger): rol LOCK del candado de cesta y meta de ciclo persistido`.

---

### Task 3: Tope de supervivencia en todas las aperturas aditivas

**Files:**
- Modify: `bot/strategy.py`:
  - DEFAULTS (líneas 30-68);
  - `__init__` (~85);
  - borrar `_net_cap_ok` (184-197);
  - `_calculate_lots` (218-240);
  - entry (1146-1162), recovery (1186-1201), rescue (875-897);
  - reset de ciclo en `core_count == 0` (~1022).
- Modify: `bot/strategy_m5.py`: DEFAULTS `m5_max_lot_cap` 0.0; `_calculate_lots` (215-218);
  apertura (~773).
- Test: `tests/test_supervivencia.py`

**Interfaces:**
- Consumes: `SurvivalGuard` (Task 1); `CycleLedger.set_meta/get_meta/reset_meta` (Task 2).
- Produces:
  - `SentinelEngine.surv: SurvivalGuard` (own_magic = `config.MAGIC_NUMBER`). El
    `cfg_provider` mezcla `DEFAULTS` de strategy con `self.cfg`.
  - `SentinelEngine._open_additive(order_type, lots, comment, role, label) -> bool`:
    1. `lots = self.surv.fit(...)`; si es 0, devuelve False;
    2. `gov.can_open(lots, type, KIND_ADDITIVE)`;
    3. `market_order`;
    4. `_register_open`;
    5. `_news_note(label)`.

    Efectos de ciclo:
    - con `role == ROLE_ENTRY`, `set_meta("ref_lot", lots)`;
    - con `ROLE_RESCUE`, `set_meta("rescue_opened", n+1)`.

    Devuelve True si quedó registrada.
  - `M5Engine.surv` igual, con su magic. Antes de `gov.can_open` en la apertura del M5:
    `lots = self.surv.fit(order_type, lots, "Scalp M5")`, y si es 0 no abre.
  - DEFAULTS M15: `max_net_lots` 0.0, `max_entry_lots` 0.0, `max_recovery_lots` 0.0, más todas
    las claves de survival de Global Constraints. En `_calculate_lots` y en el tope de recovery,
    el cap solo aplica si es > 0.
  - En el bloque `core_count == 0` (reset de ciclo) se añade `self.cycle.reset_meta()`.

- [ ] **Step 1: Write the failing tests**:
  - `test_open_additive_resizes`: `SentinelEngine(SurvBroker(magic=MAGIC_M15, equity 7000),
    logger)`, `cfg={"equity_weight": 1.0}`, neto propio BUY 0.05.
    `_open_additive(BUY, 0.20, "Recovery Buy (V-Shape)", ROLE_RECOVERY, "Recovery")` envía una
    orden de **0.15**. Con neto 0.196, no envía nada y loguea `BUDGET` "bloqueada".
  - `test_entry_sets_ref_lot_and_rescue_counter`: tras una ENTRY de 0.09, `get_meta("ref_lot")
    == 0.09`. Tras dos RESCUE, `get_meta("rescue_opened") == 2`.
  - `test_no_fixed_lot_caps`: con `cfg={}` y equity 500 000, `_calculate_lots(False)` es
    > 1.0. En el M5, `_calculate_lots()` es > 0.50.
  - `test_min_lot_account_blocks_once` (Review Focus 5): equity 1 000, neto BUY 0.02. Llamar
    `_open_additive` de RECOVERY 3 veces → 0 órdenes y exactamente 1 evento `BUDGET`.
- [ ] **Step 2: Run** `python -m tests.test_supervivencia`. Expected: FAIL (`_open_additive` no
  existe).
- [ ] **Step 3: Implement.** Entry, recovery y rescue llaman a `_open_additive` en vez de
  `_net_cap_ok` + `gov.can_open` + `market_order` + `_register_open` + `_news_note`.
- [ ] **Step 4: Run** los tres suites. Expected: los tres "TODO OK".
- [ ] **Step 5: Commit + push**:
  `feat(m15,m5): tope de supervivencia con tamaño dinámico; fuera topes de lote fijos`.

---

### Task 4: Umbrales en movimiento del precio

**Files:**
- Modify: `bot/strategy.py`:
  - DEFAULTS;
  - trail de cesta (1036-1081);
  - `_profit_banking` (`floor`, ~756);
  - `_check_rescue` (`level2/level3`, 826-827).
- Test: `tests/test_supervivencia.py`

**Interfaces:**
- Consumes: `get_meta("ref_lot")` (Task 3), `Broker.contract_size()` (Task 1).
- Produces:
  - `SentinelEngine._ref_lot() -> float`: `meta ref_lot`, o `_calculate_lots(False)` si no
    hay.
  - `SentinelEngine._move_money(move_usd: float) -> float`:
    `move_usd * _ref_lot() * contract_size()`.
  - `SentinelEngine._rescue_level(abs_dd: float) -> int`: 1, 2 o 3 según `rescue_l2_move_usd`
    / `rescue_l3_move_usd` vía `_move_money`. `_check_rescue` lo usa para el multiplicador, el
    RSI, la inmediatez y el comment.
- Reemplazos exactos:

  | Hoy | Nuevo |
  |---|---|
  | `arm_target` | `_move_money(basket_arm_move_usd)` (se elimina el piso de 2.0) |
  | `rescue_target` | `_move_money(rescue_arm_move_usd)` (sin piso) |
  | `min_green_profit` | `_move_money(min_green_move_usd)` |
  | `max(1.0, min(x, 50.0))` | `max(_move_money(retrace_min_move_usd), min(x, _move_money(retrace_max_move_usd)))` |
  | `fixed_retrace` | `_move_money(fixed_retrace_move_usd)` |
  | `unwind_money_floor` | `_move_money(unwind_floor_move_usd)` |

- [ ] **Step 1: Write the failing test** `test_parity_across_accounts`:
  - tres engines con equity 5 000 / 10 000 / 20 000 y `ref_lot` 0.09 / 0.19 / 0.38;
  - para cada uno, con `abs_dd = k * ref_lot * 100` y k ∈ {10, 17, 45}, `_rescue_level`
    devuelve (1, 2, 3) en los tres;
  - `_move_money(0.83) / ref_lot` es igual en los tres, con tolerancia 1e-9;
  - el piso de Unwind con `ref_lot` 0.09 es 3.33×0.09×100 = 29.97.
- [ ] **Step 2: Run.** Expected: FAIL (`_move_money` no existe).
- [ ] **Step 3: Implement** según la tabla.
- [ ] **Step 4: Run** los tres suites. Expected: los tres "TODO OK".
- [ ] **Step 5: Commit + push**:
  `feat(m15): umbrales de cesta en movimiento del oro x lote de referencia del ciclo`.

---

### Task 5: Fin del bucle de Op4, Unwind con S, noticias y horas de riesgo

**Files:**
- Modify: `bot/strategy.py`:
  - `_check_rescue`;
  - `_profit_banking` (bucle de `best_single`, 762-771);
  - rama `cycle_count == 2` (~1166);
  - DEFAULTS `news_enforce` True.
- Modify: `bot/strategy_m5.py`: DEFAULTS `news_enforce` True.
- Modify: `tests/test_m5_and_budget.py` [16]: la excepción L3 pasa a esperarse **bloqueada**.
- Test: `tests/test_supervivencia.py`

**Interfaces:**
- Consumes: `survival.utc_hour_from_server`, `survival.parse_hours`, `surv.s_after_close`,
  `meta rescue_opened`.
- Produces:
  - `SentinelEngine._risk_hour() -> bool`: `utc_hour_from_server(self.now)` está en
    `parse_hours(risk_hours_utc)`.
  - Cambios en `_check_rescue`:
    - el límite es `get_meta("rescue_opened", 0) >= max_rescue_legs` (se elimina el uso de
      `_rescue_leg_count`);
    - `if self.news_block: return`, sin excepción L3;
    - `if self._risk_hour(): return`.
  - En recovery (`cycle_count == 2`), `if self._risk_hour(): return` junto al resto de gates.
  - En `_profit_banking`, una pata suelta se descarta si `_closing_increases_exposure(p)` y
    `surv.s_after_close(p) < survival_move_usd`. Los pares no cambian.

- [ ] **Step 1: Write the failing tests**:
  - `test_rescue_churn_capped`: abrir una Op4, cobrarla y repetir con `rescue_cooldown` 0 →
    tras 3 aperturas, la cuarta no se envía (reproduce el 19-ago 12:57–13:11 UTC).
  - `test_unwind_respects_survival`:
    - cesta BUY 0.30 (roja, −20 $) y SELL 0.20 (verde, +100 $), con E=5 000 y
      `cycle_realized` 1 000 para abrir el freeze;
    - cobrar la SELL dejaría neto 0.30 → S = 166 < 350 → **no** se cierra;
    - variante con la BUY verde (+100 $) y la SELL roja: la BUY **sí** se cobra, porque reduce
      el neto.
  - `test_risk_hours_block_recovery_and_rescue`: con `now` = servidor 2026-08-19 16:30
    (13 UTC), `_risk_hour()` es True y `_check_rescue` no envía nada. A las 06:30 servidor
    (03 UTC) es False.
  - Ajustar [16] de `test_m5_and_budget`: el L3-CRÍTICO con `news_block` **no** abre y no hay
    evento "excepcion".
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** los tres suites. Expected: los tres "TODO OK".
- [ ] **Step 5: Commit + push**:
  `fix(m15): Op4 por abiertas en el ciclo, Unwind con aguante, noticias sin excepcion L3, horas de riesgo`.

---

### Task 6: Alertas por correo y cuenta muerta

**Files:**
- Create: `bot/alerts.py`
- Modify: `bot/config.py`: `ALERT_EMAIL_TO = os.environ.get("ALERT_EMAIL_TO", "")`, junto
  al bloque RESEND.
- Modify: `bot/strategy.py` y `bot/strategy_m5.py`: inicio de `on_tick`; atributos en
  `__init__`.
- Modify: `bot/main.py`: tras el log de `trade_allowed` (~144), loguear `SYSTEM`
  `"margin_hedged del simbolo: {rate} (use_leg={use_leg})"`.
- Test: `tests/test_supervivencia.py`

**Interfaces:**
- Produces:
  - `class AlertManager(logger, to_addr, account_label, cooldown_s=21600, sender=notify.send_async, clock=time.time)`.
    - `notify(kind: str, severity: str, subject: str, body: str) -> bool`: dedupe por `kind`
      dentro de `cooldown_s`; devuelve True si envió.
    - Asunto: `"[Sentinel {severity}] {account_label}: {subject}"`.
    - Sin `to_addr` → no-op con un log `SYSTEM` una sola vez.
  - `alerts.account_dead(broker) -> tuple[bool, str]`: True si `account_equity() <= 0` o si
    `trade_allowed()` devuelve `(False, motivo)`.
  - Ambos engines tienen `self.alerts: AlertManager`, cuyo label es el login MT5 de
    `config.MT5_LOGIN` más `config.BOT_ID`. También `self.dead = False` y
    `self._dead_last_log = 0`.
  - En `on_tick`, tras `_compute_buffers`:
    - se evalúa `account_dead`;
    - si está muerta: `self.dead = True`, ERROR como mucho cada 600 s y
      `alerts.notify("cuenta_muerta", "CRITICA", ...)`;
    - las aperturas aditivas se saltan con `self.dead`: en el M15 desde `_open_additive`; en
      el M5, en el mismo gate que `gov.can_open`;
    - se libera sola cuando la condición desaparece.
  - `SentinelEngine._check_stop_out()`, una vez por minuto: `history_deals` del último día;
    deal propio con comment que empieza por `"[so"` y ticket > `self._last_so_ticket` →
    `alerts.notify("stop_out", "CRITICA", ...)`.
  - `SentinelEngine._check_idle()`, una vez por hora: sin posiciones propias y sin deal propio
    en 72 h → `alerts.notify("inactivo", "AVISO", ...)`.

- [ ] **Step 1: Write the failing tests**:
  - `test_alert_dedupe`: un sender falso registra las llamadas; dos `notify("x", ...)` en 1 h
    → 1 envío; con `clock` + 6 h + 1 s → 2 envíos.
  - `test_dead_account_gate`: equity 0 → `_open_additive` no envía, `self.dead` es True y hay
    un solo ERROR en 3 ticks. Con equity 5 000 → vuelve a abrir.
  - `test_stop_out_alert`: `history_deals` falso con un deal `comment="[so 18.85%/13.19/69.98]"`
    → exactamente 1 alerta `stop_out`.
- [ ] **Step 2: Run.** Expected: FAIL (no existe `bot.alerts`).
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** los tres suites. Expected: los tres "TODO OK".
- [ ] **Step 5: Commit + push**:
  `feat(alerts): correos de alerta con dedupe y gate de cuenta muerta (fin del spam D2)`.

---

### Task 7: Candado de cesta (poner + estado congelado)

**Files:**
- Modify: `bot/broker.py`: `order_check(order_type, lots) -> tuple[bool, object]`. Usa
  `mt5.order_check` con una request de mercado, como `market_order`. Devuelve
  `(retcode == 0 o TRADE_RETCODE_DONE, retcode)`. En shadow, `(True, 0)`.
- Modify: `bot/strategy.py`: `on_tick` (entre `self.cycle.sync(...)` en la línea ~1015 y
  `_check_healing`), los subsistemas y `_apply_healing` (`pair_frozen`).
- Test: `tests/test_supervivencia.py`

**Interfaces:**
- Consumes: `ROLE_LOCK`, `lock_legs`, meta (Task 2); `surv.s_now` (Task 1); `alerts.notify`
  (Task 6).
- Produces:
  - Constantes `LOCK_FREE = "LIBRE"`, `LOCK_FROZEN = "CONGELADO"`, `LOCK_LOOSE = "AFLOJADO"`.
  - `SentinelEngine._lock_state(positions) -> str`:
    - sin patas LOCK → LIBRE;
    - con LOCK y `|neto propio| < volume_step` → CONGELADO;
    - si no → AFLOJADO.
  - `SentinelEngine._maybe_lock() -> None`. Si `surv.s_now() < lock_trigger_usd` y
    `|neto propio| >= step`:
    1. `order_check` del lado contrario por `|neto propio|`;
    2. si pasa, `market_order(..., "Basket Lock")` y `_register_open(res, ROLE_LOCK)`;
    3. si queda confirmado:
       - `set_meta("lock_since", now)` solo si no existía;
       - `lock_initial_volume += vol`;
       - `modify_sl(p, 0)` en toda pata propia con `sl != 0` (Review Focus 2);
       - log `PROTECCION` `"Candado puesto: {vol:.2f} lotes {BUY|SELL}. S={S:.0f} $"`;
       - `alerts.notify("candado", "INFO", ...)`.
    4. Si falla (check o envío): ERROR
       `"Candado FALLIDO ({retcode}). S={S:.0f} $. Margen libre {free:.2f}"` como mucho cada
       600 s, y `alerts.notify("candado_fallido", "CRITICA", ...)`.
  - Comportamiento por estado en `on_tick`:
    - **CONGELADO** (tabla del spec §5.3):
      - no corren `_check_healing`, `_profit_banking`, el hedge monitor, `_resize_hedge`, el
        watchdog de huérfanos, el smart trail ni el trail de Op3;
      - no se abre nada aditivo;
      - el trail de cesta (`_close_all`), el viernes en positivo y `force_close` siguen.
    - **AFLOJADO:**
      - corre lo normal, pero las patas LOCK se excluyen de los candidatos del Unwind (como
        `pair_tickets`) y de `_apply_healing` (añadidas a `pair_frozen` siempre);
      - el trail de Op3 sigue desactivado.

- [ ] **Step 1: Write the failing tests**:
  - `test_lock_triggers`: E=5 000, propias BUY 0.34 → S=147 → orden SELL 0.34
    `"Basket Lock"`, rol LOCK, y `_lock_state` == CONGELADO. Con BUY 0.30 (S=166) no hay
    candado.
  - `test_frozen_blocks_subsystems`:
    - en CONGELADO, con una pata verde suelta y `cycle_realized` alto, `_profit_banking` no
      cierra nada;
    - `_open_additive` no envía;
    - el hedge monitor no abre `"Hedge Lock"` sobre una ENTRY desnuda.
  - `test_lock_clears_trailing_sl`: una RECOVERY con `sl` 4 410 → tras el candado, `sl == 0`.
  - `test_lock_failure_dedup`: `order_check` devuelve (False, 10019) en 5 ticks dentro de
    600 s → 1 ERROR y 1 alerta. Ninguna orden enviada.
  - `test_lock_survives_restart`:
    - crear el candado y un engine nuevo con el mismo `LEDGER_PATH` (temporal);
    - el estado es CONGELADO y `_maybe_lock` no envía un segundo candado;
    - `get_meta("lock_since")` se conserva.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** los tres suites. Expected: los tres "TODO OK".
- [ ] **Step 5: Commit + push**:
  `feat(m15): candado de cesta (rol LOCK) que congela el neto cuando S < 150 $`.

---

### Task 8: Aflojar el candado por rebote confirmado

**Files:**
- Modify: `bot/strategy.py`
- Test: `tests/test_supervivencia.py`

**Interfaces:**
- Consumes: `_lock_state`, `lock_legs`, meta `unlock_ref_price` / `last_unlock_ts` y
  `surv.s_with_delta`.
- Produces: `SentinelEngine._maybe_unlock() -> None`. Corre en CONGELADO y AFLOJADO, después
  de `_maybe_lock`.
  1. **Referencia:** `get_meta("unlock_ref_price")` o, si no existe, el precio medio ponderado
     por volumen de las patas LOCK.
  2. **Dirección favorable:** contraria al tipo de las patas LOCK. Si son SELL, el neto
     original es largo y el rebote es `bid − ref`; si son BUY, es `ref − ask`.
  3. **Gates (todos):**
     - rebote ≥ `unlock_rebound_usd`;
     - `not vol_breaker`, `not spread_high`, **`not news_active`** (cualquier ventana, no solo
       con enforcement) y `not _risk_hour()`.
  4. **Volumen:** el mayor `v` (en pasos de `step`, ≤ volumen LOCK total) tal que
     `surv.s_with_delta(dir_original*v, 0.0) >= survival_move_usd` y
     `|neto propio + dir*v| <= equity_weight * n_max()`. Si `v < volume_min`, no hace nada.
  5. **Cierre:** `close_partial` / `close_position` sobre las patas LOCK, empezando por la más
     nueva. Suma lo realizado a `cycle_realized`.
  6. `set_meta("unlock_ref_price", precio_actual)` y `set_meta("last_unlock_ts", now)`.
  7. Log `PROTECCION`
     `"Candado aflojado: cerrados {v:.2f} lotes (rebote +{r:.0f} $). S={S:.0f} $"` y
     `alerts.notify("candado_aflojado", "INFO", ...)`.

  Con todas las patas LOCK cerradas: `unlock_ref_price`, `lock_since` y `lock_initial_volume`
  se ponen a None.

- [ ] **Step 1: Write the failing tests** (E=5 000, LOCK SELL 0.34 a 4 400, ENTRY/recoveries
  BUY 0.34):
  - `test_no_unlock_on_continuation`: precio 4 340 (la pata LOCK gana 60) → nada se cierra.
    *Este es el caso del anti-objetivo.*
  - `test_unlock_on_rebound`: precio 4 451, 03 UTC, sin VCB ni noticia → se cierran **0.14**
    (5000/35000 = 0.142 → 0.14) y el estado pasa a AFLOJADO.
  - `test_unlock_gates`: el mismo rebote, pero con `news_active` True, o a las 13 UTC, o con
    VCB → nada se cierra.
  - `test_successive_unlock_needs_new_rebound`: tras el aflojado a 4 451, en 4 480 no se afloja
    más; en 4 501 sí.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** los tres suites. Expected: los tres "TODO OK".
- [ ] **Step 5: Commit + push**:
  `feat(m15): aflojar el candado solo con rebote confirmado hasta S >= 350 $`.

---

### Task 9: Disolución por parejas

**Files:**
- Modify: `bot/strategy.py`
- Test: `tests/test_supervivencia.py`

**Interfaces:**
- Consumes: meta `lock_since`, `last_unlock_ts`, `lock_initial_volume` y `last_dissolve_day`;
  `survival.parse_hours`, `utc_hour_from_server`.
- Produces: `SentinelEngine._maybe_dissolve() -> None`. Corre en CONGELADO, AFLOJADO y también
  en LIBRE para el caso "ambos lados".
  1. **Gates:**
     - `now − max(lock_since, last_unlock_ts or 0) >= lock_dissolve_after_h*3600`;
     - hora UTC en `lock_dissolve_hours_utc`;
     - `last_dissolve_day` != fecha UTC de hoy;
     - `not vol_breaker`.
  2. **Con patas LOCK:**
     - la contraparte es la pata `ROLE_RECOVERY` o `ROLE_RESCUE` del lado contrario a LOCK con
       peor `(profit+swap)/volume`;
     - **nunca ENTRY, HEDGE, ORPHAN ni sus coberturas**;
     - `X = max(volume_min, floor(lock_dissolve_fraction*lock_initial_volume/step)*step)`,
       limitado a `min(vol LOCK, vol contraparte)`.
  3. **Sin patas LOCK pero con Op3/Op4 en ambos lados** y su neto < `step` (los tres gates de
     tiempo usan `last_dissolve_day` y la hora; el plazo de 24 h se mide desde el último
     candado): se emparejan la peor de cada lado.
  4. **Cierre:** primero el miembro rojo y luego el verde. Lo realizado va a `cycle_realized`,
     `set_meta("last_dissolve_day", fecha)` y log `HEALER`
     `"Disolucion por parejas: {X:.2f} lotes de #{t1} + #{t2}. Neto sin cambio."`.

- [ ] **Step 1: Write the failing tests**:
  - `test_dissolve_pairs`:
    - candado SELL 0.30 desde hace 25 h, Op3 BUY 0.18 y Op4 BUY 0.12, más el par ENTRY/HEDGE
      0.09/0.09;
    - a las 03 UTC se cierran 0.10 de LOCK + 0.10 de la peor Op3/Op4;
    - el neto propio no cambia;
    - ENTRY y HEDGE intactos;
    - una segunda llamada el mismo día no hace nada.
  - `test_dissolve_waits`: con 23 h, o a las 13 UTC → nada.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** los tres suites. Expected: los tres "TODO OK".
- [ ] **Step 5: Commit + push**:
  `feat(m15): disolución diaria por parejas del candado sin re-exponer`.

---

### Task 10: Migración, schema y memoria

**Files:**
- Create: `migrations/010_supervivencia.sql`, con la cabecera estilo `009_pnl_rebase.sql` y
  "ESTADO: PENDIENTE de aplicar".
- Modify: `schema.sql`: columnas nuevas en `bot_config`.
- Create: `docs/memory/survival-cap-basket-lock.md` y su pointer en `docs/memory/MEMORY.md`.
  Es la decisión firme, con enlace al spec.
- Modify: `docs/memory/bot-design-constraints.md`: una línea que enlace a la memoria nueva
  (el candado es otra orden protectora que congela).

**Contenido de la migración (idempotente):**
1. **Columnas nuevas:** `ALTER TABLE public.bot_config ADD COLUMN IF NOT EXISTS` para cada
   clave de Global Constraints (`DOUBLE PRECISION`, salvo `risk_hours_utc` y
   `lock_dissolve_hours_utc` en `TEXT`), con los defaults listados. Además,
   `news_enforce BOOLEAN DEFAULT true`.
2. **Topes de lotes fijos desactivados:** `UPDATE public.bot_config SET news_enforce = true,
   max_net_lots = 0, max_entry_lots = 0, max_recovery_lots = 0, m5_max_lot_cap = 0;`
3. **Drift:**
   - `UPDATE ... SET margin_cap_pct = 60, ml_no_add = 200, ml_flatten = 0,
     inp_max_spread = 350 WHERE bot_id = 'm15';`
   - `UPDATE ... SET margin_cap_pct = 60, ml_no_add = 200, ml_flatten = 0
     WHERE bot_id = 'm5';`
4. **Bloque comentado "ROLLBACK":**
   - restaura `max_net_lots = 1, max_entry_lots = 1, max_recovery_lots = 2,
     m5_max_lot_cap = 0.5, news_enforce = false`;
   - restaura los valores previos con drift, sin user_id (repo público), identificando la fila
     por "la fila m5 que tenía 10/400/250" y "la m15 con inp_max_spread 300". El operador
     consulta antes con `SELECT user_id, bot_id, margin_cap_pct, ml_no_add, ml_flatten,
     inp_max_spread FROM public.bot_config;` y guarda la salida en local.

- [ ] **Step 1:** Escribir la migración y las columnas de `schema.sql`.
- [ ] **Step 2:** Verificar que `grep -c "ADD COLUMN IF NOT EXISTS" migrations/010_supervivencia.sql`
  es igual al número de claves nuevas + 1 (`news_enforce`).
- [ ] **Step 3:** Escribir la memoria y su pointer.
- [ ] **Step 4: Run** los tres suites. Expected: los tres "TODO OK".
- [ ] **Step 5: Commit + push**:
  `feat(db): migración 010 supervivencia + memoria de la decisión`.

---

## Después del plan (no es una tarea de código)

1. Revisión de toda la rama y reporte al usuario.
2. **Esperar el OK del usuario** antes de:
   - aplicar la migración 010 en Supabase (SQL Editor; primero guardar el `SELECT` de
     rollback);
   - poner `ALERT_EMAIL_TO` en los `.env` de `instances\`;
   - `restart_all`.
3. Ciclo de demo: dejar correr días → revisar el historial y Supabase (logs `PROTECCION`,
   `BUDGET` con "reducida"/"bloqueada", `HEALER` "Disolucion") → decidir.
4. Rollback: checkout de `experimento-1-grinder` + bloque ROLLBACK de la migración +
   `restart_all`.
