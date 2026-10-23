"""Big One sobre precios REALES del broker (M15 de XAUUSD+, 2022-08 -> 2026-10), solo simulacion.

Motivo: Dukascopy trae el bid hundido en los primeros minutos de la 01:00 (artefacto de 0,3-2,4 $/oz
segun el año); en 2026 los ticks reales del broker confirman que su M15 se puede operar al ask.
Entrada a la apertura M15 de la 01:00 al ask (spread 0,17 medido + comision 0,12). Camino en M15
(dentro de la vela: primero el lado en contra -> conservador). Salidas: hora 10:00, objetivo,
trailing; candado a L x escala, con L amplio (2..6 x ATR M15 previo, o 0,5..1,5 x ATR diario).
Validacion movil: salida elegida con los años anteriores disponibles (2024: 2022-08..2023).
Uso: python -m bot_backtesting.fullsim.bigone_broker
"""
import os

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.bigone_plus import path as acct_path
from bot_backtesting.fullsim.entrylab import swap_cost

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
RESULTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
SPREAD, COMM = 0.17, 0.06    # comision real de la cuenta RAW: 3 $/lote por lado (24-oct)
LOCK_COST = SPREAD + COMM
SCALES = {"atr15": (2.0, 3.0, 4.0, 6.0), "atrd": (0.5, 1.0, 1.5)}
BASE = ([("time", None, None)] + [("tp", tp, None) for tp in (2.0, 3.0, 4.0)]
        + [("trail", a, d) for a in (2.0, 3.0) for d in (1.0, 2.0)])
CAL = pd.period_range("2024-01", "2026-10", freq="M")


def load():
    X = pd.read_pickle(os.path.join(DATA, "broker_m15_full.pkl")).sort_values("time").reset_index(drop=True)
    h, l, c = X.high.values, X.low.values, X.close.values
    tr = np.r_[h[0] - l[0], np.maximum(h[1:] - l[1:], np.maximum(abs(h[1:] - c[:-1]), abs(l[1:] - c[:-1])))]
    X["atr15"] = pd.Series(tr).rolling(14).mean().shift(1)
    X["d"] = X.time // 86400
    D = X.groupby("d").agg(H=("high", "max"), L=("low", "min"), C=("close", "last"))
    D["atrd"] = (D.H - D.L).rolling(14).mean().shift(1)
    D["s"] = (np.sign(D.C - D.C.shift(21)) + np.sign(D.C - D.C.shift(63))).shift(1)
    return X, D


def build():
    X, D = load()
    T, O, H, L, C = (X[c].values for c in ("time", "open", "high", "low", "close"))
    E = pd.read_csv(os.path.join(os.path.dirname(__file__), "events_us.csv"))
    evd = set((pd.to_datetime(E.date) - pd.Timestamp("1970-01-01")).dt.days)
    rows = []
    for k in np.nonzero(T % 86400 == 3600)[0]:
        d = T[k] // 86400
        if (d + 3) % 7 >= 5 or d not in D.index or not np.isfinite(D.at[d, "atrd"]) or not np.isfinite(X.atr15.iat[k]):
            continue
        n = 36                                                    # 01:00 -> 10:00 en velas M15
        if k + n > len(T) or T[k + n - 1] - T[k] > 9 * 3600:
            continue
        px = O[k] + SPREAD
        fav = H[k:k + n] - px; low = L[k:k + n] - px; opn = O[k:k + n] - px; last = C[k + n - 1] - px
        peak_prev = np.r_[-np.inf, np.maximum.accumulate(fav)[:-1]]
        for sc_name, locks in SCALES.items():
            sc = X.atr15.iat[k] if sc_name == "atr15" else D.at[d, "atrd"]
            u = X.atr15.iat[k]                                   # objetivos/trailing siempre en ATR M15
            for kind, a, dd in BASE:
                i_out, r = n - 1, last
                if kind == "tp":
                    hit = np.nonzero(fav >= a * u)[0]
                    if len(hit):
                        i_out, r = hit[0], a * u
                elif kind == "trail":
                    stop = peak_prev - dd * u
                    hit = np.nonzero((peak_prev >= a * u) & (low <= stop))[0]
                    if len(hit):
                        i_out = hit[0]; r = min(opn[i_out], stop[i_out])
                for lk in locks:
                    lh = np.nonzero(low[:i_out + 1] <= -lk * sc)[0]
                    io, rr, extra = i_out, r, 0.0
                    if len(lh) and lh[0] <= i_out:
                        io = lh[0]; rr = min(opn[io], -lk * sc); extra = -LOCK_COST
                    mae = rr if extra else low[:io + 1].min()
                    pnl = rr - COMM + extra + swap_cost(T[k], T[k + io] + 900, 1)
                    rows.append((T[k], d, D.at[d, "s"], int(d in evd), sc_name, kind, a, dd, lk, pnl, mae, lk * sc))
    R = pd.DataFrame(rows, columns=["t", "d", "state", "ev", "scale", "kind", "a", "dd", "lock", "pnl", "mae", "risk_oz"])
    R["year"] = pd.to_datetime(R.t, unit="s").dt.year
    R["exit"] = exit_label(R)
    R["r_mult"] = R.pnl / R.risk_oz
    return R


def exit_label(R):
    """Nombre de la salida. Con pandas 3, None/NaN en a/dd daba un nombre NaN y la validacion movil
    descartaba las salidas por hora y por objetivo: se rellenan con 0."""
    f = lambda c: R[c].astype(float).fillna(0).map(lambda v: f"{v:g}")
    return R.scale + "_" + R.kind + "_" + f("a") + "_" + f("dd") + "_L" + f("lock")


def walk_forward(R):
    R = R.assign(exit=exit_label(R))
    out = []
    for Y in (2024, 2025, 2026):
        tr, te = R[R.year.isin([Y - 2, Y - 1])], R[R.year == Y]
        best = tr.groupby("exit").r_mult.mean().idxmax()
        out.append(te[te.exit == best].assign(chosen=best))
    return pd.concat(out, ignore_index=True)


def score(T, f, n=2000):
    T = T.copy(); T["m"] = pd.to_datetime(T.t, unit="s").dt.to_period("M"); T["mr"] = T.mae / T.risk_oz
    months = [T.loc[T.m == p, ["r_mult", "mr", "w"]].values.reshape(-1, 3) for p in CAL]
    rng = np.random.default_rng(7)
    res = [acct_path(np.vstack([months[i] for i in rng.integers(0, len(months), 12)]), f, 5000) for _ in range(n)]
    mult = np.array([x[0] for x in res]) / 5000; dd = np.array([x[1] for x in res])
    real = acct_path(np.vstack(months), f, 5000)
    return dict(x12=np.median(mult), mes=np.median(mult) ** (1 / 12) - 1, p_x2=(mult >= 2).mean(), p_x3=(mult >= 3).mean(),
                p_dd50=(dd >= .5).mean(), real_x=real[0] / 5000, real_dd=real[1])


def main():
    fp = os.path.join(RESULTS, "bigone_broker_all.pkl")
    R = pd.read_pickle(fp) if os.path.exists(fp) else build()
    R.to_pickle(fp)
    pd.set_option("display.width", 250)
    ref = R[(R.exit == "atrd_time_nan_nan_L1.5")]
    print("referencia salida 10:00, candado 1,5 ATR diario, R por año y tendencia:")
    print(ref.pivot_table(index="state", columns="year", values="r_mult", aggfunc="mean").round(3).to_string())
    rows = []
    for name, wst, wev in (("alcista", {2: 1}, 1.0), ("alcista_ev50", {2: 1}, 0.5), ("todas_ev50", {2: 1, 0: .5, -2: .5}, 0.5)):
        sub = R[R.state.isin(list(wst))]
        W = pd.concat([walk_forward(g) for _, g in sub.groupby("state")], ignore_index=True)
        W["w"] = W.state.map(wst) * np.where(W.ev == 1, wev, 1.0)
        print(f"{name}: salidas elegidas", W.groupby(["state", "year"]).chosen.first().to_dict())
        print("   R por año:", W.groupby("year").r_mult.mean().round(3).to_dict(), "total", round(W.r_mult.mean(), 3), "n", len(W))
        W.to_pickle(os.path.join(RESULTS, f"bigone_broker_{name}.pkl"))
        for f in (0.02, 0.03, 0.05):
            rows.append(dict(variante=name, riesgo=f, **score(W, f)))
    print(pd.DataFrame(rows).round(3).to_string(index=False))


if __name__ == "__main__":
    main()
