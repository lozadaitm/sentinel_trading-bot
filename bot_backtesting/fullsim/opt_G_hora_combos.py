"""Linea G (coordinador): hora de salida de la Big One y combinaciones de los candidatos de B y C.

  1) Big One 01:01 -> HH:00, HH en 05..10 (vecindario completo; la pista de la linea C era 08:00).
     Misma escalera y candado; solo cambia la hora de salida.
  2) Combinaciones de candidatos sobre la base:
       U1 (linea B): peso de la Big One 0,75 fijo, sin x0,5 de noticia.
       F1 (linea C): Big One con peso 0 si vpct >= 0,5 (ATR_D/precio sobre su mediana de 252 dias).
       H8: Big One sale a las 08:00.
     y sus cruces. Se elige con sel; val solo para los finalistas.
Uso: .venv/Scripts/python -m bot_backtesting.fullsim.opt_G_hora_combos [sel|val]
"""
import sys

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.opt_base import (base_trades, compare, entries, low_priority, m15, register,
                                              run_trades, swap_cost)


def exit_at(E, hh):
    """Big One con salida a las hh:00 (servidor)."""
    E = E.copy()
    bo = E.leg == "big_one"
    E.loc[bo, "t_out"] = (E.loc[bo, "t"] // 86400) * 86400 + hh * 3600
    from bot_backtesting.fullsim.opt_base import spread_at
    E.loc[bo, "spr_out"] = spread_at(E.loc[bo, "t_out"].values - 60)
    E.loc[bo, "swap"] = [swap_cost(a, b, s) for a, b, s in zip(E.loc[bo, "t_in"], E.loc[bo, "t_out"], E.loc[bo, "side"])]
    return E


def vpct():
    X, D = m15()
    a = (D.H - D.L).rolling(14).mean() / D.C
    v = a.rolling(252, min_periods=120).rank(pct=True).shift(1)
    return v                                                   # indice = dia (epoch // 86400)


def w_u1(T):
    return np.where(T.leg == "big_one", 0.75, T.w)


def w_f1(T, w=None, thr=0.5):
    v = vpct().reindex(T.t // 86400).values
    w = T.w.values if w is None else w
    return np.where((T.leg == "big_one") & (v >= thr), 0.0, w)


def main(per):
    low_priority()
    B = base_trades()
    E = entries()
    rows = []
    H = {10: B}
    for hh in (5, 6, 7, 8, 9):
        H[hh] = run_trades(exit_at(E, hh))
    for hh, T in H.items():
        res = compare(T, B, per, f"BO sale {hh:02d}:00", boot=(hh in (7, 8, 9)))
        register("G", f"bo_exit_{hh:02d}", res, dict(hh=hh, per=per))
        rows.append(res)
    for name, hh, wfn in (("U1", 10, lambda T: w_u1(T)), ("F1", 10, lambda T: w_f1(T)),
                          ("U1+F1", 10, lambda T: w_f1(T, w_u1(T))), ("H8+U1", 8, lambda T: w_u1(T)),
                          ("H8+F1", 8, lambda T: w_f1(T)), ("H8+U1+F1", 8, lambda T: w_f1(T, w_u1(T))),
                          ("F1 thr0.4", 10, lambda T: w_f1(T, thr=0.4)), ("F1 thr0.6", 10, lambda T: w_f1(T, thr=0.6)),
                          ("H8+F1 thr0.4", 8, lambda T: w_f1(T, thr=0.4)), ("H8+F1 thr0.6", 8, lambda T: w_f1(T, thr=0.6))):
        T = H[hh].copy(); T["wG"] = wfn(T)
        res = compare(T, B, per, name, wcol="wG")
        register("G", name, res, dict(per=per))
        rows.append(res)
    S = pd.DataFrame(rows)
    # por año dentro de sel
    if per == "sel":
        for y in (2023, 2024):
            a, b = pd.Timestamp(f"{y}-01-01"), pd.Timestamp(f"{y + 1}-01-01")
            for hh in (7, 8, 9):
                r = compare(H[hh], B, (a, b), f"BO sale {hh:02d}:00 {y}", boot=False)
                print(y, hh, round(r["mar_ratio"], 2))
            for name, hh, wfn in (("H8+F1", 8, lambda T: w_f1(T)), ("F1", 10, lambda T: w_f1(T)), ("U1", 10, w_u1)):
                T = H[hh].copy(); T["wG"] = wfn(T)
                print(y, name, round(compare(T, B, (a, b), name, wcol="wG", boot=False)["mar_ratio"], 2))
    cols = ["label", "mar_c", "mar_ratio", "cagr_c", "dd_c", "cagr_lote_mayor", "peor_dia_c", "peor_dia_b",
            "peor_mes_c", "peor_mes_b", "n_c", "p", "pasa"]
    pd.set_option("display.width", 250)
    print(S[[c for c in cols if c in S]].round(3).to_string(index=False))
    S.to_pickle(f"bot_backtesting/fullsim/results/opt_G_{per}.pkl")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "sel")
