"""Linea C (27-oct-2026): POLITICA DE PESO POR REGIMEN DE DOS LADOS (bajar en el regimen malo Y subir en el bueno).

La grilla de opt_C_regimen mostro dos cosas: (1) apagar patas en un regimen baja la caida pero tambien la
exposicion (eso solo no cuenta: el nulo 'lote mayor' lo castiga), y (2) subir x1,5 en dias de tendencia
(eficiencia de Kaufman alta) sube la CAGR a la misma caida. Aqui se prueba la politica completa por pata:
   peso = w_base x (m_bueno si regimen bueno, m_malo si regimen malo)
con m_malo en {0; 0,25; 0,5} y m_bueno en {1; 1,25; 1,5}, para varias columnas/umbrales, y luego la
combinacion de la mejor regla de la Big One con la mejor del Momentum.
Tambien agrega un tercer HMM (hmmvol: MarkovRegression de 2 estados sobre log(rango diario / precio), con
media cambiante, probabilidades FILTRADAS, reajuste mensual expandido) para tener un HMM no degenerado.

Para cada variante se calcula ademas 'cagr_lm': la CAGR de la base con el riesgo que da la misma caida
(interpolada sobre una curva de 60 riesgos), igual que el nulo 'lote mayor' de compare().
Correr:  .venv/Scripts/python -m bot_backtesting.fullsim.opt_C_politica
Salidas: results/opt_C_pol.pkl, registro opt_registry.csv (line='C')
"""
import os
import warnings

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.opt_base import RESULTS, base_trades, evaluate, low_priority, register
from bot_backtesting.fullsim.opt_C_regimen import (FEATS, _BASE, attach, build_features, daily_gold, quick,
                                                   years_ratio)

warnings.filterwarnings("ignore")


def add_hmmvol(F):
    if "hmmvol_p" in F.columns:
        return F
    from statsmodels.tsa.regime_switching.markov_regression import MarkovRegression
    G = daily_gold()
    y = np.log((G.H - G.L) / G.C).replace([np.inf, -np.inf], np.nan).dropna()
    months = pd.to_datetime(y.index, unit="D").to_period("M")
    um = months.unique()
    out = pd.Series(np.nan, y.index)
    prev = None
    for i, m in enumerate(um[:-1]):
        tr = y[months <= m]
        if len(tr) < 250:
            continue
        full = y[months <= um[i + 1]]
        mod = MarkovRegression(tr.values, k_regimes=2, trend="c", switching_variance=True)
        params = None
        for kw in ((dict(start_params=prev) if prev is not None else None), dict(search_reps=10)):
            if kw is None:
                continue
            try:
                params = mod.fit(disp=False, **kw).params
                break
            except Exception:  # noqa
                continue
        if params is None:
            params = prev
        if params is None:
            continue
        prev = params
        try:
            P = np.asarray(MarkovRegression(full.values, k_regimes=2, trend="c", switching_variance=True)
                           .filter(params).filtered_marginal_probabilities)
        except Exception as e:  # noqa
            print("hmmvol filtro fallo", m, e)
            continue
        names = list(mod.param_names)
        hi = int(np.argmax([params[names.index(f"const[{j}]")] for j in range(2)]))
        nx = (months == um[i + 1])[months <= um[i + 1]]
        out.loc[full.index[nx]] = P[nx, hi]
    F["hmmvol_p"] = out.reindex(F.index).shift(1)
    F.to_pickle(FEATS)
    return F


def base_curve(B, per):
    fs = np.r_[np.linspace(0.005, 0.08, 30), np.linspace(0.082, 0.20, 30)]
    ms = [evaluate(B, per, f=f) for f in fs]
    pts = [(m["dd"], m["cagr"]) for m in ms]
    dd, cg = np.array(pts).T
    o = np.argsort(dd)
    return dd[o], cg[o]


def cagr_lm(curve, dd):
    return float(np.interp(dd, curve[0], curve[1]))


RULES = {
    "big_one": [("vpct", [0.3, 0.4, 0.5, 0.6, 0.7, 0.8]), ("er10", [0.2, 0.25, 0.3, 0.35, 0.4]),
                ("adx", [15, 18, 21, 24, 27]), ("hmmvol_p", [0.3, 0.5, 0.7]), ("rvr", [0.85, 1.0, 1.15, 1.3])],
    "momentum": [("er10", [0.2, 0.25, 0.3, 0.35, 0.4, 0.45]), ("er20", [0.15, 0.2, 0.25, 0.3, 0.35]),
                 ("slope20", [-0.5, 0.0, 0.5, 1.0]), ("rvr", [0.85, 1.0, 1.15, 1.3]),
                 ("vpct", [0.3, 0.4, 0.5, 0.6, 0.7]), ("hmmvol_p", [0.3, 0.5, 0.7])],
}


def policy(T, leg, col, th, good_hi, m_bad, m_good):
    """Devuelve copia con pesos de la pata 'leg' ajustados. good_hi=True: regimen bueno = col >= th."""
    C = T.copy()
    x = C[col]
    good = (x >= th) if good_hi else (x < th)
    ok = x.notna()
    sel = (C.leg == leg) & ok
    C.loc[sel & good, "w"] *= m_good
    C.loc[sel & ~good, "w"] *= m_bad
    return C


def main():
    low_priority()
    B = base_trades()
    _BASE["B"] = B
    F = add_hmmvol(build_features())
    T = attach(B, F)
    curve = base_curve(B, "sel")
    rows = []
    for leg, rules in RULES.items():
        for col, ths in rules:
            for th in ths:
                for good_hi in (True, False):
                    for m_bad in (0.0, 0.25, 0.5):
                        for m_good in (1.0, 1.25, 1.5):
                            lab = (f"C/pol {leg} {col}{'>=' if good_hi else '<'}{th:g} bueno x{m_good:g} "
                                   f"malo x{m_bad:g}")
                            C = policy(T, leg, col, th, good_hi, m_bad, m_good)
                            r = quick(C, lab)
                            r["cagr_lote_mayor"] = cagr_lm(curve, r["dd_c"])
                            register("C", lab, r, dict(leg=leg, col=col, th=th, good_hi=good_hi, m_bad=m_bad,
                                                       m_good=m_good))
                            rows.append(dict(leg=leg, col=col, th=th, good_hi=good_hi, m_bad=m_bad, m_good=m_good,
                                             **r))
        print("listo", leg, flush=True)
    P = pd.DataFrame(rows)
    P["vs_lm"] = P.cagr_c / P.cagr_lote_mayor
    P.to_pickle(os.path.join(RESULTS, "opt_C_pol.pkl"))
    pd.set_option("display.width", 250)
    cols = ["label", "mar_c", "mar_ratio", "cagr_c", "dd_c", "cagr_lote_mayor", "vs_lm", "peor_dia_c", "peor_mes_c",
            "pasa"]
    for leg in RULES:
        print(P[P.leg == leg].sort_values("mar_ratio", ascending=False).head(15)[cols].round(3).to_string())
        print(P[P.leg == leg].sort_values("vs_lm", ascending=False).head(10)[cols].round(3).to_string())


if __name__ == "__main__":
    main()
