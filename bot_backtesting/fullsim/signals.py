"""Senales de OP1 con el motor REAL (compuertas del ESTADO 0) y su desenlace sin ciclo.

El motor nunca abre: se registra cada vela M15 en que abriria y se simula la OP1 sola en
M5 hasta WIN (el trailing de cesta la cerraria en verde) o HEDGE (llega a la distancia de
cobertura: max(8 $, 2 ATR)). Aproximado: spread 0,20 $ y comision 0,12 $/oz constantes.

Uso: python -m bot_backtesting.fullsim.signals <frames.pkl> <desde> <hasta> <salida.pkl>
     (frames y salida dentro de data/), p. ej.  frames_duka.pkl 2021-01-15 2026-01-09 sig_duka.pkl
"""
import calendar
import datetime as dt
import os
import sys

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.harness import DATA, MAGIC_A, SYMBOL_SPECS, Eng, Market, MultiBroker, View, \
    load_frames, load_symbol, mt5
from bot import config, strategy
from bot.logger import Logger

SPREAD, COMM = 0.20, 0.12


class Scan(Eng):
    sig = None

    def _open_entry(self, order_type, lots, comment, label):
        side = 1 if order_type == mt5.ORDER_TYPE_BUY else -1
        level, n, dist_atr = self._reentry_info(side)
        self.sig.append(dict(t=self.now, side=side, px=self.b.ask() if side == 1 else self.b.bid(),
                             atr=self._effective_atr(), ema=self.ema0, rsi=self.rsi0, h4=self.struct_h4,
                             level=level, n=n, dist_lvl_atr=dist_atr))
        return False


def scan(frames_name, d0, d1):
    frames = load_frames(frames_name)
    ep = lambda s: calendar.timegm(dt.datetime.strptime(s, "%Y-%m-%d").timetuple())
    market = Market(frames)
    log = Logger(enable_file=False, console_print=False)
    br = MultiBroker(market, SYMBOL_SPECS, log, 10000, *load_symbol())
    E = Scan(View(br, MAGIC_A), log, market, MAGIC_A)
    E.cfg = {**strategy.DEFAULTS, "news_enforce": False}
    E.sig = []
    for i in range(market.start_index_for(ep(d0)), market.start_index_for(ep(d1))):
        market.step_to(i); br.mark_to_market(); E.on_tick()
    S = pd.DataFrame(E.sig)
    m5 = frames[config.TIMEFRAME_M5]
    T5, H5, L5 = m5.time.values, m5.high.values, m5.low.values
    out = []
    for r in S.itertuples():
        a = r.atr
        hd = max(8.0, 2.0 * a)                       # distancia de cobertura
        rtr = min(max(0.1 * a, 0.11), 5.6)           # retroceso dinamico de la cesta
        need = max(0.83 + COMM, 0.33 + COMM + rtr)   # pico necesario para cerrar en verde
        k = np.searchsorted(T5, r.t)
        res, mfe, mae, bars = "OPEN", 0.0, 0.0, 0
        for j in range(k, min(k + 288 * 10, len(T5))):
            if r.side == 1:
                fav = (H5[j] - SPREAD) - r.px; adv = r.px - L5[j]
            else:
                fav = r.px - (L5[j] + SPREAD); adv = (H5[j] + SPREAD) - r.px
            mae = max(mae, adv)
            if adv >= hd:
                res, bars = "HEDGE", j - k
                break
            mfe = max(mfe, fav)
            if mfe >= need:
                res, bars = "WIN", j - k
                break
        out.append(dict(res=res, mfe=mfe, mae=mae, bars=bars, hd=hd, win_val=need - rtr - COMM))
    S = pd.concat([S, pd.DataFrame(out)], axis=1)
    S["first"] = (S.t.diff() != 900) | (S.side != S.side.shift())   # primera vela de cada racha
    return S


if __name__ == "__main__":
    fr, d0, d1, outname = sys.argv[1:5]
    S = scan(fr, d0, d1)
    S.to_pickle(os.path.join(DATA, outname))
    print("velas con senal:", len(S))
    print(S.groupby("first").res.value_counts().unstack())
