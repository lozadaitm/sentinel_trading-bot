"""Op4 tendencia: abre contra la recovery que pierde (a favor del movimiento).

Spec: docs/superpowers/specs/2026-10-16-op4-tendencia-design.md
Correr:  python -m tests.test_op4_trend
"""

import pandas as pd
import MetaTrader5 as mt5

from bot import strategy
from tests.test_healer import _Deals
from tests.test_supervivencia import _eng, _pos, check, ts

BUY, SELL = mt5.POSITION_TYPE_BUY, mt5.POSITION_TYPE_SELL
ATR = 4.0
T0 = ts(2026, 8, 19, 6) + 1800      # 03:30 UTC: fuera de horas de riesgo


def _bars(e, close1, t=T0):
    """df_m15 con la vela cerrada (iloc[-2]) a close1 y la vela en curso."""
    e.df_m15 = pd.DataFrame({"time": [t - 900, t], "close": [close1, close1]})


def _cycle(close1, sell=True, rec_vol=0.22, equity=50000.0, cfg=None):
    """Ciclo del 14-oct: entrada + cobertura (par congelado) + recovery perdiendo."""
    c = {"equity_weight": 1.0, "rescue_cooldown": 0, "news_enforce": False}
    c.update(cfg or {})
    e, b, log = _eng(equity=equity, cfg=c)
    b._next = 500
    e.now, e.atr0 = T0, ATR
    if sell:
        _pos(b, 1, SELL, 0.22, 4147.0, "SMC Sell Entry", t=T0 - 9000)
        _pos(b, 2, BUY, 0.22, 4161.0, "Hedge Lock", t=T0 - 8000)
        rec = _pos(b, 3, SELL, rec_vol, 4090.0, "Recovery Sell (V-Shape)", t=T0 - 7000)
    else:
        _pos(b, 1, BUY, 0.22, 4000.0, "SMC Buy Entry", t=T0 - 9000)
        _pos(b, 2, SELL, 0.22, 3986.0, "Hedge Lock", t=T0 - 8000)
        rec = _pos(b, 3, BUY, rec_vol, 4050.0, "Recovery Buy (V-Shape)", t=T0 - 7000)
    e.cycle.sync(b.positions())
    _bars(e, close1)
    return e, b, log, rec


def _t_orders(b):
    return [o for o in b.orders if o["comment"] == strategy.OP4_TREND_COMMENT]


def _legs(b):
    return list(b.positions())


def test_trigger():
    e, b, log, _ = _cycle(4090.0 + 2.1 * ATR)
    e._check_rescue(_legs(b))
    o = _t_orders(b)
    check(len(o) == 1 and o[0]["type"] == mt5.ORDER_TYPE_BUY, f"recovery SELL a -2.1 ATR => BUY (got {b.orders})")
    check(any(t == "RESCATE" and "Op4 tendencia: BUY 0.22" in m and "Op4 1/6" in m for t, m in log.events),
          "log de apertura")
    e, b, log, _ = _cycle(4090.0 + 1.9 * ATR)
    e._check_rescue(_legs(b))
    check(not b.orders, "a -1.9 ATR no abre")


def test_size():
    e, b, log, _ = _cycle(4090.0 + 3 * ATR)
    e._check_rescue(_legs(b))
    check(abs(_t_orders(b)[0]["lots"] - 0.22) < 1e-9, "neto -0.22, recovery 0.22 => 0.22")
    e, b, log, _ = _cycle(4090.0 + 3 * ATR)
    _pos(b, 4, BUY, 0.12, 4100.0, "Recovery Buy (V-Shape)", t=T0 - 6000)
    e.cycle.sync(b.positions())
    e._check_rescue(_legs(b))
    check(abs(_t_orders(b)[0]["lots"] - 0.10) < 1e-9, f"neto -0.10 => 0.10 (got {b.orders})")
    e, b, log, _ = _cycle(4090.0 + 3 * ATR)
    _pos(b, 4, BUY, 0.22, 4100.0, "Recovery Buy (V-Shape)", t=T0 - 6000)
    e.cycle.sync(b.positions())
    e._check_rescue(_legs(b))
    check(not b.orders, "neto 0 => no abre")


def test_direction_mirror():
    e, b, log, _ = _cycle(4050.0 - 2.1 * ATR, sell=False)
    e._check_rescue(_legs(b))
    o = _t_orders(b)
    check(len(o) == 1 and o[0]["type"] == mt5.ORDER_TYPE_SELL, f"recovery BUY perdiendo => SELL (got {b.orders})")


def test_one_at_a_time():
    e, b, log, _ = _cycle(4090.0 + 3 * ATR)
    _pos(b, 4, BUY, 0.10, 4100.0, strategy.OP4_TREND_COMMENT, t=T0 - 6000)
    e.cycle.sync(b.positions())
    e._check_rescue(_legs(b))
    check(not b.orders, "con una Op4 (T) viva no se abre otra")


def test_cap():
    e, b, log, _ = _cycle(4090.0 + 3 * ATR)
    e.cycle.set_meta("rescue_opened", 6)
    e._check_rescue(_legs(b))
    _bars(e, 4090.0 + 3 * ATR, t=T0 + 900)
    e._check_rescue(_legs(b))
    n = sum(1 for t, m in log.events if "cupo del ciclo agotado" in m)
    check(not b.orders and n == 1, f"cupo 6: no abre y loguea una vez (logs {n})")


def test_gates():
    for attr in ("news_block", "vol_breaker", "spread_high", "close_only"):
        e, b, log, _ = _cycle(4090.0 + 3 * ATR)
        setattr(e, attr, True)
        e._check_rescue(_legs(b))
        check(not b.orders, f"{attr}: no abre")
    e, b, log, _ = _cycle(4090.0 + 3 * ATR)
    e.lock_state = strategy.LOCK_FROZEN
    e._check_rescue(_legs(b))
    check(not b.orders, "candado vivo: no abre")
    e, b, log, _ = _cycle(4090.0 + 3 * ATR)
    e.now = ts(2026, 8, 19, 16) + 1800    # 13:30 UTC = 09:30 NY
    _bars(e, 4090.0 + 3 * ATR, t=e.now)
    check(e._risk_hour() is True, "16:30 servidor es hora de riesgo")
    e._check_rescue(_legs(b))
    check(len(_t_orders(b)) == 1, "en hora de riesgo SI abre (no promedia)")


def test_pair_not_target():
    # Recovery en verde; la entrada SELL del par pierde 10 ATR: no es objetivo.
    e, b, log, _ = _cycle(4080.0)
    b._pos[0].price_open = 4040.0
    e._check_rescue(_legs(b))
    check(not b.orders, "la entrada del par congelado no es objetivo")


def test_once_per_bar():
    e, b, log, _ = _cycle(4090.0 + 1.9 * ATR)
    e._check_rescue(_legs(b))
    _bars(e, 4090.0 + 2.5 * ATR)              # misma vela cerrada, otro cierre
    e._check_rescue(_legs(b))
    check(not b.orders, "la misma vela cerrada no se evalua dos veces")
    _bars(e, 4090.0 + 2.5 * ATR, t=T0 + 900)
    e._check_rescue(_legs(b))
    check(len(_t_orders(b)) == 1, "la vela siguiente si")


def test_trailing_params():
    e, b, log, _ = _cycle(4100.0)
    op4 = _pos(b, 4, BUY, 0.22, 4100.0, strategy.OP4_TREND_COMMENT)
    rec = b._pos[2]
    st, ds = e._op3_trail_params(op4, 500, ATR, 0.01)
    check(abs(st - 400) < 1e-9 and abs(ds - 200) < 1e-9, f"Op4 (T): 1.0/0.5 ATR (got {st}, {ds})")
    st, ds = e._op3_trail_params(op4, 5000, ATR, 0.01)
    check(abs(ds - 200) < 1e-9, "Op4 (T): sin turbo")
    st, ds = e._op3_trail_params(rec, 500, ATR, 0.01)
    check(abs(st - 240) < 1e-9 and abs(ds - 160) < 1e-9, f"recovery: 0.6/0.4 ATR (got {st}, {ds})")
    st, ds = e._op3_trail_params(rec, 1300, ATR, 0.01)
    check(abs(ds - 480) < 1e-9, "recovery: turbo 3.0 -> 1.2 ATR intacto")


def test_healer_chain():
    close1 = 4090.0 + 5 * ATR                 # recovery a -20 $/oz
    e, b, log, rec = _cycle(close1)
    rec.profit = -20.0 * 0.22 * 100           # -440 $
    d = _Deals(b)
    e._healer_needs_rebaseline = False
    e._check_rescue(_legs(b))
    op4 = [p for p in b._pos if p.comment == strategy.OP4_TREND_COMMENT]
    check(len(op4) == 1, "abre la primera Op4 (T)")
    e._check_healing()
    check(not b.partials, "con la Op4 (T) viva la recovery no se amputa (protegida por neto)")
    b._pos.remove(op4[0])                     # el broker la cierra por trailing...
    d.win(100.0)                              # ...con +100 $
    e._check_healing()                        # bolsa 90 / 2000 $/lote => 0.04
    check(b.partials and abs(b.partials[0]["lots"] - 0.04) < 1e-9 and abs(rec.volume - 0.18) < 1e-9,
          f"el curador recorta 0.04 de la recovery (got {b.partials})")
    rec.profit = -20.0 * rec.volume * 100
    _bars(e, close1, t=T0 + 900)
    e._check_rescue(_legs(b))
    o = _t_orders(b)
    check(len(o) == 2 and abs(o[1]["lots"] - 0.18) < 1e-9, f"la siguiente Op4 (T) es del volumen restante (got {o})")


def test_copy_switch():
    e, b, log, _ = _cycle(4090.0 + 3 * ATR, cfg={"rescue_mode": "copy"})
    e._check_rescue(_legs(b))
    check(not _t_orders(b), "rescue_mode='copy': nunca abre la Op4 (T)")


def test_survival_lets_it_pass():
    e, b, log, _ = _cycle(4090.0 + 3 * ATR, equity=3000.0)   # S = 3000/22 = 136 < 350
    e._check_rescue(_legs(b))
    check(len(_t_orders(b)) == 1, "S bajo 350: la Op4 (T) pasa porque reduce el neto")


def main():
    for t in (test_trigger, test_size, test_direction_mirror, test_one_at_a_time, test_cap, test_gates,
              test_pair_not_target, test_once_per_bar, test_trailing_params, test_healer_chain,
              test_copy_switch, test_survival_lets_it_pass):
        print(t.__name__)
        t()
    print("\ntest_op4_trend: TODO OK")


if __name__ == "__main__":
    main()
