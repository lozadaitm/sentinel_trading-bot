"""Evaluacion final de la sesion de optimizacion e2 (27-oct-2026): los 3 mejores candidatos en 2026.

Candidatos (fijados con datos <= 2025, sin tocarlos despues de mirar 2026):
  U1    (linea B): peso de la Big One 0,75 fijo (sin mirar la tendencia ni el dia de noticia).
  F1    (linea C): Big One con peso 0 si vpct >= 0,5 (ATR_D/precio sobre su mediana de 252 dias); resto vigente.
  U1+F1 (linea G): las dos a la vez.
Para cada uno y cada periodo (sel, val, test=2026): MAR vs base, vs base con lote mayor (misma caida),
nulo de dias al azar (quitar las mismas Big One al azar, 500 veces), bootstrap por bloques de dias
(peor dia/mes p05, P(caida > 30/40 %)), y cuentas de 3 000 / 10 000 / 25 000.
Ademas: conteo total de variantes del registro, Benjamini-Hochberg y Deflated Sharpe.
Uso: E2OPT_FINAL=1 .venv/Scripts/python -m bot_backtesting.fullsim.opt_final
"""
import os

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.opt_base import (RESULTS, _mar_fast, base_trades, bh, compare, daily_R,
                                              deflated_sharpe, evaluate, load_registry, low_priority, period,
                                              register)
from bot_backtesting.fullsim.opt_G_hora_combos import w_f1, w_u1

CANDS = {"U1": lambda T: w_u1(T), "F1": lambda T: w_f1(T), "U1+F1": lambda T: w_f1(T, w_u1(T))}


def null_random_days(B, w, per, n=500, seed=5):
    """Mismo numero de Big One a peso 0 (o al peso del candidato) pero en dias al azar, dentro del periodo."""
    a, b = period(per)
    m = (B.t >= a.timestamp()) & (B.t < b.timestamp()) & (B.leg == "big_one")
    idx = np.nonzero(m.values)[0]
    rng = np.random.default_rng(seed); out = []
    for _ in range(n):
        ww = B.w.values.copy()
        ww[idx] = rng.permutation(w[idx])
        C = B.assign(wN=ww)
        out.append(evaluate(C, per, wcol="wN")["mar"])
    return np.array(out)


def boot_risk(T, per, wcol, n=4000, block=10, seed=9):
    x = daily_R(T, per, wcol).values
    nd = len(x); nb = int(np.ceil(252 / block)); rng = np.random.default_rng(seed)
    s = rng.integers(0, nd - block, size=(n, nb)); I = (s[:, :, None] + np.arange(block)).reshape(n, -1)[:, :252]
    X = x[I]
    mar, cagr, dd = _mar_fast(X)
    day = (0.08 * X).min(1)
    mon = np.array([(np.prod(1 + 0.08 * X[:, k:k + 21], 1) - 1) for k in range(0, 252 - 20, 21)]).min(0)
    return dict(p_dd30=(dd > .3).mean(), p_dd40=(dd > .4).mean(), dd_p50=np.median(dd), peor_dia_p05=np.quantile(day, .05),
                peor_mes_p05=np.quantile(mon, .05), x12_p50=np.median(1 + cagr))


def multiple_testing(cands):
    R = load_registry()
    R = R[~R.get("params", pd.Series("", index=R.index)).astype(str).str.contains("migrado")]
    tot = len(R)
    by = R.groupby("line").size().to_dict()
    P = R[pd.to_numeric(R.p, errors="coerce").notna()]
    p = pd.to_numeric(P.p).values
    disc = bh(p, q=0.10)
    print(f"variantes en el registro: {tot} {by}; con bootstrap: {len(p)}; descubrimientos BH(q=0,10): {disc.sum()}")
    sr = pd.to_numeric(R.sharpe_c, errors="coerce").dropna() / np.sqrt(252)
    return tot, by, len(p), int(disc.sum()), float(sr.var())


def main():
    low_priority()
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40)
    B = base_trades()
    tot, by, n_p, n_disc, sr_var = multiple_testing(CANDS)
    rows, risk, accts = [], [], []
    for name, fn in CANDS.items():
        C = B.copy(); C["wc"] = fn(C)
        for per in ("sel", "val", "test"):
            r = compare(C, B, per, name, wcol="wc")
            nul = null_random_days(B, C.wc.values, per) if name != "U1" else np.array([np.nan])
            r["nulo_pct"] = float((nul < r["mar_c"]).mean()) if name != "U1" else np.nan
            r["nulo_mediana"] = float(np.nanmedian(nul))
            if per == "test":
                register("final", name, r, dict(per=per))
            rows.append(r)
            risk.append(dict(cand=name, per=per, **boot_risk(C, per, "wc")))
            if per == "test":
                for bal in (3000, 10000, 25000):
                    mc, mb = evaluate(C, per, bal0=bal, wcol="wc"), evaluate(B, per, bal0=bal)
                    accts.append(dict(cand=name, cuenta=bal, x_c=mc["x"], dd_c=mc["dd"], x_b=mb["x"], dd_b=mb["dd"],
                                      mar_c=mc["mar"], mar_b=mb["mar"]))
        # Deflated Sharpe en sel+val (lo usado para elegir), con todas las variantes probadas
        a, b = period("selval")
        x = daily_R(C, "selval", "wc").values * 0.08
        srd = x.mean() / x.std()
        from scipy.stats import kurtosis, skew
        dsr, sr0 = deflated_sharpe(srd, tot, len(x), skew(x), kurtosis(x, fisher=False), sr_var)
        rows.append(dict(label=name, per="DSR selval", sharpe_c=srd * np.sqrt(252), p=1 - dsr, mar_c=sr0 * np.sqrt(252)))
    for per in ("sel", "val", "test"):
        risk.append(dict(cand="base", per=per, **boot_risk(B.assign(wc=B.w), per, "wc")))
    S = pd.DataFrame(rows); K = pd.DataFrame(risk); A = pd.DataFrame(accts)
    cols = ["label", "per", "mar_c", "mar_b", "mar_ratio", "cagr_c", "cagr_b", "dd_c", "dd_b", "cagr_lote_mayor",
            "f_lote_mayor", "peor_dia_c", "peor_dia_b", "peor_mes_c", "peor_mes_b", "n_c", "p", "nulo_pct", "nulo_mediana", "sharpe_c"]
    print(S[[c for c in cols if c in S]].round(3).to_string(index=False))
    print(K.round(3).to_string(index=False))
    print(A.round(3).to_string(index=False))
    pd.to_pickle((S, K, A, dict(total=tot, por_linea=by, con_p=n_p, bh=n_disc)), os.path.join(RESULTS, "opt_final.pkl"))


if __name__ == "__main__":
    main()
