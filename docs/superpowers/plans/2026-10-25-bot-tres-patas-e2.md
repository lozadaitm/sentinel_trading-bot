# Bot «tres patas» (motor e2) — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** un motor nuevo e independiente, `e2` (`SessionEngine`), para las cuentas demo nuevas. Opera las tres patas aprobadas (Big One, Momentum EE. UU. y NFP) con escalera de 3 tercios, candado a 1 ATR diario que se cierra a la hora de salida, y riesgo del 8 %.

**Architecture:**
- **Reglas puras** (señales, tamaño, precios y tiempos) en `bot/sessions.py`, sin MT5, probadas con datos sintéticos.
- **Estado persistente** en `bot/e2_state.py`.
- **Motor** `bot/strategy_e2.py`, con la misma forma que `M5Engine`: lo corren `main.run()` / `lite.run_lite()` con `engine_cls=SessionEngine`.
- Identidad y arranque integrados en `config.py`, `run_instance.ps1`, `start_all.ps1` y `provision.py`.

**Tech Stack:** Python 3.14, MetaTrader5, numpy, pandas. Las pruebas siguen el estilo del repo: `python -m tests.test_x` con `check()` / `FAILS`.

**Spec:** `docs/experimento-2/diseno-bot-tres-patas-2026-10-25.md` (aprobado el 25-oct). Valores calibrados con `bot_backtesting/fullsim/broker_rule.py`, `bigone_broker.py` y `broker_accounts.py`.

## Global Constraints

- Sin stop loss en ninguna orden (`sl=0.0`) y sin cierre de emergencia. La única protección es el **candado** (orden opuesta).
- El candado y los tercios **se cierran juntos a la hora de salida**, aunque el neto sea negativo (decisión D1 del usuario). La regla de cobertura del M15 no aplica a e2.
- Magic **100300** fijo en código (`MAGIC_E2`); `BOT_ID = "e2"`. No se toca el comportamiento de los motores m15 y m5.
- Horas en **hora del servidor** (epoch de `symbol_info_tick().time` y de las velas MT5). Lunes a viernes.
- **Valores por defecto** (`DEFAULTS` de `strategy_e2.py`, sobrescribibles por `bot_config`):

  | Parámetro | Valor |
  |---|---|
  | `e2_risk_pct` | 0.08 |
  | `e2_lock_atrd_mult` | 1.0 |
  | `e2_tp_atr15_mults` | (2.0, 3.0) |
  | `e2_mom_threshold_pct` | 0.232 |
  | `e2_bigone_weight_nontrend` | 0.5 |
  | `e2_bigone_event_weight` | 0.5 |
  | `e2_entry_grace_s` | 60 |
  | `e2_nfp_hold_bars` | 96 |
  | `e2_legs` | "bigone,mom,nfp" |

- **Definiciones exactas, idénticas al simulador:**
  - `s`: signo(C − C₂₁) + signo(C − C₆₃) sobre los cierres D1 hasta el día anterior (desplazamiento en días de mercado).
  - `ATR_D`: media de (H − L) de los 14 días de servidor anteriores.
  - `ATR15`: media **simple** del rango verdadero de las 14 velas M15 cerradas anteriores.
- Sin lecturas profundas de MT5. Solo `copy_rates_from_pos` de hasta 120 velas D1 y 200 velas M15 por tick (como el M5 actual).
- Commits en la rama `experimento-2-rediseno`, con el trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Nunca `git add -A`.

## Review Focus

1. **Reinicio a mitad de una operación:** el motor recarga `instances/e2_state_<USER_ID>.json`, no reabre la pata ese día y sigue gestionando los objetivos, el candado y la salida. Prueba en Task 4.
2. **Bot apagado a la hora de salida:** si arranca después, cierra en el primer tick. Prueba en Task 4.
3. **Orden de candado rechazada:** se reintenta en cada tick, se registra ERROR una vez por minuto y la entrada queda «desnuda». Prueba en Task 4.
4. **Sin tick dentro de los 60 s de la entrada** (feriado o mercado cerrado): la pata se omite ese día y se registra. Prueba en Task 4.
5. **NFP un viernes:** la salida cuenta 96 velas M15 de mercado, salta el fin de semana y la pausa de 00:00–01:00, y termina el lunes. Prueba en Task 2.
6. **Balance chico:** cada tercio es como mínimo 0,01 aunque eso supere el riesgo planeado; se registra el riesgo efectivo. Prueba en Task 2.

---

### Task 1: Identidad e2 en la configuración y el arranque

**Files:**
- Modify: `bot/config.py` (`MAGIC_*`, `ALL_MAGICS`, `EXPECTED_MAGIC`)
- Modify: `scripts/run_instance.ps1` (`ValidateSet`, mapa de magics, módulo)
- Modify: `scripts/start_all.ps1` (validación de `BOTS`, magics distintos, aviso de m15)
- Create: `bot/lite_e2.py`, `bot/main_e2.py` (como `lite_m5.py` y `main_m5.py`, con `engine_cls=SessionEngine`)
- Test: `tests/test_e2_identity.py`

**Interfaces:**
- Produces:
  - `config.MAGIC_E2: int = int(os.environ.get("MAGIC_E2", "100300"))`, incluido en `ALL_MAGICS`;
  - `EXPECTED_MAGIC["e2"] = MAGIC_E2`;
  - módulos `bot.lite_e2` y `bot.main_e2`.

- [ ] **Step 1: Write the failing test** `tests/test_e2_identity.py`:
  - `check(config.EXPECTED_MAGIC["e2"] == 100300, ...)`
  - `check(100300 in config.ALL_MAGICS, ...)`
  - `check(len(set(config.ALL_MAGICS)) == len(config.ALL_MAGICS), "magics distintos")`
- [ ] **Step 2:** Run `python -m tests.test_e2_identity`. Expected: FAIL (`KeyError 'e2'`).
- [ ] **Step 3:** Add `MAGIC_E2` to `bot/config.py`.
- [ ] **Step 4: `run_instance.ps1`:**
  - `ValidateSet("m15","m5","e2","")`;
  - `"e2" = $env:MAGIC_E2 o "100300"` en `$magicMap`;
  - módulo `bot.lite_e2` si `-Lite`, si no `bot.main_e2` (sin TUI para e2).
- [ ] **Step 5: `start_all.ps1`:**
  - válidos `m15, m5, e2`;
  - el aviso «BOTS no incluye m15» solo si `BOTS` contiene m5;
  - leer `MAGIC_E2` y exigir los tres magics distintos.
- [ ] **Step 6: `provision.py`:** escribir `MAGIC_E2=100300` en la plantilla del `.env`. El default `bots` queda `"m15,m5"`: las cuentas nuevas se crearán con `bots="e2"` desde el dashboard/solicitud, o editando `BOTS=e2`.
- [ ] **Step 7:** Run `python -m tests.test_e2_identity`. Expected: todo PASS.
- [ ] **Step 8:** Commit: `feat(e2): identidad del motor tres patas (magic 100300) en config y arranque`.

### Task 2: Reglas puras `bot/sessions.py`

**Files:**
- Create: `bot/sessions.py`
- Test: `tests/test_e2_sessions.py`

**Interfaces** (todas puras; los precios son float y los tiempos epoch de servidor en int):

| Función | Contrato |
|---|---|
| `trend_state(d1_close: pd.Series) -> int` | Serie de cierres D1 en orden, **hasta el día anterior inclusive**. Devuelve −2, 0 o +2 (0 si hay menos de 64 cierres) |
| `atr_daily(day_high: pd.Series, day_low: pd.Series) -> float` | Media de los últimos 14 (H − L), días anteriores; NaN si hay menos de 14 |
| `atr15(high, low, close: np.ndarray) -> float` | Media simple del rango verdadero de las últimas 14 velas cerradas que se le pasan |
| `bigone_weight(state: int, event_day: bool, w_nontrend=0.5, w_event=0.5) -> float` | 1.0 o `w_nontrend`, por `w_event` si `event_day` |
| `momentum_side(p01: float, p15: float, state: int, thr_pct=0.232) -> int` | ±1 si \|(p15 − p01) / p01 × 100\| > thr y `state in (2, -2)`; si no, 0 |
| `nfp_side(open_before: float, price_after: float) -> int` | signo(price_after − open_before); 0 si son iguales |
| `ladder_lots(balance, risk_pct, weight, atr_d, step=0.01, vmin=0.01, vmax=100.0) -> list[float]` | 3 tercios iguales: `floor(balance × risk_pct × weight / (atr_d × 100) / 3 / step) × step`, mínimo `vmin`, máximo `vmax`; `[]` si `atr_d` no es finito o es ≤ 0 |
| `lock_trigger(side: int, entry: float, atr_d: float, mult=1.0) -> float` | `entry − side × mult × atr_d` |
| `tp_prices(side: int, entry: float, atr_15: float, mults=(2.0, 3.0)) -> tuple[float, float]` | Precios de los tercios 2 y 3 |
| `exit_epoch(leg: str, entry_epoch: int, nfp_bars=96) -> int` | `"bigone"`: mismo día a las 10:00. `"mom"`: 21:00. `"nfp"`: `add_market_bars(entry_epoch, nfp_bars)` |
| `add_market_bars(t: int, n: int) -> int` | Avanza n franjas de 15 min contando solo lunes a viernes, de 01:00 a 23:59. Salta la pausa de 00:00–01:00 y los fines de semana |
| `effective_risk(lots_total, atr_d, balance) -> float` | `lots_total × atr_d × 100 / balance` |

- [ ] **Step 1: Write the failing tests** `tests/test_e2_sessions.py`:
  - **`trend_state`:**
    - serie creciente de 70 cierres → `2`;
    - decreciente → `-2`;
    - 70 cierres con C[-1] > C[-22] pero C[-1] < C[-64] → `0`;
    - 30 cierres → `0`.
  - **`atr_daily`:** 14 días con H − L = 10 y 1 día extra al final con H − L = 100 (se le pasan solo los 14 anteriores) → `10.0`.
  - **`atr15`:** 14 velas de rango 4 sin huecos → `4.0`.
  - **`bigone_weight`:** `(2, False) → 1.0`; `(0, False) → 0.5`; `(2, True) → 0.5`; `(-2, True) → 0.25`.
  - **`momentum_side`:**
    - `(4000, 4010, 2) → 1` (0,25 % > 0,232);
    - `(4000, 4009, 2) → 0` (0,225 %);
    - `(4000, 3990, -2) → -1`;
    - `(4000, 4010, 0) → 0`.
  - **`ladder_lots`:**
    - `(10000, 0.08, 1.0, 80) → [0.03, 0.03, 0.03]` (0,1 lote total / 3 = 0,0333 → 0,03);
    - `(3000, 0.08, 0.5, 80) → [0.01, 0.01, 0.01]` (mínimo);
    - `(25000, 0.08, 1.0, 40) → [0.16, 0.16, 0.16]`;
    - `atr_d = nan → []`.
  - **`effective_risk`:** `(0.03, 80, 3000) == 0.08`.
  - **`lock_trigger`:** `(1, 4000, 80) == 3920`; `(-1, 4000, 80) == 4080`.
  - **`tp_prices`:** `(1, 4000, 5) == (4010, 4015)`; `(-1, 4000, 5) == (3990, 3985)`.
  - **`exit_epoch`:**
    - Big One con entrada el martes 2026-10-20 01:00 → martes 10:00;
    - `"mom"` con entrada a las 15:00 → 21:00.
  - **`add_market_bars`:**
    - jueves 2026-10-22 16:30 + 96 → viernes 2026-10-23 17:30 (de 16:30 a 23:45 son 30 franjas, se salta la pausa de 00:00–01:00 y faltan 66 desde la 01:00);
    - **viernes** 2026-10-23 16:30 + 96 → **lunes** 2026-10-26 17:30.
  - Para fijar epochs de servidor usar `int(pd.Timestamp("2026-10-20 01:00").timestamp())`. Es la convención del repo: el servidor se trata como si fuera UTC.
- [ ] **Step 2:** Run `python -m tests.test_e2_sessions`. Expected: FAIL (`ModuleNotFoundError bot.sessions`).
- [ ] **Step 3:** Implement `bot/sessions.py` with the interfaces above. Comentarios en español; cabecera que cite el diseño.
- [ ] **Step 4:** Run `python -m tests.test_e2_sessions`. Expected: todo PASS.
- [ ] **Step 5:** Commit: `feat(e2): reglas puras de las tres patas (señales, escalera, candado, horarios)`.

### Task 3: Estado persistente `bot/e2_state.py`

**Files:**
- Create: `bot/e2_state.py`
- Test: `tests/test_e2_state.py`

**Interfaces:**
- Produces: `class E2State` con:
  - `__init__(path: str)`;
  - `load() -> None`, que tolera un archivo ausente o corrupto (empieza vacío y lo registra el llamador);
  - `save() -> None`, escritura atómica (tmp + `os.replace`);
  - `legs: dict[str, dict]`. La clave es `f"{leg}:{entry_day}"`, con `entry_day = entry_epoch // 86400` del día de la **señal**.
  - Campos de cada valor:
    - `leg`, `side`, `entry_epoch`, `exit_epoch`;
    - `entry_price`, `atr_d`, `atr15`, `lock_price`;
    - `tp`: lista de 3, con `None` para el tercio 1;
    - `thirds`: lista de tickets;
    - `closed_thirds`: lista de tickets;
    - `lock_ticket`: int o `None`;
    - `status` ∈ {`"open"`, `"locked"`, `"closed"`, `"skipped"`}.
  - Métodos:
    - `entered(leg, day) -> bool`, True si la clave existe con cualquier estado;
    - `active() -> list[dict]`, los de estado `open` o `locked`;
    - `prune(before_day: int)`, borra cerrados u omitidos de más de 10 días.

- [ ] **Step 1: Write the failing tests:**
  - guardar y recargar devuelve lo mismo;
  - archivo con basura → `load()` deja `legs == {}` sin excepción;
  - `entered()` tras marcar `"skipped"` → True;
  - `active()` filtra por estado;
  - `prune()` borra solo lo viejo y cerrado.
- [ ] **Step 2:** Run `python -m tests.test_e2_state`. Expected: FAIL.
- [ ] **Step 3:** Implement `bot/e2_state.py` (json, `os.replace`).
- [ ] **Step 4:** Run `python -m tests.test_e2_state`. Expected: PASS.
- [ ] **Step 5:** Commit: `feat(e2): estado persistente de las patas`.

### Task 4: Motor `bot/strategy_e2.py` (`SessionEngine`)

**Files:**
- Create: `bot/strategy_e2.py`
- Test: `tests/test_e2_engine.py`. Reutilizar `FakeBroker`, `FakeLogger` y `FakePos` de `tests/test_m5_and_budget.py` con `magic=100300`; extender `FakeBroker` en el test si hace falta.

**Interfaces:**
- Consumes: `bot.sessions.*` (Task 2), `bot.e2_state.E2State` (Task 3) y `bot.news.NewsGuard(config.NEWS_CALENDAR_PATH, logger)`.
- Produces: `class SessionEngine`, con la forma que espera `bot/main.py`.
  - **Atributos:** `b`, `log`, `cfg` (dict), `hud` (dict), `is_active`, `close_only`, `user_email`, `initial_balance`, `last_flow_ticket`, `baseline_applied_at`.
  - **Métodos:**
    - `init_history_cursor()`: carga el estado y no hace nada más;
    - `on_tick()`;
    - `close_all(reason) -> bool`: mismo contrato que `M5Engine.close_all`, incluido el candado.
  - **Seams para pruebas** (como el M5):
    - `_now() -> int`: epoch de servidor del último tick;
    - `_fetch_tick()`;
    - `_rates_m15(n) -> pd.DataFrame | None`;
    - `_rates_d1(n) -> pd.DataFrame | None`;
    - `_events() -> list[dict]`: eventos HIGH en USD del calendario, de `NewsGuard._events` tras `_load(now)`, con claves `time`, `name`, `currency`, `importance`.

**Comportamiento por tick** (en este orden):
1. **Gestionar las activas** (`state.active()`):
   - Si `now >= exit_epoch`: cerrar los tercios abiertos y el candado. Estado `closed`, log `CIERRE` con el P&L total.
   - Si no, y el estado es `open`:
     - comprobar el candado: compra si `bid <= lock_price`, venta si `ask >= lock_price`. Si toca, abrir la orden opuesta por la suma del volumen de los tercios abiertos, comentario `E2 Lock <leg>`, `sl=0`. Si sale bien, estado `locked`. Si falla, reintentar el siguiente tick y registrar ERROR como mucho una vez por minuto.
     - Si no hubo candado, comprobar los objetivos de los tercios 2 y 3: compra con `bid >=`, venta con `ask <=`. Cerrar ese tercio y añadirlo a `closed_thirds`.
   - En estado `locked` no se evalúan objetivos.
2. **Entradas** (si `is_active` y no `close_only`), cada pata como mucho una vez por día de señal (`state.entered`):

| Pata | Ventana | Cálculo |
|---|---|---|
| Big One | `01:00:00 <= hora < 01:00 + e2_entry_grace_s` | `w = bigone_weight(s, event_day)`; `event_day` = algún evento USD HIGH con nombre que contenga «Non-Farm», «CPI» o «Federal Funds Rate» en el mismo día de servidor |
| Momentum | `15:00:00 <= hora < 15:00 + gracia` | `p01` = apertura de la vela M15 de las 01:00 de hoy; `p15` = precio actual (ask si `side = 1`, bid si `side = −1`, para la entrada) |
| NFP | `T + 3600 <= hora < T + 3600 + gracia` | T = hora del evento «Non-Farm Employment Change» floor a 15 min; `open_before` = apertura de la vela M15 de T − 900; `price_after` = bid actual |

   - **Si pasó la ventana sin entrar** (bot apagado o sin tick): marcar `skipped` con log `OMITIDA`.
   - **Al entrar:**
     1. `lots = ladder_lots(balance, e2_risk_pct, w, atr_d)`. Si viene vacío, `skipped`.
     2. Abrir 3 órdenes a mercado (`E2 <Leg> T1/T2/T3`, `sl=0`, `tp=0`) y guardar los tickets.
     3. Calcular `entry_price` (ask para compra, bid para venta), `lock_price` y `tp`.
     4. Fijar `exit_epoch` con `exit_epoch()`.
     5. Log `APERTURA` con: pata, lado, lotes, riesgo efectivo, `s`, `ATR_D`, `ATR15`, spread y deslizamiento frente al precio del tick previo a la orden.
   - **Si una de las 3 órdenes falla:** se guardan las que entraron; el resto no se reintenta.
3. **Guardar el estado** si cambió.
4. **HUD mínimo:** próxima entrada, patas activas y riesgo efectivo.

- [ ] **Step 1: Write the failing tests** `tests/test_e2_engine.py`, con `_now` y las velas inyectadas:
  - `test_bigone_entra_una_vez`: a las 01:00:05 de un día con `s = 2` abre 3 órdenes de compra con los lotes de `ladder_lots`; un segundo tick a las 01:00:20 no abre más.
  - `test_bigone_omitida_sin_tick`: el primer tick del día llega a las 01:05 → 0 órdenes, `status == "skipped"`.
  - `test_objetivos_cierran_tercios`: el bid sube a la entrada + 2 × ATR15 → se cierra solo T2; a + 3 × ATR15 → T3; T1 sigue abierto.
  - `test_candado`: el bid baja a `lock_price` → 1 orden de venta por el volumen abierto, estado `locked`; después un bid ≥ TP no cierra tercios.
  - `test_candado_fallido_reintenta`: el `FakeBroker` rechaza la primera orden de candado y acepta la segunda en el tick siguiente → estado `locked`, un ERROR registrado.
  - `test_salida_cierra_todo_con_candado`: a las 10:00 se cierran tercios y candado aunque el neto sea negativo → posiciones del magic = 0, estado `closed`.
  - `test_reinicio`: un motor nuevo con el mismo archivo de estado a las 05:00 no reabre la Big One y a las 10:00 cierra.
  - `test_arranque_tras_salida`: el estado tiene una pata abierta con `exit_epoch` pasado → se cierra en el primer tick.
  - `test_momentum_umbral`: `p01 = 4000`, precio 4009 → no entra; 4010 → compra.
  - `test_nfp_viernes`: entrada el viernes T + 60 → `exit_epoch` del lunes (Task 2) y venta si el precio bajó desde la apertura de T − 15.
  - `test_close_all`: cierra tercios y candado y devuelve True.
- [ ] **Step 2:** Run `python -m tests.test_e2_engine`. Expected: FAIL.
- [ ] **Step 3:** Implement `bot/strategy_e2.py`:
  - `DEFAULTS` de las Global Constraints;
  - `_p(key)` como en el M5;
  - archivo de estado `os.path.join(config.INSTANCES_DIR or "instances", f"e2_state_{config.USER_ID}.json")`. Usar la constante de rutas que ya exista en `config`; si no existe, la ruta `instances/` del repo.
- [ ] **Step 4:** Run `python -m tests.test_e2_engine`. Expected: PASS. También `python -m tests.test_m5_and_budget` y `python -m tests.test_m5_trailing` siguen en PASS.
- [ ] **Step 5:** Commit: `feat(e2): motor SessionEngine de las tres patas con escalera y candado`.

### Task 5: Reproducción contra el simulador

**Files:**
- Create: `bot_backtesting/fullsim/e2_replay.py`

Alimenta `SessionEngine` con un `FakeBroker` que recorre las velas M15 del broker (`data/broker_m15_full.pkl`, fuera de git). Si falta el archivo, se omite y lo dice.

**Interfaces:**
- Consumes: `SessionEngine`, con los seams de Task 4.
- Produces: el script `python -m bot_backtesting.fullsim.e2_replay`, que imprime la comparación por pata.

- [ ] **Step 1:** Implement the replay, 2025-11-01 → 2026-10-16:
  - un tick por vela M15, al abrir, con bid = open y ask = open + 0,17;
  - calendario NFP / IPC / FOMC desde `events_us.csv`, convertido a eventos HIGH en USD con hora de servidor, como hace `broker_round2.news_entries`;
  - `e2_bigone_event_weight = 1.0` (la proyección del simulador no aplicó ese ×0,5);
  - fills al precio del tick.
- [ ] **Step 2:** Comparar contra `broker_accounts.trades_fixed(ladder=True)` filtrado a ese período: número de entradas por pata, lados, y para cada operación el estado final (candado o no) y el P&L $/oz por tercio. Diferencia de P&L medio por pata < 0,05 $/oz. Coincidencia de entradas y lados ≥ 98 %, con las diferencias listadas.
- [ ] **Step 3:** Run `python -m bot_backtesting.fullsim.e2_replay`. Expected: imprime `OK` por pata. Si falla, arreglar `sessions` / `strategy_e2`, no el simulador, salvo que se demuestre un error del simulador (documentarlo).
- [ ] **Step 4:** Commit: `test(e2): reproduccion del motor contra el simulador del broker`.

### Task 6: Reporte diario y documentación de puesta en marcha

**Files:**
- Modify: `scripts/daily_report.py`. Agregar e2 a donde se mapean los magics o bots, para que salga en el correo.
- Create: `docs/memory/e2-motor-tres-patas.md`, más su línea en `docs/memory/MEMORY.md`.
- Modify: `docs/experimento-2/diseno-bot-tres-patas-2026-10-25.md`, con un enlace al plan y el estado «implementado».

- [ ] **Step 1:** Daily report:
  - las filas del magic 100300 se etiquetan «e2 (tres patas)»;
  - se resumen operaciones por pata, leídas del comentario `E2 <Leg>`.
  - Verificar con `python -m scripts.daily_report --dry-run`, o el modo de prueba que tenga.
- [ ] **Step 2:** Memoria `e2-motor-tres-patas`:
  - qué es, magic y BOT_ID, archivo de estado, cómo arrancar (`BOTS=e2`, `start_all.ps1`) y cómo apagar una pata (`e2_legs`);
  - que el colector de ticks debe apuntar con `--login` a una cuenta nueva cuando exista.
- [ ] **Step 3:** Commit: `docs(e2): reporte diario y memoria del motor tres patas`.

### Task 7: Prueba en seco en demo (con el usuario)

- [ ] **Step 1:** Cuando el usuario cree las 3 cuentas nuevas (3 000 / 10 000 / 25 000), se provisionan con `bots="e2"`, o con `BOTS=e2` en su `.env`.
- [ ] **Step 2:** **Con permiso explícito del usuario**, arrancar una sola cuenta con `e2_risk_pct = 0.0001` (lote mínimo) durante un día:
  - verificar la apertura de los 3 tercios a la 01:00;
  - verificar el log `APERTURA` con spread y deslizamiento;
  - verificar el cierre a las 10:00 y el archivo de estado.
- [ ] **Step 3:** Con el visto bueno del usuario, poner `e2_risk_pct = 0.08` en las tres y empezar las 10 semanas de demo (criterios en §8 del diseño).
