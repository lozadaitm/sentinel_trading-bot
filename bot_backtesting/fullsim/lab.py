"""Laboratorio de variantes sobre el ciclo completo (motor REAL).

Uso (desde la raiz del repo):
  python -m bot_backtesting.fullsim.lab <modo> <balance> [--sig dc20] [--f 0.5]
         [--set clave=valor,clave2=valor2] [--ms] [--start 2026-03-01 --end 2026-10-17]
         [--frames frames.pkl]

  modo:
    actual    : el bot tal cual (bot/strategy.py + DEFAULTS + --set)
    suave     : la Op4 (T) solo abre con senal de mercado a favor de su lado
    completa  : suave + cierra la Op4 cuando la senal se da vuelta
    dir       : completa + "Op5" del MISMO lado que la recovery (f x su volumen) con
                senal a favor de la recovery; aumenta la exposicion
  --sig : dc20 / dc48 (ruptura de maximo/minimo de N velas M15), ema (EMA20 vs EMA50 M15),
          h4 (estructura H4 del bot). Solo para suave/completa/dir.
  --set : sobreescribe parametros de DEFAULTS (p. ej. healer_pair_order=recovery_first).
  --ms  : ventanas de 30 dias que arrancan cada 14 dias, sin posiciones al inicio.

Salida: una linea FULL/MS por consola y el pickle en results/.
Resultados de referencia: docs/experimento-2/analisis-op4-criterio-propio-2026-10-19.md
(alli 'actual' + healer_pair_order=cover_first es el bot desde el 20-oct).
"""
import argparse
import calendar
import datetime as dt
import math
import os
import pickle

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.harness import (MAGIC_A, RESULTS, SYMBOL_SPECS, Eng, Market, MultiBroker, View,
                                             frozen, load_frames, load_symbol, mt5)
from bot import ledger, strategy, survival
from bot.logger import Logger
from bot.strategy import LOCK_FREE, OP4_TREND_COMMENT

OP5 = OP4_TREND_COMMENT + " R"   # prefijo de Op4 (T): hereda su trailing


class Lab(Eng):
    mode, sig, f = "actual", "dc20", 0.5

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._state = 0
        self.n_op4 = self.n_op5 = self.n_sigclose = 0

    def _signal(self):
        """(estado, evento) en la ultima vela M15 cerrada: +1 alcista / -1 bajista."""
        df = self.df_m15
        c, h, l = df["close"].values, df["high"].values, df["low"].values
        if self.sig.startswith("dc"):
            n = int(self.sig[2:])
            if len(c) < n + 3:
                return self._state, 0
            ev = 1 if c[-2] > h[-(n + 2):-2].max() else (-1 if c[-2] < l[-(n + 2):-2].min() else 0)
            if ev:
                self._state = ev
            return self._state, ev
        if self.sig == "ema":
            s = pd.Series(c[:-1])
            e20, e50 = s.ewm(span=20, adjust=False).mean().values, s.ewm(span=50, adjust=False).mean().values
            st = 1 if e20[-1] > e50[-1] else -1
            prev = 1 if e20[-2] > e50[-2] else -1
            return st, (st if st != prev else 0)
        if self.sig == "h4":
            st = int(np.sign(self.struct_h4))
            ev = st if st != self._state else 0
            self._state = st
            return st, ev
        raise ValueError(self.sig)

    def _check_rescue_trend(self, positions):
        if self.mode == "actual":
            n0 = int(self.cycle.get_meta("rescue_opened", 0))
            super()._check_rescue_trend(positions)
            self.n_op4 += int(self.cycle.get_meta("rescue_opened", 0)) - n0
            return
        if self.spread_high or self.vol_breaker or self.close_only or self.news_block:
            return
        if len(positions) < 3 or self.lock_state != LOCK_FREE:
            return
        df = self.df_m15
        if df is None or len(df) < 2:
            return
        bar_t = df["time"].iloc[-2]
        if bar_t == self._op4t_bar:
            return
        self._op4t_bar = bar_t
        st, ev = self._signal()
        close1 = float(df["close"].iloc[-2])
        atr = self._effective_atr()
        k = float(self._p("rescue_trend_k_atr"))
        frozen_t = self.cycle.pair_members(positions) | {p.ticket for p in self.cycle.lock_legs(positions)}
        roles = (ledger.ROLE_RECOVERY, ledger.ROLE_RESCUE)
        trend = [p for p in positions if self._is_trend_op4(p)]
        target, worst = None, 0.0
        for p in positions:
            if p.ticket in frozen_t or self.cycle.role_of(p.ticket) not in roles or p in trend:
                continue
            loss = (p.price_open - close1) if p.type == mt5.POSITION_TYPE_BUY else (close1 - p.price_open)
            if loss >= k * atr - 1e-9 and loss > worst:
                target, worst = p, loss
        op4_side = None if target is None else (1 if target.type == mt5.POSITION_TYPE_SELL else -1)
        if self.mode in ("completa", "dir"):
            for p in trend:
                if st == -(1 if p.type == mt5.POSITION_TYPE_BUY else -1):
                    self.b.close_position(p, "Op4 senal")
                    self.n_sigclose += 1
            trend = [p for p in self.b.positions() if self._is_trend_op4(p)]
        if trend or target is None:
            return
        net = survival.net_lots(self.b.positions())
        step = self.b.volume_step()
        hit = (lambda side: ev == side) if self.sig.startswith("dc") else (lambda side: st == side)
        if hit(op4_side):
            if (op4_side == 1 and net >= 0) or (op4_side == -1 and net <= 0):
                return
            lots = round(math.floor(min(target.volume, abs(net)) / step + 1e-9) * step, 8)
            if lots >= self.b.volume_min() - 1e-9:
                otype = mt5.ORDER_TYPE_BUY if op4_side == 1 else mt5.ORDER_TYPE_SELL
                if self._open_additive(otype, lots, OP4_TREND_COMMENT, ledger.ROLE_RESCUE, "Op4 tendencia"):
                    self.n_op4 += 1
            return
        if self.mode == "dir" and hit(-op4_side):
            lots = round(math.floor(self.f * target.volume / step + 1e-9) * step, 8)
            if lots >= self.b.volume_min() - 1e-9:
                otype = mt5.ORDER_TYPE_SELL if op4_side == 1 else mt5.ORDER_TYPE_BUY
                res = self.b.market_order(otype, lots, OP5)   # sin tope de supervivencia: a proposito
                if self._register_open(res, ledger.ROLE_RESCUE):
                    self.n_op5 += 1


def run(a, frames, params, swap, start, end):
    market = Market(frames)
    log = Logger(enable_file=False, console_print=False)
    br = MultiBroker(market, SYMBOL_SPECS, log, a.balance, *swap)
    E = Lab(View(br, MAGIC_A), log, market, MAGIC_A)
    E.mode, E.sig, E.f = a.mode, a.sig, a.f
    E.cfg = dict(params)
    i0, i1 = market.start_index_for(start), market.start_index_for(end)
    peak, max_dd, min_eq, min_ml, blown, frozen_bars = a.balance, 0.0, a.balance, float("inf"), False, 0
    curve = []
    for i in range(i0, min(i1, len(market))):
        market.step_to(i)
        br.apply_swap(); br.process_bar_sl(); br.mark_to_market()
        E.on_tick()
        br.mark_to_market()
        frozen_bars += frozen(E)
        eq = br.account_equity()
        peak = max(peak, eq); max_dd = max(max_dd, (peak - eq) / peak); min_eq = min(min_eq, eq)
        ml = br.margin_level(); min_ml = min(min_ml, ml)
        if SYMBOL_SPECS.get("stop_out_level") and ml < SYMBOL_SPECS["stop_out_level"]:
            br.liquidate("StopOut"); blown = True
            break
        if i % 96 == 0:
            curve.append((market.current_time, eq))
    eq = br.account_equity()
    return dict(final=eq, ret=eq / a.balance - 1, max_dd=max_dd, min_eq=min_eq, min_ml=min_ml, blown=blown,
                frozen_days=frozen_bars / 96, n_op4=E.n_op4, n_op5=E.n_op5, n_sigclose=E.n_sigclose,
                open_end=len(br._positions), float_end=sum(p.profit + p.swap for p in br._positions),
                curve=curve, trades=br.closed_trades)


def _parse_set(text):
    out = {}
    for kv in filter(None, text.split(",")):
        k, v = kv.split("=", 1)
        if v.lower() in ("true", "false"):
            out[k] = v.lower() == "true"
        else:
            try:
                out[k] = float(v)
            except ValueError:
                out[k] = v
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("actual", "suave", "completa", "dir"))
    ap.add_argument("balance", type=float)
    ap.add_argument("--sig", default="dc20"); ap.add_argument("--f", type=float, default=0.5)
    ap.add_argument("--set", default=""); ap.add_argument("--ms", action="store_true")
    ap.add_argument("--start", default="2026-03-01"); ap.add_argument("--end", default="2026-10-17")
    ap.add_argument("--frames", default="frames.pkl")
    a = ap.parse_args()
    frames = load_frames(a.frames)
    params = {**strategy.DEFAULTS, "news_enforce": False, **_parse_set(a.set)}
    swap = load_symbol()
    ep = lambda d: calendar.timegm(d.timetuple())
    tag = f"{a.mode}{'_' + a.sig if a.mode != 'actual' else ''}{'_f' + str(a.f) if a.mode == 'dir' else ''}" \
          f"{'_' + a.set.replace('=', '').replace(',', '_') if a.set else ''}_{int(a.balance)}"
    os.makedirs(RESULTS, exist_ok=True)
    d0, d1 = dt.datetime.strptime(a.start, "%Y-%m-%d"), dt.datetime.strptime(a.end, "%Y-%m-%d")
    if a.ms:
        out = []
        while d0 + dt.timedelta(days=30) <= d1:
            r = run(a, frames, params, swap, ep(d0), ep(d0 + dt.timedelta(days=30)))
            r.pop("trades"); r["start"] = d0.date(); out.append(r)
            d0 += dt.timedelta(days=14)
        pickle.dump(out, open(os.path.join(RESULTS, f"lab_ms_{tag}.pkl"), "wb"))
        rets = [x["ret"] for x in out]
        print("MS", tag, "media", round(np.mean(rets) * 100, 2), "peor", round(min(rets) * 100, 2),
              "peorDD", round(max(x["max_dd"] for x in out) * 100, 1), "quemadas", sum(x["blown"] for x in out))
    else:
        r = run(a, frames, params, swap, ep(d0), ep(d1))
        pickle.dump(r, open(os.path.join(RESULTS, f"lab_full_{tag}.pkl"), "wb"))
        print("FULL", tag, "final", round(r["final"]), "ret", round(r["ret"] * 100, 1),
              "maxDD", round(r["max_dd"] * 100, 1), "minEq", round(r["min_eq"]), "blown", r["blown"],
              "congelado_dias", round(r["frozen_days"], 1), "op4", r["n_op4"], "op5", r["n_op5"],
              "cierres_senal", r["n_sigclose"])


if __name__ == "__main__":
    main()
