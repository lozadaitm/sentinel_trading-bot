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
    print("\ntest_supervivencia: TODO OK")


if __name__ == "__main__":
    main()
