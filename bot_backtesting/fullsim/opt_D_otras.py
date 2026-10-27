"""Linea D, ideas 1b, 4 y 5 (misma senal e2, otro momento/precio de entrada). Grilla en 'sel', todo registrado.
  twap    : repartir la entrada en tramos a mercado (Big One: 01:01 / 01:05 / 01:10 / 01:15 / 01:30;
            Momentum y NFP: +0 / +5 / +10 / +15 / +30 min) y entradas simplemente retrasadas (un solo tramo).
  mom_pre : Momentum con la senal y la entrada adelantadas a 14:45 o 14:30 (open de esa vela M15, mismo umbral
            0,232 %, misma salida 21:00). Cambia algo el conjunto de dias (la senal se mide antes).
  qlim    : Big One con limite en un cuantil PREDICHO de la profundidad del minimo de la primera hora
            (regresion por cuantiles lineal, walk-forward mensual con datos anteriores; antes de 120 casos usa el
            cuantil incondicional del pasado). Info previa a 01:01: ATR15/ATR_D, gap 23:45->01:00, rango y
            retorno del dia anterior, rango de la ultima hora del dia anterior, dia de semana, s, noticia.
Correr:  .venv/Scripts/python -m bot_backtesting.fullsim.opt_D_otras twap|mom_pre|qlim
"""
import itertools
import os
import sys
import time

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.opt_base import (RESULTS, SLIP, compare, entries, low_priority, m15, register,
                                              spread_at, swap_cost)
from bot_backtesting.fullsim.opt_D_common import _end_ok, load, raw_cache, sim
from bot_backtesting.fullsim.opt_D_limite import run_plan

KEYS = ("mar_c", "mar_b", "mar_ratio", "cagr_c", "dd_c", "peor_dia_c", "peor_mes_c", "peor_dia_b", "peor_mes_b",
        "n_leg_c", "n_leg_b", "fill_frac", "pasa")


def twap():
    E, raws, B = load()
    rows = []
    sched = {"big_one": {"d5": [(4, 1)], "d10": [(9, 1)], "d15": [(14, 1)], "d30": [(29, 1)],
                         "t2_0_5": [(0, .5), (4, .5)], "t3_0_5_10": [(0, 1 / 3), (4, 1 / 3), (9, 1 / 3)],
                         "t4_0_15": [(0, .25), (4, .25), (9, .25), (14, .25)], "t3_5_15": [(4, 1 / 3), (9, 1 / 3), (14, 1 / 3)]},
             "momentum": {"d5": [(5, 1)], "d10": [(10, 1)], "d15": [(15, 1)], "d30": [(30, 1)],
                          "t2_0_5": [(0, .5), (5, .5)], "t3_0_5_10": [(0, 1 / 3), (5, 1 / 3), (10, 1 / 3)],
                          "t4_0_15": [(0, .25), (5, .25), (10, .25), (15, .25)], "t3_5_15": [(5, 1 / 3), (10, 1 / 3), (15, 1 / 3)]}}
    sched["nfp"] = sched["momentum"]
    for leg, d in sched.items():
        for k, lv in d.items():
            for anc in ("new", "orig"):
                plan = dict(kind="twap", levels=lv, anchor=anc)
                name = f"twap_{leg}_{k}_{anc}"
                res, _ = run_plan(E, raws, B, leg, plan, name)
                rows.append(dict(name=name, leg=leg, sched=k, anchor=anc, **{kk: res[kk] for kk in KEYS}))
    return pd.DataFrame(rows)


def mom_entries(t_sig_off):
    """Momentum con senal y entrada en la vela M15 de las 15:00 - t_sig_off (s)."""
    E = entries()
    X, D = m15()
    T, O = X.time.values, X.open.values
    idx = pd.Series(np.arange(len(T)), index=T)
    Mo = E[E.leg == "momentum"]
    rows = []
    # mismos dias candidatos que el Momentum vigente lo permita (habil, no festivo, s=+-2): se recorren los dias
    # con datos y se aplica la regla con el open adelantado.
    from bot_backtesting.fullsim.opt_base import _us_holidays, _news
    hol = _us_holidays(); evd, _ = _news()
    for k in np.nonzero(T % 86400 == 15 * 3600 - t_sig_off)[0]:
        d = T[k] // 86400
        if (d + 3) % 7 >= 5 or d not in D.index or not np.isfinite(D.at[d, "atrd"]) or not np.isfinite(X.atr15.iat[k]):
            continue
        k15 = idx.get(d * 86400 + 15 * 3600); k1 = idx.get(d * 86400 + 3600)
        if k15 is None or k1 is None or k15 + 24 > len(T):
            continue
        s = D.at[d, "s"]
        if s not in (2, -2) or d in hol:
            continue
        a = (O[k] - O[k1]) / O[k1] * 100
        if abs(a) <= 0.5 * 0.464:
            continue
        side = int(np.sign(a))
        t_out = T[k15 + 23] + 900
        spr = float(spread_at(T[k]))
        px = O[k] + spr + SLIP if side == 1 else O[k] - SLIP
        rows.append(dict(leg="momentum", t=T[k], t_in=T[k], t_out=t_out, side=side, w=1.0, state=s, ev=int(d in evd),
                         atrd=D.at[d, "atrd"], atr15=X.atr15.iat[k], mid0=O[k], k15=k, spr_in=spr,
                         spr_out=float(spread_at(t_out - 60)), px=px, swap=swap_cost(T[k], t_out, side),
                         day=pd.Timestamp(d, unit="D")))
    return pd.DataFrame(rows)


def mom_pre():
    E, raws, B = load()
    rows = []
    for off in (900, 1800):
        M = mom_entries(off)
        Ms, rs = raw_cache(M, f"mom_pre{off}")
        C = sim(Ms, rs)
        T = pd.concat([B[B.leg != "momentum"], C]).sort_values("t").reset_index(drop=True)
        name = f"mom_pre_{off // 60}min"
        res = compare(T, B, "sel", label=name, boot=False)
        nb = B[(B.leg == "momentum")]
        same = len(set(Ms.day[Ms.t < pd.Timestamp('2025-01-01').timestamp()]) & set(nb.day[nb.t < pd.Timestamp('2025-01-01').timestamp()]))
        res["n_leg_c"] = int((Ms.t < pd.Timestamp('2025-01-01').timestamp()).sum()); res["dias_comunes"] = same
        register("D", name, res, dict(off=off))
        rows.append(dict(name=name, **{k: res.get(k) for k in KEYS if k in res}, dias_comunes=same))
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ cuantil predicho (Big One)
def bo_features(E, raws):
    X, D = m15()
    T, H, L, C = X.time.values, X.high.values, X.low.values, X.close.values
    rows = []
    for r, R in zip(E.itertuples(index=False), raws):
        if r.leg != "big_one":
            continue
        k = r.k15
        i0, i1 = max(k - 92, 0), k                     # sesion previa (~23 h de velas M15)
        ph, pl, pc = H[i0:i1].max(), L[i0:i1].min(), C[k - 1]
        po = X.open.values[i0]
        j0 = max(k - 5, 0)
        lh = H[j0:k].max() - L[j0:k].min()
        tt = R["tt"]; i = R["i_in"]
        j1 = int(np.searchsorted(tt, r.t_in + 3600))
        y = np.nan
        if j1 > i:
            y = ((R["l"][i:j1] + R["smax"][i:j1]).min() - r.px) / r.atr15
        rows.append(dict(t=r.t, a15d=r.atr15 / r.atrd, latrd=np.log(r.atrd), gap=(r.mid0 - pc) / r.atrd,
                         prng=(ph - pl) / r.atrd, pret=(pc - po) / r.atrd, lhr=lh / r.atr15,
                         dow=(r.t // 86400 + 3) % 7, s=r.state if np.isfinite(r.state) else 0, ev=r.ev, y=y))
    return pd.DataFrame(rows)


def q_predict(F, q, min_n=120):
    """Walk-forward mensual: para cada mes, ajusta con los meses anteriores. Devuelve la profundidad predicha."""
    from sklearn.linear_model import QuantileRegressor
    cols = ["a15d", "latrd", "gap", "prng", "pret", "lhr", "s", "ev"]
    F = F.copy()
    F["m"] = pd.to_datetime(F.t, unit="s").dt.to_period("M")
    F[[f"d{k}" for k in range(5)]] = np.eye(5)[F.dow.clip(0, 4).astype(int)]
    cols += [f"d{k}" for k in range(1, 5)]
    pred = np.full(len(F), np.nan); unc = np.full(len(F), np.nan)
    for m in F.m.unique():
        tr = F[(F.m < m) & F.y.notna()]
        te = (F.m == m).values
        if len(tr) == 0:
            continue
        unc[te] = np.quantile(tr.y, q)
        if len(tr) < min_n:
            pred[te] = unc[te]; continue
        mu, sd = tr[cols].mean(), tr[cols].std().replace(0, 1)
        qr = QuantileRegressor(quantile=q, alpha=0.0, solver="highs").fit((tr[cols] - mu) / sd, tr.y)
        pred[te] = qr.predict((F.loc[te, cols] - mu) / sd)
    return pred, unc


def pinball(y, p, q):
    e = y - p
    return float(np.nanmean(np.maximum(q * e, (q - 1) * e)))


def qlim():
    E, raws, B = load()
    F = bo_features(E, raws)
    rows = []
    sel_m = (F.t < pd.Timestamp("2025-01-01").timestamp()).values & (F.t >= pd.Timestamp("2023-01-01").timestamp()).values
    for q in (0.3, 0.5, 0.7):
        pred, unc = q_predict(F, q)
        ok = sel_m & F.y.notna().values
        print(f"q={q} pinball modelo {pinball(F.y.values[ok], pred[ok], q):.4f}  incondicional {pinball(F.y.values[ok], unc[ok], q):.4f}"
              f"  corr(pred,y) {np.corrcoef(pred[ok], F.y.values[ok])[0, 1]:.3f}", flush=True)
        for src, vals in (("modelo", pred), ("incond", unc)):
            Eq = E.copy()
            dep = pd.Series(np.maximum(-vals, 0), index=F.t.values)   # profundidad >= 0 en ATR15
            Eq["xq"] = Eq.t.map(dep).fillna(0.0).values * Eq.atr15.values
            for fb, N, anc in itertools.product(("lost", "mkt"), (60,), ("new", "orig")):
                plan = dict(kind="limit", u="col:xq", levels=[(1.0, 1.0)], N=N, fb=fb, anchor=anc)
                name = f"qlim_bo_q{q}_{src}_N{N}_{fb}_{anc}"
                res, _ = run_plan(Eq, raws, B, "big_one", plan, name)
                rows.append(dict(name=name, q=q, src=src, fb=fb, anchor=anc, **{kk: res[kk] for kk in KEYS}))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    low_priority()
    fam = sys.argv[1] if len(sys.argv) > 1 else "twap"
    t0 = time.time()
    G = {"twap": twap, "mom_pre": mom_pre, "qlim": qlim}[fam]()
    G.to_csv(os.path.join(RESULTS, f"optD_grid_{fam}.csv"), index=False)
    pd.set_option("display.width", 250)
    print(G.sort_values("mar_ratio", ascending=False).round(3).to_string(index=False))
    print("variantes", len(G), f"{time.time()-t0:.0f}s")
