"""Linea F (27-oct-2026): FINALISTAS de IA y datos externos -> bootstrap en sel, 2023/2024, nulo de dias al azar
(permuta la caracteristica entre operaciones de la pata, 200 veces, en sel y en val), VAL una sola vez.

Finalistas elegidos SOLO con sel (grillas de opt_F_tsfm y opt_F_datos):
  Familia tsfm (Chronos zero-shot, percentil pasado de la prevision):
    T1  F1 + Momentum x0 si p(mu Chronos-2)          < 0,33
    T2  F1 + Momentum x0 si p(mu Chronos-Bolt-tiny)  < 0,33
    T3  F1 + Momentum x0 si p(sig Chronos-2)         < 0,33
    T4  base + Momentum x0 si p(mu Chronos-2)        < 0,33
  Familia datos externos:
    D1  F1 + Momentum x0 si p(cambio 5 d del breakeven 5 a, T5YIE) >= 0,5
    D2  base + Momentum x0 si p(T5YIE 5 d) >= 0,33
    D3  base + TODAS x0 si p(VIX9D/VIX3M) < 0,5
    D4  F1 + Momentum x0 si p(cambio 5 d de la inflacion 5a5a, T5YIFR) >= 0,67

Correr:  .venv/Scripts/python -m bot_backtesting.fullsim.opt_F_final
Salida:  results/opt_F_tsfm_final.pkl, results/opt_F_datos_final.pkl y tablas por pantalla.
"""
import os

import pandas as pd

from bot_backtesting.fullsim.opt_base import RESULTS
from bot_backtesting.fullsim.opt_F_datos import final

TSFM = {
    "T1": dict(base="F1", col="c2_mu", lg="mom", th=0.33, bad_hi=False, mult=0.0),
    "T2": dict(base="F1", col="cbolt_tiny_mu", lg="mom", th=0.33, bad_hi=False, mult=0.0),
    "T3": dict(base="F1", col="c2_sig", lg="mom", th=0.33, bad_hi=False, mult=0.0),
    "T4": dict(base="base", col="c2_mu", lg="mom", th=0.33, bad_hi=False, mult=0.0),
}
DATOS = {
    "D1": dict(base="F1", col="t5yie_d5", lg="mom", th=0.5, bad_hi=True, mult=0.0),
    "D2": dict(base="base", col="t5yie_d5", lg="mom", th=0.33, bad_hi=True, mult=0.0),
    "D3": dict(base="base", col="vix_term", lg="all", th=0.5, bad_hi=False, mult=0.0),
    "D4": dict(base="F1", col="t5yifr_d5", lg="mom", th=0.67, bad_hi=True, mult=0.0),
}
COLS = ["spec", "sel_mar_ratio", "sel_vs_f1", "sel_p", "y2023", "y2024", "null_pct", "null_p95_vs_ref",
        "sel_peor_dia_c", "sel_peor_mes_c", "sel_cagr_c", "sel_dd_c", "sel_cagr_lote_mayor",
        "val_mar_ratio", "val_vs_f1", "val_p", "val_null_pct", "val_peor_dia_c", "val_peor_mes_c", "val_cagr_c",
        "val_dd_c", "val_cagr_lote_mayor"]

if __name__ == "__main__":
    fe = pd.read_pickle(os.path.join(RESULTS, "opt_F_tsfm_feats.pkl"))
    R1 = final(list(TSFM.values()), fe=fe, tag="tsfm", out="opt_F_tsfm_final.pkl")
    R1.insert(0, "id", list(TSFM))
    R2 = final(list(DATOS.values()), tag="datos", out="opt_F_datos_final.pkl")
    R2.insert(0, "id", list(DATOS))
    pd.set_option("display.width", 250)
    for R in (R1, R2):
        print(R[["id"] + COLS].round(3).T.to_string())
