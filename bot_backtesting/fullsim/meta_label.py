"""Meta-labeling de la Op1: P(llega a cobertura) con LightGBM, walk-forward fuera de muestra.

Entrada: senales del motor real (signals.py) + velas de cada fuente.
Salida: tabla de tasa de cobertura de las entradas que el filtro DEJA pasar, frente a
vetos ingenuos y al azar con la misma tasa de veto.
Requiere lightgbm (se uso 4.7.0 en un venv aparte; los bots no lo necesitan).
Uso: python -m bot_backtesting.fullsim.meta_label [--smoke]
Resultado de referencia: docs/experimento-2/analisis-filtro-ml-op1-2026-10-20.md (AUC 0,508).
"""
import os, sys, pickle, numpy as np, pandas as pd, lightgbm as lgb

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
SOURCES = [("sig_duka.pkl", "frames_duka.pkl"), ("sig_broker.pkl", "frames.pkl")]
if "--smoke" in sys.argv: SOURCES = SOURCES[1:]


def feats(S, fr):
    m = fr["M15"].reset_index(drop=True); h4 = fr["H4"]
    T = m.time.values + 900
    O, H, L, C = (m[c].values for c in ("open", "high", "low", "close"))
    tr = np.r_[H[0] - L[0], np.maximum(H[1:] - L[1:], np.maximum(abs(H[1:] - C[:-1]), abs(L[1:] - C[:-1])))]
    atr = pd.Series(tr).rolling(14).mean().values
    atr_med5 = pd.Series(atr).rolling(96 * 5, min_periods=96).median().values
    atr_med20 = pd.Series(atr).rolling(96 * 20, min_periods=96 * 5).median().values
    ret = np.r_[0, np.diff(np.log(C))]
    rv4 = pd.Series(ret).rolling(4).std().values; rv96 = pd.Series(ret).rolling(96).std().values
    hi48 = pd.Series(H).rolling(48).max().values; lo48 = pd.Series(L).rolling(48).min().values
    h4c = h4.close.values; h4t = h4.time.values + 4 * 3600
    e50 = pd.Series(h4c).ewm(span=50).mean().values; e200 = pd.Series(h4c).ewm(span=200).mean().values
    day = (m.time.values // 86400)
    dfd = pd.DataFrame({"d": day, "h": H, "l": L}).groupby("d").agg(h=("h", "max"), l=("l", "min"))
    prev_h = pd.Series(day).map(dfd.h.shift(1)).values; prev_l = pd.Series(day).map(dfd.l.shift(1)).values
    fvg_up = np.r_[0, 0, (L[2:] > H[:-2]).astype(int)]; fvg_dn = np.r_[0, 0, (H[2:] < L[:-2]).astype(int)]
    fu16 = pd.Series(fvg_up).rolling(16).sum().values; fd16 = pd.Series(fvg_dn).rolling(16).sum().values
    # barrido de liquidez: la vela perfora el extremo de 48 velas previo y cierra dentro
    ph48 = np.r_[np.nan, hi48[:-1]]; pl48 = np.r_[np.nan, lo48[:-1]]
    sw_hi = ((H > ph48) & (C < ph48)).astype(int); sw_lo = ((L < pl48) & (C > pl48)).astype(int)
    swh8 = pd.Series(sw_hi).rolling(8).sum().values; swl8 = pd.Series(sw_lo).rolling(8).sum().values
    up = (C > O).astype(int)
    rows = []
    for r in S.itertuples():
        i = np.searchsorted(T, r.t)
        if i >= len(T) or T[i] != r.t:
            i -= 1
        if i < 200:
            rows.append(None); continue
        s = r.side; a = atr[i]
        j = np.searchsorted(h4t, r.t, side="right") - 1
        hi24, lo24 = H[i - 95:i + 1].max(), L[i - 95:i + 1].min()
        pos24 = (C[i] - lo24) / max(1e-9, hi24 - lo24)
        k = i; run = 0
        while k > 0 and up[k] == (1 if s == 1 else 0) and run < 20:
            run += 1; k -= 1
        uw = (H[i] - max(O[i], C[i])) / a; lw = (min(O[i], C[i]) - L[i]) / a
        ts = pd.Timestamp(r.t, unit="s")
        rows.append(dict(
            atr_ratio=a / atr_med5[i], atr_ratio20=a / atr_med20[i], atr_usd=a,
            rv_ratio=rv4[i] / rv96[i] if rv96[i] > 0 else np.nan,
            ext_ema=s * (r.px - r.ema) / a, rsi_s=r.rsi if s == 1 else 100 - r.rsi,
            h4_aligned=int(r.h4 == s), bar_rng=(H[i] - L[i]) / a, bar_body=s * (C[i] - O[i]) / a,
            wick_against=uw if s == 1 else lw, wick_with=lw if s == 1 else uw,
            mom1h=s * (C[i] - C[i - 4]) / a, mom4h=s * (C[i] - C[i - 16]) / a, mom24h=s * (C[i] - C[i - 96]) / a,
            pos24=pos24 if s == 1 else 1 - pos24, rng24_atr=(hi24 - lo24) / a,
            room48=((hi48[i] - C[i]) if s == 1 else (C[i] - lo48[i])) / a,
            back48=((C[i] - lo48[i]) if s == 1 else (hi48[i] - C[i])) / a,
            prevday_room=((prev_h[i] - C[i]) if s == 1 else (C[i] - prev_l[i])) / a,
            h4_slope=s * (e50[j] - e50[j - 6]) / a, h4_vs200=s * (h4c[j] - e200[j]) / a,
            fvg_with=fu16[i] if s == 1 else fd16[i], fvg_against=fd16[i] if s == 1 else fu16[i],
            sweep_with=swl8[i] if s == 1 else swh8[i], sweep_against=swh8[i] if s == 1 else swl8[i],
            run_bars=run, hour=ts.hour, dow=ts.dayofweek,
            n_reentry=r.n))
    keep = [x is not None for x in rows]
    F = pd.concat([S[keep].reset_index(drop=True), pd.DataFrame([x for x in rows if x])], axis=1)
    return F[F.res != "OPEN"].copy()


def auc(y, p):
    o = np.argsort(p); r = np.empty(len(p)); r[o] = np.arange(1, len(p) + 1)
    n1 = y.sum(); n0 = len(y) - n1
    return (r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)


parts = []
for sp, fp in SOURCES:
    S = pickle.load(open(os.path.join(DATA, sp), "rb")); fr = pd.read_pickle(os.path.join(DATA, fp))
    S = S.loc[:, ~S.columns.duplicated()]
    parts.append(feats(S, fr))
F = pd.concat(parts, ignore_index=True).sort_values("t").reset_index(drop=True)
F["y"] = (F.res == "HEDGE").astype(int); F["first"] = F["first"].astype(int)
pickle.dump(F, open(os.path.join(DATA, "meta_feats.pkl"), "wb"))
X_COLS = [c for c in F.columns if c not in ("t", "side_x", "px", "atr", "ema", "rsi", "h4", "level", "n", "res",
                                             "mfe", "mae", "bars", "hd", "win_val", "y")]
X_COLS = [c for c in X_COLS if c in F.columns and F[c].dtype != object]
print("senales", len(F), "primeras", int(F["first"].sum()), "tasa cobertura (primeras) %.1f%%" % (100 * F[F["first"] == 1].y.mean()))
print("desde", pd.to_datetime(F.t.min(), unit="s").date(), "hasta", pd.to_datetime(F.t.max(), unit="s").date())
print("features:", X_COLS)

# walk-forward semestral, purga de 3 dias
starts = pd.date_range("2026-06-01", "2026-11-01", freq="MS") if "--smoke" in sys.argv else pd.date_range("2022-07-01", "2027-01-01", freq="6MS")
P = np.full(len(F), np.nan)
params = dict(objective="binary", learning_rate=0.03, num_leaves=15, min_data_in_leaf=60, feature_fraction=0.8,
              bagging_fraction=0.8, bagging_freq=1, lambda_l2=5.0, verbose=-1, seed=7)
imp = pd.Series(0.0, index=X_COLS)
for a, b in zip(starts[:-1], starts[1:]):
    ta, tb = a.timestamp(), b.timestamp()
    tr = F.t < ta - 3 * 86400; te = (F.t >= ta) & (F.t < tb)
    if te.sum() == 0 or tr.sum() < (300 if "--smoke" in sys.argv else 500):
        continue
    mdl = lgb.train(params, lgb.Dataset(F.loc[tr, X_COLS], F.loc[tr, "y"]), num_boost_round=300)
    P[te.values] = mdl.predict(F.loc[te, X_COLS])
    imp += pd.Series(mdl.feature_importance("gain"), index=X_COLS)
F["p"] = P
T = F[F.p.notna() & (F["first"] == 1)].copy()
print("\nFUERA DE MUESTRA (primeras senales):", len(T), "desde", pd.to_datetime(T.t.min(), unit="s").date(),
      "cobertura base %.1f%%" % (100 * T.y.mean()), "AUC %.3f" % auc(T.y.values, T.p.values))
for a, b in zip(starts[:-1], starts[1:]):
    g = T[(T.t >= a.timestamp()) & (T.t < b.timestamp())]
    if len(g) > 20 and 0 < g.y.sum() < len(g):
        print(f"  {a.date()} n={len(g):4d} cobertura {g.y.mean()*100:4.1f}%  AUC {auc(g.y.values, g.p.values):.3f}")

rng = np.random.default_rng(1)
print("\nveto  | cobertura de las que PASAN: modelo / solo atr_ratio / azar (p5-p95)")
for v in (0.1, 0.2, 0.3, 0.5):
    def kept_rate(score):
        thr = np.quantile(score, 1 - v); k = score < thr
        return T.y.values[k].mean(), k.sum()
    rm, nk = kept_rate(T.p.values)
    ra, _ = kept_rate(T.atr_ratio.fillna(1).values)
    rnd = [T.y.values[rng.random(len(T)) >= v].mean() for _ in range(2000)]
    # bootstrap del modelo
    bs = []
    for _ in range(1000):
        idx = rng.integers(0, len(T), len(T)); sub = T.iloc[idx]
        thr = np.quantile(sub.p.values, 1 - v); bs.append(sub.y.values[sub.p.values < thr].mean())
    print(f"{int(v*100):3d}%  | modelo {rm*100:4.1f}% (IC90 {np.quantile(bs,.05)*100:.1f}-{np.quantile(bs,.95)*100:.1f})"
          f"  atr {ra*100:4.1f}%  azar {np.mean(rnd)*100:4.1f}% ({np.quantile(rnd,.05)*100:.1f}-{np.quantile(rnd,.95)*100:.1f})  pasan {nk}")
print("\nimportancia (ganancia):"); print((imp / imp.sum()).sort_values(ascending=False).head(12).round(3).to_string())
pickle.dump(T, open(os.path.join(DATA, "meta_oos.pkl"), "wb"))
