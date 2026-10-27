"""Linea F (27-oct-2026): prueba ACOTADA de aprendizaje por refuerzo para el TAMANO (peso 0 / 0,5 / 1 / 1,5).

Que prueba:
  Un bandido contextual tabular que aprende EN LINEA, en orden de tiempo, que peso dar a cada operacion segun
  un contexto de 2-4 variables discretas:
     A: pata x vpct (>= 0,5 o no)                       (4 celdas)
     B: A x tendencia s (= +2 o no)                     (8 celdas)
     C: B x flujo GLD de 20 dias (>= 0 o no)           (16 celdas)
  Para decidir solo usa operaciones YA CERRADAS (t_out < t_in de la nueva). En cada celda estima la media y la
  varianza del R (con encogimiento hacia la media de la pata, k0 pseudo-observaciones) y elige el peso de
  {0; 0,5; 1; 1,5} que maximiza  w*media - lambda/2 * w^2 * varianza  (utilidad media-varianza, tipo Kelly).
  Calentamiento: hasta tener 30 operaciones cerradas en la pata se usa el peso base.
  Ojo honesto: el resultado de cada operacion se observa aunque el peso sea 0 (el camino de precios existe), asi que
  es informacion completa: en la practica es aprendizaje supervisado en linea, no un bandido de verdad.

  Dos escalas de lambda: absoluta (--abs, 9 variantes, ya registradas) y relativa a la pata (rel: con la media y la
  varianza de toda la pata el peso optimo seria 1/lam; 6 variantes).

Correr:  .venv/Scripts/python -m bot_backtesting.fullsim.opt_F_bandit [--abs]
"""
import sys

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.opt_base import VAL, compare, evaluate, low_priority, register
from bot_backtesting.fullsim.opt_F_datos import base_and_f1
from bot_backtesting.fullsim import opt_F_ext as X

ACTS = np.array([0.0, 0.5, 1.0, 1.5])


def contexts(T):
    from bot_backtesting.fullsim.opt_C_regimen import build_features
    F = build_features()[["vpct"]]
    d = (T.t // 86400).astype(int).values
    vp = F.vpct.reindex(d).values
    g = X.load_gld(); g["ton_l"] = np.log(g.tonnes)
    fl = X.asof_join(T.t_in.values, g, "ton_l") - X.asof_join(T.t_in.values - 28 * 86400, g, "ton_l")
    leg = T.leg.map({"big_one": 0, "momentum": 1, "nfp": 2}).values
    hv = (vp >= 0.5).astype(int)
    s2 = (T.state.values == 2).astype(int)
    gp = (fl >= 0).astype(int)
    return {"A": leg * 10 + hv, "B": leg * 100 + hv * 10 + s2, "C": leg * 1000 + hv * 100 + s2 * 10 + gp}


def run_policy(T, ctx, lam=4.0, k0=20, warm=30, rel=False):
    """T ordenado por t y con indice 0..n-1; ctx alineado con T."""
    ctx = np.asarray(ctx)
    R = T.pnl.values / T.atrd.values
    tin, tout, leg = T.t_in.values, T.t_out.values, T.leg.values
    w = T.w.values.copy()
    order_close = np.argsort(tout)
    for i in range(len(T)):
        if leg[i] == "nfp":
            continue                                       # NFP: muy pocas, peso base
        closed = order_close[: np.searchsorted(tout[order_close], tin[i], side="right")]
        same_leg = closed[leg[closed] == leg[i]]
        if len(same_leg) < warm:
            continue
        cell = same_leg[ctx[same_leg] == ctx[i]]
        mu_l, var_l = R[same_leg].mean(), R[same_leg].var()
        n = len(cell)
        mu = (R[cell].sum() + k0 * mu_l) / (n + k0)
        var = ((R[cell] ** 2).sum() + k0 * (var_l + mu_l ** 2)) / (n + k0) - mu ** 2
        # rel=True: lambda relativo a la pata -> con la media/varianza de la pata el peso optimo es 1/lam
        L = lam * max(mu_l, 1e-3) / max(var_l, 1e-6) if rel else lam
        u = ACTS * mu - L / 2 * ACTS ** 2 * max(var, 1e-6)
        w[i] = ACTS[int(np.argmax(u))]
    T = T.copy(); T["w"] = w
    return T


def main():
    low_priority()
    B, F1 = base_and_f1()
    B = B[B.t < VAL[1].timestamp()].sort_values("t").reset_index(drop=True)
    F1 = F1[F1.t < VAL[1].timestamp()].reset_index(drop=True)
    cx = contexts(B)
    mb1 = evaluate(F1, "sel")["mar"]
    rows = []
    for cname, lam, rel in [(c, l, False) for c in "ABC" for l in (2.0, 4.0, 8.0)] +                            [(c, l, True) for c in "ABC" for l in (1.0, 0.75)]:
        if not (rel or "--abs" in sys.argv):
            continue
        if True:
            C = run_policy(B, cx[cname], lam=lam, rel=rel)
            name = f"F/bandit ctx={cname} lam={lam}{' rel' if rel else ''}"
            r = compare(C, B, "sel", name)
            register("F", name, r, dict(ctx=cname, lam=lam, rel=rel, k0=20, warm=30))
            dist = C[(C.leg != "nfp")].w.value_counts(normalize=True).round(2).to_dict()
            rows.append(dict(variante=name, mar_ratio=r["mar_ratio"], vs_f1=r["mar_c"] / mb1, p=r["p"],
                             cagr=r["cagr_c"], dd=r["dd_c"], cagr_lm=r["cagr_lote_mayor"],
                             peor_dia=r["peor_dia_c"], peor_mes=r["peor_mes_c"], pesos=dist))
            print(rows[-1], flush=True)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    print(main().round(3).to_string())
