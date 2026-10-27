"""Linea B: finalistas de tamano (reglas). Para cada candidato elegido SOLO con sel:
  1) sel con bootstrap pareado (compare boot=True) y nulo de dias al azar (200 permutaciones de los pesos
     entre operaciones de la misma pata);
  2) vecinos (+-1 paso: corte en cuartil/quintil, peso vecino) en sel;
  3) val (2025) una sola vez: compare con bootstrap + nulo de dias al azar.
Los pesos los produce weights(nombre, B, F): funcion pura de base_trades() y opt_B_feats.build(), con cortes
calculados con cuantiles de operaciones ANTERIORES de la misma pata (sirve igual para 2026).
Uso: .venv/Scripts/python -m bot_backtesting.fullsim.opt_B_final [--val]
"""
import sys

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.opt_B_feats import build
from bot_backtesting.fullsim.opt_B_lib import evalw, perm_null
from bot_backtesting.fullsim.opt_B_rules import bucket_w, past_quantile
from bot_backtesting.fullsim.opt_base import base_trades, low_priority


def bo_trend_w(B, F, a=0.5, b=1.0, c=1.0, e=1.0):
    """Big One: peso a si s=+2, b si s=0 (o desconocido), c si s=-2; x e en dia de NFP/IPC/FOMC.
    Base vigente = (1, 0,5, 0,5, 0,5)."""
    s = F.s.values
    wb = np.where(s == 2, a, np.where(s == -2, c, b)) * np.where(F.ev_any.values == 1, e, 1.0)
    return np.where(B.leg.values == "big_one", wb, B.w.values)


def mo_bucket(B, F, base_w, feat, q_hi=2 / 3, w_hi=0.0, signed=False):
    """Momentum: peso w_hi cuando la variable supera su cuantil q_hi de las operaciones Momentum ANTERIORES."""
    x = F[feat].values * (F.side.values if signed else 1)
    cuts = past_quantile(B, x, [q_hi])
    m = bucket_w(B, x, cuts, (1.0, w_hi))
    return np.where(B.leg.values == "momentum", base_w * m, base_w)


def mo_low_cut(B, F, feat, q_lo=1 / 3, w_lo=0.0):
    """Momentum: peso w_lo cuando la variable queda por debajo de su cuantil q_lo de las Momentum ANTERIORES."""
    x = F[feat].values
    cut = past_quantile(B, x, [q_lo])[:, 0]
    low = np.isfinite(cut) & np.isfinite(x) & (x <= cut)
    return np.where((B.leg.values == "momentum") & low, B.w.values * w_lo, B.w.values)


CANDS = {
    # nombre: (funcion de pesos, descripcion)
    "R1 bo_trend a0.5 b1 c1 e1": lambda B, F: bo_trend_w(B, F, 0.5, 1, 1, 1),
    "R2 mo_ry5 sin_alto": lambda B, F: mo_bucket(B, F, B.w.values, "f_ry_d5"),
    "R3 mo_gap sin_alto": lambda B, F: mo_bucket(B, F, B.w.values, "gap"),
    "R4 mo_gvz5 sin_bajo": lambda B, F: mo_low_cut(B, F, "f_gvz_d5"),
    "R5 R1+R2": lambda B, F: mo_bucket(B, F, bo_trend_w(B, F, 0.5, 1, 1, 1), "f_ry_d5"),
}
# Agregado despues de ver el nulo de dias al azar (la inclinacion por s de la base queda en el percentil 2,5 % en sel):
# Big One con peso uniforme 0,75 y sin el x0,5 de noticia. Se evaluo aparte (fila «U1 ... |sel boot» y «|val boot»).
U1 = lambda B, F: bo_trend_w(B, F, 0.75, 0.75, 0.75, 1.0)

NEIGH = {
    "R1 bo_trend a0.5 b1 c1 e1": {
        "a0.75": lambda B, F: bo_trend_w(B, F, 0.75, 1, 1, 1),
        "a0.5 c0.75": lambda B, F: bo_trend_w(B, F, 0.5, 1, 0.75, 1),
        "a0.5 b0.75": lambda B, F: bo_trend_w(B, F, 0.5, 0.75, 1, 1),
        "a0.5 e0.75": lambda B, F: bo_trend_w(B, F, 0.5, 1, 1, 0.75),
        "a0.5 e0.5": lambda B, F: bo_trend_w(B, F, 0.5, 1, 1, 0.5),
    },
    "R2 mo_ry5 sin_alto": {
        "q0.6": lambda B, F: mo_bucket(B, F, B.w.values, "f_ry_d5", q_hi=0.6),
        "q0.75": lambda B, F: mo_bucket(B, F, B.w.values, "f_ry_d5", q_hi=0.75),
        "q0.8": lambda B, F: mo_bucket(B, F, B.w.values, "f_ry_d5", q_hi=0.8),
        "w_hi0.5": lambda B, F: mo_bucket(B, F, B.w.values, "f_ry_d5", w_hi=0.5),
        "firmado_lado": lambda B, F: mo_bucket(B, F, B.w.values, "f_ry_d5", signed=True),
        "ry_d1": lambda B, F: mo_bucket(B, F, B.w.values, "f_ry_d1"),
    },
    "R3 mo_gap sin_alto": {
        "q0.6": lambda B, F: mo_bucket(B, F, B.w.values, "gap", q_hi=0.6),
        "q0.75": lambda B, F: mo_bucket(B, F, B.w.values, "gap", q_hi=0.75),
        "w_hi0.5": lambda B, F: mo_bucket(B, F, B.w.values, "gap", w_hi=0.5),
        "firmado_lado": lambda B, F: mo_bucket(B, F, B.w.values, "gap", signed=True),
    },
    "R4 mo_gvz5 sin_bajo": {
        "q0.25": lambda B, F: mo_low_cut(B, F, "f_gvz_d5", 0.25),
        "q0.4": lambda B, F: mo_low_cut(B, F, "f_gvz_d5", 0.4),
        "w_lo0.5": lambda B, F: mo_low_cut(B, F, "f_gvz_d5", 1 / 3, 0.5),
    },
}


META = ["meta lgbm todas junto cv m_cut30", "meta logit todas junto cv m_cut30", "meta lgbm pocas junto cv m_cut30",
        "meta logit todas junto cv m_half50", "meta ridge pocas junto wf m_cut30"]


def meta_sel_weights(name, B, F):
    """Pesos fuera de muestra en sel (CV purgada / walk-forward) tal como en la grilla de opt_B_meta."""
    from bot_backtesting.fullsim import opt_B_meta as M
    from bot_backtesting.fullsim.opt_base import SEL
    _, kind, fs, scope, scheme, mp = name.split()
    X = M.design(B, F)
    cols = [c for c in X.columns if c != "w0"] if fs == "todas" else M.POCAS
    idx = np.nonzero(B.t.values < SEL[1].timestamp())[0]
    _, W = M.oos(B, X, cols, kind, scope, scheme, idx)
    m = np.ones(len(B)); m[idx] = W[mp]
    return B.w.values * m


def weights(name, B=None, F=None):
    B = base_trades() if B is None else B
    F = build() if F is None else F
    return np.asarray(CANDS[name](B, F), float)


def fmt(r, keys=("mar_ratio", "edge_lm", "r2023", "r2024", "cagr_c", "dd_c", "peor_dia_c", "peor_mes_c", "p", "pasa")):
    return " ".join(f"{k}={r[k]:.3f}" if isinstance(r.get(k), float) else f"{k}={r.get(k)}" for k in keys if k in r)


if __name__ == "__main__":
    low_priority()
    B = base_trades(); F = build()
    do_val = "--val" in sys.argv
    out = []
    for nm, fn in CANDS.items():
        w = np.asarray(fn(B, F), float)
        if not do_val:
            r = evalw(B, w, nm + " |sel boot", "final", boot=True)
            pc, pm, p95, mc = perm_null(B, w, "sel", n=200)
            print(nm, "SEL", fmt(r), f"perm_pct={pc:.3f} perm_mar_medio={pm:.2f} perm_p95={p95:.2f} mar={mc:.2f}", flush=True)
            out.append(dict(cand=nm, per="sel", **{k: r[k] for k in r if not isinstance(r[k], dict) and k != "per"}, perm_pct=pc, perm_mean=pm, perm_p95=p95))
            for vn, vf in NEIGH.get(nm, {}).items():
                rv = evalw(B, np.asarray(vf(B, F), float), f"{nm} vecino {vn}", "vecino")
                print("   vecino", vn, fmt(rv), flush=True)
                out.append(dict(cand=nm + " vecino " + vn, per="sel", **{k: rv[k] for k in rv if not isinstance(rv[k], dict) and k != "per"}))
        else:
            r = evalw(B, w, nm + " |val", "final", boot=True, per="val")
            pc, pm, p95, mc = perm_null(B, w, "val", n=200)
            print(nm, "VAL", fmt(r), f"perm_pct={pc:.3f} perm_mar_medio={pm:.2f} perm_p95={p95:.2f} mar={mc:.2f}", flush=True)
            out.append(dict(cand=nm, per="val", **{k: r[k] for k in r if not isinstance(r[k], dict) and k != "per"}, perm_pct=pc, perm_mean=pm, perm_p95=p95))
    from bot_backtesting.fullsim.opt_B_meta import weights_period
    from bot_backtesting.fullsim.opt_base import VAL
    for nm in META:
        if not do_val:
            w = meta_sel_weights(nm, B, F)
            r = evalw(B, w, nm + " |sel boot", "final", boot=True)
            pc, pm, p95, mc = perm_null(B, w, "sel", n=200)
            print(nm, "SEL", fmt(r), f"perm_pct={pc:.3f} perm_mar_medio={pm:.2f} perm_p95={p95:.2f} mar={mc:.2f}", flush=True)
        else:
            w = weights_period(nm, VAL[0], VAL[1], "2024-12-31")
            r = evalw(B, w, nm + " |val", "modelo<=2024", boot=True, per="val")
            pc, pm, p95, mc = perm_null(B, w, "val", n=200)
            print(nm, "VAL", fmt(r), f"perm_pct={pc:.3f} perm_mar_medio={pm:.2f} perm_p95={p95:.2f} mar={mc:.2f}", flush=True)
        out.append(dict(cand=nm, per="val" if do_val else "sel", **{k: r[k] for k in r if not isinstance(r[k], dict) and k != "per"},
                        perm_pct=pc, perm_mean=pm, perm_p95=p95))
    pd.DataFrame(out).to_csv(f"bot_backtesting/fullsim/results/opt_B_final_{'val' if do_val else 'sel'}.csv", index=False)
