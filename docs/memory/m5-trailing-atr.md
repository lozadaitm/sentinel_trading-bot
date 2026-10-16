---
name: m5-trailing-atr
description: Decisión firme (16-oct-2026): el trailing del M5 pasa de puntos fijos a múltiplos del ATR de la apertura (0,5 / 0,3, turbo 1,25 → 0,15); proyectar objetivos por estructura se descartó con datos
metadata:
  type: project
---

**Problema:** el M5 acertaba el 85–89 %, pero cobraba ~1,3 $/oz por ganadora y perdía ~8,5 $/oz por perdedora. En 944 operaciones reales no tenía ventaja (−185 $).
- Causa: un trailing en puntos fijos (arranca a +1 $, sigue a 0,5 $), muy pegado para un ATR(M5) mediano de 4,9 $.

**Regla actual (`bot/strategy_m5.py`: `_manage_exits`, `_entry_atr_fn`):**
- **Modo:** `m5_trail_mode = 'atr'` (DEFAULT).
- **Arranque:** a `m5_trail_start_atr` (0,50) × A.
- **Distancia:** `m5_trail_dist_atr` (0,30) × A.
- **Turbo:** desde `m5_turbo_trigger_atr` (1,25) × A, sigue a `m5_turbo_dist_atr` (0,15) × A.
- **A** = ATR(14) M5 de la vela cerrada previa a la apertura, fijo durante toda la operación.
  - Se calcula desde `df_m5`, sin estado, así que sobrevive a reinicios.
  - Respaldo: `atr1`. Sin ATR, no hay trailing.
- **Sin cambios:** histéresis `m5_trail_step`, suelo `stops_level + 20 pt`, SL solo en verde, stop inicial y TimeStop.
- **Log:** una línea `GRINDER` «Trailing ATR armado: ticket #T, ATR X $, …» por posición.
- **Vuelta atrás sin código:** `m5_trail_mode = 'points'`.

**Why:**
- **Backtest tick a tick sobre las entradas reales** (`docs/experimento-2/auditoria-m5-2026-10-16.md`, sección 6):
  - de −30 a +147,5 $ por cada 0,01 lote;
  - mejora en las 5 semanas;
  - las 72 combinaciones vecinas mejoran a la actual.
- **Descartado con datos** (sección 7):
  - proyectar el objetivo por estructura (fractales M5/M15/H1) como TP, para apretar o como filtro;
  - stops más cortos;
  - filtros por hora, RSI o ATR.

**How to apply:**
- **Siguientes pasos,** solo por configuración y uno cada vez tras evaluar el trailing:
  - `m5_hard_sl_points` 0 (stop de 2 ATR sin suelo);
  - `m5_max_trade_min` 90.
- **El M15 no se tocó** (sección 8):
  - un trailing holgado en la Op1 duplica lo cobrado pero también los ciclos; requiere un backtest del ciclo completo;
  - la Op2 no salta antes de tiempo.
- **Evaluación,** tras al menos 2 semanas o 100 operaciones del M5:
  - la relación pérdida/ganancia debe bajar a unas 3× o menos;
  - el resultado por 0,01 lote no debe ser peor.
- **Tests:** `python -m tests.test_m5_trailing`. Migración 013. Spec: `docs/superpowers/specs/2026-10-16-m5-trailing-atr-design.md`.
- Ver [[m5-range-regime-v2]].

**Despliegue:** migración 013 aplicada y `restart_all` hecho el 2026-10-16 ~01:02 UTC. Los 6 bots quedaron RUNNING, sin errores, y los M15 retomaron sus 3 posiciones del ciclo del 14-oct.
