"""Riesgo DINAMICO por operacion para la Big One (HAR + eventos x0,5), solo simulacion.

Esquemas (base 3 % del equity; tope 10 %):
  fijo        : 3 % siempre.
  colchon_g   : 3 % del equity + g x (ganancia sobre el capital inicial): arriesga mas solo con lo ganado.
  freno_dd    : 3 % reducido linealmente en caida (hasta 1,5 % con 30 % de caida).
  condicional : 3 % x clip(R previsto / R medio, 0,5, 3,3) — R previsto por un ridge entrenado solo
                con años anteriores (ventana creciente) sobre variables conocidas antes de la 01:00.
  racha       : 3 % x (1,5 si el R medio de las ultimas 20 operaciones > 0, si no 0,75).
  vol_baja    : 3 % x (vol prevista mediana / vol prevista del dia), acotado 0,5..3,3.
Medidas: remuestreo por bloques de 1 mes, 12 meses, 2 000 caminos; y el camino real 2023-2026.
Uso: python -m bot_backtesting.fullsim.risk_dyn
"""
import os

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.bigone_plus import CAL
from bot_backtesting.fullsim.entrylab import DATA, RESULTS

F0, FMAX = 0.03, 0.10
FEATS = ["m_vix_l", "mom5_l", "mom20_l", "dist_ma50_l", "x_dxy_l", "cot_z_l", "ev_any", "m_ry_chg20_l",
         "m_usd_chg20_l", "vol_ratio", "rvhat_3", "dow"]


def predicted_R(D):
    """R previsto por operacion de la Big One elegida (har, sin piramide, tendencia +2), sin mirar adelante."""
    A = pd.read_pickle(os.path.join(RESULTS, "bigone_plus_all.pkl"))
    T = pd.read_pickle(os.path.join(RESULTS, "bigone_plus_trades.pkl"))
    T = T[T.variant == "har_ev50"].copy()
    A = A[(A.scale == "har") & (A.pyr == 0) & (A.state == 2)].copy()
    A["d"] = (A.t // 86400).astype(int)
    X = D.assign(vol_ratio=D.rvhat_3 / D.rv22_l)
    A = A.join(X[FEATS], on="d")
    T["pred"] = np.nan
    for Y in sorted(T.year.unique()):
        ex = T[T.year == Y].chosen.iloc[0]
        tr = A[(A.exit == ex) & (A.year < Y)].dropna(subset=FEATS)
        te_idx = T.index[T.year == Y]
        te = A[(A.exit == ex) & (A.year == Y)].set_index("t").reindex(T.loc[te_idx, "t"].values)
        mu, sd = tr[FEATS].mean(), tr[FEATS].std().replace(0, 1)
        Xtr = ((tr[FEATS] - mu) / sd).values
        b = np.linalg.solve(Xtr.T @ Xtr + 200 * np.eye(len(FEATS)), Xtr.T @ (tr.r_mult.values - tr.r_mult.mean()))
        p = tr.r_mult.mean() + ((te[FEATS] - mu) / sd).fillna(0).values @ b
        T.loc[te_idx, "pred"] = p
        T.loc[te_idx, "rmean_tr"] = tr.r_mult.mean()
    T["vol"] = D.rvhat_3.reindex((T.t // 86400).astype(int).values).values
    return T.sort_values("t").reset_index(drop=True)


def frac(scheme, x, eq, b0, peak, hist):
    if scheme == "fijo":
        return F0
    if scheme.startswith("colchon"):
        g = float(scheme.split("_")[1])
        return min(FMAX, (F0 * eq + g * max(0.0, eq - b0)) / eq)
    if scheme == "freno_dd":
        dd = (peak - eq) / peak
        return F0 * max(0.5, 1 - dd / 0.6)
    if scheme == "condicional":
        return F0 * np.clip(x["pred"] / max(x["rmean_tr"], 1e-6), 0.5, FMAX / F0) if np.isfinite(x["pred"]) else F0
    if scheme == "racha":
        return F0 * (1.5 if len(hist) >= 20 and np.mean(hist[-20:]) > 0 else 0.75)
    if scheme == "vol_baja":
        return F0 * np.clip(x["vmed"] / x["vol"], 0.5, FMAX / F0)
    raise ValueError(scheme)


def run_path(rows, scheme, b0=5000.0):
    eq, peak, dd, hist = b0, b0, 0.0, []
    for x in rows:
        f = frac(scheme, x, eq, b0, peak, hist) * x["w"]
        risk = eq * f
        dd = max(dd, (peak - (eq + min(0.0, x["mr"]) * risk)) / peak)
        eq += x["r_mult"] * risk; hist.append(x["r_mult"])
        peak = max(peak, eq); dd = max(dd, (peak - eq) / peak)
        if eq <= b0 * 0.05:
            return eq / b0, 1.0
    return eq / b0, dd


def main():
    D = pd.read_pickle(os.path.join(DATA, "econ", "econ_daily2.pkl"))
    T = predicted_R(D)
    T["mr"] = T.mae / T.risk_oz
    T["vmed"] = T.vol.expanding().median().shift(1).fillna(T.vol.iloc[0])
    ok = T.pred.notna()
    print(f"R previsto vs real (fuera de muestra): correlacion {T.loc[ok, 'pred'].corr(T.loc[ok, 'r_mult']):+.3f}")
    q = pd.qcut(T.loc[ok, "pred"], 3, labels=["bajo", "medio", "alto"])
    print("R real por tercil de R previsto:", T.loc[ok].groupby(q, observed=True).r_mult.mean().round(3).to_dict())
    h = T.r_mult.rolling(20).mean().shift(1)
    print("R real tras racha positiva / negativa (media 20 previas):",
          round(T.r_mult[h > 0].mean(), 3), "/", round(T.r_mult[h <= 0].mean(), 3))
    print("autocorrelacion de R (lag 1):", round(T.r_mult.autocorr(1), 3))
    T["m"] = pd.to_datetime(T.t, unit="s").dt.to_period("M")
    cols = ["r_mult", "mr", "w", "pred", "rmean_tr", "vol", "vmed"]
    months = [T.loc[T.m == p, cols].to_dict("records") for p in CAL]
    allrows = [r for m in months for r in m]
    out = []
    for scheme in ("fijo", "colchon_0.03", "colchon_0.06", "colchon_0.10", "freno_dd", "condicional", "racha", "vol_baja"):
        rng = np.random.default_rng(7)
        res = []
        for _ in range(2000):
            seq = [r for i in rng.integers(0, len(months), 12) for r in months[i]]
            res.append(run_path(seq, scheme))
        mult = np.array([r[0] for r in res]); dds = np.array([r[1] for r in res])
        one = np.array([run_path(m, scheme)[0] - 1 for m in months])
        real = run_path(allrows, scheme)
        out.append(dict(esquema=scheme, mes_med=np.median(one), p_mes30=(one >= .3).mean(), x12_med=np.median(mult),
                        p_x2_12m=(mult >= 2).mean(), p_x3_12m=(mult >= 3).mean(), p_dd50=(dds >= .5).mean(),
                        p_perder=(mult < 1).mean(), real_x=real[0], real_dd=real[1]))
    pd.set_option("display.width", 250)
    print(pd.DataFrame(out).round(3).to_string(index=False))


if __name__ == "__main__":
    main()
