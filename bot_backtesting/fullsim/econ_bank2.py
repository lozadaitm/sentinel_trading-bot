"""Banco de modelos econometricos, segunda tanda (solo analisis). Usa los datos de econ_bank.

  D2b entradas del M5 mantenidas k minutos vs azar emparejado      -> TimeStop del M5
  B4  volatilidad de la proxima hora (HAR horario + estacionalidad) -> trailing/distancias del M5
  E2  regimen calma/agitado (HMM de 2 estados, filtrado)            -> interruptor de modo
  G2  Kelly con incertidumbre (remuestreo por meses)                -> % de riesgo de la Big One
Uso: python -m bot_backtesting.fullsim.econ_bank2 [D2b B4 E2 G2]
"""
import os
import pickle
import sys

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.econ_bank import C5, D, T5, TR, day, lr, m5, vr
from bot_backtesting.fullsim.entrylab import RESULTS

pd.set_option("display.width", 250)
T2023 = pd.Timestamp("2023-01-01").timestamp()


def _m5_trades():
    R = pickle.load(open(os.path.join(RESULTS, "m5race_m5_both.pkl"), "rb"))
    return pd.DataFrame([t for r in R for t in r["trades"]])


def D2b():
    print("=" * 90, "\nD2b entradas del M5 mantenidas k minutos vs AZAR emparejado (misma hora y lado, otro dia del tramo)")
    X = _m5_trades()
    sg = np.where(X.side == "BUY", 1, -1)
    ot = X.open_time.values
    k0 = np.searchsorted(T5, ot)
    O5 = m5.open.values
    rng = np.random.default_rng(5)
    tod = ot % 86400
    days = np.unique(day)
    pos = {t: i for i, t in enumerate(T5)}
    rows = []
    for k in (12, 48, 96, 144):
        sig = (C5[np.minimum(k0 + k, len(T5) - 1) - 1] - O5[k0]) * sg
        rnd = np.full(len(X), np.nan)
        for j in range(len(X)):
            acc = []
            for d in rng.choice(days, 12):
                if abs(d - ot[j] // 86400) < 3 or (d * 86400 < T2023) != (ot[j] < T2023):
                    continue
                i = pos.get(d * 86400 + tod[j])
                if i is not None and i + k < len(T5):
                    acc.append((C5[i + k - 1] - O5[i]) * sg[j])
                if len(acc) == 3:
                    break
            if acc:
                rnd[j] = np.mean(acc)
        ed = sig - rnd
        for tn, m in (("2021-22", ot < T2023), ("2023", ot >= T2023)):
            mm = m & ~np.isnan(ed)
            dd = pd.Series(ed[mm]).groupby(ot[mm] // 86400).mean()
            rows.append(dict(minutos=k * 5, tramo=tn, senal=sig[mm].mean(), azar=rnd[mm].mean(), ventaja=ed[mm].mean(),
                             t_dia=dd.mean() / dd.std() * np.sqrt(len(dd))))
    print(pd.DataFrame(rows).round(3).to_string(index=False))


def B4():
    print("=" * 90, "\nB4 volatilidad de la PROXIMA HORA (RV horaria de retornos M5), R2 fuera de muestra 2024-26")
    H = pd.DataFrame({"h": T5 // 3600, "r2": lr ** 2}).groupby("h").r2.agg(["sum", "count"])
    H = H[H["count"] >= 10]
    df = pd.DataFrame({"rv": np.sqrt(H["sum"]) * 100}, index=H.index)
    df["hod"] = df.index.values % 24
    df["d"] = df.index.values // 24
    df["y"] = pd.to_datetime(df.index.values * 3600, unit="s").year
    df["l1"] = df.rv.shift(1); df["l3"] = df.rv.rolling(3).mean().shift(1)
    df["l24"] = df.rv.rolling(24).mean().shift(1); df["l120"] = df.rv.rolling(120).mean().shift(1)
    tr = df.y <= 2023
    seas = df[tr].groupby("hod").rv.mean() / df[tr].rv.mean()
    df["seas"] = df.hod.map(seas)
    df["l3s"] = df.l3 / ((df.hod - 1) % 24).map(seas).values * df.seas
    df["dhar"] = D.rvhat_3.reindex(df.d.values).values / np.sqrt(22) * df.seas.values
    df = df.dropna()
    tr = df.y <= 2023
    y = df.rv[~tr].values
    for cols, nm in ((["l3"], "media 3 h (tipo ATR)"), (["l3s"], "media 3 h ajustada por hora"),
                     (["l1", "l3", "l24", "l120"], "HAR horario"), (["l1", "l3", "l24", "l120", "seas"], "HAR + hora"),
                     (["l1", "l3", "l24", "l120", "seas", "dhar"], "HAR + hora + HAR diario")):
        X = np.column_stack([np.ones(tr.sum())] + [df.loc[tr, c].values for c in cols])
        b = np.linalg.lstsq(X, df.rv[tr].values, rcond=None)[0]
        p_ = np.column_stack([np.ones((~tr).sum())] + [df.loc[~tr, c].values for c in cols]) @ b
        print(f"  {nm:<30} R2_oos={1 - ((y - p_) ** 2).sum() / ((y - y.mean()) ** 2).sum():.3f}")


def _hmm2(x, iters=150):
    """HMM gaussiano de 2 estados por EM (Baum-Welch escalado)."""
    mu = np.quantile(x, [.25, .75]); sd = np.array([x.std(), x.std()])
    A = np.array([[.95, .05], [.05, .95]]); pi = np.array([.5, .5]); n = len(x)
    for _ in range(iters):
        Bm = np.exp(-0.5 * ((x[:, None] - mu) / sd) ** 2) / sd
        al = np.zeros((n, 2)); c = np.zeros(n)
        al[0] = pi * Bm[0]; c[0] = al[0].sum(); al[0] /= c[0]
        for t in range(1, n):
            al[t] = (al[t - 1] @ A) * Bm[t]; c[t] = al[t].sum(); al[t] /= c[t]
        be = np.ones((n, 2))
        for t in range(n - 2, -1, -1):
            be[t] = (A @ (Bm[t + 1] * be[t + 1])) / c[t + 1]
        g = al * be; g /= g.sum(1, keepdims=True)
        xi = al[:-1, :, None] * A[None] * (Bm[1:] * be[1:])[:, None, :] / c[1:, None, None]
        A = xi.sum(0) / xi.sum((0, 2))[:, None]; pi = g[0]
        mu = (g * x[:, None]).sum(0) / g.sum(0); sd = np.sqrt((g * (x[:, None] - mu) ** 2).sum(0) / g.sum(0))
    return mu, sd, A, pi


def E2():
    print("=" * 90, "\nE2 regimen calma/agitado: HMM de 2 estados sobre log(vol diaria); entrenado 2021-23, filtrado sin mirar adelante")
    x = np.log(D.rv.values); tr = (D.year <= 2023).values
    mu, sd, A, pi = _hmm2(x[tr])
    o = np.argsort(mu); mu, sd, A, pi = mu[o], sd[o], A[np.ix_(o, o)], pi[o]
    Bm = np.exp(-0.5 * ((x[:, None] - mu) / sd) ** 2) / sd
    pf = np.zeros((len(x), 2)); a = pi * Bm[0]; pf[0] = a / a.sum()
    for t in range(1, len(x)):
        a = (pf[t - 1] @ A) * Bm[t]; pf[t] = a / a.sum()
    D["p_agit"] = np.r_[np.nan, (pf[:-1] @ A)[:, 1]]          # dia d con info hasta d-1
    print(f"  vol media calma={np.exp(mu[0]):.2f}%  agitado={np.exp(mu[1]):.2f}%  "
          f"permanencia media: calma {1 / (1 - A[0, 0]):.0f} d, agitado {1 / (1 - A[1, 1]):.0f} d")
    print("  fraccion de dias agitados por año:", D.groupby("year").p_agit.apply(lambda s: round(float((s > .5).mean()), 2)).to_dict())
    hit = ((D.p_agit > .5) == (pd.Series(pf[:, 1], index=D.index) > .5)).mean()
    print(f"  acierto del regimen de mañana con info de hoy: {hit:.2f}")
    T = pd.read_pickle(os.path.join(RESULTS, "bigone_plus_trades.pkl"))
    T = T[T.variant == "har_ev50"].copy(); T["d"] = (T.t // 86400).astype(int)
    T["reg"] = np.where(D.p_agit.reindex(T.d.values).values > .5, "agitado", "calma")
    print("  Big One (HAR) R medio y n por regimen y año:")
    print(T.pivot_table(index="reg", columns="year", values="r_mult", aggfunc=["mean", "size"]).round(2).to_string())
    X = _m5_trades(); X["oz"] = X.gross / (X.volume * 100)
    X["reg"] = np.where(D.p_agit.reindex((X.open_time // 86400).values).values > .5, "agitado", "calma")
    X["tramo"] = np.where(X.open_time < T2023, "2021-22", "2023")
    print("  M5 bruto $/oz por modo y regimen (costo ~0,32):")
    print(X.pivot_table(index=["regime", "reg"], columns="tramo", values="oz", aggfunc=["mean", "size"]).round(3).to_string())
    st = pd.Series(D.p_agit.values > .5, index=D.index).reindex(day).fillna(False).values.astype(bool)
    for lab, mm in (("calma", ~st), ("agitado", st)):
        for tn, mt in (("2021-23", TR), ("2024-26", ~TR)):
            v, zz = vr(np.where(mm & mt, lr, np.nan), 12)
            print(f"  VR(1 h) {lab:<8} {tn}: {v:.3f} (z {zz:+.2f})")


def G2():
    print("=" * 90, "\nG2 Kelly con incertidumbre: riesgo por operacion que maximiza el crecimiento, y su dispersion")
    T = pd.read_pickle(os.path.join(RESULTS, "bigone_plus_trades.pkl"))
    fs = np.arange(0.005, 0.40, 0.005)

    def kelly(rr):
        return fs[int(np.argmax([np.log(np.maximum(1 + f * rr, 1e-9)).mean() for f in fs]))]
    for v in ("base_atr", "har_ev50"):
        x = T[T.variant == v].sort_values("t")
        r = (x.r_mult * x.w).values
        mon = pd.to_datetime(x.t, unit="s").dt.to_period("M").values
        groups = pd.Series(np.arange(len(r))).groupby(mon).apply(list).tolist()
        rng = np.random.default_rng(1)
        bs = np.array([kelly(r[np.concatenate([groups[i] for i in rng.integers(0, len(groups), len(groups))])]) for _ in range(500)])
        k = kelly(r)
        print(f"  {v}: R medio {r.mean():+.3f} sd {r.std():.2f} | Kelly {k * 100:.1f}% | remuestreo p10 {np.quantile(bs, .1) * 100:.1f}% "
              f"p25 {np.quantile(bs, .25) * 100:.1f}% mediana {np.median(bs) * 100:.1f}% | P(Kelly < 3%) {(bs < .03).mean():.2f}")
        for y, g in x.assign(rw=r).groupby("year"):
            print(f"     {y}: R medio {g.rw.mean():+.3f}  Kelly del año {kelly(g.rw.values) * 100:.1f}%")


if __name__ == "__main__":
    for w in sys.argv[1:] or ["B4", "E2", "G2", "D2b"]:
        globals()[w]()
