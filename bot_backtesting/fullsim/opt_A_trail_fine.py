"""Linea A - trailing en ganancia de distancia corta: grilla fina + robustez (solo 'sel').

La grilla gruesa (opt_A_grid F1) mostro que un trailing de distancia ~1 x ATR15 armado a +2..3 x ATR15 en los
tercios 2-3 (o los tres) sube el MAR, pero con salto brusco entre dist 1 y 2. Aqui:
  G1 grilla fina en ATR15: act 1,5..4, dist 0,5..1,5, en t23 (tercio 1 a la hora) y t123;
  G2 grilla fina en ATR_D: act 0,15..0,30, dist 0,05..0,15, en t23 y t123;
  G3 por pata: el trailing solo en Big One / solo en Momentum (resto vigente);
  G4 robustez de los mejores: deslizamiento extra en la salida por stop (0,10 / 0,25 / 0,50 $/oz) y
     resolucion M15 en vez de M5 (camino mas grueso: dentro de la vela primero en contra).
Uso: .venv/Scripts/python -m bot_backtesting.fullsim.opt_A_trail_fine [G1 G2 G3 G4]
"""
import os
import sys
import time

import numpy as np
import pandas as pd

from bot_backtesting.fullsim import opt_A_common as AC
from bot_backtesting.fullsim.opt_A_grid import OUT, Runner, T0, tp, tr
from bot_backtesting.fullsim.opt_base import compare, entries, low_priority, register
from bot_backtesting.fullsim.opt_A_common import BASE_RULES, by_leg, cache_paths_m15, run_cached, years


def rules_for(where, t):
    return {"t3": (T0[0], tp(2.0), t), "t23": (T0[0], t, t), "t123": (t, t, t)}[where]


def g1(R):
    for where in ("t23", "t123"):
        for act in (1.5, 2.0, 2.5, 3.0, 3.5, 4.0):
            for dist in (0.5, 0.75, 1.0, 1.25, 1.5):
                if dist in (1.0,) and act in (2.0, 3.0):
                    continue                                    # ya en la grilla gruesa
                R.test("G1", f"{where}_a{act}_d{dist}", rules_for(where, tr(act, dist)),
                       params=dict(where=where, act=act, dist=dist, u="a15"))


def g2(R):
    for where in ("t23", "t123"):
        for act in (0.15, 0.2, 0.25, 0.3):
            for dist in (0.05, 0.075, 0.1, 0.125, 0.15):
                if where == "t23" and act in (0.2, 0.3) and dist in (0.1, 0.15):
                    continue
                R.test("G2", f"{where}_D_a{act}_d{dist}", rules_for(where, tr(act, dist, "ad")),
                       params=dict(where=where, act=act, dist=dist, u="ad"))


def g3(R):
    for leg in ("big_one", "momentum", "nfp"):
        for where, t in (("t23", tr(3.0, 1.0)), ("t123", tr(3.0, 1.0)), ("t23D", tr(0.2, 0.1, "ad"))):
            w = "t23" if where.startswith("t23") else where
            R.test("G3", f"solo_{leg}_{where}", fn=by_leg({leg: rules_for(w, t)}),
                   params=dict(leg=leg, where=where, rule=t))


BEST = {"t123_a3_d1": rules_for("t123", tr(3.0, 1.0)), "t23_a3_d1": rules_for("t23", tr(3.0, 1.0)),
        "t23_D_a0.2_d0.1": rules_for("t23", tr(0.2, 0.1, "ad")), "t123_D_a0.2_d0.1": rules_for("t123", tr(0.2, 0.1, "ad"))}


def g4(R):
    for name, rules in BEST.items():
        for ss in (0.10, 0.25, 0.50):
            AC.CFG["stop_slip"] = ss
            R.test("G4", f"{name}_slip+{ss}", rules, params=dict(base=name, stop_slip_extra=ss))
        AC.CFG["stop_slip"] = 0.0
    # resolucion M15
    C5 = R.C
    R.C = cache_paths_m15(entries(), "e2")
    R.test("G4", "base_M15res", BASE_RULES, params="base con camino M15", reg=False)
    for name, rules in BEST.items():
        R.test("G4", f"{name}_M15res", rules, params=dict(base=name, resolucion="M15"))
    R.C = C5


G = dict(G1=g1, G2=g2, G3=g3, G4=g4)

if __name__ == "__main__":
    low_priority()
    t0 = time.time()
    R = Runner()
    for g in (sys.argv[1:] or list(G)):
        G[g](R)
        R.save(); R.rows = []
        print(f"--- {g} listo ({time.time()-t0:.0f}s)", flush=True)
