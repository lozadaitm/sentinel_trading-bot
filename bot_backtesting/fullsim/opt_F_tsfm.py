"""Linea F (27-oct-2026): MODELOS FUNDACIONALES de series temporales (zero-shot) como filtro de las patas e2.

Que prueba:
  Para cada dia habil (2021-09 -> 2025-12; nada de 2026) y cada ventana de pata se pide al modelo la prevision
  del precio M15 con SOLO las 512 velas M15 cerradas antes de la entrada:
    * Big One: contexto hasta la vela de las 23:45 del dia anterior, horizonte 36 velas (01:00 -> 10:00).
    * Momentum: contexto hasta la vela de las 14:45, horizonte 24 velas (15:00 -> 21:00).
  Serie: cierres M15 del broker (desde 2022-08-17) y antes Dukascopy M15 + desfase diario al broker.
  De cada prevision salen dos caracteristicas:
    mu  = mediana prevista al final del horizonte / ultimo cierre - 1   (retorno previsto de la ventana)
    sig = (q90 - q10) al final del horizonte / ultimo cierre            (dispersion prevista = volatilidad)
  Modelos: amazon/chronos-bolt-tiny, amazon/chronos-bolt-small, amazon/chronos-2.
  Nulos triviales con la MISMA interfaz (mu, sig): media estacional (retorno medio de la misma ventana en los 60 dias
  previos; rango medio de 22 dias), AR(1) sobre retornos M15 del contexto, HAR sobre el rango de la ventana
  (1/5/22 dias, MCO con historia previa).
  Calidad: correlacion de rango (Spearman) con el retorno y con el rango realizados de la ventana (sel).
  Filtro: percentil pasado (252 dias habiles, misma hora) de mu o sig; pata x0 en la zona mala. Sobre la base y
  sobre F1 de la linea C. Ademas reglas naturales: Big One off si mu<0; Momentum off si lado*mu<0.

Correr:  .venv/Scripts/python -m bot_backtesting.fullsim.opt_F_tsfm infer   (previsiones -> results/opt_F_tsfm_fc.pkl)
         .venv/Scripts/python -m bot_backtesting.fullsim.opt_F_tsfm eval    (calidad + grilla en sel)
"""
import os
import sys
import time

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.opt_base import DATA, RESULTS, VAL, base_trades, compare, evaluate, low_priority, m15, period, register

FC = os.path.join(RESULTS, "opt_F_tsfm_fc.pkl")
GRID = os.path.join(RESULTS, "opt_F_tsfm_grid.pkl")
DAY = 86400
L_CTX = 512
WIN = {"bo": (3600, 36), "mom": (15 * 3600, 24)}
MODELS = ["amazon/chronos-bolt-tiny", "amazon/chronos-bolt-small", "amazon/chronos-2"]


def series():
    """Cierres/maximos/minimos M15 continuos (time, c, h, l): duka + desfase diario antes del broker."""
    X, _ = m15()
    d15 = pd.read_pickle(os.path.join(DATA, "frames_duka.pkl"))["M15"]
    m = X[["time", "close"]].merge(d15[["time", "close"]], on="time", suffixes=("_b", "_d"))
    m = m[(m.time % 86400) >= 7200]
    off = (m.close_b - m.close_d).groupby(m.time // 86400).median()
    t5 = X.time.min()
    a = d15[d15.time < t5].copy()
    o = off.reindex(a.time // 86400).values
    o = np.where(np.isfinite(o), o, off.iloc[:20].median())
    for c in ("open", "high", "low", "close"):
        a[c] = a[c].values + o
    S = pd.concat([a[["time", "open", "high", "low", "close"]], X[["time", "open", "high", "low", "close"]]])
    S = S[S.time < VAL[1].timestamp()].sort_values("time").reset_index(drop=True)
    return S


def queries(S):
    days = pd.bdate_range("2021-09-01", "2025-12-31")
    d0 = (days - pd.Timestamp(0)).days.values * DAY
    T = S.time.values
    rows = []
    for w, (hod, H) in WIN.items():
        for d in d0:
            tau = d + hod
            i = np.searchsorted(T, tau)             # primera vela con time >= tau
            if i < L_CTX or i + H > len(T) or T[i] != tau:
                continue
            if T[i + H - 1] - T[i] > (H - 1) * 900 + 3 * 3600:   # ventana con huecos grandes
                continue
            rows.append((w, tau, i, H))
    return pd.DataFrame(rows, columns=["win", "tau", "i", "H"])


def realized(S, Q):
    C, Hh, Ll, O = S.close.values, S.high.values, S.low.values, S.open.values
    last = C[Q.i.values - 1]
    ret = np.array([C[i + H - 1] for i, H in zip(Q.i, Q.H)]) / last - 1
    rng = np.array([Hh[i:i + H].max() - Ll[i:i + H].min() for i, H in zip(Q.i, Q.H)]) / last
    return last, ret, rng


def run_chronos(model, S, Q, bs=64):
    import torch
    from chronos import BaseChronosPipeline
    torch.set_num_threads(2)
    pipe = BaseChronosPipeline.from_pretrained(model, device_map="cpu", torch_dtype=torch.float32)
    C = S.close.values.astype(np.float32)
    mu = np.full(len(Q), np.nan); sig = np.full(len(Q), np.nan)
    t0 = time.time()
    for w in Q.win.unique():
        idx = np.nonzero(Q.win.values == w)[0]
        H = int(Q.H.values[idx[0]])
        for k in range(0, len(idx), bs):
            b = idx[k:k + bs]
            ctx = [torch.tensor(C[Q.i.values[j] - L_CTX:Q.i.values[j]]) for j in b]
            q, _ = pipe.predict_quantiles(ctx, prediction_length=H, quantile_levels=[0.1, 0.5, 0.9])
            if isinstance(q, list):
                q = torch.stack([x.squeeze(0) if x.dim() == 3 else x for x in q])
            q = q.numpy()                                  # (B, H, 3)
            last = np.array([C[Q.i.values[j] - 1] for j in b])
            mu[b] = q[:, -1, 1] / last - 1
            sig[b] = (q[:, -1, 2] - q[:, -1, 0]) / last
    dt = time.time() - t0
    return mu, sig, dt


def trivial(S, Q, last, ret, rng):
    """Nulos baratos con la misma interfaz: media estacional, AR(1) y HAR. Solo informacion previa a tau."""
    out = {}
    C = S.close.values
    for nm in ("seas", "ar1", "har"):
        out[nm] = (np.full(len(Q), np.nan), np.full(len(Q), np.nan))
    for w in Q.win.unique():
        idx = np.nonzero(Q.win.values == w)[0]
        r, g = ret[idx], rng[idx]
        for n, j in enumerate(idx):
            # media estacional: misma ventana, 60 dias previos (los realizados de dias anteriores ya se conocen)
            if n >= 22:
                out["seas"][0][j] = r[max(0, n - 60):n].mean()
                out["seas"][1][j] = g[n - 22:n].mean()
            # AR(1) en retornos M15 del contexto -> suma de previsiones h pasos; sig = desvio * sqrt(H)
            i, H = Q.i.values[j], Q.H.values[j]
            x = np.diff(np.log(C[i - L_CTX:i]))
            phi = np.dot(x[1:] - x.mean(), x[:-1] - x.mean()) / max(np.dot(x[:-1] - x.mean(), x[:-1] - x.mean()), 1e-18)
            mu_h = x.mean() * H + (x[-1] - x.mean()) * phi * (1 - phi ** H) / (1 - phi) if abs(phi) < 1 else x.mean() * H
            out["ar1"][0][j] = mu_h
            out["ar1"][1][j] = x.std() * np.sqrt(H)
        # HAR sobre el rango de la ventana, MCO con dias previos (reajuste cada 20 dias)
        lg = np.log(g)
        f1 = pd.Series(lg).shift(1); f5 = pd.Series(lg).shift(1).rolling(5).mean(); f22 = pd.Series(lg).shift(1).rolling(22).mean()
        Z = np.c_[np.ones(len(idx)), f1, f5, f22]
        beta = None
        for n, j in enumerate(idx):
            if n >= 150 and (beta is None or n % 20 == 0):
                ok = np.all(np.isfinite(Z[:n]), 1)
                beta = np.linalg.lstsq(Z[:n][ok], lg[:n][ok], rcond=None)[0]
            if beta is not None and np.all(np.isfinite(Z[n])):
                out["har"][1][j] = np.exp(Z[n] @ beta)
                out["har"][0][j] = out["seas"][0][j]
    return out


def infer():
    low_priority()
    S = series()
    Q = queries(S)
    last, ret, rng = realized(S, Q)
    Q["last"], Q["ret"], Q["rng"] = last, ret, rng
    print("previsiones a pedir por modelo:", len(Q), Q.win.value_counts().to_dict(), flush=True)
    for nm, (mu, sg) in trivial(S, Q, last, ret, rng).items():
        Q[f"{nm}_mu"], Q[f"{nm}_sig"] = mu, sg
    times = {}
    for model in MODELS:
        short = model.split("/")[-1].replace("chronos-", "c").replace("-", "_")
        try:
            mu, sg, dt = run_chronos(model, S, Q)
            Q[f"{short}_mu"], Q[f"{short}_sig"] = mu, sg
            times[short] = dt
            print(model, f"{dt:.0f}s para {len(Q)} previsiones ({dt / len(Q) * 1000:.0f} ms c/u)", flush=True)
        except Exception as e:
            print(model, "FALLA", type(e).__name__, str(e)[:200], flush=True)
        Q.attrs["times"] = times
        Q.to_pickle(FC)
    return Q


# ------------------------------------------------------------------ evaluacion
def model_names(Q):
    return [c[:-3] for c in Q.columns if c.endswith("_mu")]


def quality(Q):
    from scipy.stats import spearmanr
    a, b = period("sel")
    rows = []
    for w in ("bo", "mom"):
        M = Q[(Q.win == w) & (Q.tau >= a.timestamp()) & (Q.tau < b.timestamp())]
        for nm in model_names(Q):
            mu, sg = M[f"{nm}_mu"], M[f"{nm}_sig"]
            ok = mu.notna() & sg.notna()
            rows.append(dict(win=w, modelo=nm, n=int(ok.sum()),
                             ic_ret=spearmanr(mu[ok], M.ret[ok])[0],
                             acierto_signo=float((np.sign(mu[ok]) == np.sign(M.ret[ok])).mean()),
                             ic_rango=spearmanr(sg[ok], M.rng[ok])[0],
                             ic_absret=spearmanr(sg[ok], M.ret[ok].abs())[0]))
    return pd.DataFrame(rows)


def trade_feats(Q):
    """Por operacion de la base (hasta 2025): mu, sig de cada modelo y su percentil pasado (252 dias, misma ventana)."""
    B = base_trades()
    B = B[B.t < VAL[1].timestamp()].reset_index(drop=True)
    out = B[["t", "leg", "side"]].copy()
    for nm in model_names(Q):
        for k in ("mu", "sig"):
            out[f"{nm}_{k}"] = np.nan; out[f"p_{nm}_{k}"] = np.nan
    for w, leg in (("bo", "big_one"), ("mom", "momentum")):
        M = Q[Q.win == w].sort_values("tau").reset_index(drop=True)
        tau = M.tau.values
        m = (out.leg == leg).values
        j = np.searchsorted(tau, B.t.values[m])
        okj = (j < len(tau)) & (tau[np.clip(j, 0, len(tau) - 1)] == B.t.values[m])
        for nm in model_names(Q):
            for k in ("mu", "sig"):
                v = M[f"{nm}_{k}"].values
                # percentil pasado: entre los 252 dias previos de la misma ventana
                pc = np.full(len(M), np.nan)
                for n in range(len(M)):
                    h = v[max(0, n - 252):n]; h = h[np.isfinite(h)]
                    if len(h) >= 60 and np.isfinite(v[n]):
                        pc[n] = (h < v[n]).mean()
                vals = np.where(okj, v[np.clip(j, 0, len(tau) - 1)], np.nan)
                pcs = np.where(okj, pc[np.clip(j, 0, len(tau) - 1)], np.nan)
                out.loc[m, f"{nm}_{k}"] = vals; out.loc[m, f"p_{nm}_{k}"] = pcs
    return out


def grid(Q=None):
    from bot_backtesting.fullsim.opt_F_datos import LEGS, THS, apply_rule, base_and_f1
    low_priority()
    Q = pd.read_pickle(FC) if Q is None else Q
    Fe = trade_feats(Q)
    Fe.to_pickle(os.path.join(RESULTS, "opt_F_tsfm_feats.pkl"))
    B, F1 = base_and_f1()
    mf1 = evaluate(F1, "sel")["mar"]
    rows = []
    for base_name, T in (("base", B), ("F1", F1)):
        for nm in model_names(Q):
            for k in ("mu", "sig"):
                col = f"{nm}_{k}"
                for lg in ("bo", "mom"):
                    for th in THS:
                        for bad_hi in (True, False):
                            C = apply_rule(T, Fe, col, th, bad_hi, LEGS[lg], 0.0)
                            name = f"F/tsfm {base_name} {col} {lg} {'>=' if bad_hi else '<'}{th} x0"
                            r = compare(C, B, "sel", name, boot=False)
                            r["mar_vs_f1"] = r["mar_c"] / mf1
                            register("F", name, r, dict(base=base_name, col=col, legs=lg, th=th, bad_hi=bad_hi))
                            r.update(base=base_name, col=col, lg=lg, th=th, bad_hi=bad_hi, mult=0.0, model=nm)
                            rows.append(r)
            # reglas naturales sin umbral
            for rule in ("bo_mu_neg", "mom_disagree"):
                C = T.copy()
                f = Fe.set_index("t").reindex(C.t.values)
                if rule == "bo_mu_neg":
                    msk = (C.leg == "big_one").values & (f[f"{nm}_mu"].values < 0)
                else:
                    msk = (C.leg == "momentum").values & (C.side.values * f[f"{nm}_mu"].values < 0)
                C.loc[msk, "w"] = 0.0
                name = f"F/tsfm {base_name} {nm} {rule}"
                r = compare(C, B, "sel", name, boot=False)
                r["mar_vs_f1"] = r["mar_c"] / mf1
                register("F", name, r, dict(base=base_name, model=nm, rule=rule))
                r.update(base=base_name, col=f"{nm}_{rule}", lg=rule, th=np.nan, bad_hi=None, mult=0.0, model=nm)
                rows.append(r)
        print(base_name, "listo", len(rows), flush=True)
    G = pd.DataFrame(rows)
    G.to_pickle(GRID)
    return G


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "infer"
    if cmd == "infer":
        Q = infer()
        print(Q.attrs.get("times"))
        print(quality(Q).round(3).to_string())
    elif cmd == "quality":
        print(quality(pd.read_pickle(FC)).round(3).to_string())
    elif cmd == "eval":
        from bot_backtesting.fullsim.opt_F_datos import show_top
        Q = pd.read_pickle(FC)
        print(quality(Q).round(3).to_string())
        show_top(grid(Q), n=20)
