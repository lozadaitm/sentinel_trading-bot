"""Reglas puras de las tres patas (bot/sessions.py).

Correr:  python -m tests.test_e2_sessions
"""

import numpy as np
import pandas as pd

from bot import sessions as s

FAILS = []


def check(cond, name):
    print(("  PASS  " if cond else "  FAIL  ") + name)
    if not cond:
        FAILS.append(name)


def close(a, b):
    return abs(a - b) < 1e-9


def ep(txt):
    return int(pd.Timestamp(txt).timestamp())


def main():
    # trend_state
    up = pd.Series(np.arange(100.0, 170.0))
    check(s.trend_state(up) == 2, "trend creciente -> 2")
    check(s.trend_state(up[::-1].reset_index(drop=True)) == -2, "trend decreciente -> -2")
    v = np.full(70, 100.0)
    v[-64] = 200.0   # C[-1] < C[-64]
    v[-22] = 50.0    # C[-1] > C[-22]
    check(s.trend_state(pd.Series(v)) == 0, "trend mixto -> 0")
    check(s.trend_state(pd.Series(np.arange(30.0))) == 0, "trend 30 cierres -> 0")

    # atr_daily
    lo = pd.Series(np.zeros(14))
    check(close(s.atr_daily(lo + 10, lo), 10.0), "atr_daily 14 dias = 10")
    check(np.isnan(s.atr_daily(lo[:13] + 10, lo[:13])), "atr_daily <14 -> NaN")

    # atr15
    c = np.full(14, 100.0)
    check(close(s.atr15(c + 2, c - 2, c), 4.0), "atr15 rango 4 = 4")
    h = np.full(14, 102.0); l = np.full(14, 98.0); cc = np.full(14, 100.0)
    h[-1] = 120.0; l[-1] = 116.0   # hueco: TR = |120 - 100| = 20
    check(close(s.atr15(h, l, cc), (13 * 4.0 + 20.0) / 14), "atr15 usa cierre previo (hueco)")

    # bigone_weight
    check(s.bigone_weight(2, False) == 1.0, "bigone (2,F) 1.0")
    check(s.bigone_weight(0, False) == 0.5, "bigone (0,F) 0.5")
    check(s.bigone_weight(2, True) == 0.5, "bigone (2,T) 0.5")
    check(s.bigone_weight(-2, True) == 0.25, "bigone (-2,T) 0.25")

    # momentum_side
    check(s.momentum_side(4000, 4010, 2) == 1, "mom 0.25% -> +1")
    check(s.momentum_side(4000, 4009, 2) == 0, "mom 0.225% -> 0")
    check(s.momentum_side(4000, 3990, -2) == -1, "mom bajista -> -1")
    check(s.momentum_side(4000, 4010, 0) == 0, "mom sin tendencia -> 0")

    # nfp_side
    check(s.nfp_side(4000, 4005) == 1, "nfp sube")
    check(s.nfp_side(4000, 3995) == -1, "nfp baja")
    check(s.nfp_side(4000, 4000) == 0, "nfp igual")

    # ladder_lots
    check(s.ladder_lots(10000, 0.08, 1.0, 80) == [0.03, 0.03, 0.03], "ladder 10k")
    check(s.ladder_lots(3000, 0.08, 0.5, 80) == [0.01, 0.01, 0.01], "ladder minimo")
    check(s.ladder_lots(25000, 0.08, 1.0, 40) == [0.16, 0.16, 0.16], "ladder 25k")
    check(s.ladder_lots(10000, 0.08, 1.0, float("nan")) == [], "ladder atr nan")
    check(s.ladder_lots(10000, 0.08, 1.0, 0) == [], "ladder atr 0")

    # effective_risk
    check(close(s.effective_risk(0.03, 80, 3000), 0.08), "effective_risk")

    # lock_trigger / tp_prices
    check(close(s.lock_trigger(1, 4000, 80), 3920), "lock long")
    check(close(s.lock_trigger(-1, 4000, 80), 4080), "lock short")
    a = s.tp_prices(1, 4000, 5)
    check(close(a[0], 4010) and close(a[1], 4015), "tp long")
    b = s.tp_prices(-1, 4000, 5)
    check(close(b[0], 3990) and close(b[1], 3985), "tp short")

    # exit_epoch
    check(s.exit_epoch("bigone", ep("2026-10-20 01:00")) == ep("2026-10-20 10:00"), "exit bigone")
    check(s.exit_epoch("mom", ep("2026-10-20 15:00")) == ep("2026-10-20 21:00"), "exit mom")
    check(s.exit_epoch("nfp", ep("2026-10-22 16:30")) == ep("2026-10-23 17:30"), "exit nfp")
    try:
        s.exit_epoch("xx", 0)
        check(False, "exit pata desconocida -> ValueError")
    except ValueError:
        check(True, "exit pata desconocida -> ValueError")

    # add_market_bars
    check(s.add_market_bars(ep("2026-10-22 16:30"), 96) == ep("2026-10-23 17:30"), "bars jueves")
    check(s.add_market_bars(ep("2026-10-23 16:30"), 96) == ep("2026-10-26 17:30"), "bars viernes -> lunes")

    if FAILS:
        raise SystemExit(f"\ntest_e2_sessions: FALLOS {FAILS}")
    print("\ntest_e2_sessions: TODO OK")


if __name__ == "__main__":
    main()
