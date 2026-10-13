"""Regresion del nucleo de supervivencia (bot/survival.py). No necesita MT5.

Correr:  python -m tests.test_supervivencia
"""

import calendar
import MetaTrader5 as mt5

from bot import survival
from tests.test_m5_and_budget import FakeBroker, FakeLogger, FakePos

BUY, SELL = mt5.ORDER_TYPE_BUY, mt5.ORDER_TYPE_SELL
M15, M5 = 100200, 100300


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print(f"  OK  {msg}")


class SurvBroker(FakeBroker):
    def __init__(self, equity=7000.0, magic=M15):
        super().__init__(magic=magic, balance=equity)
        self._equity = equity
        self._mpl = 0.0   # margen por lote

    def positions(self): return [p for p in self._pos if p.magic == self.magic]
    def positions_all(self): return list(self._pos)
    def account_equity(self): return self._equity
    def account_margin(self): return self._margin
    def order_margin(self, otype, lots): return lots * self._mpl if lots > 0 else 0.0
    def stop_out_levels(self): return (100.0, 50.0)
    def contract_size(self): return 100.0


def add(b, ptype, vol, magic=M15):
    b._pos.append(FakePos(len(b._pos) + 1, ptype, vol, 4000.0, 0, "x", magic))


def guard(b, magic=M15, weight=1.0):
    log = FakeLogger()
    g = survival.SurvivalGuard(b, lambda: {"equity_weight": weight}, log, magic)
    return g, log


def ts(y, mo, d, h):
    return calendar.timegm((y, mo, d, h, 0, 0))


def test_survival_math():
    check(survival.survival_usd(5000, 0, 50, 0.0, 100) == float("inf"), "neto 0 => S infinito")
    check(abs(survival.survival_usd(6000, 2000, 50, 0.5, 100) - 100.0) < 1e-9, "(6000-1000)/(0.5*100)=100")
    check(survival.survival_usd(500, 2000, 50, 0.1, 100) == 0.0, "equity bajo el stop-out => 0")
    check(survival.parse_hours("1,13, 14,15") == {1, 13, 14, 15}, "parse_hours")
    check(survival.parse_hours("") == set(), "parse_hours vacio")


def fit_with_net(own_net_buy, req=0.20):
    b = SurvBroker()
    if own_net_buy > 0:
        add(b, BUY, own_net_buy)
    elif own_net_buy < 0:
        add(b, SELL, -own_net_buy)
    g, log = guard(b)
    return g, log, g.fit(BUY, req, "Recovery")


def test_fit_dynamic():
    check(abs(survival.SurvivalGuard(SurvBroker(), lambda: {}, FakeLogger(), M15).n_max() - 0.20) < 1e-9, "n_max=0.20")
    _, _, v = fit_with_net(0.05)
    check(abs(v - 0.15) < 1e-9, f"neto BUY 0.05 => 0.15 (got {v})")
    _, _, v = fit_with_net(0.01)
    check(abs(v - 0.19) < 1e-9, f"neto 0.01 => 0.19 (got {v})")
    _, _, v = fit_with_net(-0.15)
    check(abs(v - 0.20) < 1e-9, f"neto SELL 0.15, BUY reduce => 0.20 (got {v})")
    _, _, v = fit_with_net(0.196)
    check(v == 0.0, f"neto BUY 0.196 => 0.0 (got {v})")
    g, log, _ = fit_with_net(0.05)
    g.fit(BUY, 0.20, "Recovery")
    n = sum(1 for t, m in log.events if t == "BUDGET" and "reducida 0.20 → 0.15" in m)
    check(n == 1, f"log reducida una sola vez (got {n})")
    g, log, _ = fit_with_net(0.196)
    g.fit(BUY, 0.20, "Recovery")
    n = sum(1 for t, m in log.events if t == "BUDGET" and "bloqueada" in m)
    check(n == 1, f"log bloqueada una sola vez (got {n})")


def test_fit_share_between_bots():
    b = SurvBroker()
    g, _ = guard(b, M15, 0.8)
    v = g.fit(BUY, 0.50, "Entry")
    check(abs(v - 0.16) < 1e-9, f"M15 peso 0.8 => 0.16 (got {v})")
    g, _ = guard(b, M5, 0.2)
    v = g.fit(BUY, 0.50, "Scalp")
    check(abs(v - 0.04) < 1e-9, f"M5 peso 0.2 => 0.04 (got {v})")


def test_s_after_close():
    b = SurvBroker(equity=5000.0)
    add(b, BUY, 0.10)
    add(b, SELL, 0.04)
    g, _ = guard(b)
    s = g.s_after_close(b._pos[1])
    check(abs(s - 500.0) < 1e-9, f"s_after_close(SELL 0.04) == 500 (got {s})")
    check(abs(g.s_now() - 5000 / (0.06 * 100)) < 1e-6, "s_now con neto 0.06")


def test_utc_hour():
    check(survival.utc_hour_from_server(ts(2026, 8, 19, 16)) == 13, "verano 16:00 => 13")
    check(survival.utc_hour_from_server(ts(2026, 1, 15, 15)) == 13, "invierno 15:00 => 13")
    check(survival.utc_hour_from_server(ts(2026, 3, 9, 4)) == 1, "dia tras cambio EE.UU. => 1")
    check(survival.utc_hour_from_server(ts(2026, 3, 7, 4)) == 2, "dia antes del cambio => 2")
    check(survival.utc_hour_from_server(ts(2026, 11, 2, 4)) == 2, "dia tras fin DST (1 nov) => 2")


def _eng(equity=7000.0, weight=1.0, cfg=None):
    """SentinelEngine con ledger temporal y cfg controlada."""
    import os, tempfile
    from bot import ledger
    from bot.strategy import SentinelEngine
    b = SurvBroker(equity=equity, magic=M15)
    b._mpl = 1e-9   # margen casi nulo pero > 0 (el gobierno exige req > 0)
    log = FakeLogger()
    e = SentinelEngine(b, log)
    e.cycle = ledger.CycleLedger(os.path.join(tempfile.mkdtemp(), "l.json"), log)
    e.cfg = {"equity_weight": weight} if cfg is None else cfg
    return e, b, log


def test_open_additive_resizes():
    from bot import ledger
    e, b, log = _eng()
    add(b, BUY, 0.05)
    ok = e._open_additive(BUY, 0.20, "Recovery Buy (V-Shape)", ledger.ROLE_RECOVERY, "Recovery")
    check(ok and len(b.orders) == 1 and abs(b.orders[0]["lots"] - 0.15) < 1e-9,
          f"recovery 0.20 con neto 0.05 => orden de 0.15 (got {b.orders})")
    e, b, log = _eng()
    add(b, BUY, 0.196)
    ok = e._open_additive(BUY, 0.20, "Recovery Buy (V-Shape)", ledger.ROLE_RECOVERY, "Recovery")
    check(not ok and not b.orders, "neto 0.196 => no envia nada")
    check(any(t == "BUDGET" and "bloqueada" in m for t, m in log.events), "loguea BUDGET bloqueada")


def test_entry_sets_ref_lot_and_rescue_counter():
    from bot import ledger
    e, b, log = _eng()
    ok = e._open_additive(BUY, 0.09, "SMC Buy Entry", ledger.ROLE_ENTRY, "OP1 BUY")
    check(ok and e.cycle.get_meta("ref_lot") == 0.09, "ENTRY 0.09 => ref_lot 0.09")
    e._open_additive(BUY, 0.01, "Sentinel Op 4 (L1)", ledger.ROLE_RESCUE, "Rescue")
    e._open_additive(BUY, 0.01, "Sentinel Op 4 (L1)", ledger.ROLE_RESCUE, "Rescue")
    check(e.cycle.get_meta("rescue_opened") == 2, "dos RESCUE => rescue_opened == 2")


def test_no_fixed_lot_caps():
    e, b, log = _eng(equity=500000.0, cfg={})
    check(e._calculate_lots(False) > 1.0, "M15 sin tope fijo de entry (>1.0)")
    check(e._calculate_lots(True) > 2.0, "M15 sin tope fijo de recovery")
    from bot.strategy_m5 import M5Engine
    b5 = SurvBroker(equity=500000.0, magic=M5)
    m5 = M5Engine(b5, FakeLogger())
    m5.cfg = {}
    check(m5._calculate_lots() > 0.50, "M5 sin tope m5_max_lot_cap (>0.50)")


def test_min_lot_account_blocks_once():
    from bot import ledger
    e, b, log = _eng(equity=1000.0)
    add(b, BUY, 0.02)
    for _ in range(3):
        e._open_additive(BUY, 0.05, "Recovery Buy (V-Shape)", ledger.ROLE_RECOVERY, "Recovery")
    n = sum(1 for t, _ in log.events if t == "BUDGET")
    check(not b.orders and n == 1, f"cuenta chica: 0 ordenes y 1 evento BUDGET (got {len(b.orders)}, {n})")


def test_rescue_cooldown_only_when_sent():
    from bot import ledger
    for blocked in (True, False):
        e, b, log = _eng()
        e.now = 1_700_050_000
        e.atr0, e.rsi0, e.struct_h4 = 2.0, 75.0, 0
        for i in range(3):
            p = FakePos(2000 + i, mt5.POSITION_TYPE_SELL, 0.20 if blocked else 0.01,
                        3990.0, 1_700_000_000 + i, "SMC Sell Entry", M15)
            p.profit = -300.0
            b._pos.append(p)
        legs = list(b._pos)
        if not blocked:
            class Rej: retcode = 10019; order = 0
            b.market_order = lambda *a, **k: Rej()
        e.last_rescue_time = 0
        e._check_rescue(legs)
        if blocked:
            check(not b.orders and e.last_rescue_time == 0, "rescate bloqueado por supervivencia NO inicia cooldown")
        else:
            check(e.last_rescue_time == e.now, "rescate enviado pero rechazado SI inicia cooldown")


def test_parity_across_accounts():
    movs = []
    for eq, ref in ((5000.0, 0.09), (10000.0, 0.19), (20000.0, 0.38)):
        e, b, log = _eng(equity=eq)
        e.cycle.set_meta("ref_lot", ref)
        for k, lvl in ((10, 1), (17, 2), (45, 3)):
            got = e._rescue_level(k * ref * 100)
            check(got == lvl, f"eq {eq}: abs_dd k={k} => L{lvl} (got {got})")
        movs.append(e._move_money(0.83) / ref)
    check(abs(movs[0] - movs[1]) < 1e-9 and abs(movs[1] - movs[2]) < 1e-9,
          f"_move_money/ref_lot igual en las 3 cuentas ({movs})")
    e, b, log = _eng(equity=5000.0)
    e.cycle.set_meta("ref_lot", 0.09)
    check(abs(e._move_money(3.33) - 29.97) < 1e-9, "piso Unwind con ref_lot 0.09 = 29.97")


def main():
    test_survival_math()
    test_fit_dynamic()
    test_fit_share_between_bots()
    test_s_after_close()
    test_utc_hour()
    test_open_additive_resizes()
    test_entry_sets_ref_lot_and_rescue_counter()
    test_no_fixed_lot_caps()
    test_min_lot_account_blocks_once()
    test_rescue_cooldown_only_when_sent()
    test_parity_across_accounts()
    print("\ntest_supervivencia: TODO OK")


if __name__ == "__main__":
    main()
