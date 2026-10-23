"""Cartera final sobre precios del broker, todo elegido por validacion movil (salida y escala del candado).
Big One (medio riesgo en dias de noticia) + momentum EE.UU. + satelites FOMC/NFP (IPC descartado: R < 0).
Uso: python -m bot_backtesting.fullsim.broker_final"""
import os
import numpy as np
import pandas as pd
from bot_backtesting.fullsim.broker_rule import RESULTS, account, walk_forward

L = lambda n: pd.read_pickle(os.path.join(RESULTS, f"broker_r2_{n}.pkl"))
bo = pd.concat([walk_forward(g).assign(w={2: 1.0, 0: .5, -2: .5}[s]) for s, g in L("bigone").groupby("state") if s in (2, 0, -2)])
bo["w"] = bo.w * np.where(bo.ev == 1, 0.5, 1.0)
parts = {"bigone": bo, "ny05": walk_forward(L("ny_mom_05")).assign(w=1.0), "ny05_todas": walk_forward(L("ny_mom_05_todas")).assign(w=1.0),
         "fomc": walk_forward(L("news_fomc")).assign(w=1.0), "nfp": walk_forward(L("news_nfp")).assign(w=1.0)}
rows = []
for label, keys in (("bigone+ny05", ["bigone", "ny05"]), ("bigone+ny05+fomc+nfp", ["bigone", "ny05", "fomc", "nfp"]),
                    ("bigone+ny05todas+fomc+nfp", ["bigone", "ny05_todas", "fomc", "nfp"])):
    T = pd.concat([parts[k] for k in keys], ignore_index=True)
    for sch in (("fijo", 0.02), ("fijo", 0.03), ("gz", 0.5, 0.04), ("gz", 0.5, 0.06), ("gz", 0.6, 0.06)):
        rows.append(dict(cartera=label, esquema=str(sch), ops_mes=round(len(T) / 34, 1), R=round(T.r_mult.mean(), 3), **account(T, sch)))
pd.set_option("display.width", 250)
print(pd.DataFrame(rows).round(3).to_string(index=False))
d = {k: v.groupby("d").r_mult.sum() for k, v in parts.items()}
print("correlaciones diarias:"); print(pd.DataFrame(d).fillna(0).corr().round(2).to_string())
