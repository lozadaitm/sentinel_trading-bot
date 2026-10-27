"""Linea A - finalistas: bootstrap en 'sel', una sola mirada a 'val', 2023 vs 2024, nulos de momentos al azar.

Para cada finalista (gestor de opt_A_common.manage con reglas fijas):
  * compare(..., 'sel', boot=True) y compare(..., 'val', boot=True), ambos registrados (FIN-sel / FIN-val);
  * MAR 2023 y 2024 por separado; R medio por pata; tipo de salida y P&L minimo de las salidas por trailing;
  * nulo 'lote mayor' (lo da compare);
  * nulo de momentos al azar: random_entries(mode='time' y 'day', 5 semillas cada uno) con la gestion vigente
    vs el finalista: mejora del R medio por operacion (en ATR_D) y del MAR, comparada con la mejora en e2.
Uso: .venv/Scripts/python -m bot_backtesting.fullsim.opt_A_final
"""
import os
import time

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.opt_base import (RESULTS, SEL, VAL, base_trades, clip, compare, entries, evaluate,
                                              low_priority, random_entries, register)
from bot_backtesting.fullsim import opt_A_common as AC
from bot_backtesting.fullsim.opt_A_common import BASE_RULES, cache_paths, run_cached, years
from bot_backtesting.fullsim.opt_A_grid import T0, tp, tr

# Finalistas en modo EXACTO (stop movido solo al cierre de cada vela M5: AC.CFG["barclose"] = True)
FINALISTS = {
    "BC_t23_D_a0.2_d0.05": (T0[0], tr(0.2, 0.05, "ad"), tr(0.2, 0.05, "ad")),
    "BC_t23_D_a0.2_d0.1": (T0[0], tr(0.2, 0.1, "ad"), tr(0.2, 0.1, "ad")),
    "BC_t23_a2.5_d0.75": (T0[0], tr(2.5, 0.75), tr(2.5, 0.75)),
}
SEEDS = range(5)


def fmt(res):
    return (f"MAR {res['mar_c']:.2f} (base {res['mar_b']:.2f}, x{res['mar_ratio']:.3f}) CAGR {res['cagr_c']:.2f} "
            f"dd {res['dd_c']:.3f} dia {res['peor_dia_c']:.3f}/{res['peor_dia_b']:.3f} mes {res['peor_mes_c']:.3f}/"
            f"{res['peor_mes_b']:.3f} p {res.get('p', np.nan):.3f} lote_mayor CAGR {res['cagr_lote_mayor']:.2f} "
            f"(f={res['f_lote_mayor']:.3f}) Pdd30 {res.get('p_dd30_c', np.nan):.2f}/{res.get('p_dd30_b', np.nan):.2f}")


def main(finalists=FINALISTS):
    low_priority()
    AC.CFG["barclose"] = True
    t0 = time.time()
    E = entries()
    C = cache_paths(E, "e2")
    B = base_trades()
    Bc = run_cached(C, BASE_RULES)
    rows = []
    Es = E[(E.t >= SEL[0].timestamp()) & (E.t < VAL[1].timestamp())].reset_index(drop=True)
    rnd = {(m, s): cache_paths(random_entries(Es, s, mode=m), f"rnd_{m}_{s}") for m in ("time", "day") for s in SEEDS}
    rnd_base = {k: run_cached(v, BASE_RULES) for k, v in rnd.items()}
    print(f"nulos listos ({time.time()-t0:.0f}s)", flush=True)
    for name, rules in finalists.items():
        T = run_cached(C, rules)
        out = dict(name=name)
        for per in ("sel", "val"):
            res = compare(T, B, per, label=name, boot=True)
            register("A", f"FIN-{per}:{name}", res, dict(rules=rules))
            print(f"{name:20s} {per}: {fmt(res)}", flush=True)
            out.update({f"{per}_{k}": v for k, v in res.items() if not isinstance(v, (dict, list))})
        y = years(T, B)
        out.update(r23=y[2023][2], r24=y[2024][2], mar23=y[2023][0], mar24=y[2024][0])
        Ts, Bs = clip(T, "sel"), clip(Bc, "sel")
        dR = {leg: Ts[Ts.leg == leg].R.mean() - Bs[Bs.leg == leg].R.mean() for leg in ("big_one", "momentum", "nfp")}
        tr_ex = T.kinds.str.split("|").explode()
        print(f"   2023 x{y[2023][2]:.2f} 2024 x{y[2024][2]:.2f} | dR por pata (sel) "
              + " ".join(f"{k} {v:+.4f}" for k, v in dR.items()) + f" | salidas {tr_ex.value_counts(normalize=True).round(3).to_dict()}")
        # P&L de los tercios cerrados por trailing (debe ser > 0)
        out["dR_sel"] = Ts.R.mean() - Bs.R.mean()
        Tv, Bv = clip(T, "val"), clip(Bc, "val")
        out["dR_val"] = Tv.R.mean() - Bv.R.mean()
        # nulos al azar
        nd = []
        for (m, s), Cr in rnd.items():
            Tr = run_cached(Cr, rules)
            Br = rnd_base[(m, s)]
            for per in ("sel", "val"):
                a, b = clip(Tr, per), clip(Br, per)
                mc, mb = evaluate(Tr, per), evaluate(Br, per)
                nd.append(dict(mode=m, seed=s, per=per, dR=a.R.mean() - b.R.mean(), Rb=b.R.mean(), Rc=a.R.mean(),
                               mar_c=mc["mar"], mar_b=mb["mar"], dd_c=mc["dd"], dd_b=mb["dd"], cagr_c=mc["cagr"],
                               cagr_b=mb["cagr"]))
        N = pd.DataFrame(nd)
        g = N.groupby(["mode", "per"])[["dR", "Rb", "Rc", "cagr_b", "cagr_c", "dd_b", "dd_c"]].mean()
        print(f"   e2: dR sel {out['dR_sel']:+.4f} val {out['dR_val']:+.4f}  | nulo azar (media 5 semillas):")
        print(g.round(4).to_string())
        for (m, per), r_ in g.iterrows():
            out[f"null_{m}_{per}_dR"] = r_.dR
            out[f"null_{m}_{per}_cagr_b"] = r_.cagr_b; out[f"null_{m}_{per}_cagr_c"] = r_.cagr_c
            out[f"null_{m}_{per}_dd_b"] = r_.dd_b; out[f"null_{m}_{per}_dd_c"] = r_.dd_c
        rows.append(out)
        print(f"--- {name} ({time.time()-t0:.0f}s)", flush=True)
    pd.DataFrame(rows).to_csv(os.path.join(RESULTS, "optA_final.csv"), index=False)


if __name__ == "__main__":
    main()
