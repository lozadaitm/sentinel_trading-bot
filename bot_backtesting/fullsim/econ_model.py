"""Estudio econometrico del XAUUSD sobre econ_daily.pkl (MCO con errores Newey-West, numpy).
1) Que mueve al oro el mismo dia (explicativo).  2) Que predice el dia siguiente / la reapertura /
la semana (solo variables conocidas antes).  3) Volatilidad (HAR).  Train 2021-2023, test 2024-2026.
Uso: python -m bot_backtesting.fullsim.econ_model   (antes: econ_build)"""
import os
import numpy as np, pandas as pd
HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "econ")
D = pd.read_pickle(os.path.join(HERE, "econ_daily.pkl"))
D["fwd5"] = D.ret[::-1].rolling(5).sum()[::-1]            # % de d a d+4 (variables de d)
D["absret"] = D.ret.abs()
TR = D.year <= 2023
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 200)


def ols(y, X, lags=5):
    X = np.column_stack([np.ones(len(X)), X]); b, *_ = np.linalg.lstsq(X, y, rcond=None)
    e = y - X @ b; n, k = X.shape
    XtXi = np.linalg.pinv(X.T @ X); S = (X * e[:, None]).T @ (X * e[:, None])
    for L in range(1, lags + 1):
        w = 1 - L / (lags + 1); G = (X[L:] * e[L:, None]).T @ (X[:-L] * e[:-L, None]); S += w * (G + G.T)
    se = np.sqrt(np.diag(XtXi @ S @ XtXi))
    r2 = 1 - (e ** 2).sum() / ((y - y.mean()) ** 2).sum()
    return b, b / se, r2


def z(df, cols, ref):
    return (df[cols] - ref[cols].mean()) / ref[cols].std()


print("=" * 100, "\n1) QUE MUEVE AL ORO EL MISMO DIA (beta en % de oro por 1 desv. tipica de cada variable)")
drv = ["m_d_ry", "m_d_bei", "x_dxy", "m_d_vix", "m_d_oil", "m_d_ff"]
for nm, m in (("2021-23", TR), ("2024-26", ~TR), ("todo", TR | ~TR)):
    x = D[m].dropna(subset=drv + ["ret"])
    b, t, r2 = ols(x.ret.values, z(x, drv, x).values)
    print(f"{nm}: R2={r2:.2f}  " + "  ".join(f"{c}={bb:+.2f}(t{tt:+.1f})" for c, bb, tt in zip(drv, b[1:], t[1:])))
x = D.dropna(subset=["x_xag", "ret"]); print("correlacion oro-plata mismo dia:", round(x.ret.corr(x.x_xag), 2),
                                            "| oro-dolar(DXY):", round(D.ret.corr(D.x_dxy), 2), "| oro-bono:", round(D.ret.corr(D.x_ustbond), 2))
print("R2 por año (modelo explicativo con todo):")
for y, x in D.dropna(subset=drv + ["ret"]).groupby("year"):
    print("  ", y, round(ols(x.ret.values, z(x, drv, x).values)[2], 2))

print("=" * 100, "\n2) QUE PREDICE (solo informacion conocida antes de la 01:00). t Newey-West; test = 2024-26")
feats = [c for c in D.columns if c.endswith("_l")] + ["ev_any", "ev_NFP", "ev_CPI", "ev_FOMC", "dow"]
targets = {"ret": "dia siguiente", "r_open15": "reapertura 15 min", "r_asia": "reapertura 01-10h", "r_rest": "resto del dia", "fwd5": "proxima semana"}
rows = []
for tg in targets:
    for f in feats:
        tr = D[TR].dropna(subset=[f, tg]); te = D[~TR].dropna(subset=[f, tg])
        if tr[f].std() == 0 or len(te) < 50: continue
        lg = 5 if tg == "fwd5" else 3
        b1, t1, _ = ols(tr[tg].values, ((tr[f] - tr[f].mean()) / tr[f].std()).values[:, None], lg)
        b2, t2, _ = ols(te[tg].values, ((te[f] - tr[f].mean()) / tr[f].std()).values[:, None], lg)
        rows.append(dict(objetivo=tg, variable=f, b_train=b1[1], t_train=t1[1], b_test=b2[1], t_test=t2[1]))
R = pd.DataFrame(rows)
R["mismo_signo"] = np.sign(R.b_train) == np.sign(R.b_test)
R["robusta"] = R.mismo_signo & (R.t_train.abs() > 2) & (R.t_test.abs() > 2)
n_tests = len(R)
print(f"pruebas: {n_tests} | |t|>2 en train: {(R.t_train.abs() > 2).sum()} | en ambos con mismo signo: {R.robusta.sum()} "
      f"(por azar se esperarian ~{n_tests * 0.05 * 0.05 / 2:.1f})")
print(R[(R.t_train.abs() > 1.96) | (R.t_test.abs() > 2.5)].sort_values(["objetivo", "t_train"]).round(3).to_string(index=False))
R.to_pickle(os.path.join(HERE, "econ_univar.pkl"))

print("=" * 100, "\n2b) MODELO MULTIVARIABLE (ridge, entrenado 2021-23): R2 fuera de muestra y acierto de signo en 2024-26")
for tg in targets:
    cols = [f for f in feats if D[f].notna().mean() > 0.9]
    tr = D[TR].dropna(subset=cols + [tg]); te = D[~TR].dropna(subset=cols + [tg])
    mu, sd = tr[cols].mean(), tr[cols].std().replace(0, 1)
    Xtr = ((tr[cols] - mu) / sd).values; Xte = ((te[cols] - mu) / sd).values
    for lam in (10.0, 100.0, 1000.0):
        A = Xtr.T @ Xtr + lam * np.eye(len(cols)); b = np.linalg.solve(A, Xtr.T @ (tr[tg].values - tr[tg].mean()))
        p = te[tg].mean() * 0 + tr[tg].mean() + Xte @ b
        r2 = 1 - ((te[tg] - p) ** 2).sum() / ((te[tg] - tr[tg].mean()) ** 2).sum()
        hit = (np.sign(p - tr[tg].mean()) == np.sign(te[tg] - tr[tg].mean())).mean()
        # economico: retorno medio cuando el modelo dice "arriba del promedio" vs "abajo"
        up = te[tg][p > np.median(p)].mean(); dn = te[tg][p <= np.median(p)].mean()
        print(f"  {targets[tg]:<20} lam={lam:<6} R2_oos={r2:+.3f}  acierto={hit:.3f}  media(pred alta)={up:+.3f}%  media(pred baja)={dn:+.3f}%")

print("=" * 100, "\n3) VOLATILIDAD: HAR (rv dia d con info de d-1) + VIX + eventos del dia (calendario conocido)")
vc = ["rv_l", "rv5_l", "rv22_l", "m_vix_l", "ev_any", "ev_FOMC", "ev_NFP", "ev_CPI"]
tr = D[TR].dropna(subset=vc + ["rv"]); te = D[~TR].dropna(subset=vc + ["rv"])
for cols, nm in ((["rv22_l"], "solo media 22d (=ATR)"), (["rv_l", "rv5_l", "rv22_l"], "HAR"), (vc, "HAR+VIX+eventos")):
    X = np.column_stack([np.ones(len(tr)), tr[cols].values]); b = np.linalg.lstsq(X, tr.rv.values, rcond=None)[0]
    p = np.column_stack([np.ones(len(te)), te[cols].values]) @ b
    r2 = 1 - ((te.rv - p) ** 2).sum() / ((te.rv - te.rv.mean()) ** 2).sum()
    print(f"  {nm:<22} R2 fuera de muestra = {r2:.3f}   coef: " + " ".join(f"{c}={v:+.3f}" for c, v in zip(cols, b[1:])))
    D.loc[te.index, f"rvhat_{len(cols)}"] = p
    D.loc[tr.index, f"rvhat_{len(cols)}"] = np.column_stack([np.ones(len(tr)), tr[cols].values]) @ b
D.to_pickle(os.path.join(HERE, "econ_daily2.pkl"))
