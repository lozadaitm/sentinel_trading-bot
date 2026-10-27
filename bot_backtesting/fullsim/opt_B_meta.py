"""Linea B: meta-labeling (Lopez de Prado). Un modelo, con informacion disponible AL ENTRAR, predice si la
operacion e2 gana (o su R) y eso se convierte en peso 0 / 0,5 / 1 / 1,5 x el peso base. Direccion y salidas
no cambian (base_trades()).

Modelos : logistica L2 (C=0,1) sobre variables estandarizadas; LightGBM pequeno (4 hojas, 120 arboles,
          lr 0,03, min 30 por hoja, num_threads=1); ridge sobre R (acotado a +-1).
Variables: 'todas' (opt_B_feats + direccionales firmadas por el lado) o 'pocas' (15 de regimen).
Alcance : 'junto' (un modelo, con la pata como variable) o 'pata' (Big One y Momentum por separado; NFP = 1).
Validacion en sel (2022-09 .. 2024-12, nada de 2025 ni 2026):
  cv : K=6 bloques temporales, purga + embargo de 5 dias alrededor del bloque de prueba.
  wf : walk-forward rodante: entrena con todo lo anterior (embargo 5 dias), predice el trimestre siguiente,
       desde 2023-07 (antes: peso 1).
Mapa a pesos (umbrales = cuantiles de la prediccion del modelo del pliegue sobre SU entrenamiento, por pata):
  m_cut30 : p < q30 -> 0, resto 1          m_half50 : p < q50 -> 0,5, resto 1
  m_3tr   : <q30 -> 0,5 ; >q70 -> 1,5      m_top30  : > q70 -> 1,5, resto 1
  m_cont  : 0,5 + rango (0..1) -> [0,5; 1,5]
Finalistas (--val): modelo entrenado con todo sel (<= 2024) -> 2025; umbrales = cuantiles de la prediccion
del modelo sobre sel. fit_final(cutoff) entrena con <= cutoff para aplicar despues (2026: cutoff 2025-12-31).
Uso: .venv/Scripts/python -m bot_backtesting.fullsim.opt_B_meta          (grilla en sel)
     .venv/Scripts/python -m bot_backtesting.fullsim.opt_B_meta --val NOMBRE ...   (finalistas en val)
"""
import sys
import time

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import roc_auc_score
from scipy.stats import spearmanr

from bot_backtesting.fullsim.opt_B_feats import build
from bot_backtesting.fullsim.opt_B_lib import evalw
from bot_backtesting.fullsim.opt_base import SEL, VAL, base_trades, low_priority

DIRF = ["ret1", "ret5", "ret21", "gap", "us_prev", "usdx_r24", "bvix_chg", "f_ry_d5", "f_ry_d1", "f_usd_d5",
        "f_bei_d5", "f_gvz_d5", "xag_rel", "spx_r24", "dmi", "cot_z"]
POCAS = ["s", "rv22_pct", "eff20", "adx", "atr15_atrd", "gap_side", "tod_fav", "dow", "ev_any", "bvix",
         "f_gvz_d5", "f_ry_d5_side", "usdx_r24_side", "cot_z", "perf_leg20", "leg_bo", "leg_mo"]
EMB = 5 * 86400
MAPS = ("m_cut30", "m_half50", "m_3tr", "m_top30", "m_cont")


def design(B, F):
    X = F.copy()
    for c in DIRF:
        X[f"{c}_side"] = F[c] * F.side
    return X


def make_model(kind):
    if kind == "logit":
        return LogisticRegression(C=0.1, max_iter=2000)
    if kind == "ridge":
        return Ridge(alpha=30.0)
    import lightgbm as lgb
    return lgb.LGBMClassifier(n_estimators=120, learning_rate=0.03, num_leaves=4, min_child_samples=30,
                              subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=5.0,
                              num_threads=1, verbose=-1)


class Pre:
    """imputacion por mediana + estandarizacion (aprendidas en entrenamiento)."""
    def fit(self, X):
        self.med = np.nanmedian(X, 0); Z = np.where(np.isfinite(X), X, self.med)
        self.mu = Z.mean(0); self.sd = Z.std(0) + 1e-9
        return self

    def __call__(self, X):
        return (np.where(np.isfinite(X), X, self.med) - self.mu) / self.sd


def fit_predict(kind, Xtr, ytr_win, ytr_R, Xte):
    pre = Pre().fit(Xtr)
    A, Bt = pre(Xtr), pre(Xte)
    mdl = make_model(kind)
    if kind == "ridge":
        mdl.fit(A, np.clip(ytr_R, -1, 1))
        return mdl.predict(A), mdl.predict(Bt)
    mdl.fit(A, ytr_win)
    return mdl.predict_proba(A)[:, 1], mdl.predict_proba(Bt)[:, 1]


def to_weight(p, ptr, mp):
    q30, q50, q70 = np.quantile(ptr, [0.3, 0.5, 0.7])
    if mp == "m_cut30":
        return np.where(p < q30, 0.0, 1.0)
    if mp == "m_half50":
        return np.where(p < q50, 0.5, 1.0)
    if mp == "m_3tr":
        return np.where(p < q30, 0.5, np.where(p > q70, 1.5, 1.0))
    if mp == "m_top30":
        return np.where(p > q70, 1.5, 1.0)
    rk = np.searchsorted(np.sort(ptr), p) / len(ptr)
    return 0.5 + rk


def splits_cv(t_in, t_out, K=6):
    order = np.argsort(t_in)
    blocks = np.array_split(order, K)
    for te in blocks:
        a, b = t_in[te].min(), t_out[te].max()
        tr = np.nonzero((t_out < a - EMB) | (t_in > b + EMB))[0]
        yield tr, te


def splits_wf(t_in, t_out, start="2023-07-01", end="2025-01-01"):
    qs = pd.date_range(start, end, freq="QS")
    for a, b in zip(qs[:-1], qs[1:]):
        a, b = a.timestamp(), b.timestamp()
        te = np.nonzero((t_in >= a) & (t_in < b))[0]
        tr = np.nonzero(t_out < a - EMB)[0]
        if len(te) and len(tr) > 100:
            yield tr, te


def oos(B, X, cols, kind, scope, scheme, idx):
    """predicciones fuera de muestra y pesos por mapa para las filas idx (operaciones de sel)."""
    Bi = B.iloc[idx]
    t_in, t_out = Bi.t_in.values, Bi.t_out.values
    Xa = X.iloc[idx][cols].values.astype(float)
    yw, yR = (Bi.pnl.values > 0).astype(int), Bi.R.values
    legs = Bi.leg.values
    P = np.full(len(idx), np.nan)
    W = {mp: np.ones(len(idx)) for mp in MAPS}
    groups = [("big_one", "momentum", "nfp")] if scope == "junto" else [("big_one",), ("momentum",)]
    spl = list(splits_cv(t_in, t_out) if scheme == "cv" else splits_wf(t_in, t_out))
    for g in groups:
        gm = np.isin(legs, g)
        for tr, te in spl:
            tr = tr[gm[tr]]; te = te[gm[te]]
            if len(te) == 0 or len(tr) < 60:
                continue
            ptr, pte = fit_predict(kind, Xa[tr], yw[tr], yR[tr], Xa[te])
            P[te] = pte
            for lg in g:                                  # umbrales por pata
                a, b = legs[tr] == lg, legs[te] == lg
                if a.sum() < 20 or b.sum() == 0:
                    continue
                for mp in MAPS:
                    W[mp][te[b]] = to_weight(pte[b], ptr[a], mp)
    return P, W


def quality(B, idx, P):
    Bi = B.iloc[idx]
    out = {}
    for lg in ("big_one", "momentum"):
        m = (Bi.leg.values == lg) & np.isfinite(P)
        if m.sum() > 30:
            out[f"auc_{lg}"] = roc_auc_score(Bi.pnl.values[m] > 0, P[m])
            out[f"ic_{lg}"] = spearmanr(P[m], Bi.R.values[m])[0]
    return out


def grid():
    B = base_trades(); F = build(); X = design(B, F)
    todas = [c for c in X.columns if c not in ("w0",)]
    sets = {"todas": todas, "pocas": POCAS}
    idx = np.nonzero(B.t.values < SEL[1].timestamp())[0]          # 2022-09 .. 2024-12 (sel + calentamiento)
    rows, n, t0 = [], 0, time.time()
    for kind in ("logit", "lgbm", "ridge"):
        for fs, cols in sets.items():
            for scope in ("junto", "pata"):
                for scheme in ("cv", "wf"):
                    P, W = oos(B, X, cols, kind, scope, scheme, idx)
                    q = quality(B, idx, P)
                    for mp in MAPS:
                        m = np.ones(len(B)); m[idx] = W[mp]
                        name = f"meta {kind} {fs} {scope} {scheme} {mp}"
                        prm = dict(kind=kind, fs=fs, scope=scope, scheme=scheme, map=mp, **{k: round(v, 3) for k, v in q.items()})
                        r = evalw(B, B.w.values * m, name, prm)
                        n += 1
                        rows.append(dict(name=name, **prm, mar_ratio=r["mar_ratio"], edge_lm=r["edge_lm"],
                                         r2023=r["r2023"], r2024=r["r2024"], dia=r["peor_dia_c"], mes=r["peor_mes_c"],
                                         expo=r["expo"]))
                        print(f"{n:4d} {name:40s} {q} MAR x{r['mar_ratio']:.3f} edge {r['edge_lm']:.3f} "
                              f"23 {r['r2023']:.2f} 24 {r['r2024']:.2f} ({time.time()-t0:.0f}s)", flush=True)
    pd.DataFrame(rows).to_csv("bot_backtesting/fullsim/results/opt_B_meta_grid.csv", index=False)


def fit_final(kind, fs, scope, mp, cutoff, B=None, F=None):
    """Entrena con operaciones cerradas <= cutoff (t_out) y devuelve f(rows)->multiplicador para las
    operaciones con t_in > cutoff. Umbrales = cuantiles de la prediccion sobre el propio entrenamiento."""
    B = base_trades() if B is None else B
    F = build() if F is None else F
    X = design(B, F)
    cols = [c for c in X.columns if c != "w0"] if fs == "todas" else POCAS
    cut = pd.Timestamp(cutoff).timestamp()
    tr_all = np.nonzero(B.t_out.values <= cut)[0]
    groups = [("big_one", "momentum", "nfp")] if scope == "junto" else [("big_one",), ("momentum",)]
    models = []
    for g in groups:
        tr = tr_all[np.isin(B.leg.values[tr_all], g)]
        Xa = X.iloc[tr][cols].values.astype(float)
        pre = Pre().fit(Xa)
        mdl = make_model(kind)
        if kind == "ridge":
            mdl.fit(pre(Xa), np.clip(B.R.values[tr], -1, 1)); ptr = mdl.predict(pre(Xa))
        else:
            mdl.fit(pre(Xa), (B.pnl.values[tr] > 0).astype(int)); ptr = mdl.predict_proba(pre(Xa))[:, 1]
        thr = {lg: ptr[B.leg.values[tr] == lg] for lg in g}
        models.append((g, pre, mdl, thr))

    def apply(rows_idx):
        m = np.ones(len(rows_idx))
        legs = B.leg.values[rows_idx]
        for g, pre, mdl, thr in models:
            for lg in g:
                j = np.nonzero(legs == lg)[0]
                if len(j) == 0 or len(thr[lg]) < 20:
                    continue
                Z = pre(X.iloc[rows_idx[j]][cols].values.astype(float))
                p = mdl.predict(Z) if kind == "ridge" else mdl.predict_proba(Z)[:, 1]
                m[j] = to_weight(p, thr[lg], mp)
        return m
    return apply


def weights_period(name, per_start, per_end, cutoff):
    """Columna de pesos completa: base fuera de [per_start, per_end); modelo (entrenado <= cutoff) dentro."""
    _, kind, fs, scope, _scheme, mp = name.split()
    B = base_trades()
    f = fit_final(kind, fs, scope, mp, cutoff, B)
    j = np.nonzero((B.t.values >= pd.Timestamp(per_start).timestamp()) & (B.t.values < pd.Timestamp(per_end).timestamp()))[0]
    m = np.ones(len(B)); m[j] = f(j)
    return B.w.values * m


if __name__ == "__main__":
    low_priority()
    if len(sys.argv) > 1 and sys.argv[1] == "--val":
        B = base_trades()
        for nm in sys.argv[2:]:
            w = weights_period(nm, VAL[0], VAL[1], "2024-12-31")
            r = evalw(B, w, nm + " |val", "modelo<=2024", per="val", boot=True)
            print(nm, {k: round(v, 3) if isinstance(v, float) else v for k, v in r.items()})
    else:
        grid()
