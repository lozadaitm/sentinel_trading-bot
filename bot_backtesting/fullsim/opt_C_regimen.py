"""Linea C (sesion de optimizacion e2, 27-oct-2026): REGIMENES DE MERCADO.

Que hace este script:
  1. Construye caracteristicas diarias conocidas ANTES de empezar cada dia de servidor (todo con datos
     hasta el cierre del dia anterior; nada mira adelante):
       - tendencia/rango: eficiencia de Kaufman (10/20/40 d), ADX(14) diario, pendiente normalizada 20 d;
       - volatilidad: ATR_D/precio y su percentil rodante de 252 d, cociente vol 5 d / vol 60 d;
       - riesgo: VIX y USDX del broker (cierre del ultimo M15 antes del dia), SP500 del broker;
       - HMM: statsmodels MarkovRegression (2 y 3 estados, varianza cambiante) reajustado cada mes con
         ventana expandida, aplicado al mes siguiente con PROBABILIDADES FILTRADAS (no suavizadas);
       - clustering: GaussianMixture (2/3/4) y KMeans(3) sobre caracteristicas diarias estandarizadas,
         reajustado cada mes solo con el pasado; etiquetas ordenadas por volatilidad media del cluster.
     Historia diaria del oro: M15 Dukascopy (2021-01 -> 2022-08) + M15 del broker despues.
  2. Tabla del R de cada pata del e2 por regimen en 'sel' (y 2023 / 2024 por separado).
  3. Grilla de filtros/pesos por regimen: para cada regla, umbral, lado, pata y multiplicador
     (0 = apagar, 0,5 = medio peso, 1,5 = subir) se evalua la cartera completa en 'sel' y se registra.
     Para no tardar horas, la grilla usa una comparacion rapida (sin el nulo 'lote mayor' ni bootstrap);
     los mejores se re-evaluan con compare() completo (con bootstrap) y tambien se registran.

Correr (desde la raiz del repo):
  .venv/Scripts/python -m bot_backtesting.fullsim.opt_C_regimen            # todo
  .venv/Scripts/python -m bot_backtesting.fullsim.opt_C_regimen tabla      # solo caracteristicas + tablas
Salidas: results/opt_C_feats.pkl, results/opt_C_tabla.txt, results/opt_C_grid.pkl, registro opt_registry.csv
"""
import os
import sys
import warnings

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.opt_base import (DATA, RESULTS, base_trades, clip, compare, evaluate, low_priority, m15,
                                              register)

warnings.filterwarnings("ignore")
FEATS = os.path.join(RESULTS, "opt_C_feats.pkl")
YEARS = {"y2023": (pd.Timestamp("2023-01-01"), pd.Timestamp("2024-01-01")),
         "y2024": (pd.Timestamp("2024-01-01"), pd.Timestamp("2025-01-01"))}


# ------------------------------------------------------------------ historia diaria
def daily_gold():
    """OHLC diario por dia de servidor: duka antes del inicio del broker, broker despues."""
    X, D = m15()
    duka = pd.read_pickle(os.path.join(DATA, "frames_duka.pkl"))["M15"]
    d0 = int(D.index.min())
    a = duka[duka.time // 86400 < d0].copy()
    a["d"] = a.time // 86400
    A = a.groupby("d").agg(O=("open", "first"), H=("high", "max"), L=("low", "min"), C=("close", "last"))
    G = pd.concat([A, D[["O", "H", "L", "C"]]]).sort_index()
    G = G[((G.index + 3) % 7) < 5]
    return G


def daily_close_of(sym):
    """Cierre por dia de servidor (ultimo M15 del dia) de un simbolo de broker_multi."""
    Y = pd.read_pickle(os.path.join(DATA, "broker_multi", f"{sym}.pkl"))
    return Y.groupby(Y.time // 86400).close.last()


def _adx(H, L, C, n=14):
    up, dn = H.diff(), -L.diff()
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    mdm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = np.maximum(H - L, np.maximum((H - C.shift()).abs(), (L - C.shift()).abs()))
    a = 1 / n
    atr = tr.ewm(alpha=a, adjust=False).mean()
    pdi = 100 * pd.Series(pdm, H.index).ewm(alpha=a, adjust=False).mean() / atr
    mdi = 100 * pd.Series(mdm, H.index).ewm(alpha=a, adjust=False).mean() / atr
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi)
    return dx.ewm(alpha=a, adjust=False).mean()


def _hmm_filtered(r, k=2, ar=False, min_n=250):
    """Probabilidad FILTRADA del estado de mayor varianza (k=2) o etiqueta del estado mas probable ordenada por
    varianza (k=3). Reajuste mensual expandido; el mes siguiente se filtra con los parametros fijos."""
    from statsmodels.tsa.regime_switching.markov_autoregression import MarkovAutoregression
    from statsmodels.tsa.regime_switching.markov_regression import MarkovRegression
    r = r.dropna()
    idx = r.index
    months = pd.to_datetime(idx, unit="D").to_period("M")
    um = months.unique()
    out_p = pd.Series(np.nan, idx)
    out_l = pd.Series(np.nan, idx)
    prev = None
    for i, m in enumerate(um[:-1]):
        tr = r[months <= m]
        if len(tr) < min_n:
            continue
        nxt = months == um[i + 1]
        full = r[months <= um[i + 1]]
        try:
            if ar:
                mod = MarkovAutoregression(tr.values, k_regimes=k, order=1, switching_variance=True,
                                           switching_ar=False)
            else:
                mod = MarkovRegression(tr.values, k_regimes=k, trend="c", switching_variance=True)
            res = mod.fit(start_params=prev, disp=False, maxiter=200) if prev is not None else \
                mod.fit(disp=False, search_reps=10, maxiter=200)
            prev = res.params
            mod2 = (MarkovAutoregression(full.values, k_regimes=k, order=1, switching_variance=True,
                                         switching_ar=False) if ar else
                    MarkovRegression(full.values, k_regimes=k, trend="c", switching_variance=True))
            f = mod2.filter(res.params)
            P = np.asarray(f.filtered_marginal_probabilities)
            names = list(mod.param_names)
            sig = np.array([res.params[names.index(f"sigma2[{j}]")] for j in range(k)])
            order = np.argsort(sig)
            off = len(full) - P.shape[0]          # AR(1) pierde la primera observacion
            sel = np.nonzero(nxt[months <= um[i + 1]])[0] - off
            sel_ok = sel[sel >= 0]
            Pn = P[sel_ok][:, order]
            ix = full.index[sel_ok + off]
            out_p.loc[ix] = Pn[:, -1]
            out_l.loc[ix] = Pn.argmax(1)
        except Exception as e:  # noqa
            print("hmm fallo", m, e)
    return out_p, out_l


def _clusters(F, cols, kind="gmm", k=3, min_n=250):
    """Etiqueta de cluster ajustado cada mes solo con el pasado. Etiquetas ordenadas por la media de 'vpct'."""
    from sklearn.cluster import KMeans
    from sklearn.mixture import GaussianMixture
    Z = F[cols].dropna()
    months = pd.to_datetime(Z.index, unit="D").to_period("M")
    um = months.unique()
    lab = pd.Series(np.nan, Z.index)
    for i, m in enumerate(um[:-1]):
        tr = Z[months <= m]
        if len(tr) < min_n:
            continue
        mu, sd = tr.mean(), tr.std()
        Xt = ((tr - mu) / sd).values
        mdl = (GaussianMixture(k, covariance_type="full", random_state=0, n_init=3) if kind == "gmm"
               else KMeans(k, random_state=0, n_init=10)).fit(Xt)
        lt = mdl.predict(Xt)
        vcol = cols.index("vpct") if "vpct" in cols else 0
        means = [Xt[lt == j, vcol].mean() if (lt == j).any() else 0 for j in range(k)]
        rank = np.argsort(np.argsort(means))
        te = Z[months == um[i + 1]]
        lab.loc[te.index] = rank[mdl.predict(((te - mu) / sd).values)]
    return lab


def build_features(force=False):
    if os.path.exists(FEATS) and not force:
        return pd.read_pickle(FEATS)
    G = daily_gold()
    C = G.C
    ret = np.log(C).diff()
    F = pd.DataFrame(index=G.index)
    for n in (10, 20, 40):
        F[f"er{n}"] = ((C - C.shift(n)).abs() / C.diff().abs().rolling(n).sum()).shift(1)
    F["adx"] = _adx(G.H, G.L, C).shift(1)
    F["slope20"] = ((C / C.shift(20) - 1) / (ret.rolling(20).std() * np.sqrt(20))).shift(1)
    F["ret20"] = (C / C.shift(20) - 1).shift(1)
    atrp = (G.H - G.L).rolling(14).mean() / C
    F["atrp"] = atrp.shift(1)
    F["vpct"] = atrp.rolling(252, min_periods=120).rank(pct=True).shift(1)
    F["rvr"] = (ret.rolling(5).std() / ret.rolling(60).std()).shift(1)
    # mercados del broker (tiempo real): cierre del dia anterior
    for sym, col in (("VIX", "vix"), ("USDX", "usdx"), ("SP500", "spx")):
        s = daily_close_of(sym).reindex(range(int(G.index.min()), int(G.index.max()) + 1)).ffill()
        s = s.reindex(G.index)
        F[col] = s.shift(1)
    F["vix_rel"] = F.vix / F.vix.rolling(60, min_periods=40).mean() - 1
    F["usdx20"] = F.usdx / F.usdx.shift(20) - 1
    F["spx20"] = F.spx / F.spx.shift(20) - 1
    # HMM con probabilidades filtradas (el retorno del dia d-1 decide el regimen del dia d)
    r100 = (ret * 100)
    p2, _ = _hmm_filtered(r100, k=2)
    F["hmm2_p"] = p2.shift(1)
    _, l3 = _hmm_filtered(r100, k=3)
    F["hmm3"] = l3.shift(1)
    p2a, _ = _hmm_filtered(r100, k=2, ar=True)
    F["hmmar_p"] = p2a.shift(1)
    # clustering sobre caracteristicas de oro solamente (historia desde 2021; VIX broker empieza 2022-04)
    cols = ["vpct", "er20", "slope20", "rvr"]
    F["gmm2"] = _clusters(F, cols, "gmm", 2)
    F["gmm3"] = _clusters(F, cols, "gmm", 3)
    F["gmm4"] = _clusters(F, cols, "gmm", 4)
    F["km3"] = _clusters(F, cols, "km", 3)
    F.to_pickle(FEATS)
    return F


# ------------------------------------------------------------------ reglas binarias de regimen
def rule_defs():
    """(nombre, columna, umbrales). Regimen 'alto' = columna >= umbral."""
    return [
        ("er10", "er10", [0.2, 0.25, 0.3, 0.35, 0.4, 0.45]),
        ("er20", "er20", [0.15, 0.2, 0.25, 0.3, 0.35, 0.4]),
        ("er40", "er40", [0.1, 0.15, 0.2, 0.25, 0.3]),
        ("adx", "adx", [15, 18, 21, 24, 27, 30]),
        ("slope20", "slope20", [-1.0, -0.5, 0.0, 0.5, 1.0, 1.5]),
        ("vpct", "vpct", [0.3, 0.4, 0.5, 0.6, 0.7, 0.8]),
        ("rvr", "rvr", [0.7, 0.85, 1.0, 1.15, 1.3, 1.5]),
        ("vix", "vix", [14, 16, 18, 20, 22]),
        ("vix_rel", "vix_rel", [-0.15, -0.05, 0.0, 0.05, 0.15]),
        ("usdx20", "usdx20", [-0.02, -0.01, 0.0, 0.01, 0.02]),
        ("spx20", "spx20", [-0.03, -0.01, 0.0, 0.01, 0.03]),
        ("hmm2_p", "hmm2_p", [0.3, 0.4, 0.5, 0.6, 0.7]),
        ("hmmar_p", "hmmar_p", [0.3, 0.4, 0.5, 0.6, 0.7]),
    ]


def cat_defs():
    return ["hmm3", "gmm2", "gmm3", "gmm4", "km3"]


def attach(B, F):
    B = B.copy()
    d = (B.t // 86400).astype(int)
    for c in F.columns:
        B[c] = F[c].reindex(d.values).values
    return B


def regime_table(B, F, per="sel"):
    T = attach(clip(B, per), F)
    lines = []
    for name, col, thr in rule_defs():
        th = np.median(thr) if name not in ("hmm2_p", "hmmar_p") else 0.5
        lab = np.where(T[col].isna(), "nan", np.where(T[col] >= th, f">={th:g}", f"<{th:g}"))
        lines.append(_tab(T, lab, f"{name} (umbral {th:g})"))
    for c in cat_defs():
        lab = np.where(T[c].isna(), "nan", T[c].fillna(-1).astype(int).astype(str))
        lines.append(_tab(T, lab, c))
    lab = T.state.fillna(99).astype(int).astype(str)
    lines.append(_tab(T, lab, "s (tendencia e2)"))
    return "\n".join(lines)


def _tab(T, lab, title):
    T = T.assign(lab=lab, yr=pd.to_datetime(T.t, unit="s").dt.year)
    g = T.groupby(["leg", "lab"]).R.agg(n="size", R="mean", sd="std")
    g["t"] = g.R / (g.sd / np.sqrt(g.n))
    for y in (2023, 2024):
        g[f"R{y}"] = T[T.yr == y].groupby(["leg", "lab"]).R.mean()
    return f"--- {title}\n" + g.round(3).to_string()


# ------------------------------------------------------------------ evaluacion rapida
_BASE = {}


def quick(C, label, per="sel", wcol="w"):
    if per not in _BASE:
        _BASE[per] = evaluate(_BASE["B"], per)
    mb = _BASE[per]
    mc = evaluate(C, per, wcol=wcol)
    out = dict(label=label, per=per, mar_c=mc["mar"], mar_b=mb["mar"], mar_ratio=mc["mar"] / mb["mar"],
               cagr_c=mc["cagr"], cagr_b=mb["cagr"], dd_c=mc["dd"], dd_b=mb["dd"],
               peor_dia_c=mc["peor_dia"], peor_dia_b=mb["peor_dia"], peor_mes_c=mc["peor_mes"],
               peor_mes_b=mb["peor_mes"], n_c=mc["n"], n_b=mb["n"], sharpe_c=mc["sharpe_d"], sharpe_b=mb["sharpe_d"],
               rapido=True)
    out["pasa"] = bool(out["mar_ratio"] >= 1.25 and mc["peor_dia"] >= mb["peor_dia"] - 1e-3
                       and mc["peor_mes"] >= mb["peor_mes"] - 1e-3)
    return out


def years_ratio(C, B, wcol="w"):
    r = {}
    for y, p in YEARS.items():
        mc, mb = evaluate(C, p, wcol=wcol), evaluate(B, p)
        r[y] = mc["mar"] / mb["mar"] if mb["mar"] > 0 else np.nan
    return r


def weighted(B, mask, legs, m):
    C = B.copy()
    sel = mask & C.leg.isin(legs)
    C.loc[sel, "w"] = C.loc[sel, "w"] * m
    return C


def grid(B, F):
    """Filtro/peso por regimen. Cada punto se registra (rapido). Devuelve DataFrame de resultados."""
    T = attach(B, F)
    legsets = {"big_one": ["big_one"], "momentum": ["momentum"], "bo+mom": ["big_one", "momentum"]}
    rows = []
    mults = [0.0, 0.5, 1.5]
    for name, col, thr in rule_defs():
        for th in thr:
            hi = (T[col] >= th).values
            ok = T[col].notna().values
            for side, mask in (("alto", hi & ok), ("bajo", (~hi) & ok)):
                for ln, legs in legsets.items():
                    for m in mults:
                        lab = f"C/regla {name}{'>=' if side == 'alto' else '<'}{th:g} {ln} x{m:g}"
                        r = quick(weighted(T, mask, legs, m), lab)
                        register("C", lab, r, dict(regla=name, umbral=th, lado=side, patas=ln, mult=m))
                        rows.append(dict(familia="regla", regla=name, umbral=th, lado=side, patas=ln, mult=m, **r))
        print("listo", name, flush=True)
    for c in cat_defs():
        labs = sorted(T[c].dropna().unique())
        for L in labs:
            mask = (T[c] == L).values
            for ln, legs in legsets.items():
                for m in mults:
                    lab = f"C/cluster {c}=={int(L)} {ln} x{m:g}"
                    r = quick(weighted(T, mask, legs, m), lab)
                    register("C", lab, r, dict(regla=c, umbral=int(L), lado="==", patas=ln, mult=m))
                    rows.append(dict(familia="cluster", regla=c, umbral=L, lado="==", patas=ln, mult=m, **r))
        print("listo", c, flush=True)
    G = pd.DataFrame(rows)
    G.to_pickle(os.path.join(RESULTS, "opt_C_grid.pkl"))
    return G


def neighbors_ok(G, row):
    """Vecinos +-1 paso del umbral (misma regla, lado, patas, multiplicador) >= 1,15x."""
    if row.familia != "regla":
        return np.nan
    thr = dict((n, t) for n, _, t in rule_defs())[row.regla]
    i = thr.index(row.umbral)
    vec = [thr[j] for j in (i - 1, i + 1) if 0 <= j < len(thr)]
    S = G[(G.regla == row.regla) & (G.lado == row.lado) & (G.patas == row.patas) & (G.mult == row.mult)
          & (G.umbral.isin(vec))]
    return float(S.mar_ratio.min()) if len(S) else np.nan


def main():
    low_priority()
    B = base_trades()
    _BASE["B"] = B
    F = build_features()
    print("caracteristicas:", F.shape, "cobertura en sel:", F.loc[F.index >= 19266].notna().mean().round(2).to_dict())
    txt = regime_table(B, F, "sel")
    with open(os.path.join(RESULTS, "opt_C_tabla.txt"), "w", encoding="utf-8") as fh:
        fh.write(txt)
    print(txt)
    if len(sys.argv) > 1 and sys.argv[1] == "tabla":
        return
    G = grid(B, F)
    G["vec_min"] = [neighbors_ok(G, r) for r in G.itertuples()]
    top = G.sort_values("mar_ratio", ascending=False).head(25)
    T = attach(B, F)
    out = []
    for r in top.itertuples():
        if r.familia == "regla":
            col = dict((n, c) for n, c, _ in rule_defs())[r.regla]
            mask = (T[col] >= r.umbral) if r.lado == "alto" else (T[col] < r.umbral)
            mask = (mask & T[col].notna()).values
        else:
            mask = (T[r.regla] == r.umbral).values
        legs = {"big_one": ["big_one"], "momentum": ["momentum"], "bo+mom": ["big_one", "momentum"]}[r.patas]
        C = weighted(T, mask, legs, r.mult)
        res = compare(C, B, "sel", r.label + " [boot]")
        register("C", r.label + " [boot]", res, "re-evaluacion con bootstrap del top-25 de la grilla")
        res.update(years_ratio(C, B))
        res["vec_min"] = r.vec_min
        out.append(res)
    O = pd.DataFrame(out)
    O.to_pickle(os.path.join(RESULTS, "opt_C_top.pkl"))
    pd.set_option("display.width", 250)
    print(O[["label", "mar_c", "mar_ratio", "cagr_c", "dd_c", "peor_dia_c", "peor_mes_c", "p", "cagr_lote_mayor",
             "y2023", "y2024", "vec_min", "pasa"]].round(3).to_string())


if __name__ == "__main__":
    main()
