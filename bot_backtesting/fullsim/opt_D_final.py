"""Linea D - finalistas: bootstrap en sel, 2023 vs 2024, vecindario, robustez de llenado, nulos y UNA mirada a val.
Nulos:
  (i)  quitar al azar: la fraccion llenada de cada operacion de la pata (fillf) se permuta entre las operaciones
       base de esa pata (>= 200 veces) -> percentil del MAR del candidato (lo que da solo quitar operaciones).
  (ii) momentos al azar: la misma regla sobre random_entries(E, seed, mode='time') (10 semillas) -> ratio MAR
       regla / MAR base en esas entradas al azar.
  (iii) lote mayor: lo da compare (cagr_lote_mayor).
Robustez: penetracion exigida al limite 0,05 -> 0,15 $/oz.
Correr:  .venv/Scripts/python -m bot_backtesting.fullsim.opt_D_final
"""
import os
import sys
import time

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.opt_base import RESULTS, compare, entries, evaluate, low_priority, random_entries, register
from bot_backtesting.fullsim.opt_D_common import load, raw_cache, sim
from bot_backtesting.fullsim.opt_D_limite import run_plan

Y23 = (pd.Timestamp("2023-01-01"), pd.Timestamp("2024-01-01"))
Y24 = (pd.Timestamp("2024-01-01"), pd.Timestamp("2025-01-01"))

# (nombre, pata, plan, vecinos = nombres de la grilla a +-1 paso, ya registrados alli)
L = lambda u, x, N, fb, anc, kind="limit": dict(kind=kind, u=u, levels=[(x, 1.0)], N=N, fb=fb, anchor=anc)
FINALISTS = [
    ("limit_big_one_ad0.01_N15_lost_orig", "big_one", L("ad", 0.01, 15, "lost", "orig"),
     ["limit_big_one_ad0.02_N15_lost_orig", "limit_big_one_ad0.01_N30_lost_orig", "limit_big_one_ad0.01_N15_lost_new"]),
    ("stop_momentum_ad0.05_N30_lost_new", "momentum", L("ad", 0.05, 30, "lost", "new", "stop"),
     ["stop_momentum_ad0.02_N30_lost_new", "stop_momentum_ad0.1_N30_lost_new", "stop_momentum_ad0.05_N15_lost_new",
      "stop_momentum_ad0.05_N60_lost_new"]),
    ("stop_momentum_a151.0_N30_lost_new", "momentum", L("a15", 1.0, 30, "lost", "new", "stop"),
     ["stop_momentum_a150.5_N30_lost_new", "stop_momentum_a151.5_N30_lost_new", "stop_momentum_a151.0_N15_lost_new",
      "stop_momentum_a151.0_N60_lost_new"]),
    ("limit_momentum_ad0.01_N15_mkt_new", "momentum", L("ad", 0.01, 15, "mkt", "new"),
     ["limit_momentum_ad0.02_N15_mkt_new", "limit_momentum_ad0.01_N30_mkt_new", "limit_momentum_a150.25_N15_mkt_new"]),
    ("twap_big_one_d5_orig", "big_one", dict(kind="twap", levels=[(4, 1)], anchor="orig"),
     ["twap_big_one_d10_orig", "twap_big_one_t2_0_5_orig", "twap_big_one_d5_new"]),
]


def grid_ratio(names):
    G = pd.concat([pd.read_csv(os.path.join(RESULTS, f"optD_grid_{f}.csv")) for f in ("limit", "stop", "ladder", "twap")])
    m = G.set_index("name").mar_ratio
    return [round(float(m.get(n, np.nan)), 3) for n in names]


def leg_R(T, B, leg, per):
    a, b = (pd.Timestamp(x).timestamp() for x in per)
    f = lambda Z: Z[(Z.leg == leg) & (Z.t >= a) & (Z.t < b)]
    c, z = f(T), f(B)
    return float((c.w * c.pnl / c.atrd).sum()), float((z.w * z.pnl / z.atrd).sum())


def null_drop(B, C, leg, per, n=200, seed=7):
    """Percentil del MAR del candidato entre las bases con la misma fraccion llenada permutada al azar."""
    rng = np.random.default_rng(seed)
    T, _ = C
    mc = evaluate(T, per)["mar"]
    Bl = B[B.leg == leg].copy()
    ff = T[T.leg == leg].set_index(["t"]).fillf.reindex(Bl.t).fillna(0.0).values
    out = []
    for _ in range(n):
        Bp = Bl.copy()
        fp = rng.permutation(ff)
        Bp["pnl"] = Bp.pnl.values * fp
        Bp.loc[fp == 0, "w"] = 0.0
        Z = pd.concat([B[B.leg != leg], Bp]).sort_values("t")
        out.append(evaluate(Z, per)["mar"])
    out = np.array(out)
    return float((out < mc).mean()), float(np.median(out)), float(np.percentile(out, 95))


def null_time(leg, plan, seeds=range(10)):
    E = entries()
    rat = []
    for s in seeds:
        R = random_entries(E[E.t < pd.Timestamp("2025-01-01").timestamp()], s, mode="time")
        Rs, rr = raw_cache(R, f"rnd_time_{s}")
        Bz = sim(Rs, rr)
        m = (Rs.leg == leg).values
        Cz = sim(Rs[m].reset_index(drop=True), [x for x, k in zip(rr, m) if k], plan, legs=(leg,))
        Tz = pd.concat([Bz[Bz.leg != leg], Cz]).sort_values("t")
        mb, mc = evaluate(Bz, "sel")["mar"], evaluate(Tz, "sel")["mar"]
        rat.append(mc / mb if mb > 0 else np.nan)
    return float(np.nanmedian(rat)), [round(x, 3) for x in rat]


def main(look_val=True):
    low_priority()
    E, raws, B = load()
    out = []
    for name, leg, plan, neigh in FINALISTS:
        t0 = time.time()
        res, T = run_plan(E, raws, B, leg, plan, name + "_selboot", boot=True)
        r23, _ = run_plan(E, raws, B, leg, plan, name + "_2023", per=Y23)
        r24, _ = run_plan(E, raws, B, leg, plan, name + "_2024", per=Y24)
        rob, _ = run_plan(E, raws, B, leg, plan | {"pen": 0.15}, name + "_pen015")
        nb = grid_ratio(neigh)
        rc, rb = leg_R(T, B, leg, ("2022-10-01", "2025-01-01"))
        pd_, med, p95 = null_drop(B, (T, None), leg, "sel") if res["fill_frac"] < 0.999 else (np.nan, np.nan, np.nan)
        nt, nts = null_time(leg, plan)
        row = dict(name=name, leg=leg, sel_mar=res["mar_c"], sel_ratio=res["mar_ratio"], sel_cagr=res["cagr_c"],
                   sel_dd=res["dd_c"], sel_pdia=res["peor_dia_c"], sel_pmes=res["peor_mes_c"], p=res["p"], sumR_leg_c=rc, sumR_leg_b=rb,
                   cagr_lote_mayor=res["cagr_lote_mayor"], fill=res["fill_frac"], r2023=r23["mar_ratio"],
                   r2024=r24["mar_ratio"], pen015=rob["mar_ratio"], vecinos=[round(x, 3) for x in nb],
                   nulo_quitar_pct=pd_, nulo_quitar_med=med, nulo_quitar_p95=p95, nulo_tiempo_ratio=nt, nulo_tiempo=nts)
        if look_val:
            rv, Tv = run_plan(E, raws, B, leg, plan, name + "_VAL", per="val", boot=True)
            rcv, rbv = leg_R(Tv, B, leg, ("2025-01-01", "2026-01-01"))
            row.update(sumR_leg_c_val=rcv, sumR_leg_b_val=rbv)
            row.update(val_mar=rv["mar_c"], val_ratio=rv["mar_ratio"], val_cagr=rv["cagr_c"], val_dd=rv["dd_c"],
                       val_pdia=rv["peor_dia_c"], val_pmes=rv["peor_mes_c"], val_p=rv["p"],
                       val_pdia_b=rv["peor_dia_b"], val_pmes_b=rv["peor_mes_b"], val_mar_b=rv["mar_b"])
        out.append(row)
        print({k: (round(v, 3) if isinstance(v, float) else v) for k, v in row.items()}, f"{time.time()-t0:.0f}s", flush=True)
    F = pd.DataFrame(out)
    F.to_csv(os.path.join(RESULTS, "optD_finalistas.csv"), index=False)
    return F


if __name__ == "__main__" and len(sys.argv) == 1:
    main()


def null_time_R(seeds=range(10)):
    """Nulo (ii) en R (el MAR de entradas al azar suele ser <= 0 y el cociente no sirve):
    cambio de sum(w x R) de la pata al aplicar la regla, en entradas al azar vs en las e2 reales (sel). No mira val."""
    low_priority()
    E, raws, B = load()
    E0 = entries()
    rnd = []
    for s in seeds:
        R = random_entries(E0[E0.t < pd.Timestamp("2025-01-01").timestamp()], s, mode="time")
        Rs, rr = raw_cache(R, f"rnd_time_{s}")
        rnd.append((Rs, rr, sim(Rs, rr)))
    out = []
    for name, leg, plan, _ in FINALISTS:
        _, T = run_plan(E, raws, B, leg, plan, name, reg=False)
        rc, rb = leg_R(T, B, leg, ("2022-10-01", "2025-01-01"))
        d = []
        for Rs, rr, Bz in rnd:
            m = (Rs.leg == leg).values
            Cz = sim(Rs[m].reset_index(drop=True), [x for x, k in zip(rr, m) if k], plan, legs=(leg,))
            zc, zb = leg_R(Cz, Bz, leg, ("2022-10-01", "2025-01-01"))
            d.append(zc - zb)
        row = dict(name=name, dR_real=rc - rb, dR_azar_med=float(np.median(d)), dR_azar=[round(x, 2) for x in d],
                   pct_real=float((np.array(d) < rc - rb).mean()))
        print(row, flush=True)
        out.append(row)
    pd.DataFrame(out).to_csv(os.path.join(RESULTS, "optD_nulo_tiempo.csv"), index=False)


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "nulo_tiempo":
    null_time_R()
