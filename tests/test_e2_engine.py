"""Motor e2 de las tres patas (bot/strategy_e2.py, SessionEngine).

Sin MT5 ni Supabase: broker falso (magic 100300), velas sinteticas y reloj
inyectado por los seams _now/_fetch_tick/_rates_d1/_rates_m15/_events.
El archivo de estado vive en una carpeta temporal.

Correr:  python -m tests.test_e2_engine
"""

import json
import os
import sys
import tempfile
from types import SimpleNamespace

import MetaTrader5 as mt5
import pandas as pd

from bot import config, sessions
from bot.strategy_e2 import SessionEngine
from tests.test_m5_and_budget import FakeBroker, FakeLogger, FakePos

FAILS = []
MAGIC = 100300
TUE = 19997   # dia de servidor (epoch // 86400) que cae en martes
FRI = 20000   # viernes
H = 3600
OPENING_READS = 5   # = strategy_e2.OPENING_MISS_READS


def check(cond, name, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  [{detail}]"))
    if not cond:
        FAILS.append(name)


class E2Broker(FakeBroker):
    """FakeBroker con rechazo programable de ordenes y hora de apertura real."""

    def __init__(self, **kw):
        super().__init__(magic=MAGIC, **kw)
        self.reject = {}        # prefijo de comentario -> cuantas rechazar
        self.close_reject = 0   # cuantos cierres rechazar
        self.clock = 0
        self.closes = []
        self.empty_reads = 0    # lecturas de posiciones que devuelven [] (reconexion MT5)
        self.partial = {}       # prefijo de comentario -> volumen ejecutado (DONE_PARTIAL, una vez)
        self.gone = {}          # ticket -> volumen de las posiciones cerradas (historial)
        self.history_never = False  # historial que nunca confirma nada (devuelve [])
        self.hedging = True         # modo de margen de la cuenta (None = lectura fallida)
        self.none_result = {}       # prefijo -> cuantas ordenes devuelven None pero SI entran
        self.reject_rc = 10019      # retcode de los rechazos programados (10018 = mercado cerrado)

    def is_hedging_account(self):
        return self.hedging

    def positions_checked(self):
        if self.empty_reads > 0:
            self.empty_reads -= 1
            return []
        return super().positions_checked()

    def history_deals_for_position(self, ticket):
        if self.history_never:
            return []
        if ticket in self.gone:
            v = self.gone[ticket]
            return [SimpleNamespace(entry=mt5.DEAL_ENTRY_IN, volume=v),
                    SimpleNamespace(entry=mt5.DEAL_ENTRY_OUT, volume=v)]
        p = next((p for p in self._pos if p.ticket == ticket), None)
        return [SimpleNamespace(entry=mt5.DEAL_ENTRY_IN, volume=p.volume)] if p else []

    def external_close(self, ticket):
        p = next(p for p in self._pos if p.ticket == ticket)
        self._pos.remove(p)
        self.gone[ticket] = p.volume

    def check_free_margin(self, lots, order_type):
        return True

    def market_order(self, otype, lots, comment, sl=0.0, tp=0.0):
        for pref, n in self.reject.items():
            if n > 0 and comment.startswith(pref):
                self.reject[pref] = n - 1
                self.orders.append({"type": otype, "lots": lots, "comment": comment,
                                    "sl": sl, "rejected": True})
                return SimpleNamespace(retcode=self.reject_rc, order=0)
        none_pref = next((pref for pref, n in self.none_result.items()
                          if n > 0 and comment.startswith(pref)), None)
        part = next((pref for pref in self.partial if comment.startswith(pref)), None)
        vol = self.partial.pop(part) if part else lots
        r = super().market_order(otype, vol, comment, sl, tp)
        self._pos[-1].time = self.clock
        self.orders[-1]["tp"] = tp
        self.orders[-1]["lots"] = lots
        if none_pref:
            self.none_result[none_pref] -= 1
            return None          # order_send devolvio None aunque la orden SI entro
        if part:
            return SimpleNamespace(retcode=mt5.TRADE_RETCODE_DONE_PARTIAL, order=r.order,
                                   volume=vol)
        return r

    def close_position(self, p, comment="Close"):
        if self.close_reject > 0:
            self.close_reject -= 1
            return SimpleNamespace(retcode=10019)
        self.closes.append((p.ticket, comment))
        self.gone[p.ticket] = p.volume
        return super().close_position(p, comment)


def d1_frame(day, n=120):
    """D1 alcista (s = +2) con rango diario 40 -> ATR_D = 40. La ultima fila es el dia en curso."""
    days = [day - n + 1 + i for i in range(n)]
    close = [3000.0 + 10 * i for i in range(n)]
    return pd.DataFrame({
        "time": [d * 86400 for d in days],
        "open": close, "high": [c + 20 for c in close], "low": [c - 20 for c in close],
        "close": close,
    })


def m15_frame(now, opens=None, n=200):
    """M15 planas (TR = 2 -> ATR15 = 2); la ultima es la vela en formacion."""
    opens = opens or {}
    end = (now // 900) * 900
    times = [end - 900 * k for k in range(n - 1, -1, -1)]
    o = [opens.get(t, 4000.0) for t in times]
    return pd.DataFrame({"time": times, "open": o, "high": [4001.0] * n,
                         "low": [3999.0] * n, "close": [4000.0] * n})


class Rig:
    def __init__(self, path, day=TUE, br=None, events=None, opens=None, balance=10000.0):
        self.br = br or E2Broker(balance=balance)
        self.lg = FakeLogger()
        self.t = day * 86400
        self.day = day
        self.events = events or []
        self.opens = opens or {}
        self.wall = 1_000_000.0     # reloj local simulado (watchdog de ticks)
        self.eng = self._mk(path)

    def _mk(self, path):
        eng = SessionEngine(self.br, self.lg, state_path=path)
        eng._now = lambda: self.t
        eng._fetch_tick = lambda: SimpleNamespace(time=self.t, bid=self.br._price,
                                                  ask=self.br._price + 0.25)
        eng._rates_d1 = lambda n: d1_frame(self.t // 86400, n)
        eng._rates_m15 = lambda n: m15_frame(self.t, self.opens, n)
        eng._events = lambda: list(self.events)
        eng._calendar_status = lambda day: (True, "")
        eng._wall = lambda: self.wall
        eng.is_active, eng.close_only = True, False
        eng.init_history_cursor()
        return eng

    def restart(self, path):
        self.eng = self._mk(path)

    def tick(self, t, price=None):
        self.t = t
        self.br.clock = t
        if price is not None:
            self.br._price = price
        self.eng.on_tick()

    def leg(self, leg):
        return self.eng.state.legs.get(f"{leg}:{self.t // 86400}") or next(
            (e for e in self.eng.state.legs.values() if e["leg"] == leg), None)

    def kinds(self, kind):
        return [m for k, m in self.lg.events if k == kind]


def fresh_path(d, name):
    return os.path.join(d, name, "e2_state_test.json")


def opened_bigone(d, name):
    r = Rig(fresh_path(d, name))
    r.tick(TUE * 86400 + H + 5, 4000.0)
    return r


def test_bigone_entra_una_vez(d):
    r = opened_bigone(d, "b1")
    lots = sessions.ladder_lots(10000.0, 0.08, 1.0, 40.0)
    orders = r.br.orders
    check(len(orders) == 3, "bigone: 3 ordenes a las 01:00:05", orders)
    check(all(o["type"] == mt5.ORDER_TYPE_BUY for o in orders), "bigone: todas de compra")
    check([o["lots"] for o in orders] == lots, "bigone: lotes de ladder_lots", (orders, lots))
    check([o["comment"] for o in orders] == ["E2 BigOne T1", "E2 BigOne T2", "E2 BigOne T3"],
          "bigone: comentarios T1/T2/T3", orders)
    check(all(o["sl"] == 0.0 and o["tp"] == 0.0 for o in orders), "bigone: sin SL ni TP")
    e = r.leg("bigone")
    check(e and e["status"] == "open", "bigone: estado open", e)
    check(e and abs(e["entry_price"] - 4000.25) < 1e-9, "bigone: entrada al ask", e)
    check(e and abs(e["lock_price"] - 3960.25) < 1e-9, "bigone: candado a -1 ATR_D", e)
    check(e and e["exit_epoch"] == TUE * 86400 + 10 * H, "bigone: salida 10:00", e)
    check(len(r.kinds("APERTURA")) == 1, "bigone: log APERTURA", r.lg.events)
    ok_log = r.kinds("APERTURA") and all(w in r.kinds("APERTURA")[0]
                                         for w in ("riesgo", "ATR_D", "ATR15", "spread", "desliz"))
    check(bool(ok_log), "bigone: APERTURA con riesgo/ATR/spread/deslizamiento", r.kinds("APERTURA"))
    r.tick(TUE * 86400 + H + 20)
    check(len(r.br.orders) == 3, "bigone: segundo tick 01:00:20 no abre mas", r.br.orders)
    check(os.path.exists(r.eng.state.path), "bigone: estado guardado en disco")


def test_bigone_omitida_sin_tick(d):
    r = Rig(fresh_path(d, "b2"))
    r.tick(TUE * 86400 + H + 300, 4000.0)
    e = r.eng.state.legs.get(f"bigone:{TUE}")
    check(len(r.br.orders) == 0, "omitida: 0 ordenes a las 01:05", r.br.orders)
    check(e is not None and e["status"] == "skipped", "omitida: status skipped", e)
    check(len(r.kinds("OMITIDA")) == 1, "omitida: log OMITIDA", r.lg.events)
    # close_only: no marca omitidas
    r2 = Rig(fresh_path(d, "b2b"))
    r2.eng.close_only, r2.eng.is_active = True, False
    r2.tick(TUE * 86400 + H + 5, 4000.0)
    r2.tick(TUE * 86400 + H + 300)
    check(len(r2.br.orders) == 0 and not r2.eng.state.legs,
          "close_only: no abre ni marca omitida", r2.eng.state.legs)


def test_mercado_cerrado_reintenta(d):
    """El broker cotiza desde las 01:00 pero opera desde las 01:01: 10018 -> reintento."""
    br = E2Broker(balance=10000.0)
    br.reject_rc, br.reject = 10018, {"E2 BigOne T1": 2}
    r = Rig(fresh_path(d, "mc"), br=br)
    r.tick(TUE * 86400 + H + 5, 4000.0)
    check(len(br.orders) == 1 and r.eng.state.legs.get(f"bigone:{TUE}") is None,
          "cerrado: 1 rechazo y sin registro de la pata", (br.orders, r.eng.state.legs))
    check(any("aun no acepta" in m for m in r.kinds("SYSTEM")), "cerrado: aviso de reintento",
          r.lg.events)
    r.tick(TUE * 86400 + H + 7)
    check(len(br.orders) == 1, "cerrado: espera 5 s entre intentos", br.orders)
    r.tick(TUE * 86400 + H + 11)
    check(len(br.orders) == 2, "cerrado: segundo intento rechazado", br.orders)
    r.tick(TUE * 86400 + H + 61)
    e = r.leg("bigone")
    check(e and e["status"] == "open" and len([o for o in br.orders if not o.get("rejected")]) == 3,
          "cerrado: a las 01:01 entra la escalera completa (pasada la gracia de 60 s)", br.orders)
    check(len([m for m in r.kinds("SYSTEM") if "aun no acepta" in m]) == 1,
          "cerrado: el aviso sale una sola vez", r.lg.events)
    # Nunca abre: se omite a los 10 minutos
    br2 = E2Broker(balance=10000.0)
    br2.reject_rc, br2.reject = 10018, {"E2 BigOne T1": 10 ** 6}
    r2 = Rig(fresh_path(d, "mc2"), br=br2)
    for k in range(0, 700, 5):
        r2.tick(TUE * 86400 + H + 5 + k, 4000.0)
    e2 = r2.eng.state.legs.get(f"bigone:{TUE}")
    check(e2 and e2["status"] == "skipped" and "mercado cerrado" in e2.get("reason", ""),
          "cerrado: a los 10 min se omite", e2)
    n = len(br2.orders)
    r2.tick(TUE * 86400 + H + 800)
    check(len(br2.orders) == n and n <= 125, "cerrado: tras omitir no reintenta", n)
    # Otro rechazo (no 10018) sigue sin reintentar
    br3 = E2Broker(balance=10000.0)
    br3.reject = {"E2 BigOne": 3}
    r3 = Rig(fresh_path(d, "mc3"), br=br3)
    r3.tick(TUE * 86400 + H + 5, 4000.0)
    r3.tick(TUE * 86400 + H + 30)
    check(len(br3.orders) == 3 and r3.leg("bigone")["status"] == "skipped",
          "rechazo 10019: no se reintenta", br3.orders)


def test_objetivos_cierran_tercios(d):
    r = opened_bigone(d, "tp")
    e = r.leg("bigone")
    t1, t2, t3 = e["thirds"]
    r.tick(TUE * 86400 + 2 * H, 4000.25 + 2 * 2.0)
    live = {p.ticket for p in r.br.positions()}
    check(t2 not in live and t1 in live and t3 in live, "objetivos: +2 ATR15 cierra solo T2", live)
    r.tick(TUE * 86400 + 2 * H + 60, 4000.25 + 3 * 2.0)
    live = {p.ticket for p in r.br.positions()}
    check(t3 not in live and t1 in live, "objetivos: +3 ATR15 cierra T3; T1 sigue", live)
    check(sorted(r.leg("bigone")["closed_thirds"]) == sorted([t2, t3]),
          "objetivos: closed_thirds = T2, T3", r.leg("bigone"))
    check(r.leg("bigone")["status"] == "open", "objetivos: la pata sigue open")


def test_candado(d):
    r = opened_bigone(d, "lock")
    r.tick(TUE * 86400 + 2 * H, 3960.25)
    locks = [o for o in r.br.orders if o["comment"].startswith("E2 Lock")]
    check(len(locks) == 1, "candado: 1 orden de candado", r.br.orders)
    check(locks and locks[0]["type"] == mt5.ORDER_TYPE_SELL, "candado: es venta")
    check(locks and abs(locks[0]["lots"] - 0.18) < 1e-9, "candado: volumen = tercios abiertos", locks)
    check(locks and locks[0]["comment"] == "E2 Lock BigOne" and locks[0]["sl"] == 0.0,
          "candado: comentario 'E2 Lock BigOne', sl=0", locks)
    e = r.leg("bigone")
    check(e["status"] == "locked" and e["lock_ticket"], "candado: estado locked con ticket", e)
    r.tick(TUE * 86400 + 3 * H, 4010.0)
    check(len(r.br.positions()) == 4, "candado: tras el candado un bid >= TP no cierra tercios",
          r.br.positions())
    r.tick(TUE * 86400 + 3 * H + 1, 3900.0)
    check(len([o for o in r.br.orders if o["comment"].startswith("E2 Lock")]) == 1,
          "candado: no se duplica en locked")


def test_candado_fallido_reintenta(d):
    r = opened_bigone(d, "lockfail")
    r.br.reject["E2 Lock"] = 1
    r.tick(TUE * 86400 + 2 * H, 3960.0)
    check(r.leg("bigone")["status"] == "open", "candado fallido: sigue open tras el rechazo")
    r.tick(TUE * 86400 + 2 * H + 1, 3960.0)
    check(r.leg("bigone")["status"] == "locked", "candado fallido: locked al tick siguiente",
          r.leg("bigone"))
    errs = [m for m in r.kinds("ERROR") if "andado" in m]
    check(len(errs) == 1, "candado fallido: un ERROR registrado", r.lg.events)


def test_salida_cierra_todo_con_candado(d):
    r = opened_bigone(d, "exit")
    r.tick(TUE * 86400 + 2 * H, 3960.0)
    for p in r.br._pos:
        p.profit = -50.0 if p.type == mt5.POSITION_TYPE_BUY else 10.0
    r.tick(TUE * 86400 + 10 * H, 3950.0)
    check(len(r.br.positions_of_magic(MAGIC)) == 0, "salida: posiciones del magic = 0",
          r.br.positions())
    check(r.leg("bigone")["status"] == "closed", "salida: estado closed", r.leg("bigone"))
    cierres = [m for m in r.kinds("CIERRE") if "P&L" in m]
    check(len(cierres) == 1 and "-" in cierres[0], "salida: log CIERRE con P&L total negativo",
          r.kinds("CIERRE"))


def test_salida_cierre_fallido_reintenta(d):
    r = opened_bigone(d, "exitfail")
    r.br.close_reject = 1
    r.tick(TUE * 86400 + 10 * H, 4000.0)
    check(r.leg("bigone")["status"] != "closed" and len(r.br.positions()) == 1,
          "salida fallida: queda una posicion y no se marca closed", r.br.positions())
    r.tick(TUE * 86400 + 10 * H + 1)
    check(r.leg("bigone")["status"] == "closed" and not r.br.positions(),
          "salida fallida: se reintenta y cierra", r.br.positions())


def test_reinicio(d):
    path = fresh_path(d, "restart")
    r = Rig(path)
    r.tick(TUE * 86400 + H + 5, 4000.0)
    check(len(r.br.orders) == 3, "reinicio: entro la Big One")
    r.restart(path)
    r.tick(TUE * 86400 + 5 * H, 4001.0)
    check(len(r.br.orders) == 3, "reinicio: motor nuevo a las 05:00 no reabre", r.br.orders)
    r.tick(TUE * 86400 + 10 * H, 4001.0)
    check(not r.br.positions() and r.leg("bigone")["status"] == "closed",
          "reinicio: a las 10:00 cierra", r.br.positions())


def test_arranque_tras_salida(d):
    path = fresh_path(d, "late")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    br = E2Broker()
    for tk in (11, 12, 13):
        br._pos.append(FakePos(tk, mt5.POSITION_TYPE_BUY, 0.06, 4000.0,
                               TUE * 86400 + H, f"E2 BigOne T{tk - 10}", MAGIC))
    br._pos.append(FakePos(14, mt5.POSITION_TYPE_SELL, 0.18, 3960.0,
                           TUE * 86400 + 2 * H, "E2 Lock BigOne", MAGIC))
    entry = {"leg": "bigone", "side": "buy", "entry_epoch": TUE * 86400 + H + 5,
             "exit_epoch": TUE * 86400 + 10 * H, "entry_price": 4000.0, "atr_d": 40.0,
             "atr15": 2.0, "lock_price": 3960.0, "tp": [None, 4004.0, 4006.0],
             "thirds": [11, 12, 13], "closed_thirds": [], "lock_ticket": 14,
             "status": "locked"}
    with open(path, "w", encoding="utf-8") as f:
        json.dump({f"bigone:{TUE}": entry}, f)
    r = Rig(path, br=br)
    r.tick(TUE * 86400 + 12 * H, 3990.0)
    check(not br.positions(), "arranque tras salida: cierra todo en el primer tick", br.positions())
    check(r.eng.state.legs[f"bigone:{TUE}"]["status"] == "closed", "arranque tras salida: closed")
    check(len(br.orders) == 0, "arranque tras salida: no abre nada (Big One pasada no se reabre)",
          br.orders)


def test_momentum_umbral(d):
    opens = {TUE * 86400 + H: 4000.0}
    r = Rig(fresh_path(d, "mom1"), opens=opens)
    r.tick(TUE * 86400 + H + 5, 4000.0)       # Big One entra (irrelevante aqui)
    n0 = len(r.br.orders)
    r.tick(TUE * 86400 + 15 * H + 2, 4009.0)
    check(len(r.br.orders) == n0, "momentum: 4009 (0,225 %) no entra", r.br.orders[n0:])
    e = r.eng.state.legs.get(f"mom:{TUE}")
    check(e is not None and e["status"] == "skipped", "momentum: sin senal queda skipped", e)
    r2 = Rig(fresh_path(d, "mom2"), opens=opens)
    r2.eng.cfg = {"e2_legs": "mom"}
    r2.tick(TUE * 86400 + 15 * H + 2, 4010.0)
    mo = [o for o in r2.br.orders if o["comment"].startswith("E2 MomUS")]
    check(len(mo) == 3 and all(o["type"] == mt5.ORDER_TYPE_BUY for o in mo),
          "momentum: 4010 (0,25 %) compra 3 tercios", r2.br.orders)
    e2 = r2.eng.state.legs.get(f"mom:{TUE}")
    check(e2 and e2["exit_epoch"] == TUE * 86400 + 21 * H, "momentum: salida 21:00", e2)
    check(not [o for o in r2.br.orders if o["comment"].startswith("E2 BigOne")],
          "e2_legs='mom' desactiva la Big One")


def test_nfp_viernes(d):
    T = FRI * 86400 + 15 * H + 30 * 60          # 15:30 servidor
    events = [{"time": T, "name": "Non-Farm Employment Change", "currency": "USD",
               "importance": "high"}]
    opens = {T - 900: 4000.0}
    r = Rig(fresh_path(d, "nfp"), day=FRI, events=events, opens=opens)
    r.eng.cfg = {"e2_legs": "nfp"}
    r.tick(T + 3600 - 10, 3990.0)
    check(len(r.br.orders) == 0, "nfp: antes de T+60 no entra")
    r.tick(T + 3600 + 3, 3990.0)
    nf = [o for o in r.br.orders if o["comment"].startswith("E2 NFP")]
    check(len(nf) == 3 and all(o["type"] == mt5.ORDER_TYPE_SELL for o in nf),
          "nfp: venta si el precio bajo desde la apertura de T-15", r.br.orders)
    e = r.eng.state.legs.get(f"nfp:{FRI}")
    exp = sessions.exit_epoch("nfp", T + 3600 + 3, 96)
    check(e and e["exit_epoch"] == exp, "nfp: exit_epoch de sessions.exit_epoch", e)
    check(e and (e["exit_epoch"] // 86400 + 3) % 7 == 0, "nfp: la salida cae en lunes", e)
    check(e and abs(e["lock_price"] - (3990.0 + 40.0)) < 1e-9, "nfp: candado por encima en venta", e)
    # event_day para la Big One: el dia del NFP la Big One va a medio peso extra
    r2 = Rig(fresh_path(d, "nfpbig"), day=FRI, events=events)
    r2.tick(FRI * 86400 + H + 5, 4000.0)
    lots = sessions.ladder_lots(10000.0, 0.08, 0.5, 40.0)
    check([o["lots"] for o in r2.br.orders] == lots, "bigone: x0,5 en dia de NFP", r2.br.orders)


def test_close_all(d):
    r = opened_bigone(d, "closeall")
    r.tick(TUE * 86400 + 2 * H, 3960.0)
    check(len(r.br.positions()) == 4, "close_all: tercios + candado vivos")
    ok = r.eng.close_all("Cierre forzado por el usuario")
    check(ok is True and not r.br.positions(), "close_all: cierra todo y devuelve True",
          r.br.positions())
    check(r.leg("bigone")["status"] == "closed", "close_all: la pata queda closed")
    r2 = opened_bigone(d, "closeall2")
    r2.br.close_reject = 1
    check(r2.eng.close_all("x") is False, "close_all: con un rechazo devuelve False")


def test_recuperacion_tras_caida(d):
    """Caida entre el envio de las ordenes y el guardado: se adoptan, no se duplican."""
    path = fresh_path(d, "crash")
    r = Rig(path)
    r.t = TUE * 86400 + H + 5
    r.br.clock = r.t
    orig = r.br.market_order
    calls = []

    def boom(*a, **k):
        res = orig(*a, **k)
        calls.append(1)
        if len(calls) == 3:
            raise RuntimeError("caida simulada")
        return res
    r.br.market_order = boom
    try:
        r.eng.on_tick()
    except RuntimeError:
        pass
    r.br.market_order = orig
    check(len(r.br.positions()) == 3, "caida: quedaron 3 tercios vivos")
    r.restart(path)
    r.tick(TUE * 86400 + H + 20, 4000.0)
    check(len(r.br.orders) == 3, "caida: el motor nuevo no duplica la entrada", r.br.orders)
    e = r.eng.state.legs.get(f"bigone:{TUE}")
    check(e and e["status"] == "open" and None not in e["thirds"],
          "caida: adopta los tercios por comentario", e)
    r.tick(TUE * 86400 + 10 * H, 4000.0)
    check(not r.br.positions(), "caida: y los cierra a la hora de salida")


def test_estado_corrupto(d):
    path = fresh_path(d, "corrupt")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write("{{{ basura")
    r = Rig(path)
    check(os.path.exists(path + ".bak"), "corrupto: copia .bak")
    check(any("estado" in m.lower() for m in r.kinds("ERROR")), "corrupto: ERROR registrado")
    check(any("BLOQUEADAS" in m for m in r.kinds("ERROR")), "corrupto: ERROR avisa del bloqueo")
    r.tick(TUE * 86400 + H + 5, 4000.0)
    check(len(r.br.orders) == 0, "corrupto: sin entradas nuevas el dia de la carga", r.br.orders)
    r.tick(TUE * 86400 + 15 * H + 5, 4000.0)
    check(len(r.br.orders) == 0, "corrupto: tampoco entra mas tarde ese dia", r.br.orders)
    r.tick((TUE + 1) * 86400 + H + 5, 4000.0)
    check(len(r.br.orders) == 3, "corrupto: al dia siguiente vuelve a operar", r.br.orders)


def test_lectura_vacia_no_cierra(d):
    """C1: una lectura vacia de posiciones (reconexion) no da tercios por cerrados."""
    r = opened_bigone(d, "empty")
    r.br.empty_reads = 1
    r.tick(TUE * 86400 + 2 * H, 4000.0)
    e = r.leg("bigone")
    check(e["status"] == "open" and e["closed_thirds"] == [],
          "lectura vacia: la pata sigue open sin tercios cerrados", e)
    r.tick(TUE * 86400 + 2 * H + 10, 3960.0)
    check(r.leg("bigone")["status"] == "locked", "lectura vacia: despues sigue gestionando (candado)")
    r.tick(TUE * 86400 + 10 * H, 3960.0)
    check(not r.br.positions() and r.leg("bigone")["status"] == "closed",
          "lectura vacia: y cierra todo a la salida", r.br.positions())
    # cierre externo real: confirmado por historial -> se apunta como cerrado
    r2 = opened_bigone(d, "extclose")
    t2 = r2.leg("bigone")["thirds"][1]
    r2.br.external_close(t2)
    r2.tick(TUE * 86400 + 2 * H, 4000.0)
    check(t2 in r2.leg("bigone")["closed_thirds"], "cierre externo confirmado en historial")


def test_salida_lectura_vacia(d):
    """M5: a la hora de salida una lectura vacia no marca la pata closed."""
    r = opened_bigone(d, "exitempty")
    r.br.empty_reads = 1
    r.tick(TUE * 86400 + 10 * H, 4000.0)
    check(r.leg("bigone")["status"] == "open" and len(r.br.positions()) == 3,
          "salida con lectura vacia: no se marca closed", r.leg("bigone"))
    r.tick(TUE * 86400 + 10 * H + 1, 4000.0)
    check(r.leg("bigone")["status"] == "closed" and not r.br.positions(),
          "salida con lectura vacia: cierra al tick siguiente", r.br.positions())


def test_close_all_lectura_fallida(d):
    """C2: close_all con lectura fallida devuelve False y no marca patas cerradas."""
    r = opened_bigone(d, "cafail")
    r.br.pos_fail = True
    check(r.eng.close_all("x") is False, "close_all: lectura fallida -> False")
    check(r.leg("bigone")["status"] == "open", "close_all: la pata no se marca closed")
    r.br.pos_fail = False
    check(r.eng.close_all("x") is True and not r.br.positions(), "close_all: luego cierra")


def test_adp_no_cuenta(d):
    """I1: el ADP no es el NFP ni hace dia de evento para la Big One."""
    T = FRI * 86400 + 15 * H + 15 * 60
    events = [{"time": T, "name": "ADP Non-Farm Employment Change", "currency": "USD",
               "importance": "high"}]
    r = Rig(fresh_path(d, "adp"), day=FRI, events=events, opens={T - 900: 4000.0})
    r.tick(FRI * 86400 + H + 5, 4000.0)
    lots = sessions.ladder_lots(10000.0, 0.08, 1.0, 40.0)
    check([o["lots"] for o in r.br.orders] == lots, "ADP: la Big One va a peso completo",
          r.br.orders)
    r.tick(T + 3600 + 3, 3990.0)
    check(not [o for o in r.br.orders if o["comment"].startswith("E2 NFP")],
          "ADP: no dispara la pata NFP", r.br.orders)


def test_ejecucion_parcial(d):
    """I2: DONE_PARTIAL en un tercio se rastrea; el candado parcial se completa."""
    r = Rig(fresh_path(d, "partial"))
    r.br.partial["E2 BigOne T2"] = 0.03
    r.tick(TUE * 86400 + H + 5, 4000.0)
    e = r.leg("bigone")
    check(e["thirds"][1] is not None and abs(e["lots"][1] - 0.03) < 1e-9,
          "parcial: T2 rastreado con 0,03 lotes", e)
    r.br.partial["E2 Lock"] = 0.05
    r.tick(TUE * 86400 + 2 * H, 3960.0)
    check(r.leg("bigone")["status"] == "open", "candado parcial: aun no locked", r.leg("bigone"))
    r.tick(TUE * 86400 + 2 * H + 1, 4000.0)     # el precio ya se fue, pero se completa igual
    locks = [p for p in r.br.positions() if p.comment == "E2 Lock BigOne"]
    vol = round(sum(p.volume for p in locks), 2)
    check(r.leg("bigone")["status"] == "locked" and abs(vol - 0.15) < 1e-9,
          "candado parcial: se completa hasta el volumen de los tercios (0,15)", (vol, locks))
    r.tick(TUE * 86400 + 2 * H + 2, 3950.0)
    check(len([p for p in r.br.positions() if p.comment == "E2 Lock BigOne"]) == 2,
          "candado: no se agranda de mas")
    r.tick(TUE * 86400 + 10 * H, 3950.0)
    check(not r.br.positions(), "parcial: la salida cierra los dos tickets de candado")


def test_excepcion_en_tick(d):
    """I3: una excepcion persistente no escapa de on_tick y se loguea con throttle."""
    r = Rig(fresh_path(d, "exc"))

    def boom(n):
        raise ValueError("velas rotas")
    r.eng._rates_d1 = boom
    raised = False
    try:
        r.tick(TUE * 86400 + H + 5, 4000.0)
        r.tick(TUE * 86400 + H + 6, 4000.0)
    except Exception:  # noqa: BLE001
        raised = True
    errs = [m for m in r.kinds("ERROR") if "velas rotas" in m]
    check(not raised, "excepcion: no escapa de on_tick")
    check(len(errs) == 1, "excepcion: un ERROR por minuto", r.lg.events)


def test_persistencia_previa_fallida(d):
    """M1: si no se puede guardar el registro opening, no se envian ordenes."""
    r = Rig(fresh_path(d, "savefail"))

    def nosave():
        raise OSError("disco lleno")
    r.eng.state.save = nosave
    r.tick(TUE * 86400 + H + 5, 4000.0)
    r.tick(TUE * 86400 + H + 6, 4000.0)
    check(len(r.br.orders) == 0, "persistencia fallida: no se envian ordenes", r.br.orders)
    check(len([m for m in r.kinds("ERROR") if "persistir" in m]) == 1,
          "persistencia fallida: un ERROR (con throttle)", r.kinds("ERROR"))


def test_ticket_sin_confirmar_no_contagia(d):
    """N1: un ticket ausente que el historial nunca confirma no bloquea la pata para
    siempre ni hace que la pata vieja cierre las entradas del dia siguiente."""
    import bot.strategy_e2 as se
    WED = TUE + 1
    r = opened_bigone(d, "unconf")
    r.br.history_never = True
    t1 = r.leg("bigone")["thirds"][0]
    r.br.external_close(t1)
    old_giveup = getattr(se, "UNCONFIRMED_GIVEUP_S", 900)
    se.UNCONFIRMED_GIVEUP_S = 10 ** 9          # primero: la pata vieja sigue atascada
    try:
        r.tick(TUE * 86400 + 10 * H, 4000.0)
        e1 = r.eng.state.legs[f"bigone:{TUE}"]
        check(e1["status"] != "closed" and not r.br.positions(),
              "sin confirmar: tras la salida T2/T3 cerrados, la pata espera", e1)
        errs = lambda: [m for m in r.kinds("ERROR") if f"#{t1}" in m and "sin cierre" in m]
        check(len(errs()) == 1, "sin confirmar: ERROR con pata y ticket", r.kinds("ERROR"))
        r.tick(TUE * 86400 + 10 * H + 60, 4000.0)
        check(len(errs()) == 1, "sin confirmar: ERROR con throttle (no a cada tick)")
        r.tick(TUE * 86400 + 10 * H + 660, 4000.0)
        check(len(errs()) == 2, "sin confirmar: el ERROR se repite a los 10 min")
        r.tick(WED * 86400 + H + 5, 4000.0)       # entra la Big One del miercoles
        e2 = r.eng.state.legs.get(f"bigone:{WED}")
        check(e2 and e2["status"] == "open" and len(r.br.positions()) == 3,
              "dia 2: la Big One nueva entra", e2)
        r.tick(WED * 86400 + H + 20, 4000.0)
        check(len(r.br.positions()) == 3 and not [c for c in r.br.closes
                                                   if c[1] == "E2 Salida BigOne"
                                                   and c[0] in e2["thirds"]],
              "dia 2: la pata vieja NO cierra las posiciones nuevas", r.br.closes)
    finally:
        se.UNCONFIRMED_GIVEUP_S = old_giveup
    for k in range(OPENING_READS):                # ahora rige el limite: N lecturas no vacias
        r.tick(WED * 86400 + H + 30 + k, 4000.0)
    e1 = r.eng.state.legs[f"bigone:{TUE}"]
    check(e1["status"] == "closed" and e1.get("unconfirmed") == [t1],
          "sin confirmar: tras el limite la pata vieja cierra y apunta el ticket", e1)
    check(any("sin confirmar" in m and f"[{t1}]" in m for m in r.kinds("WARNING")),
          "sin confirmar: WARNING al darla por cerrada", r.kinds("WARNING"))
    check(len(r.br.positions()) == 3 and r.eng.state.legs[f"bigone:{WED}"]["status"] == "open",
          "dia 2: la pata nueva sigue intacta")


def test_vuelta_tras_salida_lectura_vacia(d):
    """N1c (1): bot caido durante la salida, vuelve a los +20 min con una lectura
    vacia -> la pata NO se da por cerrada; la siguiente lectura normal cierra todo."""
    path = fresh_path(d, "late_empty")
    r = Rig(path)
    r.tick(TUE * 86400 + H + 5, 4000.0)
    r.restart(path)
    r.br.empty_reads = 1
    r.tick(TUE * 86400 + 10 * H + 20 * 60, 4000.0)
    check(r.leg("bigone")["status"] != "closed" and len(r.br.positions()) == 3,
          "vuelta +20 min con lectura vacia: la pata NO se cierra", r.leg("bigone"))
    r.tick(TUE * 86400 + 10 * H + 20 * 60 + 1, 4000.0)
    check(not r.br.positions() and r.leg("bigone")["status"] == "closed"
          and not r.leg("bigone").get("unconfirmed"),
          "siguiente lectura normal: cierra las posiciones vivas", r.br.positions())


def test_lecturas_vacias_persistentes(d):
    """N1c (2): 30 min de lecturas vacias tras la salida no cierran la pata."""
    r = opened_bigone(d, "empty30")
    r.br.empty_reads = 10 ** 6
    for m in range(0, 31):
        r.tick(TUE * 86400 + 10 * H + m * 60, 4000.0)
    check(r.leg("bigone")["status"] != "closed" and len(r.br.positions()) == 3,
          "30 min de lecturas vacias: la pata sigue abierta", r.leg("bigone"))
    r.br.empty_reads = 0
    r.tick(TUE * 86400 + 10 * H + 31 * 60, 4000.0)
    check(not r.br.positions() and r.leg("bigone")["status"] == "closed",
          "al volver las lecturas normales: cierra todo")


def test_abandono_legitimo(d):
    """N1c (3): ticket realmente cerrado, historial que nunca confirma y lecturas
    no vacias sin el durante > 15 min -> se da por cerrada con WARNING."""
    br = E2Broker()
    br._pos.append(FakePos(77, mt5.POSITION_TYPE_BUY, 0.05, 4000.0, TUE * 86400,
                           "manual", MAGIC))   # mantiene las lecturas no vacias
    r = Rig(fresh_path(d, "giveup"), br=br)
    r.tick(TUE * 86400 + H + 5, 4000.0)
    r.br.history_never = True
    t2 = r.leg("bigone")["thirds"][1]
    r.br.external_close(t2)
    r.tick(TUE * 86400 + 10 * H, 4000.0)       # cierra T1 y T3; T2 queda sin confirmar
    check(r.leg("bigone")["status"] != "closed" and [p.ticket for p in r.br.positions()] == [77],
          "abandono: a las 10:00 cierra lo vivo y espera por T2", r.br.positions())
    for m in range(1, 10):
        r.tick(TUE * 86400 + 10 * H + m * 60, 4000.0)
    check(r.leg("bigone")["status"] != "closed", "abandono: antes de 15 min aun espera")
    r.tick(TUE * 86400 + 10 * H + 17 * 60, 4000.0)
    e = r.leg("bigone")
    check(e["status"] == "closed" and e.get("unconfirmed") == [t2],
          "abandono: tras 15 min y N lecturas cierra con el ticket apuntado", e)
    check(any("sin confirmar" in m for m in r.kinds("WARNING")), "abandono: WARNING",
          r.kinds("WARNING"))
    check([p.ticket for p in r.br.positions()] == [77], "abandono: la posicion ajena sigue intacta")


def test_aviso_posiciones_sueltas(d):
    """M6: al arrancar se avisa de posiciones del magic que no gestiona ninguna pata."""
    br = E2Broker()
    br._pos.append(FakePos(77, mt5.POSITION_TYPE_BUY, 0.05, 4000.0, TUE * 86400,
                           "manual", MAGIC))
    r = Rig(fresh_path(d, "stray"), br=br)
    r.tick(TUE * 86400 + 5 * H, 4000.0)
    w = r.kinds("WARNING")
    check(len(w) == 1 and "#77" in w[0], "posiciones sueltas: WARNING al arrancar", r.lg.events)
    r.tick(TUE * 86400 + 5 * H + 60, 4000.0)
    check(len(r.kinds("WARNING")) == 1, "posiciones sueltas: throttle horario")


def main():
    config.ALERT_EMAIL_TO = ""
    with tempfile.TemporaryDirectory() as d:
        for fn in (test_bigone_entra_una_vez, test_bigone_omitida_sin_tick,
                   test_mercado_cerrado_reintenta, test_objetivos_cierran_tercios, test_candado, test_candado_fallido_reintenta,
                   test_salida_cierra_todo_con_candado, test_salida_cierre_fallido_reintenta,
                   test_reinicio, test_arranque_tras_salida, test_momentum_umbral,
                   test_nfp_viernes, test_close_all, test_recuperacion_tras_caida,
                   test_estado_corrupto, test_lectura_vacia_no_cierra,
                   test_salida_lectura_vacia, test_close_all_lectura_fallida,
                   test_adp_no_cuenta, test_ejecucion_parcial, test_excepcion_en_tick,
                   test_persistencia_previa_fallida, test_aviso_posiciones_sueltas,
                   test_ticket_sin_confirmar_no_contagia,
                   test_vuelta_tras_salida_lectura_vacia, test_lecturas_vacias_persistentes,
                   test_abandono_legitimo):
            print(f"[{fn.__name__}]")
            try:
                fn(d)
            except Exception as e:  # noqa: BLE001
                import traceback
                traceback.print_exc()
                check(False, f"{fn.__name__} lanzo {type(e).__name__}: {e}")
    print("\n" + "=" * 60)
    if FAILS:
        print("FALLOS (%d): %s" % (len(FAILS), FAILS))
        return 1
    print("TODO OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
