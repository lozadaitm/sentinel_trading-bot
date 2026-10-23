"""«Big One» generica para cualquier activo de data/cross_*.pkl (solo simulacion).

Regla: entrar a la hora h:00 servidor (apertura M5), lado fijo, opcionalmente solo con la tendencia
diaria propia s = +2 / 0 / -2; salida por hora (h + hz), objetivo o trailing, con candado a
L x ATR M15 (congela la perdida). Costo = spread medido en el broker + comision (multiasset.COST).
Sin swap: la salida es antes de la medianoche. Salida elegida por año con los 2 anteriores
(2023..2026), igual que bigone_plus. R = ganancia / distancia del candado.
Uso: python -m bot_backtesting.fullsim.reopen_asset eurusd 1 3 2 [lado]
"""
import os
import sys

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.multiasset import COST

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
RESULTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
TEST_YEARS = (2023, 2024, 2025, 2026)
LOCKS = (1.0, 2.0, 3.0)
_BASE = ([("time", None, None)] + [("tp", tp, None) for tp in (1.0, 2.0, 3.0)]
         + [("trail", a, d) for a in (1.0, 2.0) for d in (0.5, 1.0)])
EXITS = [(k, a, d, lk) for (k, a, d) in _BASE for lk in LOCKS]


def load(name):
    x = pd.read_pickle(os.path.join(DATA, f"cross_{name}.pkl")).reset_index(drop=True)
    idx = pd.to_datetime(x.time, unit="s")
    m15 = x.set_index(idx).resample("15min").agg({"high": "max", "low": "min", "close": "last"}).dropna()
    h, l, c = m15.high.values, m15.low.values, m15.close.values
    tr = np.r_[h[0] - l[0], np.maximum(h[1:] - l[1:], np.maximum(abs(h[1:] - c[:-1]), abs(l[1:] - c[:-1])))]
    a15 = pd.Series(pd.Series(tr).rolling(14).mean().values, index=(m15.index - pd.Timestamp("1970-01-01")) // pd.Timedelta("1s"))
    d1 = x.set_index(idx).close.resample("1D").last().dropna()
    s = (np.sign(d1 - d1.shift(21)) + np.sign(d1 - d1.shift(63))).shift(1)
    st = pd.Series(s.values, index=(d1.index - pd.Timestamp("1970-01-01")).days)
    return x, a15, st


def trades(name, hour, hz, need, side=1):
    x, a15, st = load(name)
    T, O, H, L, C = (x[c].values for c in ("time", "open", "high", "low", "close"))
    cost_pct = COST[name] / 100
    tod = T % 86400
    starts = np.nonzero((tod == hour * 3600) & (((T // 86400) + 3) % 7 < 5))[0]
    rows = []
    for k in starts:
        d = T[k] // 86400
        s_ = st.get(d, np.nan)
        if need is not None and s_ != need:
            continue
        j = a15.index.searchsorted(T[k]) - 2                     # ATR de la vela M15 anterior cerrada
        if j < 0 or not np.isfinite(a15.iloc[j]):
            continue
        scale = a15.iloc[j]
        n = int(hz * 12)
        if k + n >= len(T) or T[k + n - 1] - T[k] > hz * 3600 + 600:
            continue
        o, hh, ll, cc = O[k:k + n], H[k:k + n], L[k:k + n], C[k:k + n]
        px = o[0]
        fav = (hh - px) if side == 1 else (px - ll)
        low = (ll - px) if side == 1 else (px - hh)
        opn = (o - px) * side
        last = (cc[-1] - px) * side
        peak = np.maximum.accumulate(fav); pprev = np.r_[-np.inf, peak[:-1]]
        cost = px * cost_pct
        for kind, a, dd, lk in EXITS:
            i_out, r = n - 1, last
            if kind == "tp":
                hit = np.nonzero(fav >= a * scale)[0]
                if len(hit):
                    i_out, r = hit[0], a * scale
            elif kind == "trail":
                stop = pprev - dd * scale
                hit = np.nonzero((pprev >= a * scale) & (low <= stop))[0]
                if len(hit):
                    i_out = hit[0]; r = min(opn[i_out], stop[i_out])
            lh = np.nonzero(low[:i_out + 1] <= -lk * scale)[0]
            extra = 0.0
            if len(lh):
                i_out = lh[0]; r = min(opn[i_out], -lk * scale); extra = cost
            mae = low[:i_out + 1].min() if not len(lh) else r
            rows.append((T[k], kind, a, dd, lk, (r - cost - extra) / (lk * scale), mae / (lk * scale), s_))
    R = pd.DataFrame(rows, columns=["t", "kind", "a", "d", "lock", "r_mult", "mr", "state"])
    R["year"] = pd.to_datetime(R.t, unit="s").dt.year
    R["exit"] = R.kind + "_" + R.a.astype(str) + "_" + R.d.astype(str) + "_L" + R.lock.astype(str)
    return R


def walk_forward(R):
    out = []
    for Y in TEST_YEARS:
        tr, te = R[R.year.isin([Y - 2, Y - 1])], R[R.year == Y]
        if tr.empty or te.empty:
            continue
        best = tr.groupby("exit").r_mult.mean().idxmax()
        out.append(te[te.exit == best].assign(chosen=best))
    return pd.concat(out, ignore_index=True)


def main():
    name, hour, hz = sys.argv[1], int(sys.argv[2]), float(sys.argv[3])
    need = None if sys.argv[4] == "all" else int(sys.argv[4])
    side = int(sys.argv[5]) if len(sys.argv) > 5 else 1
    R = trades(name, hour, hz, need, side)
    W = walk_forward(R)
    lab = f"{name}_{hour}_{hz:g}_{sys.argv[4]}_{side}"
    W.to_pickle(os.path.join(RESULTS, f"reopen_{lab}.pkl"))
    print(f"{lab}: operaciones/año {len(R[R.exit == R.exit.iloc[0]]) / 5.8:.0f}")
    print("  solo hora, candado 3 (sin elegir): R medio por año", R[R.exit == "time_nan_nan_L3.0"].groupby("year").r_mult.mean().round(3).to_dict())
    print("  validacion movil: R medio por año", W.groupby("year").r_mult.mean().round(3).to_dict(),
          "| total", round(W.r_mult.mean(), 3), "n", len(W))


if __name__ == "__main__":
    main()
