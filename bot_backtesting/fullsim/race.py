"""Carrera hasta el objetivo: desde muchos arranques, ¿el bot duplica la cuenta antes de quemarla?

Para cada fecha de arranque (cada STEP_DAYS dias) se simula el bot (motor REAL del codigo que
este junto a este archivo) con BALANCE hasta que:
  * equity >= TARGET x balance  -> "duplica";
  * equity <= BURN x balance o stop-out -> "quema";
  * pasan MAX_DAYS dias           -> "sin final".
Ademas se registra cada CICLO (de 0 posiciones a 0 posiciones): patas, lotes brutos y netos
maximos, movimiento adverso del precio desde la primera entrada (en $ y en ATR diario), peor
equity dentro del ciclo y duracion. Sirve para ver que ciclos queman la cuenta.
Cada ciclo reparte su cambio de equity en: con exposicion neta (d_open), con neto 0 o
candado (d_lock) y swap (d_swap, incluido en los anteriores); y guarda el equity al llegar
al maximo de patas (eq_cap) para separar lo perdido antes y despues de agotar el rescate.

Uso (desde la raiz del repo, o de un worktree con este archivo copiado):
  python -m bot_backtesting.fullsim.race <etiqueta> [--balance 1000] [--step 7] [--from 2021-03-01]
         [--to 2026-08-15] [--set clave=valor,...] [--workers 3] [--only race_x.pkl:quema]
         [--guard cap,k,u]
Datos: data/bars_all.pkl (entrylab build). FULLSIM_DATA permite apuntar a otra carpeta.
"""
import argparse
import calendar
import datetime as dt
import os
import pickle
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.harness import (DATA, MAGIC_A, RESULTS, SYMBOL_SPECS, Eng, Market, MultiBroker, View,
                                             load_symbol, mt5)

TARGET, BURN, MAX_DAYS = 2.0, 0.30, 120
MAGIC_G = 100999   # guardian (fuera del motor): candado tras agotar el rescate


class Guard:
    """Candado externo al motor (otro magic, el motor no lo gestiona).

    Cuando el ciclo del motor tiene >= `cap` patas y exposicion neta, y el precio se aleja
    `k` ATR diarios mas en contra desde el precio al llegar al tope, abre la cobertura del
    neto (congela la perdida). La suelta cuando el precio vuelve `u` ATR a favor del nivel del
    candado (re-expone el ciclo), y la cierra si el motor queda sin posiciones.
    """

    def __init__(self, br, cap, k, u):
        self.br, self.cap, self.k, self.u = br, cap, k, u
        self.cap_px = None
        self.locks = 0

    def step(self, atr_d):
        br = self.br
        eng = [p for p in br._positions if p.magic == MAGIC_A]
        mine = [p for p in br._positions if p.magic == MAGIC_G]
        if not eng:
            for p in mine:
                br.close_position(p, "Guard Release")
            self.cap_px = None
            return
        net = sum(p.volume if p.type == mt5.POSITION_TYPE_BUY else -p.volume for p in eng)
        px = br.bid()
        if len(eng) >= self.cap and self.cap_px is None:
            self.cap_px = px
        if mine:
            lk = mine[0]
            side = -1 if lk.type == mt5.POSITION_TYPE_BUY else 1          # lado del neto cubierto
            if (px - lk.price_open) * side >= self.u * atr_d:
                br.close_position(lk, "Guard Release")
            return
        if self.cap_px is None or abs(net) < 1e-6 or not atr_d == atr_d:
            return
        side = 1 if net > 0 else -1
        if (self.cap_px - px) * side >= self.k * atr_d:
            br.market_order(mt5.ORDER_TYPE_SELL if side > 0 else mt5.ORDER_TYPE_BUY, round(abs(net), 2), "Guard Lock")
            br._positions[-1].magic = MAGIC_G
            self.locks += 1


def _frames():
    from bot import config
    B = pd.read_pickle(os.path.join(DATA, "bars_all.pkl"))
    return {config.TIMEFRAME_CORE: B["M15"], config.TIMEFRAME_M5: B["M5"], config.TIMEFRAME_STRUCT: B["H4"]}, B["D1"]


def _atr_d1(d1):
    h, l, c = d1.high.values, d1.low.values, d1.close.values
    tr = np.r_[h[0] - l[0], np.maximum(h[1:] - l[1:], np.maximum(abs(h[1:] - c[:-1]), abs(l[1:] - c[:-1])))]
    return pd.Series(pd.Series(tr).rolling(14).mean().values, index=d1.time.values // 86400)


def one_run(args):
    start, balance, params, label = args[:4]
    guard_cfg = args[4] if len(args) > 4 else None
    from bot import strategy
    from bot.logger import Logger
    frames, d1 = _frames()
    atr_d = _atr_d1(d1)
    market = Market(frames)
    log = Logger(enable_file=False, console_print=False)
    br = MultiBroker(market, SYMBOL_SPECS, log, balance, *load_symbol())
    E = Eng(View(br, MAGIC_A), log, market, MAGIC_A)
    E.cfg = {**strategy.DEFAULTS, "news_enforce": False, **params}
    G = Guard(br, *guard_cfg) if guard_cfg else None
    i0 = market.start_index_for(start)
    i1 = market.start_index_for(start + MAX_DAYS * 86400)
    cycles, cur = [], None
    outcome, t_end, min_eq = "sin final", None, balance
    prev_eq, prev_net = balance, 0.0
    for i in range(i0, min(i1, len(market))):
        market.step_to(i)
        sw0 = sum(p.swap for p in br._positions)
        br.apply_swap()
        d_swap = sum(p.swap for p in br._positions) - sw0
        br.process_bar_sl(); br.mark_to_market()
        E.on_tick()
        br.mark_to_market()
        if G is not None:
            G.step(float(atr_d.get(market.current_time // 86400 - 1, np.nan)))
            br.mark_to_market()
        pos = br._positions
        eq = br.account_equity()
        if cur is not None:
            cur["d_open" if abs(prev_net) > 1e-6 else "d_lock"] += eq - prev_eq
            cur["d_swap"] += d_swap
        net_now = sum(p.volume if p.type == mt5.POSITION_TYPE_BUY else -p.volume for p in pos)
        min_eq = min(min_eq, eq)
        now = market.current_time
        if pos and cur is None:
            first = min(pos, key=lambda p: p.time)
            cur = dict(start=now, side=1 if first.type == mt5.POSITION_TYPE_BUY else -1, px0=first.price_open,
                       eq0=eq, legs=0, gross=0.0, net=0.0, adverse=0.0, min_eq=eq,
                       atr_d=float(atr_d.get(now // 86400 - 1, np.nan)),
                       d_open=eq - prev_eq, d_lock=0.0, d_swap=0.0, eq_cap=None, t_cap=None)
        if cur is not None:
            px = br.bid()
            if len(pos) > cur["legs"]:
                cur["eq_cap"], cur["t_cap"] = eq, now
            cur["legs"] = max(cur["legs"], len(pos))
            cur["gross"] = max(cur["gross"], sum(p.volume for p in pos))
            cur["net"] = max(cur["net"], abs(sum(p.volume if p.type == mt5.POSITION_TYPE_BUY else -p.volume for p in pos)))
            cur["adverse"] = max(cur["adverse"], (cur["px0"] - px) * cur["side"])
            cur["min_eq"] = min(cur["min_eq"], eq)
            if not pos:
                cur.update(end=now, eq1=eq, result=eq - cur["eq0"])
                cycles.append(cur); cur = None
        prev_eq, prev_net = eq, net_now
        ml = br.margin_level()
        if eq >= TARGET * balance:
            outcome, t_end = "duplica", now
            break
        if eq <= BURN * balance or (SYMBOL_SPECS.get("stop_out_level") and ml < SYMBOL_SPECS["stop_out_level"]):
            outcome, t_end = "quema", now
            break
    if cur is not None:
        cur.update(end=market.current_time, eq1=br.account_equity(), result=br.account_equity() - cur["eq0"], open=True)
        cycles.append(cur)
    t_end = t_end or market.current_time
    return dict(label=label, start=start, outcome=outcome, days=(t_end - start) / 86400, min_eq=min_eq,
                final=br.account_equity(), cycles=cycles, locks=G.locks if G else 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("label"); ap.add_argument("--balance", type=float, default=1000)
    ap.add_argument("--step", type=int, default=7)
    ap.add_argument("--from", dest="d0", default="2021-03-01"); ap.add_argument("--to", dest="d1", default="2026-08-15")
    ap.add_argument("--set", default=""); ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--guard", default="", help="cap,k,u: candado externo (ver Guard), p.ej. 6,0.5,0.5")
    ap.add_argument("--only", default="", help="race_x.pkl:resultado -> solo los arranques con ese resultado")
    a = ap.parse_args()
    params = {}
    for kv in filter(None, a.set.split(",")):
        k, v = kv.split("=", 1)
        params[k] = v.lower() == "true" if v.lower() in ("true", "false") else (float(v) if v.replace(".", "", 1).lstrip("-").isdigit() else v)
    ep = lambda s: calendar.timegm(dt.datetime.strptime(s, "%Y-%m-%d").timetuple())
    starts = list(range(ep(a.d0), ep(a.d1), a.step * 86400))
    if a.only:
        f, res = a.only.rsplit(":", 1)
        keep = {r["start"] for r in pickle.load(open(os.path.join(RESULTS, f), "rb")) if r["outcome"] == res}
        starts = [s for s in starts if s in keep]
    guard = tuple(float(x) for x in a.guard.split(",")) if a.guard else None
    jobs = [(s, a.balance, params, a.label, guard) for s in starts]
    out = []
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        for r in ex.map(one_run, jobs):
            out.append(r)
            print(a.label, pd.to_datetime(r["start"], unit="s").date(), r["outcome"], round(r["days"], 1),
                  "final", round(r["final"]), flush=True)
    os.makedirs(RESULTS, exist_ok=True)
    pickle.dump(out, open(os.path.join(RESULTS, f"race_{a.label}.pkl"), "wb"))
    o = pd.Series([r["outcome"] for r in out]).value_counts()
    d = pd.Series([r["days"] for r in out if r["outcome"] == "duplica"])
    print("\nRESUMEN", a.label, o.to_dict(), "| dias hasta duplicar: mediana", round(d.median(), 1) if len(d) else None)


if __name__ == "__main__":
    main()
