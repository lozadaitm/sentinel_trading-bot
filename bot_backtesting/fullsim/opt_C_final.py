"""Linea C (27-oct-2026): FINALISTAS de regimen -> bootstrap en sel, anos 2023/2024, vecinos, VAL (una vez),
nulo de dias al azar (permuta la etiqueta de regimen entre dias, 300 veces) y, para estrategias nuevas, nulo de
momentos al azar (random_entries).

Finalistas (elegidos SOLO con 'sel' en opt_C_regimen / opt_C_politica / opt_C_estrategias):
  F1 bo_vpct_off     : Big One apagada si vpct >= 0,5 (percentil 252 d de ATR_D/precio, hasta ayer).
  F2 bo_vpct_pol     : Big One x1,5 si vpct < 0,5 y x0 si vpct >= 0,5.
  F3 mom_er10_pol    : Momentum x1,5 si er10 >= 0,35 y x0 si er10 < 0,35 (eficiencia de Kaufman 10 d).
  F4 combo           : F2 + F3.
  F5 rango_mr_18h    : estrategia nueva en rango (ver STRAT y strat_trades).
Funcion reproducible: regime_weights(B, F, policies) con F = opt_C_regimen.build_features() (+ hmmvol).

Correr:  .venv/Scripts/python -m bot_backtesting.fullsim.opt_C_final
Salida:  results/opt_C_final.pkl y tabla por pantalla.
"""
import os

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.opt_base import (RESULTS, base_trades, compare, evaluate, low_priority, period,
                                              random_entries, register, run_trades)
from bot_backtesting.fullsim.opt_C_estrategias import combine, strat_pool
from bot_backtesting.fullsim.opt_C_politica import add_hmmvol
from bot_backtesting.fullsim.opt_C_regimen import YEARS, attach, build_features

POL = {
    "F1 bo_vpct_off": [("big_one", "vpct", 0.5, False, 0.0, 1.0)],
    "F2 bo_vpct_pol": [("big_one", "vpct", 0.5, False, 0.0, 1.5)],
    "F3 mom_er10_pol": [("momentum", "er10", 0.35, True, 0.0, 1.5)],
    "F4 combo": [("big_one", "vpct", 0.5, False, 0.0, 1.5), ("momentum", "er10", 0.35, True, 0.0, 1.5)],
}
NEIGH = {"vpct": [0.4, 0.6], "er10": [0.3, 0.4]}


def regime_weights(T, policies):
    """policies: lista de (pata, columna, umbral, bueno_si_alto, mult_malo, mult_bueno).
    Regimen bueno = col >= umbral si bueno_si_alto, si no col < umbral. Dias sin dato: peso sin cambio."""
    C = T.copy()
    for leg, col, th, good_hi, m_bad, m_good in policies:
        x = C[col]
        good = (x >= th) if good_hi else (x < th)
        sel = (C.leg == leg) & x.notna()
        C.loc[sel & good, "w"] = C.loc[sel & good, "w"] * m_good
        C.loc[sel & ~good, "w"] = C.loc[sel & ~good, "w"] * m_bad
    return C


def permuted(T, F, per, rng):
    """Permuta las caracteristicas entre los dias del periodo (todas juntas: misma fraccion de dias buenos/malos)."""
    a, b = period(per)
    d = np.array([x for x in F.index if a.timestamp() <= x * 86400 < b.timestamp()])
    Fp = F.copy()
    Fp.loc[d] = F.loc[rng.permutation(d)].values
    return attach(T[[c for c in T.columns if c not in F.columns]], Fp)


def evaluate_policy(name, pols, B, F, T, n_perm=300):
    out = {"finalista": name}
    C = regime_weights(T, pols)
    rs = compare(C, B, "sel", f"C/final {name} [sel]")
    register("C", f"C/final {name} [sel]", rs, pols)
    for y, p in YEARS.items():
        out[y] = evaluate(C, p)["mar"] / evaluate(B, p)["mar"]
    # vecinos +-1 paso de cada umbral
    vm = []
    for i, (leg, col, th, gh, mb, mg) in enumerate(pols):
        for th2 in NEIGH[col]:
            p2 = list(pols); p2[i] = (leg, col, th2, gh, mb, mg)
            r2 = compare(regime_weights(T, p2), B, "sel", boot=False)
            register("C", f"C/final {name} vecino {col}={th2}", r2, p2)
            vm.append(r2["mar_ratio"])
    out["vec_min"] = min(vm)
    # nulo de dias al azar
    rng = np.random.default_rng(7)
    null = []
    for _ in range(n_perm):
        null.append(evaluate(regime_weights(permuted(T, F, "sel", rng), pols), "sel")["mar"])
    null = np.array(null)
    out["null_pct"] = float((null < rs["mar_c"]).mean())
    out["null_p95"] = float(np.percentile(null, 95) / rs["mar_b"])
    rv = compare(C, B, "val", f"C/final {name} [val]")
    register("C", f"C/final {name} [val]", rv, pols)
    for k in ("mar_c", "mar_ratio", "cagr_c", "dd_c", "peor_dia_c", "peor_mes_c", "p", "cagr_lote_mayor", "pasa"):
        out[f"sel_{k}"] = rs.get(k)
        out[f"val_{k}"] = rv.get(k)
    return out


STRAT = dict(key="S1|h18|H3|t3", dev=0.5, col="er20", th=0.2, w=1.0)
STRAT_NEIGH = [dict(dev=0.3), dict(dev=0.7), dict(th=0.15), dict(th=0.25), dict(key="S1|h18|H5|t3"),
               dict(key="S1|h16|H3|t3")]


def strat_trades(pool, F, key, dev, col, th, w):
    """F5: reversion a la media en rango. 18:00 servidor, si |open 18:00 - open 01:00| > dev x ATR_D y er20 < th
    (rango), se opera en contra; tercios hora 21:00 / TP 2 / TP 3 ATR15, candado -1 ATR_D."""
    P = attach(pool[key], F)
    return P[(P.dev > dev) & (P[col] < th)].assign(w=w)


def evaluate_strat(B, F, pool, n_rand=40):
    name = "F5 rango_mr_18h"
    S = strat_trades(pool, F, **STRAT)
    C = combine(B, S, STRAT["w"])
    out = {"finalista": name}
    rs = compare(C, B, "sel", f"C/final {name} [sel]")
    register("C", f"C/final {name} [sel]", rs, STRAT)
    for y, p in YEARS.items():
        out[y] = evaluate(C, p)["mar"] / evaluate(B, p)["mar"]
    vm = []
    for nb in STRAT_NEIGH:
        prm = dict(STRAT, **nb)
        r2 = compare(combine(B, strat_trades(pool, F, **prm), prm["w"]), B, "sel", boot=False)
        register("C", f"C/final {name} vecino {nb}", r2, prm)
        vm.append(r2["mar_ratio"])
    out["vec_min"] = min(vm)
    # nulo de momentos al azar: mismas filas (lado, hora 18:00, duracion) en dias habiles al azar; mismo filtro
    # de regimen evaluado en el dia nuevo; se re-simula el camino intra-vela
    E0 = pool[STRAT["key"]]
    E0 = attach(E0, F)
    E0 = E0[E0.dev > STRAT["dev"]][[c for c in pool[STRAT["key"]].columns if c not in ("pnl", "mae", "locked", "R")]]
    null = []
    for sd in range(n_rand):
        Rr = random_entries(E0.drop(columns=["dev"]), seed=sd, mode="day")
        Rr = run_trades(Rr)
        Rr = attach(Rr, F)
        Rr = Rr[Rr[STRAT["col"]] < STRAT["th"]]
        null.append(evaluate(combine(B, Rr, STRAT["w"]), "sel")["mar"])
    null = np.array(null)
    out["null_pct"] = float((null < rs["mar_c"]).mean())
    out["null_p95"] = float(np.percentile(null, 95) / rs["mar_b"])
    rv = compare(C, B, "val", f"C/final {name} [val]")
    register("C", f"C/final {name} [val]", rv, STRAT)
    for k in ("mar_c", "mar_ratio", "cagr_c", "dd_c", "peor_dia_c", "peor_mes_c", "p", "cagr_lote_mayor", "pasa"):
        out[f"sel_{k}"] = rs.get(k)
        out[f"val_{k}"] = rv.get(k)
    return out


def main():
    low_priority()
    B = base_trades()
    F = add_hmmvol(build_features())
    T = attach(B, F)
    rows = []
    for n, p in POL.items():
        rows.append(evaluate_policy(n, p, B, F, T))
        print(n, {k: round(v, 3) if isinstance(v, float) else v for k, v in rows[-1].items()}, flush=True)
    rows.append(evaluate_strat(B, F, strat_pool()))
    print(rows[-1], flush=True)
    R = pd.DataFrame(rows)
    R.to_pickle(os.path.join(RESULTS, "opt_C_final.pkl"))
    pd.set_option("display.width", 250)
    print(R.round(3).T.to_string())


if __name__ == "__main__":
    main()
