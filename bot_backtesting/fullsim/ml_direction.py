"""Modelo de DIRECCION (LightGBM): cada hora en punto (servidor), P(el oro sube en las proximas
HZ horas). Validacion movil: cada ano se predice con un modelo entrenado SOLO con los dos anos
anteriores. Las entradas (p > P_HI compra, p < 1 - P_HI vende) se guardan en
data/ml_dir_events.pkl y entrylab las evalua con costes, swap y referencia al azar (regla 'ml_dir').

Requiere lightgbm (venv aparte con --system-site-packages). Uso, desde la raiz del repo:
  <venv>/python -m bot_backtesting.fullsim.ml_direction
"""
import os

import lightgbm as lgb
import numpy as np
import pandas as pd

from bot_backtesting.fullsim.entrylab import DATA, _cross_m15, atr

HZ = 4                 # horas
P_HI = 0.56
YEARS = (2023, 2024, 2025, 2026)


def features(B):
    df = B["M15"].reset_index(drop=True); T = df.time.values
    c = df.close.values; lc = np.log(c)
    a = atr(df)
    f = pd.DataFrame({"t": T + 900})
    for w in (1, 4, 16, 96, 480):
        r = pd.Series(lc).diff(w)
        f[f"r{w}"] = (r / r.rolling(2000, min_periods=500).std()).values
    f["atr_ratio"] = a / pd.Series(a).rolling(96 * 20, min_periods=96 * 5).median().values
    f["rng_atr"] = (df.high - df.low).values / a
    tt = pd.to_datetime(T, unit="s")
    f["hour"] = tt.hour; f["dow"] = tt.dayofweek
    day_open = pd.Series(df.open.values).groupby(tt.normalize()).transform("first").values
    f["from_open"] = (c - day_open) / a
    d1 = B["D1"]; dc = d1.close
    s = (np.sign(dc - dc.shift(21)) + np.sign(dc - dc.shift(63))).shift(1)
    f["tsmom"] = pd.Series(s.values, index=d1.time.values // 86400).reindex(T // 86400).values
    x = _cross_m15("xau", T)
    v = x.volume.values
    f["vol_z"] = np.log1p(v) - pd.Series(np.log1p(v)).rolling(96 * 5, min_periods=96).mean().values
    for name in ("xag", "eurusd", "dxy", "ustbond"):
        if not os.path.exists(os.path.join(DATA, f"cross_{name}.pkl")):
            continue
        xc = np.log(_cross_m15(name, T).close.values)
        for w in (1, 4, 16):
            r = pd.Series(xc).diff(w)
            f[f"{name}_r{w}"] = (r / r.rolling(2000, min_periods=500).std()).values
    # objetivo: retorno de las proximas HZ horas (cierre M15 + HZ*4 velas), en ATR
    fut = pd.Series(c).shift(-HZ * 4).values
    f["y_ret"] = (fut - c) / a
    f["atr"] = a
    return f


def main():
    B = pd.read_pickle(os.path.join(DATA, "bars_all.pkl"))
    F = features(B)
    F["year"] = pd.to_datetime(F.t, unit="s").dt.year
    F = F[pd.to_datetime(F.t - 900, unit="s").dt.minute == 45]   # decision a la hora en punto
    X_COLS = [c for c in F.columns if c not in ("t", "y_ret", "atr", "year")]
    F = F.dropna(subset=["y_ret", "atr"])
    params = dict(objective="binary", learning_rate=0.03, num_leaves=15, min_data_in_leaf=100,
                  feature_fraction=0.7, bagging_fraction=0.8, bagging_freq=1, lambda_l2=10.0, verbose=-1, seed=5)
    out = []
    for Y in YEARS:
        tr = F[F.year.isin([Y - 2, Y - 1])]
        tr = tr[tr.t < pd.Timestamp(f"{Y}-01-01").timestamp() - HZ * 3600]   # purga: el objetivo no cruza a Y
        te = F[F.year == Y]
        if te.empty:
            continue
        m = lgb.train(params, lgb.Dataset(tr[X_COLS], (tr.y_ret > 0).astype(int)), num_boost_round=300)
        p = m.predict(te[X_COLS])
        hit = ((p > 0.5) == (te.y_ret > 0)).mean()
        sel = (p > P_HI) | (p < 1 - P_HI)
        print(Y, "acierto direccion", round(hit, 3), "| senales", int(sel.sum()), "de", len(te),
              "| acierto en senales", round(((p[sel] > 0.5) == (te.y_ret.values[sel] > 0)).mean(), 3), flush=True)
        imp = pd.Series(m.feature_importance("gain"), index=X_COLS).sort_values(ascending=False)
        print("   importancia:", ", ".join(imp.index[:6]))
        out.append(pd.DataFrame({"t": te.t.values[sel], "side": np.where(p[sel] > 0.5, 1, -1),
                                 "scale": te.atr.values[sel], "hz": HZ, "base": "matched"}))
    E = pd.concat(out, ignore_index=True)
    E.to_pickle(os.path.join(DATA, "ml_dir_events.pkl"))
    print("eventos guardados:", len(E))


if __name__ == "__main__":
    main()
