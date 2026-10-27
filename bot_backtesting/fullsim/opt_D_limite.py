"""Linea D, ideas 1-3: orden limite a -x (y stop de entrada a +x) con la MISMA senal e2. Grilla en 'sel'.
Cada punto de la grilla se registra con register('D', ...) (boot=False). Resultado: results/optD_grid_<fam>.csv.
Familias:
  limit : x en ATR15 (0,25-3) o ATR_D (0,01-0,10), N = 15/30/60/120 min, si no llena 'lost' o 'mkt',
          TP/candado desde el precio nuevo ('new') o desde el original ('orig'); una pata por vez.
  stop  : stop de entrada a +x a favor (confirmacion), mismas dimensiones.
  ladder: la misma orden escalonada en 2-3 limites (fracciones iguales), fallback 'mkt' o 'lost'.
Correr:  .venv/Scripts/python -m bot_backtesting.fullsim.opt_D_limite limit|stop|ladder
"""
import itertools
import os
import sys
import time

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.opt_base import RESULTS, compare, low_priority, register
from bot_backtesting.fullsim.opt_D_common import load, sim

LEGS = ("big_one", "momentum", "nfp")
XS = [("a15", x) for x in (0.25, 0.5, 1.0, 1.5, 2.0, 3.0)] + [("ad", x) for x in (0.01, 0.02, 0.05, 0.10)]
NS = (15, 30, 60, 120)


def leg_variant(E, raws, B, leg, plan):
    """Base con la pata `leg` reemplazada por el plan."""
    m = (E.leg == leg).values
    Es = E[m].reset_index(drop=True)
    rs = [r for r, k in zip(raws, m) if k]
    C = sim(Es, rs, plan, legs=(leg,))
    return pd.concat([B[B.leg != leg], C]).sort_values("t").reset_index(drop=True), C


def run_plan(E, raws, B, leg, plan, name, per="sel", boot=False, reg=True):
    T, C = leg_variant(E, raws, B, leg, plan)
    res = compare(T, B, per, label=name, boot=boot)
    Cs = C[(C.t >= pd.Timestamp("2022-10-01").timestamp()) & (C.t < pd.Timestamp("2025-01-01").timestamp())]
    nb = ((B.leg == leg) & (B.t >= pd.Timestamp("2022-10-01").timestamp()) & (B.t < pd.Timestamp("2025-01-01").timestamp())).sum()
    res["n_leg_c"] = int(len(Cs)); res["n_leg_b"] = int(nb)
    res["fill_full"] = float((Cs.fillf >= 0.999).mean()) if len(Cs) else 0.0
    res["fill_frac"] = float(Cs.fillf.sum() / max(nb, 1))
    if reg:
        register("D", name, res, plan | {"leg": leg})
    return res, T


def grid(fam):
    low_priority()
    E, raws, B = load()
    rows = []
    t0 = time.time()
    if fam in ("limit", "stop"):
        combos = itertools.product(LEGS, XS, NS, ("lost", "mkt"), ("new", "orig"))
        for leg, (u, x), N, fb, anc in combos:
            if fam == "stop" and anc == "orig":
                continue          # con stop el precio es peor: 'orig' solo empeora TP; se prueba 'new'
            plan = dict(kind=fam, u=u, levels=[(x, 1.0)], N=N, fb=fb, anchor=anc)
            name = f"{fam}_{leg}_{u}{x}_N{N}_{fb}_{anc}"
            res, _ = run_plan(E, raws, B, leg, plan, name)
            rows.append(dict(name=name, leg=leg, u=u, x=x, N=N, fb=fb, anchor=anc, **{k: res[k] for k in (
                "mar_c", "mar_b", "mar_ratio", "cagr_c", "dd_c", "peor_dia_c", "peor_mes_c", "peor_dia_b", "peor_mes_b",
                "n_leg_c", "n_leg_b", "fill_full", "fill_frac", "pasa")}))
            if len(rows) % 20 == 0:
                print(len(rows), f"{time.time()-t0:.0f}s", flush=True)
    elif fam == "ladder":
        lv = {"a15_2": ("a15", [(0.5, .5), (1.5, .5)]), "a15_3": ("a15", [(0.5, 1 / 3), (1.0, 1 / 3), (2.0, 1 / 3)]),
              "a15_3b": ("a15", [(0.25, 1 / 3), (0.75, 1 / 3), (1.5, 1 / 3)]),
              "a15_0": ("a15", [(0.0, 1 / 3), (1.0, 1 / 3), (2.0, 1 / 3)]),
              "ad_3": ("ad", [(0.01, 1 / 3), (0.03, 1 / 3), (0.06, 1 / 3)]),
              "ad_2": ("ad", [(0.02, .5), (0.05, .5)])}
        for leg, (k, (u, levels)), N, fb, anc in itertools.product(LEGS, lv.items(), NS, ("lost", "mkt"), ("new", "orig")):
            plan = dict(kind="limit", u=u, levels=levels, N=N, fb=fb, anchor=anc)
            name = f"ladder_{leg}_{k}_N{N}_{fb}_{anc}"
            res, _ = run_plan(E, raws, B, leg, plan, name)
            rows.append(dict(name=name, leg=leg, u=u, x=k, N=N, fb=fb, anchor=anc, **{kk: res[kk] for kk in (
                "mar_c", "mar_b", "mar_ratio", "cagr_c", "dd_c", "peor_dia_c", "peor_mes_c", "peor_dia_b", "peor_mes_b",
                "n_leg_c", "n_leg_b", "fill_full", "fill_frac", "pasa")}))
            if len(rows) % 20 == 0:
                print(len(rows), f"{time.time()-t0:.0f}s", flush=True)
    G = pd.DataFrame(rows)
    G.to_csv(os.path.join(RESULTS, f"optD_grid_{fam}.csv"), index=False)
    pd.set_option("display.width", 250)
    for leg in LEGS:
        print(G[G.leg == leg].sort_values("mar_ratio", ascending=False).head(12).round(3).to_string(index=False))
    print("variantes", len(G), f"{time.time()-t0:.0f}s")


if __name__ == "__main__":
    grid(sys.argv[1] if len(sys.argv) > 1 else "limit")
