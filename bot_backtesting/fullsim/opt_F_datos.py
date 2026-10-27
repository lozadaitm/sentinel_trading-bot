"""Linea F (27-oct-2026): DATOS EXTERNOS NUEVOS como filtro / peso de las patas e2.

Que prueba:
  Caracteristicas que B y C no usaron, cada una unida "as of" la hora de entrada con su retraso real de publicacion
  (opt_F_ext.asof_join): GLD (tenencias, prima, volumen), CBOE (VIX9D/VIX3M, SKEW, GVZ/VIX), FRED nuevas
  (breakeven 5 a, 5a5a, tasa real 5 a, pendiente 10-2, letra 3 m, estres STLFSI4, incertidumbre EPU) y
  GDELT (tono y cuota de articulos sobre oro y sobre la Fed en las 24 h ANTERIORES a la entrada).
  Cada caracteristica se pasa a percentil de los 252 dias habiles PREVIOS (misma hora del dia), asi el umbral no mira
  adelante. Regla: pata(s) x mult si percentil >= u (o < u). Grilla sobre la base y encima de F1 de la linea C.
  Finalistas: bootstrap, 2023/2024, vecinos +-1 paso, nulo de dias al azar (permuta la caracteristica entre dias,
  >= 200 veces), val una vez.
  Ademas un modelo logistico L2 con TODAS las nuevas, CV purgada con embargo de 5 dias (pocas variantes).

Correr:  .venv/Scripts/python -m bot_backtesting.fullsim.opt_F_datos feats   (construye results/opt_F_feats.pkl)
         .venv/Scripts/python -m bot_backtesting.fullsim.opt_F_datos grid    (grilla en sel -> results/opt_F_grid.pkl)
         .venv/Scripts/python -m bot_backtesting.fullsim.opt_F_datos final   (finalistas, nulos y val)
"""
import os
import sys
import time

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.opt_base import (RESULTS, VAL, base_trades, compare, evaluate, low_priority, period,
                                              register)
from bot_backtesting.fullsim import opt_F_ext as X

FEATS = os.path.join(RESULTS, "opt_F_feats.pkl")
GRID = os.path.join(RESULTS, "opt_F_grid.pkl")
YEARS = {"y2023": (pd.Timestamp("2023-01-01"), pd.Timestamp("2024-01-01")),
         "y2024": (pd.Timestamp("2024-01-01"), pd.Timestamp("2025-01-01"))}
T_END = VAL[1].timestamp()          # nada de 2026
DAY = 86400


# ------------------------------------------------------------------ caracteristicas en un instante tau (seg. servidor)
class Sources:
    def __init__(self):
        self.fred = {s: X.load_fred(s) for s in X.FRED}
        self.cboe = {k: X.load_cboe(k) for k in X.CBOE}
        self.gld = X.load_gld()
        self.gd = {n: X.load_gdelt(n) for n in X.GDELT_Q}
        for k, F in self.fred.items():
            F["m7"] = F.v.rolling(7, min_periods=3).mean()
        g = self.gld
        g["ton_l"] = np.log(g.tonnes)
        g["prem5"] = g.prem.rolling(5, min_periods=3).mean()
        g["volz"] = np.log(g.vol / g.vol.rolling(60, min_periods=30).median())
        for n, G in self.gd.items():
            if G is None:
                continue
            G = G[G.avail <= T_END + 2 * DAY].copy()
            G["n"] = G.n.fillna(0); G["norm"] = G.get("norm", pd.Series(np.nan, G.index)).fillna(0)
            G["tone"] = G.tone.fillna(0)
            G["cn"] = G.n.cumsum(); G["cnorm"] = G.norm.cumsum(); G["ctn"] = (G.tone * G.n).cumsum()
            self.gd[n] = G

    def at(self, tau):
        """dict de caracteristicas en los instantes tau (array)."""
        tau = np.asarray(tau, float)
        f, A = {}, X.asof_join
        F = self.fred
        f["t5yie_d5"] = A(tau, F["T5YIE"], "v") - A(tau - 7 * DAY, F["T5YIE"], "v")
        f["t5yifr_d5"] = A(tau, F["T5YIFR"], "v") - A(tau - 7 * DAY, F["T5YIFR"], "v")
        f["dfii5_d5"] = A(tau, F["DFII5"], "v") - A(tau - 7 * DAY, F["DFII5"], "v")
        f["t10y2y"] = A(tau, F["T10Y2Y"], "v")
        f["t10y2y_d20"] = f["t10y2y"] - A(tau - 28 * DAY, F["T10Y2Y"], "v")
        f["dgs3mo_d20"] = A(tau, F["DGS3MO"], "v") - A(tau - 28 * DAY, F["DGS3MO"], "v")
        f["stlfsi"] = A(tau, F["STLFSI4"], "v")
        f["stlfsi_d"] = f["stlfsi"] - A(tau - 14 * DAY, F["STLFSI4"], "v")
        f["epu7"] = np.log(A(tau, F["USEPUINDXD"], "m7"))
        C = self.cboe
        f["vix_term"] = A(tau, C["VIX9D"], "v") / A(tau, C["VIX3M"], "v")
        f["skew"] = A(tau, C["SKEW"], "v")
        f["skew_d5"] = f["skew"] - A(tau - 7 * DAY, C["SKEW"], "v")
        f["gvz_vix"] = A(tau, C["GVZ"], "v") / A(tau, C["VIX"], "v")
        g = self.gld
        f["gld_flow5"] = A(tau, g, "ton_l") - A(tau - 7 * DAY, g, "ton_l")
        f["gld_flow20"] = A(tau, g, "ton_l") - A(tau - 28 * DAY, g, "ton_l")
        f["gld_prem5"] = A(tau, g, "prem5")
        f["gld_volz"] = A(tau, g, "volz")
        for n, G in self.gd.items():
            if G is None:
                continue
            def cum(t, c):
                return A(t, G, c)
            n24 = cum(tau, "cn") - cum(tau - DAY, "cn")
            nm24 = cum(tau, "cnorm") - cum(tau - DAY, "cnorm")
            n30 = cum(tau, "cn") - cum(tau - 30 * DAY, "cn")
            nm30 = cum(tau, "cnorm") - cum(tau - 30 * DAY, "cnorm")
            tn24 = cum(tau, "ctn") - cum(tau - DAY, "ctn")
            tn30 = cum(tau, "ctn") - cum(tau - 30 * DAY, "ctn")
            with np.errstate(all="ignore"):
                tone24 = tn24 / n24
                f[f"{n}_tone24"] = tone24
                f[f"{n}_tone_rel"] = tone24 - tn30 / n30
                f[f"{n}_att_rel"] = np.log((n24 / nm24) / (n30 / nm30))
            # cobertura insuficiente (arranque de la descarga): NaN
            bad = ~(n30 > 0) | (tau - 30 * DAY < G.avail.min())
            for k in ("tone24", "tone_rel", "att_rel"):
                f[f"{n}_{k}"] = np.where(bad, np.nan, f[f"{n}_{k}"])
        return f


def _pct_past(series_vals, series_t, q_vals, q_t, win=252, min_n=60):
    """Percentil de q_vals[i] entre los valores de la serie diaria con t en [q_t[i]-win dias habiles, q_t[i])."""
    out = np.full(len(q_vals), np.nan)
    st = np.asarray(series_t); sv = np.asarray(series_vals, float)
    for i, (v, t) in enumerate(zip(q_vals, q_t)):
        if not np.isfinite(v):
            continue
        j1 = np.searchsorted(st, t, side="left")
        j0 = max(0, j1 - win)
        h = sv[j0:j1]; h = h[np.isfinite(h)]
        if len(h) >= min_n:
            out[i] = (h < v).mean()
    return out


def build_feats(force=False):
    """Una fila por operacion de la base (hasta 2025) con cada caracteristica cruda y su percentil pasado."""
    if os.path.exists(FEATS) and not force:
        return pd.read_pickle(FEATS)
    S = Sources()
    B = base_trades()
    B = B[B.t < T_END].reset_index(drop=True)
    days = pd.bdate_range("2021-06-01", "2025-12-31")
    d0 = ((days - pd.Timestamp(0)).days.values * DAY).astype(float)
    out = B[["t", "t_in", "leg"]].copy()
    raw = S.at(B.t_in.values.astype(float))
    for hod, legs in ((3600 + 60, ("big_one",)), (15 * 3600, ("momentum", "nfp"))):
        ser = S.at(d0 + hod)
        m = B.leg.isin(legs).values
        for k, v in raw.items():
            if k not in out:
                out[k] = v
                out[f"p_{k}"] = np.nan
            # serie diaria a la misma hora del dia, para el percentil pasado (estrictamente antes de la entrada)
            out.loc[m, f"p_{k}"] = _pct_past(ser[k], d0 + hod, np.asarray(v)[m], B.t_in.values[m])
    out.to_pickle(FEATS)
    return out


FEAT_NAMES = ["t5yie_d5", "t5yifr_d5", "dfii5_d5", "t10y2y", "t10y2y_d20", "dgs3mo_d20", "stlfsi", "stlfsi_d",
              "epu7", "vix_term", "skew", "skew_d5", "gvz_vix", "gld_flow5", "gld_flow20", "gld_prem5", "gld_volz",
              "gold_tone24", "gold_tone_rel", "gold_att_rel", "fed_tone24", "fed_tone_rel", "fed_att_rel"]


# ------------------------------------------------------------------ base, F1 y reglas
def base_and_f1():
    from bot_backtesting.fullsim.opt_C_final import POL, regime_weights
    from bot_backtesting.fullsim.opt_C_regimen import attach, build_features
    B = base_trades()
    F1 = regime_weights(attach(B, build_features()[["vpct"]]), POL["F1 bo_vpct_off"])
    return B, F1


def apply_rule(T, Fe, col, th, bad_hi, legs, mult):
    """Peso x mult en las operaciones de `legs` cuyo percentil pasado cae en la zona mala
    (>= th si bad_hi, < th si no). Sin dato: peso sin cambio."""
    C = T.copy()
    p = pd.Series(Fe.set_index("t")[f"p_{col}"]).reindex(C.t.values).values
    bad = (p >= th) if bad_hi else (p < th)
    m = C.leg.isin(legs).values & np.isfinite(p) & bad
    C.loc[m, "w"] = C.loc[m, "w"] * mult
    return C


LEGS = {"bo": ("big_one",), "mom": ("momentum",), "all": ("big_one", "momentum", "nfp")}
THS = [0.33, 0.5, 0.67]


def grid():
    low_priority()
    Fe = build_feats()
    B, F1 = base_and_f1()
    rows = []
    t0 = time.time()
    for base_name, T in (("base", B), ("F1", F1)):
        for col in FEAT_NAMES:
            if f"p_{col}" not in Fe or Fe[f"p_{col}"].notna().sum() < 200:
                continue
            for lg, legs in LEGS.items():
                if base_name == "F1" and lg == "all":
                    continue
                for th in THS:
                    for bad_hi in (True, False):
                        for mult in ((0.0, 0.5) if base_name == "base" else (0.0,)):
                            C = apply_rule(T, Fe, col, th, bad_hi, legs, mult)
                            name = f"F/datos {base_name} {col} {lg} {'>=' if bad_hi else '<'}{th} x{mult}"
                            r = compare(C, B, "sel", name, boot=False)
                            rr = dict(r)
                            if base_name == "F1":
                                rr["mar_vs_f1"] = r["mar_c"] / evaluate(F1, "sel")["mar"]
                            register("F", name, rr, dict(base=base_name, col=col, legs=lg, th=th, bad_hi=bad_hi,
                                                         mult=mult))
                            rr.update(base=base_name, col=col, lg=lg, th=th, bad_hi=bad_hi, mult=mult,
                                      expo=C.loc[(C.t >= period("sel")[0].timestamp()) & (C.t < period("sel")[1].timestamp()), "w"].sum())
                            rows.append(rr)
        print(base_name, "listo", len(rows), f"{time.time()-t0:.0f}s", flush=True)
    G = pd.DataFrame(rows)
    G.to_pickle(GRID)
    return G


def neighbors(G, row):
    S = G[(G.base == row.base) & (G.col == row.col) & (G.lg == row.lg) & (G.bad_hi == row.bad_hi)
          & (G.mult == row.mult) & (abs(G.th - row.th) > 1e-9) & (abs(G.th - row.th) < 0.2)]
    return float(S.mar_ratio.min()) if len(S) else np.nan


def show_top(G, n=25):
    for b in ("base", "F1"):
        H = G[G.base == b].copy()
        H["vec_min"] = [neighbors(G, r) for r in H.itertuples()]
        H["ok_dm"] = (H.peor_dia_c >= H.peor_dia_b - 1e-3) & (H.peor_mes_c >= H.peor_mes_b - 1e-3)
        key = "mar_vs_f1" if b == "F1" else "mar_ratio"
        print(f"=== {b}: {len(H)} variantes; mediana {key} {H[key].median():.2f}; p95 {H[key].quantile(.95):.2f}")
        cols = ["col", "lg", "th", "bad_hi", "mult", key, "mar_ratio", "vec_min", "ok_dm", "peor_dia_c", "peor_mes_c",
                "cagr_c", "cagr_lote_mayor", "dd_c"]
        print(H.sort_values(key, ascending=False)[cols].head(n).round(3).to_string())


# ------------------------------------------------------------------ finalistas
def perm_null(T, Fe, spec, per, n=200, seed=11):
    """Permuta el percentil de la caracteristica entre las operaciones de la(s) pata(s) dentro del periodo."""
    a, b = period(per)
    rng = np.random.default_rng(seed)
    col = f"p_{spec['col']}"
    m = (Fe.t >= a.timestamp()) & (Fe.t < b.timestamp()) & Fe.leg.isin(LEGS[spec["lg"]])
    out = []
    for _ in range(n):
        Fp = Fe.copy()
        v = Fp.loc[m, col].values.copy()
        Fp.loc[m, col] = rng.permutation(v)
        C = apply_rule(T, Fp, spec["col"], spec["th"], spec["bad_hi"], LEGS[spec["lg"]], spec["mult"])
        out.append(evaluate(C, per)["mar"])
    return np.array(out)


def final(specs, fe=None, tag="datos", out="opt_F_datos_final.pkl"):
    """specs: lista de dict(base, col, lg, th, bad_hi, mult). fe: tabla de caracteristicas (por defecto la de datos)."""
    low_priority()
    Fe = build_feats() if fe is None else fe
    B, F1 = base_and_f1()
    res = []
    for spec in specs:
        T = F1 if spec["base"] == "F1" else B
        C = apply_rule(T, Fe, spec["col"], spec["th"], spec["bad_hi"], LEGS[spec["lg"]], spec["mult"])
        nm = f"F/{tag} final {spec}"
        o = {"spec": str(spec)}
        rs = compare(C, B, "sel", nm + " [sel]"); register("F", nm + " [sel]", rs, spec)
        mf1 = evaluate(F1, "sel")["mar"]
        o["sel_vs_f1"] = rs["mar_c"] / mf1
        for y, p in YEARS.items():
            o[y] = evaluate(C, p)["mar"] / evaluate(T, p)["mar"]
        nl = perm_null(T, Fe, spec, "sel")
        o["null_pct"] = float((nl < rs["mar_c"]).mean())
        o["null_p95_vs_ref"] = float(np.percentile(nl, 95) / evaluate(T, "sel")["mar"])
        rv = compare(C, B, "val", nm + " [val]"); register("F", nm + " [val]", rv, spec)
        o["val_vs_f1"] = rv["mar_c"] / evaluate(F1, "val")["mar"]
        nlv = perm_null(T, Fe, spec, "val", n=200)
        o["val_null_pct"] = float((nlv < rv["mar_c"]).mean())
        for k in ("mar_c", "mar_ratio", "cagr_c", "dd_c", "peor_dia_c", "peor_mes_c", "p", "cagr_lote_mayor", "pasa"):
            o[f"sel_{k}"] = rs.get(k); o[f"val_{k}"] = rv.get(k)
        res.append(o)
        print(pd.Series(o).to_string(), flush=True)
    R = pd.DataFrame(res)
    R.to_pickle(os.path.join(RESULTS, out))
    return R


# ------------------------------------------------------------------ modelo con todas las nuevas (CV purgada)
def purged_folds(t, k=5, embargo_days=5):
    t = np.asarray(t); o = np.argsort(t); folds = np.array_split(o, k)
    for f in folds:
        a, b = t[f].min(), t[f].max()
        tr = np.nonzero((t < a - embargo_days * DAY) | (t > b + embargo_days * DAY))[0]
        yield tr, f


def meta(drop_frac=0.3):
    """Logistica L2 sobre percentiles de las 23 nuevas: P(R>0) por pata (BO, Momentum), CV purgada en sel.
    Peso 0 al `drop_frac` mas bajo (corte con los cuantiles del pliegue de entrenamiento)."""
    from sklearn.linear_model import LogisticRegression
    low_priority()
    Fe = build_feats()
    B, F1 = base_and_f1()
    a, b = period("sel")
    out = []
    for base_name, T in (("base", B), ("F1", F1)):
        for C_reg in (0.1, 1.0):
            W = T.copy()
            aucs = []
            for leg in ("big_one", "momentum"):
                M = T[(T.leg == leg) & (T.t >= a.timestamp()) & (T.t < b.timestamp()) & (T.w > 0)]
                Z = Fe.set_index("t").reindex(M.t.values)[[f"p_{c}" for c in FEAT_NAMES]].fillna(0.5).values - 0.5
                y = (M.pnl.values > 0).astype(int)
                sc = np.full(len(M), np.nan); thr = np.full(len(M), np.nan)
                for tr, te in purged_folds(M.t.values):
                    m = LogisticRegression(C=C_reg, max_iter=500).fit(Z[tr], y[tr])
                    sc[te] = m.predict_proba(Z[te])[:, 1]
                    thr[te] = np.quantile(m.predict_proba(Z[tr])[:, 1], drop_frac)
                from sklearn.metrics import roc_auc_score
                aucs.append(roc_auc_score(y, sc))
                W.loc[M.index[sc < thr], "w"] = 0.0
            name = f"F/meta logit C={C_reg} {base_name} quita{drop_frac}"
            r = compare(W, B, "sel", name)
            register("F", name, r, dict(C=C_reg, base=base_name, auc_bo=aucs[0], auc_mom=aucs[1]))
            out.append(dict(name=name, auc_bo=aucs[0], auc_mom=aucs[1], mar_ratio=r["mar_ratio"], p=r["p"],
                            vs_f1=r["mar_c"] / evaluate(F1, "sel")["mar"]))
            print(out[-1], flush=True)
    return pd.DataFrame(out)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "feats"
    if cmd == "feats":
        low_priority()
        t0 = time.time()
        Fe = build_feats(force=True)
        print(Fe.describe().T.round(3).to_string(), f"\n{time.time()-t0:.0f}s")
    elif cmd == "grid":
        show_top(grid())
    elif cmd == "top":
        show_top(pd.read_pickle(GRID))
    elif cmd == "meta":
        print(meta().round(3).to_string())
