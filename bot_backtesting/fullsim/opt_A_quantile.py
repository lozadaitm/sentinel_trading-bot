"""Linea A - idea 1: TP proyectado por regresion de cuantiles del maximo favorable (antes del candado)
hasta la hora de salida, con informacion disponible AL ENTRAR. Solo simulacion, 2026 excluido.

Modelos: lightgbm objective='quantile' (num_threads=1, arboles chicos) y statsmodels QuantReg (lineal).
Objetivo: MFE / ATR15 (recortado a [0, 20]). Variables (todas conocidas al entrar): pata, lado, tendencia s,
s*lado, dia de noticia, dia de semana, ATR_D, ATR15/ATR_D, rango del dia anterior/ATR_D, rango del dia hasta
la entrada/ATR_D, retorno del dia hasta la entrada, del dia anterior y de 5 dias (en ATR_D y por el lado),
hueco de apertura/ATR_D, vol realizada de 48 velas M15 / ATR_D.
Walk-forward mensual expansivo con purga (solo operaciones cerradas antes del mes) y embargo de 5 dias; minimo
150 operaciones de entrenamiento (antes de eso, TP vigentes 2 y 3 x ATR15).
TP de los tercios 2 y 3 = cuantiles qa y qb previstos (x ATR15), minimo 0,5 x ATR15. Tercio 1: hora.
Uso: .venv/Scripts/python -m bot_backtesting.fullsim.opt_A_quantile
"""
import os
import time

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.opt_base import RESULTS, VAL, base_trades, compare, entries, low_priority, m15, register
from bot_backtesting.fullsim.opt_A_common import cache_paths, manage, run_fn, years

QS = (0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8)
EMBARGO = 5 * 86400
MIN_TRAIN = 150


def features(cache):
    X, D = m15()
    T, O, H, L, C = (X[c].values for c in ("time", "open", "high", "low", "close"))
    Dd = D.copy()
    rows = []
    for r, P in cache:
        k = r.k15
        d = int(T[k] // 86400)
        sd = r.side
        i0 = np.searchsorted(T, d * 86400)
        hp = H[i0:k].max() if k > i0 else np.nan
        lp = L[i0:k].min() if k > i0 else np.nan
        prev = Dd.loc[:d - 1].tail(6)
        pr = prev.iloc[-1] if len(prev) else None
        tr48 = np.mean(H[k - 48:k] - L[k - 48:k])
        rows.append(dict(
            t=r.t, leg=r.leg, legc={"big_one": 0, "momentum": 1, "nfp": 2}[r.leg], side=sd, s=r.state,
            s_side=r.state * sd, ev=r.ev, dow=(d + 3) % 7, atrd=r.atrd, a15d=r.atr15 / r.atrd,
            prev_rng=(pr.H - pr.L) / r.atrd if pr is not None else np.nan,
            today_rng=(hp - lp) / r.atrd if k > i0 else 0.0,
            today_ret=sd * (O[k] - O[i0]) / r.atrd if k > i0 else 0.0,
            prev_ret=sd * (pr.C - pr.O) / r.atrd if pr is not None else np.nan,
            ret5=sd * (pr.C - prev.iloc[0].O) / r.atrd if len(prev) >= 5 else np.nan,
            gap=sd * (O[k] - C[k - 1]) / r.atrd,
            rv48=tr48 / r.atrd,
        ))
    F = pd.DataFrame(rows)
    # objetivo: MFE antes del candado hasta la hora
    y = []
    for r, P in cache:
        nb = P["nb"]
        lk = np.nonzero(P["adv"][:nb] <= -r.atrd)[0]
        il = lk[0] if len(lk) else nb
        y.append(P["fav"][:il].max() / r.atr15 if il > 0 else 0.0)
    F["y"] = np.clip(y, 0, 20)
    F["t_out"] = [r.t_out for r, _ in cache]
    return F


FEATS = ["legc", "side", "s", "s_side", "ev", "dow", "atrd", "a15d", "prev_rng", "today_rng", "today_ret",
         "prev_ret", "ret5", "gap", "rv48"]


def fit_predict(F, model="lgb"):
    """Predicciones walk-forward mensuales para cada cuantil. Devuelve DataFrame (n, len(QS)) con NaN donde no
    hay entrenamiento suficiente."""
    import lightgbm as lgb
    import statsmodels.api as sm
    months = pd.to_datetime(F.t, unit="s").dt.to_period("M")
    pred = np.full((len(F), len(QS)), np.nan)
    for m in sorted(months.unique()):
        te = np.nonzero((months == m).values)[0]
        t_start = m.start_time.timestamp()
        tr = np.nonzero((F.t_out.values < t_start - EMBARGO))[0]
        if len(tr) < MIN_TRAIN:
            continue
        Xtr = F.iloc[tr][FEATS].fillna(0.0).values; ytr = F.y.values[tr]
        Xte = F.iloc[te][FEATS].fillna(0.0).values
        for j, q in enumerate(QS):
            if model == "lgb":
                mdl = lgb.LGBMRegressor(objective="quantile", alpha=q, n_estimators=150, learning_rate=0.03,
                                        num_leaves=7, min_child_samples=30, subsample=0.8, subsample_freq=1,
                                        colsample_bytree=0.8, num_threads=1, verbose=-1, random_state=1)
                mdl.fit(Xtr, ytr)
                pred[te, j] = mdl.predict(Xte)
            else:
                mu, sdv = Xtr.mean(0), Xtr.std(0) + 1e-9
                A = sm.add_constant((Xtr - mu) / sdv, has_constant="add")
                res = sm.QuantReg(ytr, A).fit(q=q, max_iter=2000)
                pred[te, j] = sm.add_constant((Xte - mu) / sdv, has_constant="add") @ res.params
    return pd.DataFrame(pred, columns=[f"q{q}" for q in QS])


def pinball(y, p, q):
    e = y - p
    return np.mean(np.maximum(q * e, (q - 1) * e))


def main():
    low_priority()
    t0 = time.time()
    C = cache_paths(entries(), "e2")
    B = base_trades()
    F = features(C)
    out = []
    for model in ("lgb", "qr"):
        fp = os.path.join(RESULTS, f"optA_qpred_{model}.pkl")
        if os.path.exists(fp):
            Pq = pd.read_pickle(fp)
        else:
            Pq = fit_predict(F, model); Pq.to_pickle(fp)
        print(f"{model} predicciones listas ({time.time()-t0:.0f}s)", flush=True)
        # calidad fuera de muestra (sel, con prediccion) vs cuantil constante de entrenamiento expansivo
        ok = np.isfinite(Pq.iloc[:, 0].values) & (F.t.values < VAL[0].timestamp())
        for j, q in enumerate(QS):
            yv = F.y.values[ok]
            const = np.array([np.quantile(F.y.values[:i][F.t_out.values[:i] < F.t.values[i] - EMBARGO], q)
                              for i in np.nonzero(ok)[0]])
            print(f"  q{q}: pinball modelo {pinball(yv, Pq.iloc[:, j].values[ok], q):.3f}  constante "
                  f"{pinball(yv, const, q):.3f}  corr(pred,y) {np.corrcoef(Pq.iloc[:, j].values[ok], yv)[0, 1]:.3f}")
        key = dict(zip(zip(F.leg, F.t), range(len(F))))
        for qa, qb in ((0.2, 0.4), (0.3, 0.5), (0.3, 0.6), (0.4, 0.6), (0.3, 0.7), (0.5, 0.7), (0.4, 0.8),
                       (0.5, 0.8), (0.6, 0.8)):
            ja, jb = QS.index(qa), QS.index(qb)

            def fn(P, r, lock_k=1.0, _ja=ja, _jb=jb, _Pq=Pq):
                i = key[(r.leg, r.t)]
                a, b = _Pq.iat[i, _ja], _Pq.iat[i, _jb]
                if not np.isfinite(a):
                    a, b = 2.0, 3.0
                a, b = max(a, 0.5), max(b, 0.5)
                return manage(P, r, rules=({"k": "time"}, {"k": "tp", "m": a}, {"k": "tp", "m": b}), lock_k=lock_k)
            T = run_fn(C, fn)
            name = f"{model}_q{qa}_q{qb}"
            res = compare(T, B, "sel", label=name, boot=False)
            register("A", f"Q1:{name}", res, dict(model=model, qa=qa, qb=qb, min_train=MIN_TRAIN, embargo_d=5))
            y = years(T, B)
            print(f"Q1 {name:20s} MAR {res['mar_c']:.2f} x{res['mar_ratio']:.3f} CAGR {res['cagr_c']:.2f} dd "
                  f"{res['dd_c']:.3f} dia {res['peor_dia_c']:.3f} mes {res['peor_mes_c']:.3f} 23 x{y[2023][2]:.2f} "
                  f"24 x{y[2024][2]:.2f}", flush=True)
            out.append(dict(fam="Q1", name=name, mar=res["mar_c"], ratio=res["mar_ratio"], cagr=res["cagr_c"],
                            dd=res["dd_c"], pdia=res["peor_dia_c"], pmes=res["peor_mes_c"], r23=y[2023][2],
                            r24=y[2024][2]))
    pd.DataFrame(out).to_csv(os.path.join(RESULTS, "optA_quantile.csv"), index=False)


if __name__ == "__main__":
    main()
