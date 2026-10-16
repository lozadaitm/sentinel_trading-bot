"""Trailing del M5 proporcional al ATR de la apertura.

Spec: docs/superpowers/specs/2026-10-16-m5-trailing-atr-design.md
Correr:  python -m tests.test_m5_trailing
"""

import numpy as np
import pandas as pd
import MetaTrader5 as mt5

from bot.strategy_m5 import M5Engine
from tests.test_m5_and_budget import FakeBroker, FakeLogger, FakePos

T0 = 1_700_000_000
OPEN_BAR = 150                       # la posicion abre dentro de esta vela
BUY, SELL = mt5.POSITION_TYPE_BUY, mt5.POSITION_TYPE_SELL
FAILS = []


def check(cond, name):
    print(("  PASS  " if cond else "  FAIL  ") + name)
    if not cond:
        FAILS.append(name)


def _df(atr_before=4.0, atr_after=None, n=200):
    """Velas M5 con rango constante => ATR Wilder exacto. Desde OPEN_BAR el rango
    puede cambiar (atr_after) para comprobar que manda el ATR de la apertura."""
    rng = np.full(n, atr_before)
    if atr_after is not None:
        rng[OPEN_BAR:] = atr_after
    c = np.full(n, 4000.0)
    return pd.DataFrame({"time": pd.to_datetime(T0 + np.arange(n) * 300, unit="s"),
                         "open": c, "high": c + rng / 2, "low": c - rng / 2, "close": c})


def _eng(cfg=None, atr_before=4.0, atr_after=None, live_atr=None):
    b, log = FakeBroker(), FakeLogger()
    e = M5Engine(b, log)
    e.cfg = dict(cfg or {})
    e.df_m5 = _df(atr_before, atr_after)
    e.atr1 = live_atr if live_atr is not None else (atr_after or atr_before)
    e.now = T0 + OPEN_BAR * 300 + 120
    return e, b, log


def _pos(b, side=BUY, open_=4000.0, t=None):
    p = FakePos(len(b._pos) + 1, side, 0.10, open_, T0 + OPEN_BAR * 300 + 60 if t is None else t,
                "M5 Surfer Buy" if side == BUY else "M5 Surfer Sell", b.magic)
    b._pos.append(p)
    return p


def _move(p, adv):
    p.price_current = p.price_open + adv if p.type == BUY else p.price_open - adv
    p.profit = adv * p.volume * 100


def _armed(log):
    return [m for t, m in log.events if m.startswith("Trailing ATR armado")]


def test_start():
    e, b, log = _eng()
    p = _pos(b)
    _move(p, 1.9)
    e._manage_exits()
    check(p.sl == 0, "+1.9 $ < 0.5 ATR (2.0): sin SL")
    _move(p, 2.1)
    e._manage_exits()
    check(abs(p.sl - 4000.9) < 1e-6, f"+2.1 $: SL a 0.3 ATR = 4000.90 (got {p.sl})")


def test_normal_and_turbo():
    e, b, log = _eng()
    p = _pos(b)
    _move(p, 3.0)
    e._manage_exits()
    check(abs(p.sl - 4001.8) < 1e-6, f"+3.0 $: SL 4001.80 (got {p.sl})")
    _move(p, 5.5)
    e._manage_exits()
    check(abs(p.sl - 4004.9) < 1e-6, f"+5.5 $ (> 1.25 ATR): turbo a 0.15 ATR = 4004.90 (got {p.sl})")


def test_entry_atr_fixed():
    e, b, log = _eng(atr_before=4.0, atr_after=10.0)      # el ATR vivo sube a 10
    p = _pos(b)
    _move(p, 2.1)
    e._manage_exits()
    check(abs(p.sl - 4000.9) < 1e-6, f"manda el ATR de la apertura (4.0), no el vivo (got {p.sl})")


def test_fallback_live_atr():
    e, b, log = _eng(atr_before=4.0, live_atr=6.0)
    p = _pos(b, t=T0 - 3600)                               # abrio antes de la primera vela de df_m5
    _move(p, 2.9)
    e._manage_exits()
    check(p.sl == 0, "respaldo atr1=6: +2.9 < 3.0 sin SL")
    _move(p, 3.1)
    e._manage_exits()
    check(abs(p.sl - 4001.3) < 1e-6, f"respaldo atr1=6: SL a 1.8 $ = 4001.30 (got {p.sl})")


def test_no_atr_no_trailing():
    e, b, log = _eng()
    e.df_m5 = None
    e.atr1 = 0.0
    p = _pos(b)
    _move(p, 5.0)
    e._manage_exits()
    check(p.sl == 0, "sin ATR disponible: no se arma el trailing")


def test_broker_floor():
    e, b, log = _eng(atr_before=1.0)                       # turbo 0.15 $ < stops_level 30 + 20 pt
    p = _pos(b)
    _move(p, 2.0)
    e._manage_exits()
    check(abs(p.sl - 4001.5) < 1e-6, f"distancia minima del broker 0.50 $ (got {p.sl})")


def test_sell_mirror():
    e, b, log = _eng()
    p = _pos(b, SELL)
    _move(p, 1.9)
    e._manage_exits()
    check(p.sl == 0, "venta +1.9: sin SL")
    _move(p, 3.0)
    e._manage_exits()
    check(abs(p.sl - 3998.2) < 1e-6, f"venta +3.0: SL 3998.20 (got {p.sl})")
    _move(p, 5.5)
    e._manage_exits()
    check(abs(p.sl - 3995.1) < 1e-6, f"venta turbo: SL 3995.10 (got {p.sl})")


def test_step_and_green():
    e, b, log = _eng()
    p = _pos(b)
    _move(p, 3.0)
    e._manage_exits()
    prev = p.sl
    _move(p, 3.05)
    e._manage_exits()
    check(p.sl == prev, "histeresis: 5 pt < trail_step 10 no mueve el SL")
    e2, b2, _ = _eng(cfg={"m5_trail_start_atr": 0.2})      # arranca a 0.8 $, distancia 1.2 $
    q = _pos(b2)
    _move(q, 1.0)
    e2._manage_exits()
    check(q.sl == 0, "el SL nunca queda en rojo")


def test_log_once():
    e, b, log = _eng()
    p = _pos(b)
    for adv in (2.1, 3.0, 4.0, 5.5):
        _move(p, adv)
        e._manage_exits()
    a = _armed(log)
    check(len(a) == 1 and f"#{p.ticket}" in a[0] and "ATR 4.00 $" in a[0], f"un solo log de armado ({a})")


def test_points_mode_unchanged():
    e, b, log = _eng(cfg={"m5_trail_mode": "points"})
    p = _pos(b)
    _move(p, 1.5)                                          # +150 pt > trail_start 100
    e._manage_exits()
    check(abs(p.sl - 4001.0) < 1e-6, f"modo points: SL a 50 pt del precio (got {p.sl})")
    check(not _armed(log), "modo points: sin log de ATR")


def main():
    for t in (test_start, test_normal_and_turbo, test_entry_atr_fixed, test_fallback_live_atr,
              test_no_atr_no_trailing, test_broker_floor, test_sell_mirror, test_step_and_green,
              test_log_once, test_points_mode_unchanged):
        print(t.__name__)
        t()
    if FAILS:
        raise SystemExit(f"\ntest_m5_trailing: FALLOS {FAILS}")
    print("\ntest_m5_trailing: TODO OK")


if __name__ == "__main__":
    main()
