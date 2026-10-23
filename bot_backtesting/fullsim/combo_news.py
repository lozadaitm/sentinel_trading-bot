"""Big One (HAR + eventos x0,5) + satelites de noticias (seguir FOMC/NFP, contra IPC; objetivo 3,
candado 2 x ATR M15, max 24 h; salida fijada de antemano). Solo simulacion, 2023-2026.
R del satelite = pnl / (2 x ATR M15). Riesgo Big One 3 %; satelites 0, 1, 2 %.
Uso: python -m bot_backtesting.fullsim.combo_news
"""
import os

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.bigone_plus import CAL
from bot_backtesting.fullsim.cand_intraday import scale_at
from bot_backtesting.fullsim.entrylab import RESULTS

SAT = {"fomc_sigue": (3.0, 2.0), "nfp_sigue": (3.0, 2.0), "ipc_contra": (3.0, 2.0)}


def sats():
    out = []
    for name, (tp, sl) in SAT.items():
        R = pd.read_pickle(os.path.join(RESULTS, f"cand_{name}.pkl"))
        R = R[(R.tp == tp) & (R.sl == sl)].copy()
        R["risk_oz"] = [sl * scale_at(t) for t in R.t]
        R["r_mult"] = R.pnl / R.risk_oz
        R["mr"] = np.minimum(R.r_mult, 0)
        out.append(R.assign(mod=name)[["t", "year", "r_mult", "mr", "mod"]])
    return pd.concat(out)


def main():
    S = sats()
    print("satelites R medio por año:"); print(S.pivot_table(index="mod", columns="year", values="r_mult", aggfunc="mean").round(2).to_string())
    print("todos los años:", S.groupby("mod").r_mult.agg(["mean", "size"]).round(3).to_dict())
    T = pd.read_pickle(os.path.join(RESULTS, "bigone_plus_trades.pkl"))
    T = T[T.variant == "har_ev50"].copy(); T["mr"] = T.mae / T.risk_oz; T["mod"] = "big_one"
    rows = []
    for fs in (0.0, 0.01, 0.02):
        A = pd.concat([T[["t", "r_mult", "mr", "w", "mod"]].assign(f=0.03),
                       S[S.year >= 2023].assign(w=1.0, f=fs)]).sort_values("t")
        A = A[A.f > 0]
        A["m"] = pd.to_datetime(A.t, unit="s").dt.to_period("M")
        months = [A.loc[A.m == p, ["r_mult", "mr", "w", "f"]].values.reshape(-1, 4) for p in CAL]

        def path(seq, bal=5000.0):
            eq, peak, dd = bal, bal, 0.0
            for r, m, w, f in seq:
                risk = eq * f * w
                dd = max(dd, (peak - (eq + min(0.0, m) * risk)) / peak)
                eq += r * risk; peak = max(peak, eq); dd = max(dd, (peak - eq) / peak)
                if eq <= bal * 0.05:
                    return eq / bal, 1.0
            return eq / bal, dd
        rng = np.random.default_rng(7)
        res = [path(np.vstack([months[i] for i in rng.integers(0, len(months), 12)])) for _ in range(2000)]
        mult = np.array([r[0] for r in res]); dds = np.array([r[1] for r in res])
        one = np.array([path(m)[0] - 1 for m in months]); real = path(np.vstack(months))
        rows.append(dict(riesgo_satelites=fs, ops_mes=len(A) / len(months), mes_med=np.median(one), p_mes30=(one >= .3).mean(),
                         x12_med=np.median(mult), p_x2=(mult >= 2).mean(), p_dd50=(dds >= .5).mean(), real_x=real[0], real_dd=real[1]))
    pd.set_option("display.width", 250)
    print(pd.DataFrame(rows).round(3).to_string(index=False))


if __name__ == "__main__":
    main()
