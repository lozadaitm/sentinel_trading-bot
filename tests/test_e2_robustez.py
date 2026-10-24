"""Motor e2: robustez de la revision final (posiciones huerfanas, calendario viejo,
sin ticks, feriados, cuenta hedging, configuracion, apertura interrumpida...).

Mismo rig que tests/test_e2_engine.py (broker falso, reloj y velas inyectados).

Correr:  python -m tests.test_e2_robustez
"""

import json
import os
import sys
import tempfile

import MetaTrader5 as mt5
import pandas as pd

import bot.strategy_e2 as se
from bot import config, news, sessions
from tests.test_e2_engine import E2Broker, FRI, H, MAGIC, TUE, Rig, fresh_path, opened_bigone
from tests.test_m5_and_budget import FakePos

FAILS = []


def check(cond, name, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  [{detail}]"))
    if not cond:
        FAILS.append(name)


def ep(txt):
    return int(pd.Timestamp(txt).timestamp())


def ladder(br, comment, t, ptype=mt5.POSITION_TYPE_BUY, vol=0.06, price=4000.0, first=11):
    """Tres tercios vivos en el broker con su comentario y hora de apertura."""
    for i in range(3):
        br._pos.append(FakePos(first + i, ptype, vol, price, t, f"{comment} T{i + 1}", MAGIC))
    br._next = max(br._next, first + 10)


# ----------------------------------------------------------------------------- hallazgo 1
def test_guardia_segunda_escalera(d):
    """1a: estado perdido y tercios de la Big One de hoy vivos -> no abre otra escalera."""
    br = E2Broker()
    ladder(br, "E2 BigOne", TUE * 86400 + H + 2)
    r = Rig(fresh_path(d, "guard"), br=br)
    r.eng._next_reconcile = 10 ** 12           # que actue la guardia de la entrada, no la hora
    r.tick(TUE * 86400 + H + 10, 4000.0)
    check(len(br.orders) == 0, "guardia: no se abre una segunda escalera", br.orders)
    e = r.eng.state.legs.get(f"bigone:{TUE}")
    check(e is not None and e.get("adopted") and e["status"] == "open"
          and e["thirds"] == [11, 12, 13], "guardia: los tercios vivos se adoptan", e)
    check(any("NO se abre otra escalera" in m for m in r.kinds("ERROR")),
          "guardia: ERROR registrado", r.kinds("ERROR"))
    r.tick(TUE * 86400 + H + 20, 4000.0)
    check(len(br.orders) == 0, "guardia: el tick siguiente tampoco abre")
    # una posicion de AYER con el mismo comentario no bloquea la entrada de hoy
    br2 = E2Broker()
    ladder(br2, "E2 MomUS", (TUE - 1) * 86400 + 15 * H + 2)
    r2 = Rig(fresh_path(d, "guard2"), br=br2)
    r2.eng._next_reconcile = 10 ** 12
    r2.tick(TUE * 86400 + H + 10, 4000.0)
    check(len([o for o in br2.orders if o["comment"].startswith("E2 BigOne")]) == 3,
          "guardia: posiciones de otra pata/dia no bloquean", br2.orders)


def test_huerfanas_adoptadas(d):
    """1b: posiciones e2 sin pata en el estado -> pata minima adoptada y gestionada."""
    br = E2Broker()
    t0 = TUE * 86400 + H + 3
    ladder(br, "E2 BigOne", t0, price=4000.25)
    r = Rig(fresh_path(d, "orph"), br=br)
    r.tick(TUE * 86400 + 3 * H, 4000.0)
    e = r.eng.state.legs.get(f"bigone:{TUE}")
    check(e is not None and e.get("adopted") and e["entry_epoch"] == t0, "huerfanas: pata adoptada", e)
    check(e and e["exit_epoch"] == TUE * 86400 + 10 * H, "huerfanas: salida 10:00 por la regla", e)
    check(e and e["side"] == "buy" and e["thirds"] == [11, 12, 13], "huerfanas: lado y tercios", e)
    check(e and abs(e["lock_price"] - (4000.25 - 40.0)) < 1e-9 and abs(e["tp"][1] - 4004.25) < 1e-9,
          "huerfanas: candado y objetivos recalculados con ATR", e)
    errs = [m for m in r.kinds("ERROR") if "adoptada" in m]
    check(len(errs) == 1, "huerfanas: un ERROR 'adoptada' por grupo", r.kinds("ERROR"))
    check(not r.kinds("WARNING"), "huerfanas: ya no se avisan como sueltas", r.kinds("WARNING"))
    r.tick(TUE * 86400 + 4 * H, 3960.0)
    locks = [o for o in br.orders if o["comment"] == "E2 Lock BigOne"]
    check(len(locks) == 1 and abs(locks[0]["lots"] - 0.18) < 1e-9, "huerfanas: candado al gatillo", locks)
    r.tick(TUE * 86400 + 10 * H, 3950.0)
    check(not br.positions() and e["status"] == "closed", "huerfanas: cierra todo a la salida",
          br.positions())


def test_huerfanas_salida_pasada(d):
    """1b: huerfanas cuya hora de salida ya paso -> se cierran en el primer tick."""
    br = E2Broker()
    ladder(br, "E2 MomUS", (TUE - 1) * 86400 + 15 * H + 2, ptype=mt5.POSITION_TYPE_SELL)
    br._pos.append(FakePos(30, mt5.POSITION_TYPE_BUY, 0.18, 4040.0, (TUE - 1) * 86400 + 17 * H,
                           "E2 Lock MomUS", MAGIC))
    r = Rig(fresh_path(d, "orphlate"), br=br)
    r.tick(TUE * 86400 + 2 * H, 4000.0)
    check(not br.positions(), "salida pasada: tercios y candado cerrados en el primer tick",
          br.positions())
    e = r.eng.state.legs.get(f"mom:{TUE - 1}")
    check(e is not None and e["status"] == "closed" and e["side"] == "sell",
          "salida pasada: pata de ayer adoptada y cerrada", e)
    check(any("adoptada" in m for m in r.kinds("ERROR")), "salida pasada: ERROR 'adoptada'")


def test_huerfanas_sin_atr(d):
    """1b: sin velas para el ATR -> solo se gestiona la salida (sin candado ni objetivos)."""
    br = E2Broker()
    ladder(br, "E2 BigOne", TUE * 86400 + H + 3)
    r = Rig(fresh_path(d, "orphnoatr"), br=br)
    r.eng._rates_d1 = lambda n: None
    r.tick(TUE * 86400 + 3 * H, 4000.0)
    e = r.eng.state.legs.get(f"bigone:{TUE}")
    check(e and e.get("no_atr") and e["lock_price"] is None and e["tp"] == [None, None, None],
          "sin ATR: pata adoptada sin candado ni objetivos", e)
    r.tick(TUE * 86400 + 4 * H, 3900.0)     # muy por debajo del candado teorico
    r.tick(TUE * 86400 + 4 * H + 5, 4100.0)  # y por encima de los objetivos
    check(len(br.orders) == 0 and len(br.positions()) == 3, "sin ATR: no pone candado ni cierra TP",
          br.orders)
    check(any("solo se gestiona la salida" in m for m in r.kinds("ERROR")), "sin ATR: lo dice el log")
    r.tick(TUE * 86400 + 10 * H, 4000.0)
    check(not br.positions(), "sin ATR: cierra a la salida")


def test_huerfanas_con_candado_y_dias(d):
    """1b: dos grupos (dos dias) y uno con candado -> dos patas, la del candado 'locked'."""
    br = E2Broker()
    ladder(br, "E2 NFP", FRI * 86400 + 16 * H + 32 * 60, ptype=mt5.POSITION_TYPE_SELL, first=11)
    br._pos.append(FakePos(20, mt5.POSITION_TYPE_BUY, 0.18, 4040.0, FRI * 86400 + 18 * H,
                           "E2 Lock NFP", MAGIC))
    ladder(br, "E2 BigOne", (FRI + 3) * 86400 + H + 2, first=31)   # lunes
    r = Rig(fresh_path(d, "orph2"), br=br)
    r.tick((FRI + 3) * 86400 + 2 * H, 4000.0)
    nfp = r.eng.state.legs.get(f"nfp:{FRI}")
    big = r.eng.state.legs.get(f"bigone:{FRI + 3}")
    check(nfp and nfp["status"] == "locked" and nfp["locks"] == [[20, 0.18]],
          "dos grupos: NFP adoptada como locked", nfp)
    check(nfp and nfp["exit_epoch"] == sessions.exit_epoch("nfp", FRI * 86400 + 16 * H + 32 * 60),
          "dos grupos: salida NFP por 96 velas de mercado", nfp)
    check(big and big["status"] == "open" and big["thirds"] == [31, 32, 33], "dos grupos: Big One", big)
    check(len([m for m in r.kinds("ERROR") if "adoptada" in m]) == 2, "dos grupos: un ERROR por grupo")
    check(len(br.orders) == 0, "dos grupos: no abre nada", br.orders)


# ----------------------------------------------------------------------------- hallazgo 4
def _cal_rig(d, name, generated_at_rel, day, events):
    path = os.path.join(d, name, "cal.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    r = Rig(fresh_path(d, name), day=day, events=events,
            opens={e["time"] // 900 * 900 - 900: 4000.0 for e in events})
    del r.eng._calendar_status                # el real, contra NewsGuard
    del r.eng._events
    r.eng.news = news.NewsGuard(path, r.lg)
    r._calpath, r._calrel, r._calev = path, generated_at_rel, events
    return r


def _write_cal(r, now):
    with open(r._calpath, "w", encoding="utf-8") as f:
        json.dump({"generated_at": now + r._calrel, "events": r._calev}, f)
    r.eng.news._next_load_check = 0


def test_calendario_viejo(d):
    T = FRI * 86400 + 15 * H + 30 * 60
    ev = [{"time": T, "name": "Non-Farm Employment Change", "currency": "USD", "importance": "high"},
          {"time": FRI * 86400 + 20 * H, "name": "Otro", "currency": "USD", "importance": "low"}]
    # fresco: la NFP entra y la Big One va a peso de evento
    r = _cal_rig(d, "calok", -600, FRI, ev)
    _write_cal(r, FRI * 86400 + H + 5)
    r.tick(FRI * 86400 + H + 5, 4000.0)
    _write_cal(r, T + 3600 + 3)
    r.tick(T + 3600 + 3, 3990.0)
    check(len([o for o in r.br.orders if o["comment"].startswith("E2 NFP")]) == 3,
          "calendario fresco: la NFP entra", r.br.orders)
    check(not [m for m in r.kinds("ERROR") if "calendario" in m.lower()], "calendario fresco: sin ERROR")
    # viejo (7 h): NFP omitida, Big One a peso reducido, ERROR con throttle
    r2 = _cal_rig(d, "calold", -7 * 3600, FRI, ev)
    _write_cal(r2, FRI * 86400 + H + 5)
    r2.tick(FRI * 86400 + H + 5, 4000.0)
    big = [o for o in r2.br.orders if o["comment"].startswith("E2 BigOne")]
    check([o["lots"] for o in big] == sessions.ladder_lots(10000.0, 0.08, 0.5, 40.0),
          "calendario viejo: Big One a peso de dia de evento (x0,5)", big)
    r2.tick(T + 3600 + 3, 3990.0)
    check(not [o for o in r2.br.orders if o["comment"].startswith("E2 NFP")],
          "calendario viejo: la NFP NO entra", r2.br.orders)
    errs = [m for m in r2.kinds("ERROR") if "calendario de noticias NO fiable" in m]
    check(len(errs) >= 1 and "h" in errs[0], "calendario viejo: ERROR con el motivo", r2.kinds("ERROR"))
    n = len(errs)
    r2.tick(T + 3600 + 10, 3990.0)
    check(len([m for m in r2.kinds("ERROR") if "NO fiable" in m]) == n, "calendario viejo: throttle")
    # fresco pero sin cubrir hoy (eventos de otra semana)
    r3 = _cal_rig(d, "calcover", -600, FRI,
                  [dict(ev[0], time=T - 7 * 86400)])
    _write_cal(r3, FRI * 86400 + H + 5)
    r3.tick(FRI * 86400 + H + 5, 4000.0)
    check(any("no cubre" in m for m in r3.kinds("ERROR")), "calendario que no cubre hoy: ERROR",
          r3.kinds("ERROR"))


# ----------------------------------------------------------------------------- hallazgo 5
def test_sin_ticks(d):
    r = Rig(fresh_path(d, "notick"))
    r.eng._fetch_tick = lambda: None
    r.wall = 1000.0
    r.eng.on_tick()
    r.wall = 1059.0
    r.eng.on_tick()
    check(not r.kinds("ERROR"), "sin ticks: nada antes de 60 s")
    r.wall = 1061.0
    r.eng.on_tick()
    check(len([m for m in r.kinds("ERROR") if "ningun tick" in m]) == 1, "sin ticks: ERROR a los 60 s",
          r.lg.events)
    r.wall = 1300.0
    r.eng.on_tick()
    check(len(r.kinds("ERROR")) == 1, "sin ticks: throttle por reloj local (no por el servidor)")
    r.wall = 1061.0 + 601
    r.eng.on_tick()
    check(len(r.kinds("ERROR")) == 2, "sin ticks: se repite a los 10 min de reloj")
    # tick congelado en horario de mercado
    r2 = Rig(fresh_path(d, "frozen"))
    r2.wall = 0.0
    r2.tick(TUE * 86400 + 5 * H, 4000.0)
    r2.wall = 61.0
    r2.tick(TUE * 86400 + 5 * H, 4000.0)
    check(len([m for m in r2.kinds("ERROR") if "tick nuevo" in m]) == 1,
          "tick congelado en mercado: ERROR", r2.lg.events)
    # fin de semana: el ultimo tick del viernes congelado no es un error
    r3 = Rig(fresh_path(d, "weekend"), day=FRI)
    r3.wall = 0.0
    r3.tick(FRI * 86400 + 23 * H + 59 * 60, 4000.0)
    r3.wall = 3600.0
    r3.tick(FRI * 86400 + 23 * H + 59 * 60, 4000.0)
    check(not [m for m in r3.kinds("ERROR") if "tick" in m], "fin de semana: sin ERROR", r3.lg.events)


# ----------------------------------------------------------------------------- hallazgo 6
def _mom_rig(d, name, day):
    r = Rig(fresh_path(d, name), day=day, opens={day * 86400 + H: 4000.0})
    r.eng.cfg = {"e2_legs": "mom"}
    return r


def test_feriados(d):
    for txt in ("2026-11-27", "2026-07-03", "2026-06-19", "2026-12-24", "2026-12-31"):
        day = ep(txt) // 86400
        r = _mom_rig(d, f"hol{txt}", day)
        r.tick(day * 86400 + 15 * H + 2, 4010.0)
        r.tick(day * 86400 + 15 * H + 30, 4010.0)
        e = r.eng.state.legs.get(f"mom:{day}")
        om = [m for m in r.kinds("OMITIDA") if "feriado" in m]
        check(not r.br.orders and e and e["status"] == "skipped" and len(om) == 1,
              f"feriado {txt}: Momentum no entra (OMITIDA una vez)", (r.br.orders, om))
    day = ep("2026-11-24") // 86400
    r = _mom_rig(d, "normal", day)
    r.tick(day * 86400 + 15 * H + 2, 4010.0)
    check(len(r.br.orders) == 3, "dia normal 2026-11-24: Momentum entra", r.br.orders)
    # la Big One no se ve afectada
    day = ep("2026-11-27") // 86400
    r = Rig(fresh_path(d, "holbig"), day=day)
    r.tick(day * 86400 + H + 5, 4000.0)
    check(len(r.br.orders) == 3, "feriado: la Big One entra igual", r.br.orders)
    # NFP en feriado y NFP cuya salida cae en feriado despues de las 19:45
    for txt, hhmm, expect, label in (("2026-07-03", "15:30", 0, "NFP el dia feriado"),
                                     ("2026-11-25", "19:00", 0, "NFP con salida jue 20:00 feriado"),
                                     ("2026-11-25", "15:30", 3, "NFP con salida jue 16:30 (antes 19:45)")):
        day = ep(txt) // 86400
        T = ep(f"{txt} {hhmm}")
        evs = [{"time": T, "name": "Non-Farm Employment Change", "currency": "USD",
                "importance": "high"}]
        r = Rig(fresh_path(d, f"nfp{txt}{hhmm}".replace(":", "")), day=day, events=evs,
                opens={T - 900: 4000.0})
        r.eng.cfg = {"e2_legs": "nfp"}
        r.tick(T + 3600 + 3, 3990.0)
        check(len(r.br.orders) == expect, f"{label}: {expect} ordenes", (r.br.orders, r.kinds("OMITIDA")))


# ----------------------------------------------------------------------------- hallazgo 11
def test_cuenta_no_hedging(d):
    br = E2Broker()
    br.hedging = False
    r = Rig(fresh_path(d, "netting"), br=br)
    r.tick(TUE * 86400 + H + 5, 4000.0)
    check(not br.orders, "netting: no se abren entradas", br.orders)
    check(any("NO es hedging" in m for m in r.kinds("ERROR")), "netting: ERROR", r.kinds("ERROR"))
    br2 = E2Broker()
    br2.hedging = None
    r2 = Rig(fresh_path(d, "hedgeunk"), br=br2)
    r2.tick(TUE * 86400 + H + 5, 4000.0)
    check(not br2.orders, "modo desconocido: no se abren entradas")
    br2.hedging = True
    r2.tick(TUE * 86400 + H + 10, 4000.0)
    check(len(br2.orders) == 3, "modo confirmado despues: entra dentro de la ventana", br2.orders)


# ----------------------------------------------------------------------------- hallazgo 3
def test_config_coercion(d):
    r = Rig(fresh_path(d, "cfg"))
    eng = r.eng
    eng.cfg = {"e2_risk_pct": None, "e2_entry_grace_s": "90", "e2_tp_atr15_mults": "2.5,3.5",
               "e2_lock_atrd_mult": "1.5", "e2_legs": None, "e2_nfp_hold_bars": 96.0,
               "e2_mom_threshold_pct": "basura"}
    check(eng._p("e2_risk_pct") == 0.08, "cfg: NULL -> default")
    check(eng._p("e2_entry_grace_s") == 90 and isinstance(eng._p("e2_entry_grace_s"), int),
          "cfg: '90' -> int 90")
    check(eng._p("e2_tp_atr15_mults") == (2.5, 3.5), "cfg: '2.5,3.5' -> (2.5, 3.5)")
    check(eng._p("e2_lock_atrd_mult") == 1.5, "cfg: '1.5' -> float")
    check(eng._p("e2_legs") == "bigone,mom,nfp", "cfg: e2_legs NULL -> default")
    check(eng._p("e2_nfp_hold_bars") == 96, "cfg: 96.0 -> 96")
    check(eng._p("e2_mom_threshold_pct") == 0.232, "cfg: invalido -> default")
    for v, exp in (("{2,3}", (2.0, 3.0)), ([2, 4], (2.0, 4.0)), ("x", (2.0, 3.0)),
                   ("2,3,4", (2.0, 3.0)), ("-1,3", (2.0, 3.0))):
        eng.cfg = {"e2_tp_atr15_mults": v}
        check(eng._p("e2_tp_atr15_mults") == exp, f"cfg: tp {v!r} -> {exp}")
    check(se.SessionEngine.runs_without_cfg is True, "SessionEngine.runs_without_cfg")
    eng.cfg = {}
    r.tick(TUE * 86400 + H + 5, 4000.0)
    check(len(r.br.orders) == 3, "cfg vacia: opera con DEFAULTS")


# ----------------------------------------------------------------------------- hallazgo 7
def test_pata_malformada(d):
    path = fresh_path(d, "badleg")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    br = E2Broker()
    ladder(br, "E2 BigOne", TUE * 86400 + H + 5)
    good = {"leg": "bigone", "side": "buy", "entry_epoch": TUE * 86400 + H + 5,
            "exit_epoch": TUE * 86400 + 10 * H, "entry_price": 4000.0, "atr_d": 40.0, "atr15": 2.0,
            "lock_price": 3960.0, "tp": [None, 4004.0, 4006.0], "thirds": [11, 12, 13],
            "closed_thirds": [], "lock_ticket": None, "status": "open"}
    bad = {"leg": "mom", "entry_epoch": (TUE - 1) * 86400 + 15 * H, "status": "open"}  # sin exit/thirds
    with open(path, "w", encoding="utf-8") as f:
        json.dump({f"mom:{TUE - 1}": bad, f"bigone:{TUE}": good}, f)
    r = Rig(path, br=br)
    r.tick(TUE * 86400 + 10 * H, 4000.0)
    check(not br.positions() and r.eng.state.legs[f"bigone:{TUE}"]["status"] == "closed",
          "pata malformada: las demas se siguen gestionando", br.positions())
    check(any("error gestionando la pata mom" in m for m in r.kinds("ERROR")),
          "pata malformada: ERROR con throttle", r.kinds("ERROR"))


# ----------------------------------------------------------------------------- hallazgo 8
def test_apertura_interrumpida_regla(d):
    path = fresh_path(d, "openrule")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    br = E2Broker()
    br._pos.append(FakePos(77, mt5.POSITION_TYPE_BUY, 0.05, 4000.0, TUE * 86400, "manual", MAGIC))
    opening = {"leg": "bigone", "side": "buy", "entry_epoch": TUE * 86400 + H + 5,
               "exit_epoch": TUE * 86400 + 10 * H, "entry_price": None, "atr_d": 40.0,
               "atr15": 2.0, "lots": [0.06] * 3, "lock_price": None, "tp": [None] * 3,
               "thirds": [None] * 3, "closed_thirds": [], "lock_ticket": None, "status": "opening"}
    with open(path, "w", encoding="utf-8") as f:
        json.dump({f"bigone:{TUE}": opening}, f)
    r = Rig(path, br=br)
    t = TUE * 86400 + H + 30
    for k in range(8):                          # 8 lecturas no vacias en 8 s
        r.tick(t + k, 4000.0)
    check(r.eng.state.legs[f"bigone:{TUE}"]["status"] == "opening",
          "apertura: 8 lecturas en segundos no bastan (falta el tiempo)")
    # otra pata 'opening': 2 lecturas no vacias y luego 20 min de lecturas vacias
    path2 = fresh_path(d, "openrule2")
    os.makedirs(os.path.dirname(path2), exist_ok=True)
    with open(path2, "w", encoding="utf-8") as f:
        json.dump({f"bigone:{TUE}": opening}, f)
    r2 = Rig(path2, br=br)
    r2.tick(t, 4000.0)
    r2.tick(t + 1, 4000.0)
    br.empty_reads = 10 ** 6
    for m in range(1, 21):
        r2.tick(t + 60 * m, 4000.0)
    br.empty_reads = 0
    st = r2.eng.state.legs[f"bigone:{TUE}"]
    check(st["status"] == "opening", "apertura: lecturas vacias no cuentan", st)
    for k in range(3):
        r2.tick(t + 60 * 21 + k, 4000.0)
    check(st["status"] == "skipped", "apertura: N lecturas no vacias + 15 min -> omitida", st)
    # sin ninguna lectura no vacia: pasada la salida + 15 min se abandona igual
    br3 = E2Broker()
    path3 = fresh_path(d, "openrule3")
    os.makedirs(os.path.dirname(path3), exist_ok=True)
    with open(path3, "w", encoding="utf-8") as f:
        json.dump({f"bigone:{TUE}": opening}, f)
    r3 = Rig(path3, br=br3)
    r3.tick(TUE * 86400 + 5 * H, 4000.0)
    r3.tick(TUE * 86400 + 10 * H + 16 * 60, 4000.0)
    check(r3.eng.state.legs[f"bigone:{TUE}"]["status"] == "skipped",
          "apertura: cuenta plana, pasada la salida + 15 min -> omitida")


# ----------------------------------------------------------------------------- hallazgos 9/10
def test_tercio_sin_respuesta(d):
    br = E2Broker()
    br.none_result["E2 BigOne T2"] = 1
    r = Rig(fresh_path(d, "noresp"), br=br)
    r.tick(TUE * 86400 + H + 5, 4000.0)
    e = r.leg("bigone")
    check(e["thirds"][1] is None and len(br.positions()) == 3, "sin respuesta: T2 entro sin ticket")
    r.tick(TUE * 86400 + H + 6, 4000.0)
    check(e["thirds"][1] is not None, "sin respuesta: T2 adoptado en su hueco al tick siguiente", e)
    check(any("no confirmo" in m for m in r.kinds("WARNING")), "sin respuesta: WARNING")
    r.tick(TUE * 86400 + 2 * H, 3960.0)
    lk = [o for o in br.orders if o["comment"] == "E2 Lock BigOne"]
    check(lk and abs(lk[0]["lots"] - 0.18) < 1e-9, "sin respuesta: el candado cubre los 3 tercios", lk)
    # duplicado (comentario de tercio sin hueco libre) -> cuenta para el candado y la salida
    br2 = E2Broker()
    r2 = Rig(fresh_path(d, "dupthird"), br=br2)
    r2.tick(TUE * 86400 + H + 5, 4000.0)
    br2._pos.append(FakePos(99, mt5.POSITION_TYPE_BUY, 0.06, 4000.0, TUE * 86400 + H + 6,
                            "E2 BigOne T1", MAGIC))
    r2.tick(TUE * 86400 + 2 * H, 3960.0)
    lk = [o for o in br2.orders if o["comment"] == "E2 Lock BigOne"]
    check(lk and abs(lk[0]["lots"] - 0.24) < 1e-9, "duplicado: el candado incluye el tercio extra", lk)
    r2.tick(TUE * 86400 + 10 * H, 3960.0)
    check(not br2.positions(), "duplicado: la salida lo cierra")


def test_candado_excedente(d):
    r = opened_bigone(d, "excess")
    r.tick(TUE * 86400 + 2 * H, 3960.0)
    t1 = r.leg("bigone")["thirds"][0]
    r.br.external_close(t1)
    r.tick(TUE * 86400 + 2 * H + 10, 3960.0)
    r.tick(TUE * 86400 + 2 * H + 20, 3960.0)
    w = [m for m in r.kinds("WARNING") if "Candado BigOne: cubre" in m]
    check(len(w) == 1 and "0.18" in w[0] and "0.12" in w[0], "candado excedente: WARNING una vez", w)


# ----------------------------------------------------------------------------- triage M3
def test_deslizamiento_por_tercio(d):
    r = Rig(fresh_path(d, "slip"))
    prices = iter([4000.0, 4000.5, 4001.0, 4001.5])
    base = r.eng._fetch_tick

    def moving():
        t = base()
        try:
            r.br._price = next(prices)
        except StopIteration:
            pass
        t.bid, t.ask = r.br._price, r.br._price + 0.25
        return t
    r.eng._fetch_tick = moving
    r.tick(TUE * 86400 + H + 5, 4000.0)
    lines = [m for m in r.kinds("SYSTEM") if "ejecutada" in m]
    check(len(lines) == 3 and all(w in lines[0] for w in ("ref", "fill", "deslizamiento", "spread")),
          "deslizamiento: una linea por tercio con ref/fill/desliz/spread", lines)
    check("ref 4000.75" in lines[0] and "ref 4001.25" in lines[1] and "ref 4001.75" in lines[2],
          "deslizamiento: tick fresco antes de cada orden", lines)


def main():
    config.ALERT_EMAIL_TO = ""
    with tempfile.TemporaryDirectory() as d:
        for fn in (test_guardia_segunda_escalera, test_huerfanas_adoptadas,
                   test_huerfanas_salida_pasada, test_huerfanas_sin_atr,
                   test_huerfanas_con_candado_y_dias, test_calendario_viejo, test_sin_ticks,
                   test_feriados, test_cuenta_no_hedging, test_config_coercion,
                   test_pata_malformada, test_apertura_interrumpida_regla,
                   test_tercio_sin_respuesta, test_candado_excedente,
                   test_deslizamiento_por_tercio):
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
