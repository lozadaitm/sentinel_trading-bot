"""Regresion del nucleo de supervivencia (bot/survival.py). No necesita MT5.

Correr:  python -m tests.test_supervivencia
"""

import calendar
import MetaTrader5 as mt5

from bot import config, survival
from tests.test_m5_and_budget import FakeBroker, FakeLogger, FakePos

config.ALERT_EMAIL_TO = ""   # los tests nunca deben mandar correos reales (AlertManager queda no-op)

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


def test_rescue_churn_capped():
    """19-ago 12:57-13:11 UTC: Op4 abierta, cobrada y reabierta en bucle. El tope
    cuenta las abiertas en el CICLO (meta rescue_opened), no las vivas."""
    e, b, log = _eng(cfg={"equity_weight": 1.0, "rescue_cooldown": 0, "news_enforce": False})
    e.now = ts(2026, 8, 19, 6) + 1800   # 03 UTC: fuera de horas de riesgo
    e.atr0, e.rsi0, e.struct_h4 = 2.0, 75.0, 0
    b._price = 4000.0
    e.cycle.set_meta("ref_lot", 0.01)
    legs = []
    for i in range(3):
        p = FakePos(2000 + i, mt5.POSITION_TYPE_SELL, 0.01, 3990.0, e.now - 5000 + i,
                    "SMC Sell Entry", M15)
        p.profit = -300.0
        b._pos.append(p)
        legs.append(p)
    for _ in range(5):
        e._check_rescue(legs)
        for q in list(b._pos):          # "cobrar" la Op4 recien abierta
            if q not in legs:
                b._pos.remove(q)
    check(len(b.orders) == 3, f"tras 3 aperturas la cuarta no se envia (ordenes: {len(b.orders)})")
    check(e.cycle.get_meta("rescue_opened") == 3, "rescue_opened == 3")


def _unwind_setup(buy_vol, buy_pnl, sell_vol, sell_pnl):
    e, b, log = _eng(equity=5000.0)
    e.now = ts(2026, 8, 19, 6)
    e.atr0 = 2.0
    e.cycle.set_meta("ref_lot", 0.20)
    e.cycle_realized = 1000.0           # abre el freeze
    pb = FakePos(1, mt5.POSITION_TYPE_BUY, buy_vol, 4000.0, e.now - 900, "x", M15)
    ps = FakePos(2, mt5.POSITION_TYPE_SELL, sell_vol, 4000.0, e.now - 800, "x", M15)
    pb.profit, ps.profit = buy_pnl, sell_pnl
    b._pos += [pb, ps]
    return e, b, pb, ps


def test_unwind_respects_survival():
    e, b, pb, ps = _unwind_setup(0.30, -20.0, 0.20, 100.0)
    e._profit_banking()
    check(ps in b._pos, "SELL verde 0.20 NO se cobra: dejaria neto 0.30 (S=166 < 350)")
    # variante: la verde es la BUY y cerrarla REDUCE el neto (0.20 -> 0.10)
    e, b, pb, ps = _unwind_setup(0.30, 100.0, 0.10, -20.0)
    e._profit_banking()
    check(pb not in b._pos, "BUY verde que reduce el neto SI se cobra")


def test_risk_hours_block_recovery_and_rescue():
    e, b, log = _eng(cfg={"equity_weight": 1.0, "rescue_cooldown": 0, "news_enforce": False})
    e.atr0, e.rsi0, e.struct_h4 = 2.0, 75.0, 0
    e.cycle.set_meta("ref_lot", 0.01)
    legs = []
    for i in range(3):
        p = FakePos(2000 + i, mt5.POSITION_TYPE_SELL, 0.01, 3990.0, 1_700_000_000 + i,
                    "SMC Sell Entry", M15)
        p.profit = -300.0
        b._pos.append(p)
        legs.append(p)
    e.now = ts(2026, 8, 19, 16) + 1800   # 16:30 servidor = 13:30 UTC
    check(e._risk_hour() is True, "16:30 servidor (13 UTC) es hora de riesgo")
    e._check_rescue(legs)
    check(not b.orders, "en hora de riesgo _check_rescue no envia nada")
    e.now = ts(2026, 8, 19, 6) + 1800    # 03 UTC
    check(e._risk_hour() is False, "06:30 servidor (03 UTC) no es hora de riesgo")
    e._check_rescue(legs)
    check(len(b.orders) == 1, "fuera de hora de riesgo el rescate si abre")


def test_alert_dedupe():
    from bot import alerts
    sent, t = [], [1000.0]
    m = alerts.AlertManager(FakeLogger(), "a@b.c", "123/m15",
                            sender=lambda to, s, b, lg=None: sent.append((to, s)), clock=lambda: t[0])
    check(m.notify("x", "AVISO", "hola", "cuerpo") is True, "primer envio True")
    t[0] += 3600
    check(m.notify("x", "AVISO", "hola", "cuerpo") is False and len(sent) == 1, "dentro de 1 h => dedupe")
    t[0] += 6 * 3600 + 1
    m.notify("x", "AVISO", "hola", "cuerpo")
    check(len(sent) == 2, "pasado el cooldown => 2 envios")
    check(sent[0][1] == "[Sentinel AVISO] 123/m15: hola", f"asunto (got {sent[0][1]})")
    log = FakeLogger()
    m2 = alerts.AlertManager(log, "", "x", sender=lambda *a, **k: sent.append(1))
    m2.notify("k", "AVISO", "s", "b"); m2.notify("k", "AVISO", "s", "b")
    check(len(sent) == 2 and sum(1 for t_, _ in log.events if t_ == "SYSTEM") == 1,
          "sin destinatario: no envia y un solo log SYSTEM")


def test_dead_account_gate():
    from bot import alerts, ledger
    e, b, log = _eng(equity=0.0)
    sent = []
    e.alerts = alerts.AlertManager(log, "a@b.c", "x", sender=lambda to, s, bd, lg=None: sent.append(s))
    for i in range(3):
        e.now = 1_700_000_000 + i
        alerts.update_dead(e)
    ok = e._open_additive(BUY, 0.10, "Recovery Buy (V-Shape)", ledger.ROLE_RECOVERY, "Recovery")
    errs = [m for t_, m in log.events if t_ == "ERROR"]
    check(e.dead and not ok and not b.orders, "equity 0 => dead y no abre")
    check(len(errs) == 1 and len(sent) == 1, f"un solo ERROR y un correo en 3 ticks (got {len(errs)}/{len(sent)})")
    b._equity = 5000.0
    e.now += 5
    alerts.update_dead(e)
    ok = e._open_additive(BUY, 0.10, "Recovery Buy (V-Shape)", ledger.ROLE_RECOVERY, "Recovery")
    check(not e.dead and ok and len(b.orders) == 1, "equity 5000 => se libera y abre")


def test_stop_out_alert():
    from bot import alerts
    e, b, log = _eng()
    sent = []
    e.alerts = alerts.AlertManager(log, "a@b.c", "x", sender=lambda to, s, bd, lg=None: sent.append(s))

    class D:
        ticket, magic, entry, profit = 77, b.magic, 1, -50.0
        comment = "[so 18.85%/13.19/69.98]"
    class D2(D):
        ticket = 90
    deals = [D()]
    calls = []
    b.history_deals = lambda a, c: (calls.append((a, c)), list(deals))[1]
    e.now = 1_700_000_000
    e._check_stop_out()
    import datetime as _dt
    f, t = calls[0]
    check(t - f == _dt.timedelta(days=1) and f <= e._server_dt() <= t, "ventana stop-out: 1 dia y contiene 'ahora' servidor")
    check(len(sent) == 0 and e._last_so_ticket == 77, "primer chequeo solo siembra el ancla (0 alertas)")
    deals.append(D2())
    for i in range(1, 4):
        e.now = 1_700_000_000 + i * 61
        e._check_stop_out()
    check(len(sent) == 1 and "stop-out" in sent[0], f"deal nuevo => exactamente 1 alerta (got {len(sent)})")
    check(e._last_so_ticket == 90, "ancla avanzo a 90")


def test_idle_alert():
    from bot import alerts
    e, b, log = _eng()
    sent = []
    e.alerts = alerts.AlertManager(log, "a@b.c", "x", sender=lambda to, s, bd, lg=None: sent.append(s))
    deals = []
    calls = []
    b.history_deals = lambda a, c: (calls.append((a, c)), list(deals))[1]
    e.now = 1_700_000_000
    e.close_only = True
    e._check_idle()
    check(len(sent) == 0, "close_only => sin alerta de inactividad")
    e.close_only = False
    e.now += 3601
    deals.append(type("D", (), {"ticket": 1, "magic": b.magic, "comment": "", "profit": 0.0})())
    e._check_idle()
    check(len(sent) == 0, "deal propio reciente => sin alerta")
    e.now += 3601
    deals.clear()
    e._check_idle()
    import datetime as _dt
    f, t = calls[-1]
    check(t - f == _dt.timedelta(hours=72) and f <= e._server_dt() <= t, "ventana idle: 72 h y contiene 'ahora' servidor")
    check(len(sent) == 1 and "inactivo" in sent[0], f"sin posiciones ni deals => 1 alerta (got {sent})")


# ----------------------------------------------------------------------
# Candado de cesta (spec §5.3)
# ----------------------------------------------------------------------
def _pos(b, ticket, ptype, vol, price_open, comment, profit=0.0, sl=0.0, t=1_700_000_000):
    p = FakePos(ticket, ptype, vol, price_open, t, comment, M15, sl)
    p.profit = profit
    b._pos.append(p)
    return p


def _lock_eng(equity=5000.0, cfg=None):
    e, b, log = _eng(equity=equity, cfg=cfg)
    b._next = 500          # tickets de ordenes nuevas lejos de los de _pos
    e.now = ts(2026, 8, 19, 6)   # miercoles 06:00 servidor
    return e, b, log


def _rec_alerts(e, log):
    from bot import alerts
    sent = []
    e.alerts = alerts.AlertManager(log, "a@b.c", "x",
                                   sender=lambda to, s, bd, lg=None: sent.append(s))
    return sent


def test_lock_triggers():
    from bot import ledger, strategy
    e, b, log = _lock_eng()
    sent = _rec_alerts(e, log)
    _pos(b, 1, mt5.POSITION_TYPE_BUY, 0.34, 4000.0, "SMC Buy Entry")
    e.cycle.sync(b.positions())
    check(e.surv.s_now() < 150, f"S={e.surv.s_now():.0f} < 150")
    e._maybe_lock()
    check(len(b.orders) == 1 and b.orders[0]["type"] == SELL
          and abs(b.orders[0]["lots"] - 0.34) < 1e-9 and b.orders[0]["comment"] == "Basket Lock",
          f"orden SELL 0.34 'Basket Lock' (got {b.orders})")
    lock = [p for p in b._pos if p.comment == "Basket Lock"][0]
    check(e.cycle.role_of(lock.ticket) == ledger.ROLE_LOCK, "rol LOCK en el ledger")
    check(e._lock_state(b.positions()) == strategy.LOCK_FROZEN, "estado CONGELADO")
    check(abs(e.cycle.get_meta("lock_initial_volume") - 0.34) < 1e-9, "lock_initial_volume 0.34")
    check(e.cycle.get_meta("lock_since") == e.now, "lock_since = now")
    check(any(t == "PROTECCION" and "Candado puesto: 0.34 lotes SELL. S=147 $" in m
              for t, m in log.events), "log PROTECCION del candado")
    check(len(sent) == 1, f"una alerta 'candado' (got {sent})")
    e._maybe_lock()
    check(len(b.orders) == 1, "con el neto en 0 no se pone un segundo candado")

    e, b, log = _lock_eng()
    _pos(b, 1, mt5.POSITION_TYPE_BUY, 0.30, 4000.0, "SMC Buy Entry")
    e.cycle.sync(b.positions())
    e._maybe_lock()
    check(not b.orders, "BUY 0.30 (S=166) => sin candado")
    check(e._lock_state(b.positions()) == strategy.LOCK_FREE, "estado LIBRE sin patas LOCK")


def _tick_eng(equity=5000.0):
    import pandas as _pd
    from bot import indicators as _ind
    from bot.strategy import SentinelEngine
    e, b, log = _lock_eng(equity=equity)

    def fake_buffers():
        e.atr0 = e.atr1 = 2.0
        e.ema0, e.rsi0 = b._price, 50.0
        e.m5_open1 = e.m5_close1 = b._price
        e.df_m15 = _pd.DataFrame({"high": [b._price + 0.5], "low": [b._price - 0.5]})
        e.df_h4 = e.df_m15
        return True
    e._compute_buffers = fake_buffers
    _ind_orig = (_ind.get_h4_structure, _ind.check_m15_breakout)
    return e, b, log, _ind, _ind_orig


def test_frozen_blocks_subsystems():
    from bot import ledger, strategy
    e, b, log, _ind, orig = _tick_eng()
    _ind.get_h4_structure = lambda df, use=True: 0
    _ind.check_m15_breakout = lambda df: 0
    try:
        b._price = 3990.0
        entry = _pos(b, 1, mt5.POSITION_TYPE_BUY, 0.20, 4000.0, "SMC Buy Entry", profit=-200.0)
        entry.price_current = 3990.0   # ENTRY desnuda 1000 pts en rojo (> hedge_dist)
        green = _pos(b, 2, mt5.POSITION_TYPE_BUY, 0.14, 3980.0, "Recovery Buy (V-Shape)", profit=140.0)
        green.price_current = 3990.0
        e.cycle.set_meta("ref_lot", 0.01)
        e.cycle_realized = 1000.0
        e.on_tick()
        check([o["comment"] for o in b.orders] == ["Basket Lock"],
              f"on_tick: solo el candado, sin Hedge Lock sobre la ENTRY (got {b.orders})")
        check(e.lock_state == strategy.LOCK_FROZEN, "estado del tick CONGELADO")
        e.on_tick()
        check(len(b.orders) == 1, "segundo tick congelado: nada nuevo")
        e._profit_banking()
        check(green in b._pos and entry in b._pos, "CONGELADO: _profit_banking no cierra nada")
        ok = e._open_additive(BUY, 0.01, "Recovery Buy (V-Shape)", ledger.ROLE_RECOVERY, "Recovery")
        check(not ok and len(b.orders) == 1, "CONGELADO: _open_additive no envia")
    finally:
        _ind.get_h4_structure, _ind.check_m15_breakout = orig


def test_loose_excludes_lock_legs():
    """AFLOJADO: las patas LOCK son intocables para Unwind y Healer."""
    from bot import ledger, strategy
    e, b, log = _lock_eng(equity=50000.0)
    e.atr0 = 2.0
    e.cycle.set_meta("ref_lot", 0.01)
    _pos(b, 1, mt5.POSITION_TYPE_BUY, 0.30, 4000.0, "SMC Buy Entry", profit=-50.0)
    lock = _pos(b, 2, mt5.POSITION_TYPE_SELL, 0.10, 4010.0, "Basket Lock", profit=100.0)
    lock.price_current = 4000.0
    e.cycle.sync(b.positions())
    check(e._lock_state(b.positions()) == strategy.LOCK_LOOSE, "LOCK + neto 0.20 => AFLOJADO")
    e.lock_state = strategy.LOCK_LOOSE
    e.cycle_realized = 1000.0
    e._profit_banking()
    check(lock in b._pos, "AFLOJADO: el Unwind no cobra la pata LOCK verde")
    lock.profit = -300.0
    e.cycle_realized = 5000.0   # protect_cover False: sin el candado, el LOCK seria el peor
    e._apply_healing(10000.0)
    check(not any(pp["ticket"] == lock.ticket for pp in b.partials),
          f"AFLOJADO: el Healer no amputa la pata LOCK (got {b.partials})")


def test_lock_clears_trailing_sl():
    e, b, log = _lock_eng()
    _pos(b, 1, mt5.POSITION_TYPE_BUY, 0.20, 4000.0, "SMC Buy Entry")
    rec = _pos(b, 2, mt5.POSITION_TYPE_BUY, 0.14, 4400.0, "Recovery Buy (V-Shape)", sl=4410.0)
    e.cycle.sync(b.positions())
    e._maybe_lock()
    check(len(b.orders) == 1, "candado puesto")
    check(rec.sl == 0, f"tras el candado la RECOVERY queda sin SL (got {rec.sl})")


def test_lock_failure_dedup():
    e, b, log = _lock_eng()
    sent = _rec_alerts(e, log)
    b.order_check = lambda otype, lots: (False, 10019)
    _pos(b, 1, mt5.POSITION_TYPE_BUY, 0.34, 4000.0, "SMC Buy Entry")
    e.cycle.sync(b.positions())
    for i in range(5):
        e.now += 100
        e._maybe_lock()
    errs = [m for t, m in log.events if t == "ERROR"]
    check(not b.orders, "ninguna orden enviada")
    check(len(errs) == 1 and "Candado FALLIDO (10019). S=147 $." in errs[0],
          f"un solo ERROR en 5 ticks (got {errs})")
    check(len(sent) == 1, f"una sola alerta 'candado_fallido' (got {sent})")
    e.now += 600
    e._maybe_lock()
    check(sum(1 for t, _ in log.events if t == "ERROR") == 2, "pasados 600 s se vuelve a loguear")


def test_lock_survives_restart():
    from bot import ledger, strategy
    from bot.strategy import SentinelEngine
    e, b, log = _lock_eng()
    _pos(b, 1, mt5.POSITION_TYPE_BUY, 0.34, 4000.0, "SMC Buy Entry")
    e.cycle.sync(b.positions())
    e._maybe_lock()
    since = e.cycle.get_meta("lock_since")
    path = e.cycle.path
    e2 = SentinelEngine(b, FakeLogger())
    e2.cycle = ledger.CycleLedger(path, FakeLogger())
    e2.cfg = {"equity_weight": 1.0}
    e2.now = e.now + 3600
    e2.cycle.sync(b.positions())
    check(e2._lock_state(b.positions()) == strategy.LOCK_FROZEN, "tras reinicio: CONGELADO")
    e2._maybe_lock()
    check(len(b.orders) == 1, "tras reinicio no se pone un segundo candado")
    check(e2.cycle.get_meta("lock_since") == since, "lock_since se conserva")


def _no_signals():
    from bot import indicators as _ind
    orig = (_ind.get_h4_structure, _ind.check_m15_breakout)
    _ind.get_h4_structure = lambda df, use=True: 0
    _ind.check_m15_breakout = lambda df: 0
    return _ind, orig


def test_lock_sl_cleared_each_tick():
    """Con candado vivo, cualquier SL propio se limpia en cada tick (p.ej. tras un reinicio)."""
    from bot import strategy
    _ind, orig = _no_signals()
    try:
        e, b, log, _, _ = _tick_eng(equity=50000.0)
        entry = _pos(b, 1, mt5.POSITION_TYPE_BUY, 0.20, 4000.0, "SMC Buy Entry", sl=3900.0)
        _pos(b, 2, mt5.POSITION_TYPE_SELL, 0.20, 4000.0, "Basket Lock")
        e.on_tick()
        check(e.lock_state == strategy.LOCK_FROZEN, "ENTRY+LOCK => CONGELADO")
        check(entry.sl == 0 and not b.orders, f"on_tick congelado limpia el SL (got {entry.sl})")
        # el broker rechaza la modificacion: ERROR como mucho cada 600 s
        entry.sl = 3900.0
        class Rej: retcode = 10006
        b.modify_sl = lambda p, sl: Rej()
        for _ in range(5):
            e.now += 60
            e.on_tick()
        errs = [m for t, m in log.events if t == "ERROR" and "no se pudo quitar el SL" in m]
        check(len(errs) == 1, f"SL no limpiado: 1 ERROR en 5 ticks (got {len(errs)})")
    finally:
        _ind.get_h4_structure, _ind.check_m15_breakout = orig


def test_loose_no_hedges():
    """R10: en AFLOJADO ni el hedge monitor ni el watchdog abren Hedge Lock."""
    from bot import strategy
    _ind, orig = _no_signals()
    try:
        e, b, log, _, _ = _tick_eng(equity=50000.0)
        b._price = 3990.0
        entry = _pos(b, 1, mt5.POSITION_TYPE_BUY, 0.30, 4000.0, "SMC Buy Entry", profit=-300.0)
        entry.price_current = 3990.0
        orphan = _pos(b, 2, mt5.POSITION_TYPE_BUY, 0.01, 4000.0, "manual", profit=-10.0)
        orphan.price_current = 3990.0
        _pos(b, 3, mt5.POSITION_TYPE_SELL, 0.10, 4000.0, "Basket Lock")
        e.on_tick()
        check(e.lock_state == strategy.LOCK_LOOSE, "neto 0.21 con LOCK => AFLOJADO")
        check(not any(o["comment"] == "Hedge Lock" for o in b.orders),
              f"AFLOJADO: sin Hedge Lock sobre ENTRY ni huerfano desnudos (got {b.orders})")
    finally:
        _ind.get_h4_structure, _ind.check_m15_breakout = orig


def test_healer_gate_excludes_lock():
    """R11: la profundidad del Healer no cuenta las patas LOCK."""
    from bot import ledger
    e, b, log = _lock_eng(equity=50000.0)
    entry = _pos(b, 1, mt5.POSITION_TYPE_BUY, 0.30, 4000.0, "SMC Buy Entry", profit=-300.0)
    _pos(b, 2, mt5.POSITION_TYPE_SELL, 0.30, 4000.0, "Hedge Lock", profit=290.0)
    _pos(b, 3, mt5.POSITION_TYPE_SELL, 0.10, 4000.0, "Basket Lock")
    e.cycle.sync(b.positions())
    check(e.cycle.role_of(2) == ledger.ROLE_HEDGE and e.cycle.role_of(3) == ledger.ROLE_LOCK,
          "ENTRY + HEDGE + LOCK en el ledger")
    class D: ticket, magic, entry, profit = 900, M15, mt5.DEAL_ENTRY_OUT, 1000.0
    b.history_deals = lambda a, c: [D()]
    e._healer_needs_rebaseline = False
    e.cycle_realized = 5000.0      # protect_cover False: el par no estaria congelado
    e._check_healing()
    check(not b.partials, f"2 legs de cesta + LOCK: el Healer no amputa (got {b.partials})")


def test_hedge_fail_throttled():
    """R12: 'Hedge Lock FALLIDO' como mucho una vez cada 600 s por ticket."""
    e, b, log = _lock_eng()
    class Rej: retcode = 10019; order = 0
    b.market_order = lambda *a, **k: Rej()
    entry = _pos(b, 1, mt5.POSITION_TYPE_BUY, 0.10, 4000.0, "SMC Buy Entry", sl=3950.0)
    for _ in range(5):
        e.now += 60
        check(e._open_hedge(entry) is False, "hedge rechazado => False (se reintenta)")
    n = sum(1 for t, m in log.events if t == "ERROR" and "Hedge Lock FALLIDO" in m)
    check(n == 1 and entry.sl == 3950.0, f"5 rechazos en 600 s => 1 ERROR y SL intacto (got {n})")
    e.now += 600
    e._open_hedge(entry)
    n = sum(1 for t, m in log.events if t == "ERROR" and "Hedge Lock FALLIDO" in m)
    check(n == 2, "pasados 600 s se vuelve a loguear")


def test_lock_vmax_zero():
    e, b, log = _lock_eng()
    b.volume_max = lambda: 0.0
    _pos(b, 1, mt5.POSITION_TYPE_BUY, 0.34, 4000.0, "SMC Buy Entry")
    e.cycle.sync(b.positions())
    e._maybe_lock()
    check(len(b.orders) == 1 and abs(b.orders[0]["lots"] - 0.34) < 1e-9,
          f"volume_max 0 => una sola pata de 0.34 (got {b.orders})")


# ----------------------------------------------------------------------
# Aflojar el candado por rebote confirmado (spec §5.4)
# ----------------------------------------------------------------------
def _unlock_setup(price, equity=5000.0):
    """E=5000, LOCK SELL 0.34 a 4400 y ENTRY BUY 0.34 (cesta congelada)."""
    e, b, log = _lock_eng(equity=equity)
    _pos(b, 1, mt5.POSITION_TYPE_BUY, 0.34, 4400.0, "SMC Buy Entry")
    _pos(b, 2, mt5.POSITION_TYPE_SELL, 0.34, 4400.0, "Basket Lock")
    e.cycle.sync(b.positions())
    e.cycle.set_meta("lock_since", e.now - 3600)
    e.cycle.set_meta("lock_initial_volume", 0.34)
    b._price = price
    return e, b, log


def _lock_vol(e, b):
    return round(sum(p.volume for p in e.cycle.lock_legs(b.positions())), 8)


def test_no_unlock_on_continuation():
    """Anti-objetivo: la pata LOCK en verde (precio siguio cayendo) NO es motivo para aflojar."""
    from bot import strategy
    e, b, log = _unlock_setup(4340.0)
    e._maybe_unlock()
    check(not b.partials and _lock_vol(e, b) == 0.34,
          f"precio 4340 (LOCK gana 60): nada se cierra (got {b.partials})")
    check(e._lock_state(b.positions()) == strategy.LOCK_FROZEN, "sigue CONGELADO")


def test_unlock_on_rebound():
    from bot import strategy
    e, b, log = _unlock_setup(4451.0)
    sent = _rec_alerts(e, log)
    check(e._risk_hour() is False, "06:00 servidor (03 UTC) no es hora de riesgo")
    e._maybe_unlock()
    check(len(b.partials) == 1 and abs(b.partials[0]["lots"] - 0.14) < 1e-9,
          f"rebote +51 => se cierran 0.14 (got {b.partials})")
    check(abs(_lock_vol(e, b) - 0.20) < 1e-9, "quedan 0.20 de LOCK")
    check(e._lock_state(b.positions()) == strategy.LOCK_LOOSE, "estado AFLOJADO")
    check(e.cycle.get_meta("unlock_ref_price") == 4451.0, "unlock_ref_price = 4451")
    check(e.cycle.get_meta("last_unlock_ts") == e.now, "last_unlock_ts = now")
    check(any(t == "PROTECCION" and "Candado aflojado: cerrados 0.14 lotes (rebote +51 $). S=357 $" in m
              for t, m in log.events), f"log PROTECCION del aflojado (got {log.events})")
    check(len(sent) == 1, f"una alerta candado_aflojado (got {sent})")
    check(e.cycle.get_meta("lock_since") is not None, "con LOCK vivo lock_since se conserva")


def test_unlock_gates():
    for name in ("news", "risk_hour", "vcb", "spread"):
        e, b, log = _unlock_setup(4451.0)
        if name == "news":
            e.news_active = True
        elif name == "risk_hour":
            e.now = ts(2026, 8, 19, 16)   # 16:00 servidor = 13 UTC
        elif name == "vcb":
            e.vol_breaker = True
        else:
            e.spread_high = True
        e._maybe_unlock()
        check(not b.partials and _lock_vol(e, b) == 0.34,
              f"gate {name}: el mismo rebote no afloja (got {b.partials})")


def test_successive_unlock_needs_new_rebound():
    from bot import strategy
    e, b, log = _unlock_setup(4451.0)
    e._maybe_unlock()
    check(abs(_lock_vol(e, b) - 0.20) < 1e-9, "primer aflojado: quedan 0.20")
    b._equity = 10000.0   # el rebote subio el equity: S admite mas neto
    b._price = 4480.0
    e._maybe_unlock()
    check(len(b.partials) == 1, "4480: rebote +29 desde el aflojado anterior => nada")
    b._price = 4501.0
    e._maybe_unlock()
    check(len(b.partials) == 2 and abs(b.partials[1]["lots"] - 0.14) < 1e-9,
          f"4501: nuevo rebote +50 => se cierran otras 0.14 (got {b.partials})")
    check(abs(_lock_vol(e, b) - 0.06) < 1e-9, "quedan 0.06 de LOCK")
    check(e.cycle.get_meta("unlock_ref_price") == 4501.0, "referencia movida a 4501")
    # ultima pata: con equity holgado se cierra entera y el estado vuelve a LIBRE
    b._equity = 50000.0
    b._price = 4551.0
    e._maybe_unlock()
    check(not e.cycle.lock_legs(b.positions()), "sin patas LOCK")
    check(e._lock_state(b.positions()) == strategy.LOCK_FREE, "estado LIBRE")
    for k in ("unlock_ref_price", "lock_since", "lock_initial_volume"):
        check(e.cycle.get_meta(k) is None, f"{k} a None")
    check(e.cycle.get_meta("last_unlock_ts") == e.now, "last_unlock_ts se conserva")


def test_unlock_newest_first():
    """Varias patas LOCK: se cierra primero la mas nueva; la ultima necesaria en parcial."""
    e, b, log = _lock_eng(equity=7000.0)   # cabe 7000/35000 = 0.20
    _pos(b, 1, mt5.POSITION_TYPE_BUY, 0.30, 4400.0, "SMC Buy Entry")
    old = _pos(b, 2, mt5.POSITION_TYPE_SELL, 0.20, 4400.0, "Basket Lock", t=1_700_000_000)
    new = _pos(b, 3, mt5.POSITION_TYPE_SELL, 0.10, 4400.0, "Basket Lock", t=1_700_000_500)
    e.cycle.sync(b.positions())
    b._price = 4451.0
    e._maybe_unlock()
    check(new not in b._pos, "la pata mas nueva (0.10) se cierra entera")
    check(abs(old.volume - 0.10) < 1e-9 and b.partials[-1]["ticket"] == old.ticket,
          f"la vieja se cierra en parcial 0.10 (queda {old.volume})")


def test_unlock_wired_in_tick():
    from bot import strategy
    _ind, orig = _no_signals()
    try:
        e, b, log, _, _ = _tick_eng(equity=5000.0)
        _pos(b, 1, mt5.POSITION_TYPE_BUY, 0.34, 4400.0, "SMC Buy Entry")
        _pos(b, 2, mt5.POSITION_TYPE_SELL, 0.34, 4400.0, "Basket Lock")
        b._price = 4451.0
        e.on_tick()
        check(abs(_lock_vol(e, b) - 0.20) < 1e-9, f"on_tick afloja 0.14 (LOCK {_lock_vol(e, b)})")
        check(e.lock_state == strategy.LOCK_LOOSE, "el tick ve el estado AFLOJADO")
    finally:
        _ind.get_h4_structure, _ind.check_m15_breakout = orig


def test_unlock_buy_lock_mirror():
    """Neto original CORTO (LOCK BUY): rebote = ref - ask."""
    from bot import strategy
    e, b, log = _lock_eng(equity=5000.0, cfg={"equity_weight": 1.0})
    _pos(b, 1, mt5.POSITION_TYPE_SELL, 0.34, 4400.0, "SMC Sell Entry")
    _pos(b, 2, mt5.POSITION_TYPE_BUY, 0.34, 4400.0, "Basket Lock")
    e.cycle.sync(b.positions())
    b._price = 4460.0 - 0.25   # ask 4460: el precio siguio subiendo (continuacion)
    e._maybe_unlock()
    check(not b.partials and _lock_vol(e, b) == 0.34, f"ask 4460 (LOCK BUY gana): nada (got {b.partials})")
    b._price = 4349.0 - 0.25   # ask 4349: rebote +51 a favor del corto
    e._maybe_unlock()
    check(len(b.partials) == 1 and abs(b.partials[0]["lots"] - 0.14) < 1e-9,
          f"ask 4349 => se cierran 0.14 (got {b.partials})")
    check(e.cycle.get_meta("unlock_ref_price") == 4349.0, "unlock_ref_price = ask 4349")
    check(e._lock_state(b.positions()) == strategy.LOCK_LOOSE, "estado AFLOJADO")


def test_relock_resets_unlock_ref():
    """R13: tras recongelar, el rebote se mide desde el precio del NUEVO candado."""
    e, b, log = _unlock_setup(4451.0)
    e._maybe_unlock()
    check(e.cycle.get_meta("unlock_ref_price") == 4451.0, "aflojado a 4451")
    b._price = 4300.0
    b._equity = 2000.0          # S = 2000/(0.14*100) = 143 < 150 => recongela
    e._maybe_lock()
    check(b.orders and b.orders[-1]["comment"] == "Basket Lock"
          and abs(b.orders[-1]["lots"] - 0.14) < 1e-9, f"recandado 0.14 SELL (got {b.orders})")
    check(e.cycle.get_meta("unlock_ref_price") == 4300.0, "ref = precio del nuevo candado (4300)")
    b._equity = 5000.0
    b._price = 4350.0
    e._maybe_unlock()
    check(abs(_lock_vol(e, b) - 0.20) < 1e-9 and e.cycle.get_meta("unlock_ref_price") == 4350.0,
          f"rebote +50 desde 4300 afloja 0.14 (no hace falta 4501) (LOCK {_lock_vol(e, b)})")


# ----------------------------------------------------------------------
# Disolucion por parejas (spec §5.5)
# ----------------------------------------------------------------------
def _dissolve_setup(hours=25.0):
    """Candado SELL 0.30 desde hace `hours` h, Op3 BUY 0.18 y Op4 BUY 0.12,
    mas el par ENTRY/HEDGE 0.09/0.09. Neto propio 0 (CONGELADO). 06:00 servidor = 03 UTC."""
    e, b, log = _lock_eng(equity=5000.0, cfg={"equity_weight": 1.0})
    _pos(b, 1, mt5.POSITION_TYPE_BUY, 0.09, 4400.0, "SMC Buy Entry", profit=-200.0)
    _pos(b, 2, mt5.POSITION_TYPE_SELL, 0.09, 4400.0, "Hedge Lock", profit=150.0)
    _pos(b, 3, mt5.POSITION_TYPE_BUY, 0.18, 4400.0, "Recovery Buy (V-Shape)", profit=-180.0)
    _pos(b, 4, mt5.POSITION_TYPE_BUY, 0.12, 4400.0, "Sentinel Op 4 (L1)", profit=-60.0)
    _pos(b, 5, mt5.POSITION_TYPE_SELL, 0.30, 4400.0, "Basket Lock", profit=240.0)
    e.cycle.sync(b.positions())
    e.cycle.set_meta("lock_since", e.now - int(hours * 3600))
    e.cycle.set_meta("lock_initial_volume", 0.30)
    return e, b, log


def test_dissolve_pairs():
    from bot import ledger, strategy
    e, b, log = _dissolve_setup()
    check(e.cycle.role_of(2) == ledger.ROLE_HEDGE and e.cycle.role_of(1) == ledger.ROLE_ENTRY,
          "par ENTRY/HEDGE reconocido")
    net0 = survival.net_lots(b.positions())
    check(e._lock_state(b.positions()) == strategy.LOCK_FROZEN, "CONGELADO")
    e._maybe_dissolve()
    check([(x["ticket"], round(x["lots"], 8)) for x in b.partials] == [(3, 0.10), (5, 0.10)],
          f"primero el rojo (#3 Op3, peor por lote) 0.10 y luego LOCK #5 0.10 (got {b.partials})")
    check(abs(survival.net_lots(b.positions()) - net0) < 1e-9, "el neto propio no cambia")
    vols = {p.ticket: p.volume for p in b.positions()}
    check(vols[1] == 0.09 and vols[2] == 0.09, "ENTRY y HEDGE intactos")
    check(abs(vols[3] - 0.08) < 1e-9 and abs(vols[5] - 0.20) < 1e-9 and vols[4] == 0.12,
          f"Op3 0.08, LOCK 0.20, Op4 0.12 (got {vols})")
    check(abs(e.cycle_realized - (-100.0 + 80.0)) < 1e-6,
          f"realizado prorrateado -100+80 (got {e.cycle_realized})")
    check(e.cycle.get_meta("last_dissolve_day") == "2026-08-19", "last_dissolve_day = 2026-08-19")
    check(any(t == "HEALER" and m == "Disolucion por parejas: 0.10 lotes de #3 + #5. Neto sin cambio."
              for t, m in log.events), f"log HEALER (got {log.events})")
    e._maybe_dissolve()
    check(len(b.partials) == 2, "segunda llamada el mismo dia: nada")
    # Dia siguiente, 03 UTC: Op3 sigue siendo la peor por lote (-80/0.08); X tope 0.08
    e.now += 24 * 3600
    e._maybe_dissolve()
    check([(x["ticket"], round(x["lots"], 8)) for x in b.partials[2:]] == [(5, 0.08)]
          and 3 not in {p.ticket for p in b.positions()},
          f"dia 2: Op3 0.08 cerrada entera + 0.08 de LOCK (got {b.partials[2:]})")
    check(abs(survival.net_lots(b.positions()) - net0) < 1e-9, "dia 2: neto sin cambio")
    check(e.cycle.get_meta("last_dissolve_day") == "2026-08-20", "last_dissolve_day = 2026-08-20")


def test_dissolve_waits():
    for name in ("23h", "13utc", "vcb"):
        e, b, log = _dissolve_setup(hours=23.0 if name == "23h" else 25.0)
        if name == "13utc":
            e.now = ts(2026, 8, 19, 16)   # 16:00 servidor = 13 UTC
            e.cycle.set_meta("lock_since", e.now - 25 * 3600)
        elif name == "vcb":
            e.vol_breaker = True
        e._maybe_dissolve()
        check(not b.partials and len(b.positions()) == 5
              and e.cycle.get_meta("last_dissolve_day") is None,
              f"gate {name}: nada se cierra (got {b.partials})")
    # 24 h desde el ultimo aflojado (no desde el candado)
    e, b, log = _dissolve_setup(hours=48.0)
    e.cycle.set_meta("last_unlock_ts", e.now - 10 * 3600)
    e._maybe_dissolve()
    check(not b.partials, "aflojado hace 10 h: nada (el plazo cuenta desde el ultimo aflojado)")


def test_dissolve_lock_side_only_opposite():
    """Contraparte solo Recovery/Op4 del lado contrario al LOCK; ENTRY nunca."""
    e, b, log = _lock_eng(equity=5000.0, cfg={"equity_weight": 1.0})
    _pos(b, 1, mt5.POSITION_TYPE_BUY, 0.20, 4400.0, "SMC Buy Entry", profit=-300.0)
    _pos(b, 2, mt5.POSITION_TYPE_SELL, 0.10, 4400.0, "Recovery Sell (V-Shape)", profit=-90.0)
    _pos(b, 3, mt5.POSITION_TYPE_SELL, 0.10, 4400.0, "Basket Lock", profit=100.0)
    e.cycle.sync(b.positions())
    e.cycle.set_meta("lock_since", e.now - 25 * 3600)
    e.cycle.set_meta("lock_initial_volume", 0.10)
    e._maybe_dissolve()
    check(not b.partials and len(b.positions()) == 3,
          f"solo Recovery del MISMO lado que LOCK (la ENTRY no cuenta): nada (got {b.partials})")


def _fail_lock_closes(b):
    """El broker rechaza cerrar el ticket #5 (LOCK) mientras st['fail']."""
    orig = b.close_partial
    st = {"fail": True, "tries": 0}

    def failing(p, lots, comment="Partial"):
        if p.ticket == 5 and st["fail"]:
            st["tries"] += 1
            class R: retcode = 10006
            return R()
        return orig(p, lots, comment)
    b.close_partial = failing
    return st


def test_dissolve_second_close_fails():
    """R14: la deuda del segundo cierre se persiste y solo se reintenta ESE resto."""
    e, b, log = _dissolve_setup()
    sent = _rec_alerts(e, log)
    st = _fail_lock_closes(b)
    net0 = survival.net_lots(b.positions())
    e._maybe_dissolve()
    check(len(b.partials) == 1 and b.partials[0]["ticket"] == 3, "se cerro solo el rojo (#3)")
    net1 = survival.net_lots(b.positions())
    check(abs(net1 - (net0 - 0.10)) < 1e-9, f"neto fuera exactamente X=0.10 (got {net1})")
    check(e.cycle.get_meta("last_dissolve_day") is None, "sin last_dissolve_day")
    pend = e.cycle.get_meta("dissolve_pending")
    check(pend and pend["side"] == "SELL" and abs(pend["lots"] - 0.10) < 1e-9 and pend["tickets"] == [5],
          f"deuda pendiente SELL 0.10 en #5 (got {pend})")
    errs = [m for t, m in log.events if t == "ERROR"]
    check(len(errs) == 1 and "restantes del mismo par" in errs[0], f"un ERROR claro (got {errs})")
    check(len(sent) == 1 and "CRITICA" in sent[0], f"una alerta CRITICA (got {sent})")
    tries0 = st["tries"]
    e._maybe_dissolve()
    check(st["tries"] == tries0, "backoff 60 s: el mismo tick no reintenta")
    for _ in range(5):
        e.now += 61
        e._maybe_dissolve()
    check(len(b.partials) == 1, f"5 ticks: ninguna pareja nueva (got {b.partials})")
    check(st["tries"] == tries0 + 5, f"cada tick tras el backoff reintenta #5 (got {st['tries']})")
    check(abs(survival.net_lots(b.positions()) - net1) < 1e-9, "el neto no se agrava")
    check(len([m for t, m in log.events if t == "ERROR"]) == 1, "ERROR throttled (600 s)")
    check(len(sent) == 1, "sin alertas extra")
    check(not any(t == "HEALER" for t, m in log.events), "sin log HEALER")
    # El broker acepta de nuevo: fuera de hora (13 UTC) el reintento igual cierra la deuda.
    st["fail"] = False
    e.now = ts(2026, 8, 19, 16)
    e._maybe_dissolve()
    check(b.partials[-1]["ticket"] == 5 and abs(b.partials[-1]["lots"] - 0.10) < 1e-9,
          f"se cierran los 0.10 pendientes de #5 (got {b.partials})")
    check(abs(survival.net_lots(b.positions()) - net0) < 1e-9, "neto de vuelta al previo")
    check(e.cycle.get_meta("dissolve_pending") is None, "deuda limpia")
    check(e.cycle.get_meta("last_dissolve_day") == "2026-08-19", "last_dissolve_day marcado")
    check(any(t == "HEALER" and m == "Disolucion por parejas: 0.10 lotes de #3 + #5. Neto sin cambio."
              for t, m in log.events), "log HEALER de la pareja")
    n = len(b.partials)
    e.now += 120
    e._maybe_dissolve()
    check(len(b.partials) == n, "mismo dia: nada mas")


def test_dissolve_pending_survives_restart():
    from bot import ledger
    from bot.strategy import SentinelEngine
    e, b, log = _dissolve_setup()
    st = _fail_lock_closes(b)
    net0 = survival.net_lots(b.positions())
    e._maybe_dissolve()
    check(e.cycle.get_meta("dissolve_pending") is not None, "deuda pendiente antes del reinicio")
    st["fail"] = False
    e2 = SentinelEngine(b, log)
    e2.cycle = ledger.CycleLedger(e.cycle.path, log)
    e2.cycle.sync(b.positions())
    e2.cfg = {"equity_weight": 1.0}
    e2.now = e.now + 5
    check(e2.cycle.get_meta("dissolve_pending")["tickets"] == [5], "deuda rehidratada del ledger")
    e2._maybe_dissolve()
    check(abs(survival.net_lots(b.positions()) - net0) < 1e-9, "tras reinicio: neto de vuelta al previo")
    check(e2.cycle.get_meta("dissolve_pending") is None, "deuda limpia tras reinicio")
    check(len(b.partials) == 2, f"ninguna pareja nueva, solo el resto (got {b.partials})")


def test_dissolve_pending_cleared_when_gone():
    e, b, log = _dissolve_setup()
    _fail_lock_closes(b)
    e._maybe_dissolve()
    b._pos = [p for p in b._pos if p.ticket != 5]   # cerrada fuera (p. ej. _close_all)
    e.now += 61
    e._maybe_dissolve()
    check(e.cycle.get_meta("dissolve_pending") is None, "patas de la deuda inexistentes: deuda limpia")
    check(len(b.partials) == 1, "y no se empieza otra pareja en ese tick")


def test_dissolve_both_sides_free():
    """LIBRE: sin LOCK, Op3/Op4 en ambos lados con neto < step => se emparejan las peores."""
    from bot import strategy
    e, b, log = _lock_eng(equity=5000.0, cfg={"equity_weight": 1.0})
    _pos(b, 1, mt5.POSITION_TYPE_BUY, 0.09, 4400.0, "SMC Buy Entry", profit=-500.0)
    _pos(b, 2, mt5.POSITION_TYPE_SELL, 0.09, 4400.0, "Hedge Lock", profit=450.0)
    _pos(b, 3, mt5.POSITION_TYPE_BUY, 0.10, 4400.0, "Recovery Buy (V-Shape)", profit=-50.0)
    _pos(b, 4, mt5.POSITION_TYPE_BUY, 0.05, 4400.0, "Sentinel Op 4 (L1)", profit=-40.0)
    _pos(b, 5, mt5.POSITION_TYPE_SELL, 0.15, 4400.0, "Recovery Sell (V-Shape)", profit=30.0)
    e.cycle.sync(b.positions())
    check(e._lock_state(b.positions()) == strategy.LOCK_FREE, "LIBRE")
    e._maybe_dissolve()
    check(not b.partials and len(b.positions()) == 5,
          "sin lock_since ni last_unlock_ts: el plazo falla, nada")
    e.cycle.set_meta("last_unlock_ts", e.now - 25 * 3600)
    net0 = survival.net_lots(b.positions())
    e._maybe_dissolve()
    check(4 not in {p.ticket for p in b.positions()}
          and [(x["ticket"], round(x["lots"], 8)) for x in b.partials] == [(5, 0.05)],
          f"peor BUY (#4, -800/lote) 0.05 entera y SELL #5 0.05 parcial (got {b.partials})")
    check(abs(survival.net_lots(b.positions()) - net0) < 1e-9, "neto sin cambio")
    check({p.ticket: p.volume for p in b.positions()}.get(1) == 0.09, "ENTRY intacta")
    check(any(t == "HEALER" and m == "Disolucion por parejas: 0.05 lotes de #4 + #5. Neto sin cambio."
              for t, m in log.events), "log HEALER ambos lados")
    # neto de Op3/Op4 >= step => nada
    e, b, log = _lock_eng(equity=5000.0, cfg={"equity_weight": 1.0})
    _pos(b, 3, mt5.POSITION_TYPE_BUY, 0.10, 4400.0, "Recovery Buy (V-Shape)", profit=-50.0)
    _pos(b, 5, mt5.POSITION_TYPE_SELL, 0.05, 4400.0, "Recovery Sell (V-Shape)", profit=30.0)
    e.cycle.sync(b.positions())
    e.cycle.set_meta("last_unlock_ts", e.now - 25 * 3600)
    e._maybe_dissolve()
    check(not b.partials and len(b.positions()) == 2, "Op3/Op4 con neto 0.05 >= step: nada")


def test_dissolve_exhausts_lock():
    """Al agotarse las patas LOCK por disolucion: estado LIBRE y meta del candado limpia,
    conservando la referencia del plazo en last_unlock_ts."""
    from bot import strategy
    e, b, log = _lock_eng(equity=5000.0, cfg={"equity_weight": 1.0})
    _pos(b, 1, mt5.POSITION_TYPE_BUY, 0.10, 4400.0, "Recovery Buy (V-Shape)", profit=-100.0)
    _pos(b, 2, mt5.POSITION_TYPE_SELL, 0.10, 4400.0, "Basket Lock", profit=100.0)
    e.cycle.sync(b.positions())
    since = e.now - 25 * 3600
    e.cycle.set_meta("lock_since", since)
    e.cycle.set_meta("lock_initial_volume", 0.30)   # X = 0.10 (tope: vol LOCK)
    e._maybe_dissolve()
    check(not b.positions(), f"ambas patas cerradas enteras (quedan {b.positions()})")
    check(e._lock_state(b.positions()) == strategy.LOCK_FREE, "LIBRE")
    for k in ("unlock_ref_price", "lock_since", "lock_initial_volume"):
        check(e.cycle.get_meta(k) is None, f"{k} a None")
    check(e.cycle.get_meta("last_unlock_ts") == since, "last_unlock_ts = referencia del plazo")


def test_dissolve_wired_in_tick():
    from bot import strategy
    _ind, orig = _no_signals()
    try:
        e, b, log, _, _ = _tick_eng(equity=5000.0)
        e.cfg = {"equity_weight": 1.0}
        _pos(b, 3, mt5.POSITION_TYPE_BUY, 0.18, 4400.0, "Recovery Buy (V-Shape)", profit=-180.0)
        _pos(b, 5, mt5.POSITION_TYPE_SELL, 0.18, 4400.0, "Basket Lock", profit=180.0)
        b._price = 4400.0
        e.cycle.sync(b.positions())
        e.cycle.set_meta("lock_since", e.now - 25 * 3600)
        e.cycle.set_meta("lock_initial_volume", 0.18)
        e.on_tick()
        check(abs(_lock_vol(e, b) - 0.12) < 1e-9, f"on_tick disuelve 0.06 (LOCK {_lock_vol(e, b)})")
        check(e.lock_state == strategy.LOCK_FROZEN, "sigue CONGELADO (neto 0)")
    finally:
        _ind.get_h4_structure, _ind.check_m15_breakout = orig


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
    test_rescue_churn_capped()
    test_unwind_respects_survival()
    test_risk_hours_block_recovery_and_rescue()
    test_alert_dedupe()
    test_dead_account_gate()
    test_stop_out_alert()
    test_idle_alert()
    test_lock_triggers()
    test_frozen_blocks_subsystems()
    test_loose_excludes_lock_legs()
    test_lock_clears_trailing_sl()
    test_lock_failure_dedup()
    test_lock_survives_restart()
    test_lock_sl_cleared_each_tick()
    test_loose_no_hedges()
    test_healer_gate_excludes_lock()
    test_hedge_fail_throttled()
    test_lock_vmax_zero()
    test_no_unlock_on_continuation()
    test_unlock_on_rebound()
    test_unlock_gates()
    test_successive_unlock_needs_new_rebound()
    test_unlock_newest_first()
    test_unlock_wired_in_tick()
    test_unlock_buy_lock_mirror()
    test_relock_resets_unlock_ref()
    test_dissolve_pairs()
    test_dissolve_waits()
    test_dissolve_lock_side_only_opposite()
    test_dissolve_second_close_fails()
    test_dissolve_pending_survives_restart()
    test_dissolve_pending_cleared_when_gone()
    test_dissolve_both_sides_free()
    test_dissolve_exhausts_lock()
    test_dissolve_wired_in_tick()
    print("\ntest_supervivencia: TODO OK")


if __name__ == "__main__":
    main()
