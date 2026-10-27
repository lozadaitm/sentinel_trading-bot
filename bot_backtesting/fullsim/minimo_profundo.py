"""Revision a fondo de las pocas variantes de minimo_lab que salieron bien en OOS (elegidas MIRANDO el OOS:
hay que leerlas con desconfianza). Lee results/minimo_store.pkl y recargas_trades.pkl.
Para cada una: R anadido por año, alfa por año, cartera al 8 % (base / +recarga / lote mayor con el mismo R),
y dos nulos: (1) mismo dia, momento al azar en perdida; (2) dia al azar de la misma pata y periodo, momento
al azar en perdida (mide si el valor esta en ELEGIR EL DIA, no el momento).
Uso: python -m bot_backtesting.fullsim.minimo_profundo
"""
import os

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.recargas_minimo import RESULTS, alpha_p, low_priority
from bot_backtesting.fullsim.minimo_lab import port_stats

CANDS = {"momentum": ["ML_yb_gbdt_q0.98_time", "ML_yb_gbdt_q0.98_tp2", "ML_ya_gbdt_q0.9_time"],
         "big_one": ["CAP_2_2.5_time", "CAP_3_2.5_tp2"]}
NREP = 2000


def main():
    low_priority()
    rng = np.random.default_rng(5)
    trs = pd.read_pickle(os.path.join(RESULTS, "recargas_trades.pkl"))
    meta, store = pd.read_pickle(os.path.join(RESULTS, "minimo_store.pkl"))
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
    for leg, vs in CANDS.items():
        for v in vs:
            addR = store[v]
            mode = "tp2" if v.endswith("tp2") else "time"
            L = (meta.leg == leg).values
            fired = L & (addR != 0)
            print(f"\n==== {leg} {v}")
            y = pd.DataFrame(dict(year=meta.year, a=addR, b=meta.R, f=fired))[L]
            tab = y.groupby("year").agg(ops=("a", "size"), disparos=("f", "sum"), R_recarga=("a", "sum"), R_base=("b", "sum"))
            tab["alfa_p"] = [alpha_p(g.a.values, g.b.values)[1] for _, g in y.groupby("year")]
            print(tab.round(3).to_string())
            for per, msk in (("IS", meta.is_.values), ("OOS", ~meta.is_.values)):
                sel = L & msk
                f = np.nonzero(sel & fired)[0]
                obs = addR[f].sum()
                pools = {i: trs[i]["nt"][mode][trs[i]["nloss"]] / trs[i]["atrd"] * trs[i]["w"] for i in np.nonzero(sel)[0]}
                pools = {i: p for i, p in pools.items() if len(p)}
                s1 = np.zeros(NREP); s2 = np.zeros(NREP)
                keys = np.array(list(pools))
                for i in f:
                    if i in pools:
                        s1 += pools[i][rng.integers(0, len(pools[i]), NREP)]
                for r in range(NREP):
                    for i in rng.choice(keys, len(f), replace=False):
                        s2[r] += pools[i][rng.integers(0, len(pools[i]))]
                p1 = ((s1 >= obs).sum() + 1) / (NREP + 1); p2 = ((s2 >= obs).sum() + 1) / (NREP + 1)
                base = meta.R.values
                k = 1 + addR[sel].sum() / base[sel].sum()
                rows = {"base": port_stats(meta, base, msk), "+recarga": port_stats(meta, base + np.where(sel, addR, 0), msk),
                        f"lote x{k:.2f}": port_stats(meta, base * np.where(sel, k, 1), msk)}
                print(f" {per}: disparos {len(f)} | R recarga {obs:+.2f} | nulo mismo dia {s1.mean():+.2f} (p={p1:.3f}) | "
                      f"nulo dia al azar {s2.mean():+.2f} (p={p2:.3f})")
                print(pd.DataFrame(rows).T.round(2).to_string())


if __name__ == "__main__":
    main()
