"""Re-entradas sobre la misma ruptura, suelo del hedge y horas de riesgo NY.

Spec: docs/superpowers/specs/2026-10-15-reentrada-y-suelo-hedge-design.md
Correr:  python -m tests.test_reentrada
"""

import MetaTrader5 as mt5
import numpy as np
import pandas as pd

from bot import indicators, survival
from tests.test_supervivencia import (_eng, _no_signals, _pos, _tick_eng, check, ts)

BUY, SELL = mt5.ORDER_TYPE_BUY, mt5.ORDER_TYPE_SELL
LEVEL = 105.0


def _df(direction=1, n=40):
    """M15 sintetico con un fractal confirmado en shift 5 y la vela cerrada (shift 1)
    rompiendolo. direction=1: fractal superior 105 roto al alza; -1: inferior 95 a la baja."""
    highs = np.full(n, 100.0)
    lows = np.full(n, 99.0)
    closes = np.full(n, 99.5)
    k = n - 1 - 5
    if direction == 1:
        highs[k] = LEVEL
        highs[n - 2], closes[n - 2] = 106.5, 106.0
    else:
        lows[:] = 98.0
        highs[:] = 101.0
        lows[k] = 95.0
        lows[n - 2], closes[n - 2] = 93.5, 94.0
    return pd.DataFrame({"high": highs, "low": lows, "close": closes, "open": closes})


class _TkLogger:
    """FakeLogger que ademas guarda el ticket de cada linea Re-entrada."""
    def __init__(self):
        self.events, self.tickets = [], []

    def write(self, t, m, price=0.0, lots=0.0, balance=0.0, ticket=0):
        self.events.append((t, m))
        if m.startswith("Re-entrada"):
            self.tickets.append(ticket)


def _entry_eng(cfg=None, price=None):
    c = {"equity_weight": 1.0}
    c.update(cfg or {})
    e, b, _ = _eng(equity=50000.0, cfg=c)
    log = e.log = _TkLogger()
    e.now = ts(2026, 8, 19, 6)
    e.atr0 = e.atr1 = 2.0          # ATR efectivo = 2.0 $
    e.df_m15 = _df(1)
    b._price = price if price is not None else LEVEL + 0.5   # ask = 105.75 (0.375 ATR)
    return e, b, log


def _set_ask(b, ask):
    b._price = ask - 0.25          # FakeBroker: ask = bid + 0.25


def _obs(log):
    return [m for t, m in log.events if t == "SYSTEM" and m.startswith("Re-entrada")]


def _close_all(b):
    b._pos.clear()


def test_breakout_level_matches_signal():
    for d in (1, -1):
        df = _df(d)
        sig, level = indicators.m15_breakout_level(df)
        check(sig == indicators.check_m15_breakout(df) == d, f"senal coherente ({d})")
        check(level == (LEVEL if d == 1 else 95.0), f"nivel roto = fractal ({level})")
    flat = pd.DataFrame({"high": np.full(40, 100.0), "low": np.full(40, 99.0),
                         "close": np.full(40, 99.5)})
    check(indicators.m15_breakout_level(flat) == (0, 0.0), "sin ruptura => (0, 0.0)")
    check(indicators.m15_breakout_level(flat.iloc[:1]) == (0, 0.0), "datos cortos => (0, 0.0)")


def test_first_entry_far_opens_without_log():
    e, b, log = _entry_eng()
    _set_ask(b, LEVEL + 4.0)       # 2 ATR del nivel
    check(e._open_entry(BUY, 0.01, "SMC Buy Entry", "OP1 BUY") is True, "primera entrada lejana abre")
    check(len(b.orders) == 1, "una orden")
    check(not _obs(log), "primera entrada: sin log de re-entrada")
    check(e._last_entry_signal == (1, LEVEL, 1), f"senal registrada (got {e._last_entry_signal})")


def test_near_reentry_logs_cercana():
    e, b, log = _entry_eng()
    e._open_entry(BUY, 0.01, "SMC Buy Entry", "OP1 BUY")
    _close_all(b)
    _set_ask(b, LEVEL + 1.0)       # 0.5 ATR
    check(e._open_entry(BUY, 0.01, "SMC Buy Entry", "OP1 BUY") is True, "re-entrada cercana abre")
    obs = _obs(log)
    check(len(obs) == 1 and "cercana" in obs[0] and "2.a entrada" in obs[0], f"log cercana N=2 (got {obs})")
    check(log.tickets[-1] == b._pos[-1].ticket, f"log con el ticket de la OP1 ({log.tickets})")


def test_far_reentry_observation_opens():
    e, b, log = _entry_eng()
    e._open_entry(BUY, 0.01, "SMC Buy Entry", "OP1 BUY")
    _close_all(b)
    _set_ask(b, LEVEL + 3.0)       # 1.5 ATR
    check(e._open_entry(BUY, 0.01, "SMC Buy Entry", "OP1 BUY") is True, "observacion: la lejana abre")
    check(len(b.orders) == 2, "dos ordenes")
    obs = _obs(log)
    check(len(obs) == 1 and "lejana (observacion)" in obs[0] and "Se abre igual" in obs[0]
          and "1.50 ATR" in obs[0], f"log de observacion (got {obs})")
    check(e._last_entry_signal == (1, LEVEL, 2), "ordinal 2")


def test_far_reentry_enforced_blocks_once():
    e, b, log = _entry_eng(cfg={"reentry_enforce": True})
    e._open_entry(BUY, 0.01, "SMC Buy Entry", "OP1 BUY")
    _close_all(b)
    _set_ask(b, LEVEL + 3.0)
    for _ in range(3):
        check(e._open_entry(BUY, 0.01, "SMC Buy Entry", "OP1 BUY") is False, "freno: no abre")
    check(len(b.orders) == 1, "solo la primera orden")
    frenos = [m for m in _obs(log) if "frenada" in m]
    check(len(frenos) == 1, f"un solo log por senal (got {frenos})")
    _set_ask(b, LEVEL + 1.0)
    check(e._open_entry(BUY, 0.01, "SMC Buy Entry", "OP1 BUY") is True, "al volver cerca, abre")


def test_new_breakout_is_first_entry():
    e, b, log = _entry_eng(cfg={"reentry_enforce": True})
    e._open_entry(BUY, 0.01, "SMC Buy Entry", "OP1 BUY")
    _close_all(b)
    e.df_m15 = _df(-1)             # ruptura bajista: otro lado y otro nivel
    b._price = 95.0 - 4.0          # 2 ATR por debajo
    check(e._open_entry(SELL, 0.01, "SMC Sell Entry", "OP1 SELL") is True, "ruptura nueva lejana abre")
    check(e._last_entry_signal == (-1, 95.0, 1), f"ordinal 1 (got {e._last_entry_signal})")
    check(not _obs(log), "sin log de re-entrada")


def test_switch_off():
    e, b, log = _entry_eng(cfg={"reentry_max_atr": 0, "reentry_enforce": True})
    e._open_entry(BUY, 0.01, "SMC Buy Entry", "OP1 BUY")
    _close_all(b)
    _set_ask(b, LEVEL + 6.0)
    check(e._open_entry(BUY, 0.01, "SMC Buy Entry", "OP1 BUY") is True, "reentry_max_atr=0: abre")
    check(not _obs(log), "reentry_max_atr=0: ni observa ni frena")


def test_broker_reject_keeps_signal():
    e, b, log = _entry_eng()
    orig = b.market_order

    def reject(*a, **k):
        class R:
            retcode = 10019   # sin dinero
            order = 0
        return R()
    b.market_order = reject
    check(e._open_entry(BUY, 0.01, "SMC Buy Entry", "OP1 BUY") is False, "rechazo: False")
    check(e._last_entry_signal is None, "rechazo: no registra la senal")
    b.market_order = orig
    check(e._open_entry(BUY, 0.01, "SMC Buy Entry", "OP1 BUY") is True, "luego abre")
    check(e._last_entry_signal == (1, LEVEL, 1), "y cuenta como primera entrada")


def test_tick_enforced_reentry():
    """Integracion: en ESTADO 0 on_tick pasa por _open_entry (freno activo => sin orden)."""
    _ind, orig = _no_signals()
    try:
        _ind.get_h4_structure = lambda df, use=True: 1
        _ind.check_m15_breakout = lambda df: 1
        e, b, log, _, _ = _tick_eng(equity=50000.0)
        e.cfg = {"equity_weight": 1.0, "reentry_enforce": True, "news_enforce": False,
                 "use_pullback": False, "use_m5_confirm": False}

        def buffers():
            e.atr0 = e.atr1 = 2.0
            e.ema0, e.rsi0 = b._price, 50.0
            e.m5_open1 = e.m5_close1 = b._price
            e.df_m15 = _df(1)
            e.df_h4 = e.df_m15
            return True
        e._compute_buffers = buffers
        _set_ask(b, LEVEL + 3.0)
        e._last_entry_signal = (1, LEVEL, 1)
        e.on_tick()
        check(not [o for o in b.orders if "Entry" in o["comment"]],
              f"re-entrada lejana frenada en el tick (got {b.orders})")
        e._last_entry_signal = None
        e.now += 60
        e.on_tick()
        check(len([o for o in b.orders if o["comment"] == "SMC Buy Entry"]) == 1,
              f"ruptura nueva: abre OP1 en el tick (got {b.orders})")
    finally:
        _ind.get_h4_structure, _ind.check_m15_breakout = orig


def test_hedge_floor_800():
    _ind, orig = _no_signals()
    try:
        for price, hedged in ((3995.0, False), (3991.8, True)):
            e, b, log, _, _ = _tick_eng(equity=50000.0)   # ATR 2.0 => 2*ATR = 400 pt < 800
            entry = _pos(b, 1, mt5.POSITION_TYPE_BUY, 0.10, 4000.0, "SMC Buy Entry", profit=-50.0)
            e.cycle.sync(b.positions())
            b._price = price
            entry.price_current = price
            e.on_tick()
            got = any(o["comment"] == "Hedge Lock" for o in b.orders)
            check(got is hedged, f"{(4000 - price) * 100:.0f} pt en rojo => hedge={hedged} (got {b.orders})")
    finally:
        _ind.get_h4_structure, _ind.check_m15_breakout = orig


def test_risk_hours_follow_ny_dst():
    check(survival.ny_hour_from_server(ts(2026, 8, 19, 16) + 1800) == 9, "agosto 16:30 servidor = 9 NY")
    check(survival.ny_hour_from_server(ts(2026, 12, 9, 16) + 1800) == 9, "diciembre 16:30 servidor = 9 NY")
    e, b, log = _eng(cfg={"equity_weight": 1.0})
    for when, risk, why in ((ts(2026, 8, 19, 16) + 1800, True, "verano 9:30 NY (13:30 UTC)"),
                            (ts(2026, 12, 9, 16) + 1800, True, "invierno 9:30 NY (14:30 UTC)"),
                            (ts(2026, 12, 9, 15) + 1800, False, "invierno 8:30 NY (13:30 UTC)"),
                            (ts(2026, 8, 19, 6) + 1800, False, "06:30 servidor"),
                            (ts(2026, 8, 19, 4) + 1800, True, "verano 01:30 UTC (Asia)")):
        e.now = when
        check(e._risk_hour() is risk, f"{why} => riesgo={risk}")
    e.cfg = {"equity_weight": 1.0, "risk_hours_utc": "1,13,14,15"}   # fila sin migrar
    e.now = ts(2026, 12, 9, 15) + 1800
    check(e._risk_hour() is True, "fila sin migrar: 13 UTC sigue siendo riesgo (ventana mas amplia)")


def main():
    for t in (test_breakout_level_matches_signal, test_first_entry_far_opens_without_log,
              test_near_reentry_logs_cercana, test_far_reentry_observation_opens,
              test_far_reentry_enforced_blocks_once, test_new_breakout_is_first_entry,
              test_switch_off, test_broker_reject_keeps_signal, test_tick_enforced_reentry,
              test_hedge_floor_800, test_risk_hours_follow_ny_dst):
        print(t.__name__)
        t()
    print("\ntest_reentrada: TODO OK")


if __name__ == "__main__":
    main()
