"""Velas M1 del broker construidas desde los ticks guardados (data/ticks/XAUUSD+/*.pkl.gz).

OHLC sobre el bid (como las velas de MT5), spread medio y maximo del minuto (ask - bid, $/oz) y
numero de ticks. Hora = servidor (NY+7). Salida: data/broker_m1_ticks.pkl.
Uso: python -m bot_backtesting.fullsim.build_m1
"""
import glob
import os

import numpy as np
import pandas as pd

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def main():
    out = []
    for f in sorted(glob.glob(os.path.join(D, "ticks", "XAUUSD+", "*.pkl.gz"))):
        T = pd.read_pickle(f)
        if not len(T):
            continue
        m = (T.time_msc.values // 60000) * 60
        sp = T.ask.values - T.bid.values
        g = pd.DataFrame({"time": m, "bid": T.bid.values, "sp": sp}).groupby("time")
        B = g.bid.agg(["first", "max", "min", "last", "size"])
        B.columns = ["open", "high", "low", "close", "ticks"]
        B["spread_mean"] = g.sp.mean()
        B["spread_max"] = g.sp.max()
        out.append(B.reset_index())
    M = pd.concat(out).drop_duplicates("time").sort_values("time").reset_index(drop=True)
    M.to_pickle(os.path.join(D, "broker_m1_ticks.pkl"))
    t = pd.to_datetime(M.time, unit="s")
    print(f"M1: {len(M)} velas, {t.min()} -> {t.max()}, spread medio {M.spread_mean.mean():.3f}")


if __name__ == "__main__":
    main()
