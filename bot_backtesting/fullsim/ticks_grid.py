"""Rejilla de 5 segundos a partir de los ticks del broker (data/ticks/XAUUSD+/*.pkl.gz), dia por dia.

Columnas por bloque de 5 s (hora servidor): bid y ask del ultimo tick, mid, n de ticks, ticks al alza y
a la baja del mid (regla del tick), spread maximo. Bloques sin ticks se rellenan con el ultimo precio
(n = 0). Salida: data/ticks_5s.pkl. Uso: python -m bot_backtesting.fullsim.ticks_grid
"""
import glob
import os

import numpy as np
import pandas as pd

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def day_grid(fp):
    X = pd.read_pickle(fp)
    t = X.time_msc.values // 1000
    mid = (X.bid.values + X.ask.values) / 2
    dm = np.sign(np.r_[0.0, np.diff(mid)])
    b = t // 5 * 5
    df = pd.DataFrame({"b": b, "bid": X.bid.values, "ask": X.ask.values, "up": dm > 0, "dn": dm < 0, "sp": X.ask.values - X.bid.values})
    g = df.groupby("b").agg(bid=("bid", "last"), ask=("ask", "last"), n=("bid", "size"), up=("up", "sum"), dn=("dn", "sum"), spmax=("sp", "max"))
    full = pd.RangeIndex(int(g.index.min()), int(g.index.max()) + 5, 5)
    g = g.reindex(full)
    g[["n", "up", "dn"]] = g[["n", "up", "dn"]].fillna(0)
    g[["bid", "ask"]] = g[["bid", "ask"]].ffill()
    g["spmax"] = g.spmax.fillna(g.ask - g.bid)
    g.index.name = "t"
    return g.astype({"n": "int32", "up": "int32", "dn": "int32", "bid": "float32", "ask": "float32", "spmax": "float32"})


def main():
    files = sorted(glob.glob(os.path.join(DATA, "ticks", "XAUUSD+", "*.pkl.gz")))
    parts = []
    for i, fp in enumerate(files):
        parts.append(day_grid(fp))
        if i % 20 == 0:
            print(i, os.path.basename(fp), flush=True)
    G = pd.concat(parts)
    G = G[~G.index.duplicated()]
    G.to_pickle(os.path.join(DATA, "ticks_5s.pkl"))
    print("filas", len(G), "MB", round(G.memory_usage().sum() / 1e6))


if __name__ == "__main__":
    main()
