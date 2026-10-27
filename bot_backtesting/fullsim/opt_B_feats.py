"""Linea B (tamano inteligente / meta-labeling): caracteristicas por operacion e2, solo con informacion
disponible AL ENTRAR (t_in). Una fila por operacion de base_trades(), mismo indice.

Que construye (todo estrictamente antes de t_in):
  * regimen del oro (velas M15 del broker): s, rv de 1/5/22 dias, HAR simple, percentil de rv22 en 250 dias,
    retornos de 1/5/21/63 dias en ATR_D, eficiencia de Kaufman 20 d, ADX(14) diario, ATR_D / ATR_D de 100 d.
  * sesion: hueco de apertura (open 01:00 vs ultimo cierre del dia previo), retorno de EE.UU. del dia previo
    (15:00 -> ultimo cierre), y para Momentum/NFP el tramo 01:00 -> t (retorno a favor del lado, rango, rv).
  * mercados del broker M15 en tiempo real (ultimo cierre anterior a t_in): VIX (nivel, cambio 1 d), USDX
    (retorno 24 h, firmado por el lado), plata y SP500 (retorno 24 h).
  * FRED con retraso de 2 dias habiles (fecha NY): VIXCLS, GVZCLS (nivel, cambio 5 d), DFII10 (cambio 1 y 5 d),
    DTWEXBGS (cambio 5 d), T10YIE (cambio 5 d). BAMLH0A0HYM2 empieza en 2023-10: no se usa.
  * COT (dinero gestionado neto / OI y su z de 52 semanas): martes + 6 dias (publicado viernes 15:30 NY).
  * calendario: dia de la semana, NFP/IPC/FOMC por separado, fin de mes.
  * desempeno reciente (solo operaciones YA cerradas al entrar): R medio de las ultimas 20/60 de la misma
    pata y de la cartera, y desviacion de las ultimas 60 de la pata.
Salida: results/opt_B_feats.pkl (cacheado). Uso: .venv/Scripts/python -m bot_backtesting.fullsim.opt_B_feats
"""
import os

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.opt_base import DATA, HERE, RESULTS, base_trades, low_priority, m15

FP = os.path.join(RESULTS, "opt_B_feats.pkl")


def _asof(times, vals, tq):
    """ultimo valor con time < tq (estricto)."""
    i = np.searchsorted(times, tq, side="left") - 1
    out = np.where(i >= 0, vals[np.clip(i, 0, None)], np.nan)
    return out


def _broker(sym):
    x = pd.read_pickle(os.path.join(DATA, "broker_multi", f"{sym}.pkl")).sort_values("time")
    # el close de la vela que empieza en time se conoce en time+900
    return x.time.values + 900, x.close.values.astype(float)


def _fred(name):
    z = pd.read_csv(os.path.join(DATA, "econ", "macro", f"{name}.csv"))
    z.columns = ["date", "v"]
    z["v"] = pd.to_numeric(z.v, errors="coerce")
    z = z.dropna()
    return pd.Series(z.v.values, index=pd.to_datetime(z.date)).sort_index()


def build(force=False):
    if os.path.exists(FP) and not force:
        return pd.read_pickle(FP)
    B = base_trades().copy()
    X, D = m15()
    T, O, H, L, C = (X[c].values for c in ("time", "open", "high", "low", "close"))
    # ---------------- diario (dia servidor), todo conocido al cierre del dia d -> se usa con shift(1)
    lr = np.r_[np.nan, np.diff(np.log(C))]
    X = X.assign(lr=lr)
    rv = np.sqrt(X.groupby("d").lr.apply(lambda s: np.nansum(s.values ** 2))) * 100
    Dd = D.copy()
    Dd["rv"] = rv
    c = Dd.C
    Dd["rv1"] = Dd.rv.shift(1); Dd["rv5"] = Dd.rv.rolling(5).mean().shift(1); Dd["rv22"] = Dd.rv.rolling(22).mean().shift(1)
    Dd["har"] = 0.35 * Dd.rv1 + 0.35 * Dd.rv5 + 0.30 * Dd.rv22
    Dd["rv22_pct"] = Dd.rv22.rolling(250, min_periods=60).rank(pct=True)
    Dd["rv_ratio"] = Dd.rv5 / Dd.rv22
    atr = Dd.atrd
    Dd["atr_ratio"] = atr / atr.rolling(100, min_periods=40).mean()
    for k in (1, 5, 21, 63):
        Dd[f"ret{k}"] = ((c - c.shift(k)) / atr).shift(1)          # en ATR_D, conocido antes del dia d
    ch = c.diff().abs()
    Dd["eff20"] = ((c - c.shift(20)).abs() / ch.rolling(20).sum()).shift(1)
    # ADX(14) diario
    up, dn = Dd.H.diff(), -Dd.L.diff()
    pdm = np.where((up > dn) & (up > 0), up, 0.0); ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = np.maximum(Dd.H - Dd.L, np.maximum((Dd.H - c.shift()).abs(), (Dd.L - c.shift()).abs()))
    atr14 = tr.ewm(alpha=1 / 14, adjust=False).mean()
    pdi = 100 * pd.Series(pdm, index=Dd.index).ewm(alpha=1 / 14, adjust=False).mean() / atr14
    ndi = 100 * pd.Series(ndm, index=Dd.index).ewm(alpha=1 / 14, adjust=False).mean() / atr14
    dx = 100 * (pdi - ndi).abs() / (pdi + ndi)
    Dd["adx"] = dx.ewm(alpha=1 / 14, adjust=False).mean().shift(1)
    Dd["dmi"] = ((pdi - ndi) / (pdi + ndi)).shift(1)
    # retorno de EE.UU. del dia previo: open 15:00 -> ultimo cierre del dia, en ATR_D
    s15 = pd.Series(O, index=T)
    us_open = s15.reindex(Dd.index.values * 86400 + 15 * 3600).values
    Dd["us_prev"] = pd.Series((Dd.C.values - us_open), index=Dd.index).shift(1) / atr
    Dd["c_prev"] = Dd.C.shift(1)
    d = (B.t // 86400).values
    F = pd.DataFrame(index=B.index)
    for k in ("rv1", "rv5", "rv22", "har", "rv22_pct", "rv_ratio", "atr_ratio", "ret1", "ret5", "ret21", "ret63",
              "eff20", "adx", "dmi", "us_prev"):
        F[k] = Dd[k].reindex(d).values
    F["s"] = Dd.s.reindex(d).values
    F["leg_bo"] = (B.leg == "big_one").astype(int).values
    F["leg_mo"] = (B.leg == "momentum").astype(int).values
    F["side"] = B.side.values
    F["w0"] = B.w.values
    F["atr15_atrd"] = (B.atr15 / B.atrd).values
    # hueco 01:00 vs ultimo cierre previo
    o01 = s15.reindex(d * 86400 + 3600).values
    F["gap"] = (o01 - Dd.c_prev.reindex(d).values) / B.atrd.values
    # tramo del dia hasta la entrada (solo Momentum/NFP; la Big One entra a las 01:01)
    k15 = B.k15.values
    tod = np.zeros(len(B)); rng = np.zeros(len(B)); rvs = np.zeros(len(B))
    for i, (kk, leg, dd) in enumerate(zip(k15, B.leg.values, d)):
        if leg == "big_one":
            tod[i] = rng[i] = rvs[i] = 0.0
            continue
        k0 = np.searchsorted(T, dd * 86400 + 3600)
        if k0 >= kk:
            continue
        tod[i] = (O[kk] - O[k0]) * B.side.values[i]
        rng[i] = H[k0:kk].max() - L[k0:kk].min()
        rvs[i] = np.sqrt(np.nansum(lr[k0 + 1:kk] ** 2)) * 100
    F["tod_fav"] = tod / B.atrd.values; F["tod_rng"] = rng / B.atrd.values
    F["tod_rv"] = np.where(B.leg.values == "big_one", 0, rvs / F.rv22.values)
    # ---------------- broker en tiempo real
    tq = B.t_in.values
    for sym, nm in (("VIX", "bvix"), ("USDX", "usdx"), ("XAGUSD", "xag"), ("SP500", "spx")):
        tt, cc = _broker(sym)
        now = _asof(tt, cc, tq); prev = _asof(tt, cc, tq - 86400)
        if nm == "bvix":
            F["bvix"] = now; F["bvix_chg"] = now - prev
        else:
            F[f"{nm}_r24"] = (now / prev - 1) * 100
    F["usdx_r24_side"] = F.usdx_r24 * F.side
    g_now = _asof(T + 900, C, tq); g_prev = _asof(T + 900, C, tq - 86400)
    F["xag_rel"] = F.xag_r24 - (g_now / g_prev - 1) * 100
    # ---------------- FRED, 2 dias habiles de retraso sobre la fecha NY de la entrada
    ny = pd.to_datetime(tq, unit="s") - pd.Timedelta(hours=7)
    cut = ny.normalize() - pd.offsets.BDay(2)
    cutv = cut.values
    for nm, key in (("VIXCLS", "vix"), ("GVZCLS", "gvz"), ("DFII10", "ry"), ("DTWEXBGS", "usd"), ("T10YIE", "bei")):
        s = _fred(nm)
        def lag(k):
            i = np.searchsorted(s.index.values, cutv, side="right") - 1 - k     # ultimo dato con fecha <= corte
            return np.where(i >= 0, s.values[np.clip(i, 0, None)], np.nan)
        F[f"f_{key}"] = lag(0)
        F[f"f_{key}_d5"] = lag(0) - lag(5) if key != "usd" else (lag(0) / lag(5) - 1) * 100
        if key == "ry":
            F["f_ry_d1"] = lag(0) - lag(1)
    F["gvz_vix"] = F.f_gvz / F.f_vix
    # ---------------- COT
    Cc = pd.read_csv(os.path.join(DATA, "econ", "cot", "gold_cot.csv"))
    Cc["avail"] = pd.to_datetime(Cc["Report_Date_as_YYYY-MM-DD"]) + pd.Timedelta(days=6)
    Cc = Cc.sort_values("avail").drop_duplicates("avail")
    net = (Cc.M_Money_Positions_Long_All - Cc.M_Money_Positions_Short_All) / Cc.Open_Interest_All * 100
    cz = (net - net.rolling(52).mean()) / net.rolling(52).std()
    srv_day = pd.to_datetime(d * 86400, unit="s")
    av = Cc.avail.values
    for nm, ser in (("cot_net", net), ("cot_z", cz), ("cot_chg", net.diff())):
        i = np.searchsorted(av, srv_day.values, side="right") - 1
        F[nm] = np.where(i >= 0, ser.values[np.clip(i, 0, None)], np.nan)
    # ---------------- calendario
    E = pd.read_csv(os.path.join(HERE, "events_us.csv"))
    ed = (pd.to_datetime(E.date) - pd.Timestamp("1970-01-01")).dt.days
    for k in ("NFP", "CPI", "FOMC"):
        F[f"ev_{k}"] = np.isin(d, ed[E.event == k].values).astype(int)
    F["ev_any"] = F[["ev_NFP", "ev_CPI", "ev_FOMC"]].max(axis=1)
    F["dow"] = (d + 3) % 7
    dt = pd.to_datetime(d * 86400, unit="s")
    F["month_end"] = ((dt + pd.offsets.BDay(2)).month != dt.month).astype(int)
    # ---------------- desempeno reciente (solo cerradas antes de entrar)
    t_out, R, legs = B.t_out.values, B.R.values, B.leg.values
    order = np.argsort(t_out)
    for nm, n, mask_leg in (("perf_leg20", 20, True), ("perf_leg60", 60, True), ("perf_all60", 60, False)):
        out = np.full(len(B), np.nan)
        for i in range(len(B)):
            j = order[t_out[order] <= tq[i]]
            if mask_leg:
                j = j[legs[j] == legs[i]]
            if len(j) >= n // 2:
                out[i] = R[j[-n:]].mean()
        F[nm] = out
    sd = np.full(len(B), np.nan)
    for i in range(len(B)):
        j = order[t_out[order] <= tq[i]]
        j = j[legs[j] == legs[i]]
        if len(j) >= 30:
            sd[i] = R[j[-60:]].std()
    F["sd_leg60"] = sd
    F.to_pickle(FP)
    return F


if __name__ == "__main__":
    low_priority()
    F = build(force=True)
    B = base_trades()
    S = B.t < pd.Timestamp("2025-01-01").timestamp()
    print(F.shape)
    print(F[S.values].describe().T[["count", "mean", "std", "min", "max"]].round(3).to_string())
