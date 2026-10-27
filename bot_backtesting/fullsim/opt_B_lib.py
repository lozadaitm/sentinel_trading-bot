"""Linea B: utilidades comunes (evaluar una columna de pesos, normalizar exposicion, nulo de dias al azar).

  * evalw(B, w, name, params, boot=False, per='sel') -> dict con compare() + extras, y lo anota en el registro.
      Extras (no van al registro global para no descuadrar sus columnas; van a results/opt_B_log.csv):
        edge_lm  = CAGR candidato / CAGR de la base con lote mayor a la MISMA caida (>1 = mejor que subir el lote)
        r2023, r2024 = MAR candidato / MAR base en cada ano de sel (estabilidad)
        expo     = suma de pesos del candidato / suma de pesos base en el periodo
  * normalize(B, w, per='sel'): reescala w para que la suma de pesos en sel sea la de la base (presupuesto neutro).
      La constante se fija en sel y se aplica igual a todos los periodos.
  * perm_null(B, w, per, n=200): permuta los pesos del candidato entre operaciones de la misma pata del periodo
      y devuelve (percentil del MAR del candidato, MAR medio de las permutaciones).
"""
import os

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.opt_base import RESULTS, clip, compare, evaluate, period, register

LOG = os.path.join(RESULTS, "opt_B_log.csv")
BOOT_KEYS = ("p", "mar_ratio_med", "p_dd30_c", "p_dd30_b", "p_dd40_c", "p_dd40_b")
Y23 = (pd.Timestamp("2023-01-01"), pd.Timestamp("2024-01-01"))
Y24 = (pd.Timestamp("2024-01-01"), pd.Timestamp("2025-01-01"))


def _mask(B, per):
    a, b = period(per) if isinstance(per, str) else per
    return (B.t >= a.timestamp()).values & (B.t < b.timestamp()).values


def normalize(B, w, per="sel", cap=None):
    w = np.asarray(w, float)
    m = _mask(B, per)
    c = B.w.values[m].sum() / max(w[m].sum(), 1e-12)
    w = w * c
    if cap is not None:
        w = np.minimum(w, cap)
    return w


def evalw(B, w, name, params="", boot=False, per="sel", reg=True, years=True):
    C = B.assign(wB=np.asarray(w, float))
    res = compare(C, B, per, label=name, wcol="wB", boot=boot)
    full = {k: v for k, v in res.items() if k not in BOOT_KEYS and k != "pasa"}
    for k in BOOT_KEYS:
        full[k] = res.get(k, np.nan)
    full["pasa"] = res["pasa"]
    if reg:
        register("B", name, full, params)
    ex = dict(full)
    ex["edge_lm"] = res["cagr_c"] / res["cagr_lote_mayor"] if res["cagr_lote_mayor"] > 0 else np.nan
    m = _mask(B, per)
    ex["expo"] = C.wB.values[m].sum() / B.w.values[m].sum()
    if years and per == "sel":
        for nm, yy in (("r2023", Y23), ("r2024", Y24)):
            a = evaluate(C, yy, wcol="wB"); b = evaluate(B, yy)
            ex[nm] = a["mar"] / b["mar"] if b["mar"] > 0 else np.nan
    ex["variant"] = name; ex["params"] = str(params)
    pd.DataFrame([ex]).to_csv(LOG, mode="a", header=not os.path.exists(LOG), index=False)
    return ex


def perm_null(B, w, per="sel", n=200, seed=11):
    """Nulo de dias al azar: mismos pesos, repartidos al azar entre operaciones de la misma pata."""
    m = _mask(B, per)
    C = B[m].copy()
    wc = np.asarray(w, float)[m]
    C["wB"] = wc
    mar_c = evaluate(C, per, wcol="wB")["mar"]
    rng = np.random.default_rng(seed)
    legs = C.leg.values
    out = []
    for _ in range(n):
        wp = wc.copy()
        for lg in np.unique(legs):
            j = np.nonzero(legs == lg)[0]
            wp[j] = wc[rng.permutation(j)]
        C["wB"] = wp
        out.append(evaluate(C, per, wcol="wB")["mar"])
    out = np.array(out)
    return float((out < mar_c).mean()), float(out.mean()), float(np.percentile(out, 95)), mar_c
