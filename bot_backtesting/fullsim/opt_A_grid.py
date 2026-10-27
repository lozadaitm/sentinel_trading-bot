"""Linea A (mejores salidas) - grillas de gestores de salida sobre el camino intra-vela (M5), solo en 'sel'.

Prueba (misma senal, misma entrada, mismo peso; solo cambia la salida):
  F1 trailing en ganancia (ATR15 fijo / ATR_D / Chandelier con ATR15 vivo / que se aprieta con el tiempo)
     aplicado al 3er tercio, al 2o y 3o, o a los tres;
  F2 trailing con objetivo (tope) a la vez;
  F3 parabolico (SAR) en ganancia;
  F4 agotamiento (vela fina grande en contra tras +x) y estancamiento (n velas sin nuevo maximo tras +x);
  F5 extension de la hora de salida con trailing si va en ganancia (con/sin tendencia a favor);
  F6 candado a 0,5..1,5 x ATR_D con lote dimensionado a la distancia real del candado (igual riesgo);
     y 'deshacer el candado' (REQUIERE CERRAR EN PERDIDA, aparte);
  F7 objetivos distintos por pata; F8 fracciones de la escalera.
Cada variante se registra con register('A', ...) (boot=False). Los resultados van a results/optA_grid.csv.
Uso: .venv/Scripts/python -m bot_backtesting.fullsim.opt_A_grid [familia ...]
"""
import os
import sys
import time

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.opt_base import RESULTS, base_trades, compare, entries, low_priority, register
from bot_backtesting.fullsim.opt_A_common import BASE_RULES, by_leg, cache_paths, run_cached, run_fn, years

OUT = os.path.join(RESULTS, "optA_grid.csv")
T0 = ({"k": "time"},)


def tp(m, u="a15"):
    return {"k": "tp", "m": m, "u": u}


def tr(act, dist, u="a15", **kw):
    return dict(k="trail", act=act, dist=dist, u=u, **kw)


class Runner:
    def __init__(self):
        self.C = cache_paths(entries(), "e2")
        self.B = base_trades()
        self.rows = []

    def test(self, fam, name, rules=None, fn=None, params="", lock_k=1.0, reg=True, **kw):
        if fn is not None:
            T = run_fn(self.C, fn, lock_k=lock_k, **kw)
            if lock_k != 1.0:
                T["atrd"] = T.atrd * lock_k; T["R"] = T.pnl / T.atrd
        else:
            T = run_cached(self.C, rules, lock_k=lock_k, **kw)
        res = compare(T, self.B, "sel", label=name, boot=False)
        y = years(T, self.B)
        neg = T.kinds.str.contains("trail|mkt|ext_trail")
        row = dict(fam=fam, name=name, params=str(params), mar=res["mar_c"], ratio=res["mar_ratio"], cagr=res["cagr_c"],
                   dd=res["dd_c"], pdia=res["peor_dia_c"], pmes=res["peor_mes_c"], cagr_lm=res["cagr_lote_mayor"],
                   r23=y[2023][2], r24=y[2024][2], pasa=res["pasa"])
        self.rows.append(row)
        if reg:
            register("A", f"{fam}:{name}", res, params)
        print(f"{fam:4s} {name:42s} MAR {res['mar_c']:.2f} x{res['mar_ratio']:.3f} CAGR {res['cagr_c']:.2f} "
              f"dd {res['dd_c']:.3f} dia {res['peor_dia_c']:.3f} mes {res['peor_mes_c']:.3f} "
              f"23 x{y[2023][2]:.2f} 24 x{y[2024][2]:.2f}", flush=True)
        return T, res

    def save(self):
        D = pd.DataFrame(self.rows)
        D.to_csv(OUT, mode="a", header=not os.path.exists(OUT), index=False)


def fam_trail(R):
    # F1: trailing en ATR15 fijo, en el 3er tercio / 2o+3o / los tres
    for where in ("t3", "t23", "t123"):
        for act in (1.0, 2.0, 3.0):
            for dist in (1.0, 2.0, 3.0):
                t = tr(act, dist)
                rules = {"t3": (T0[0], tp(2.0), t), "t23": (T0[0], t, t), "t123": (t, t, t)}[where]
                R.test("F1", f"{where}_a{act}_d{dist}", rules, params=dict(where=where, act=act, dist=dist, u="a15"))
    # en ATR_D
    for where in ("t3", "t23"):
        for act in (0.1, 0.2, 0.3):
            for dist in (0.1, 0.15, 0.25):
                t = tr(act, dist, "ad")
                rules = {"t3": (T0[0], tp(2.0), t), "t23": (T0[0], t, t)}[where]
                R.test("F1", f"{where}_D_a{act}_d{dist}", rules, params=dict(where=where, act=act, dist=dist, u="ad"))
    # Chandelier (ATR15 vivo) y apriete con el tiempo, en el 3er tercio
    for act in (2.0, 3.0):
        for dist in (2.0, 3.0):
            R.test("F1", f"t3_chand_a{act}_d{dist}", (T0[0], tp(2.0), tr(act, dist, live=True)),
                   params=dict(where="t3", act=act, dist=dist, live=True))
            for tight in (0.5, 0.8):
                R.test("F1", f"t3_tight{tight}_a{act}_d{dist}", (T0[0], tp(2.0), tr(act, dist, tight=tight)),
                       params=dict(where="t3", act=act, dist=dist, tight=tight))
    # trailing en el tercio de hora (el 1o) dejando TP 2 y 3
    for act in (1.0, 2.0, 3.0):
        for dist in (1.0, 2.0, 3.0):
            R.test("F1", f"t1_a{act}_d{dist}", (tr(act, dist), tp(2.0), tp(3.0)), params=dict(where="t1", act=act, dist=dist))


def fam_trail_tp(R):
    # F2: trailing + objetivo tope en el 3er tercio y en el 1o
    for act in (2.0, 3.0):
        for dist in (1.0, 2.0):
            for cap in (4.0, 6.0):
                R.test("F2", f"t3_a{act}_d{dist}_cap{cap}", (T0[0], tp(2.0), tr(act, dist, tp=cap)),
                       params=dict(where="t3", act=act, dist=dist, cap=cap))
                R.test("F2", f"t1_a{act}_d{dist}_cap{cap}", (tr(act, dist, tp=cap), tp(2.0), tp(3.0)),
                       params=dict(where="t1", act=act, dist=dist, cap=cap))


def fam_sar(R):
    for where in ("t3", "t1"):
        for act in (1.0, 2.0, 3.0):
            for afmax in (0.1, 0.2):
                s = dict(k="sar", act=act, u="a15", af0=0.02, step=0.02, afmax=afmax)
                rules = (T0[0], tp(2.0), s) if where == "t3" else (s, tp(2.0), tp(3.0))
                R.test("F3", f"{where}_sar_a{act}_m{afmax}", rules, params=dict(where=where, act=act, afmax=afmax))


def fam_exh(R):
    for where in ("t3", "t1"):
        for act in (1.0, 2.0, 3.0):
            for kr in (1.5, 2.0, 3.0):
                e = dict(k="exh", act=act, u="a15", kr=kr, look=12)
                rules = (T0[0], tp(2.0), e) if where == "t3" else (e, tp(2.0), tp(3.0))
                R.test("F4", f"{where}_exh_a{act}_k{kr}", rules, params=dict(where=where, act=act, kr=kr))
            for nbars in (6, 12, 24):
                e = dict(k="stall", act=act, u="a15", nbars=nbars)
                rules = (T0[0], tp(2.0), e) if where == "t3" else (e, tp(2.0), tp(3.0))
                R.test("F4", f"{where}_stall_a{act}_n{nbars}", rules, params=dict(where=where, act=act, nbars=nbars))


def fam_ext(R):
    # F5: extension de la hora de salida para los tercios que siguen abiertos y van en ganancia
    for h in (1, 2, 3, 6):
        for dist in (1.0, 2.0, 3.0):
            for need_s in (False, True):
                ext = dict(h=h, dist=dist, u="a15", need_s=need_s, minp=0.0)
                R.test("F5", f"ext_h{h}_d{dist}_s{int(need_s)}", BASE_RULES, ext=ext,
                       params=dict(h=h, dist=dist, need_s=need_s))
    # extension solo de Big One / solo de Momentum (h=2, d=2)
    for leg in ("big_one", "momentum", "nfp"):
        for h in (2, 3):
            ext = dict(h=h, dist=2.0, u="a15", need_s=False, minp=0.0)

            def f(P, r, lock_k=1.0, _leg=leg, _ext=ext):
                from bot_backtesting.fullsim.opt_A_common import manage
                return manage(P, r, rules=BASE_RULES, lock_k=lock_k, ext=_ext if r.leg == _leg else None)
            R.test("F5", f"ext_{leg}_h{h}_d2", fn=f, params=dict(leg=leg, h=h, dist=2.0))


def fam_lock(R):
    for k in (0.5, 0.75, 1.25, 1.5):
        R.test("F6", f"lock{k}_size", BASE_RULES, lock_k=k, params=dict(lock_k=k, size_lock=True))
        R.test("F6", f"lock{k}_nosize", BASE_RULES, lock_k=k, size_lock=False, params=dict(lock_k=k, size_lock=False))
    for k in (0.75, 1.0):
        for back in (0.25, 0.5):
            R.test("F6X", f"PERDIDA_undo_lock{k}_back{back}", BASE_RULES, lock_k=k, undo_lock=dict(back=back),
                   params=dict(lock_k=k, back=back, requiere_cerrar_en_perdida=True))


def fam_tpleg(R):
    # F7: objetivos por pata (tercios hora / TP a / TP b), una pata cada vez, el resto vigente
    for leg in ("big_one", "momentum", "nfp"):
        for a, b in ((1.5, 2.5), (2.0, 4.0), (2.5, 4.0), (3.0, 5.0), (2.0, 6.0), (1.0, 3.0)):
            R.test("F7", f"{leg}_tp{a}_{b}", fn=by_leg({leg: (T0[0], tp(a), tp(b))}), params=dict(leg=leg, a=a, b=b))


def fam_fracs(R):
    # F8: fracciones y composicion de la escalera
    R.test("F8", "solo_hora", (T0[0],), params="todo a la hora")
    R.test("F8", "tp2_tp3_tp3", (tp(2.0), tp(2.0), tp(3.0)), params="sin tercio de hora: TP2,TP2,TP3")
    R.test("F8", "hora_tp3_tp3", (T0[0], tp(3.0), tp(3.0)), params="hora,TP3,TP3")
    R.test("F8", "hora_hora_tp3", (T0[0], T0[0], tp(3.0)), params="hora,hora,TP3")
    R.test("F8", "hora_tp2_tp3_tp4", (T0[0], tp(2.0), tp(3.0), tp(4.0)), params="cuartos hora,TP2,TP3,TP4")
    R.test("F8", "hora_tp2_tp4_trail", (T0[0], tp(2.0), tp(4.0), tr(2.0, 2.0)), params="cuartos con trailing a2 d2")


FAMS = dict(F1=fam_trail, F2=fam_trail_tp, F3=fam_sar, F4=fam_exh, F5=fam_ext, F6=fam_lock, F7=fam_tpleg, F8=fam_fracs)

if __name__ == "__main__":
    low_priority()
    t0 = time.time()
    R = Runner()
    R.test("B", "base_repro", BASE_RULES, reg=False)
    for f in (sys.argv[1:] or list(FAMS)):
        FAMS[f](R)
        R.save(); R.rows = []
        print(f"--- {f} listo ({time.time()-t0:.0f}s)", flush=True)
