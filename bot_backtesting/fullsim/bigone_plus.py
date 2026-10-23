"""Big One mejorada (solo simulacion): tres palancas sobre la compra en la reapertura 01:00.

  1) Escala por VOLATILIDAD PREVISTA (HAR diario de econ_build) en vez del ATR M15 de la vela
     de entrada; la distancia del candado y el lote salen de esa escala. Dias de evento
     (NFP/IPC/FOMC) con riesgo reducido.
  2) Tambien en dias de tendencia NEUTRA (y bajista) con riesgo reducido: la reapertura tiene
     sesgo comprador en los tres estados.
  3) Gestion tipo Op: PIRAMIDE (una segunda compra igual al llegar a +P x escala a favor; sale
     con la primera) — la idea de rediseñar Op2..Op4 alrededor de la Big One.
Salidas: hora (10:00), objetivo o trailing; candado a L x escala (congela la perdida). Salida
elegida por año con los 2 anteriores (validacion movil, 2023..2026). Costes y swap de entrylab.

Uso: python -m bot_backtesting.fullsim.bigone_plus      (requiere data/econ/econ_daily.pkl)
"""
import os

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.entrylab import COMM, DATA, RESULTS, SPREAD, _tsmom_state, atr, swap_cost

TEST_YEARS = (2023, 2024, 2025, 2026)
LOCKS = (1.0, 2.0, 3.0)
PYR = (None, 1.0, 1.5)
_BASE = ([("time", None, None)] + [("tp", tp, None) for tp in (2.0, 3.0)]
         + [("trail", a, d) for a in (1.0, 2.0) for d in (0.5, 1.0, 1.5)])
EXITS = [(k, a, d, lk, p) for (k, a, d) in _BASE for lk in LOCKS for p in PYR]
LOCK_COST = COMM + SPREAD


def events(B, D):
    """Una entrada por dia habil a la 01:00, con estado de tendencia, evento y dos escalas."""
    m15 = B["M15"]
    a = pd.Series(atr(m15)).shift(1).values                  # ATR de la vela ANTERIOR (sin mirar adelante)
    tt = pd.to_datetime(m15.time.values, unit="s")
    m = (tt.hour == 1) & (tt.minute == 0) & (tt.dayofweek < 5) & ~np.isnan(a)
    E = pd.DataFrame({"t": m15.time.values[m], "atr": a[m], "px": m15.open.values[m]})
    E["d"] = E.t // 86400
    E["state"] = _tsmom_state(B).reindex(E.d.values).values
    X = D.reindex(E.d.values)
    E["ev"] = X.ev_any.values
    E["year"] = pd.to_datetime(E.t, unit="s").dt.year
    # escala HAR: volatilidad diaria prevista ($) llevada a la unidad del ATR M15 con la razon
    # mediana ATR/vol-22d de 2021-2022 (fija, sin mirar el futuro de la prueba)
    rv_usd = X.rvhat_3.values / 100 * E.px.values
    rv22_usd = X.rv22_l.values / 100 * E.px.values
    k = np.nanmedian((E.atr / rv22_usd)[E.year <= 2022])
    E["har"] = rv_usd * k
    return E.dropna(subset=["state", "har"]).reset_index(drop=True)


class Paths:
    def __init__(self, B):
        m5 = B["M5"]
        self.T, self.O, self.H, self.L, self.C = (m5[c].values for c in ("time", "open", "high", "low", "close"))

    def trade(self, t, scale, hz=9.0):
        k = np.searchsorted(self.T, t)
        n = min(int(hz * 12), len(self.T) - k)
        if k <= 0 or n < 3:
            return None
        O, H, L, C = self.O[k:k + n], self.H[k:k + n], self.L[k:k + n], self.C[k:k + n]
        px = O[0] + SPREAD
        fav, low, opn, last = H - px, L - px, O - px, C[-1] - px
        peak = np.maximum.accumulate(fav); peak_prev = np.r_[-np.inf, peak[:-1]]
        res = {}
        for kind, a, d, lk, p in EXITS:
            i_out, r = n - 1, last
            if kind == "tp":
                hit = np.nonzero(fav >= a * scale)[0]
                if len(hit):
                    i_out, r = hit[0], a * scale
            elif kind == "trail":
                stop = peak_prev - d * scale
                hit = np.nonzero((peak_prev >= a * scale) & (low <= stop))[0]
                if len(hit):
                    i_out = hit[0]; r = min(opn[i_out], stop[i_out])
            lstop = -lk * scale
            lh = np.nonzero(low[:i_out + 1] <= lstop)[0]
            extra, locked = 0.0, False
            if len(lh):
                i_out = lh[0]; r = min(opn[i_out], lstop); extra = -LOCK_COST; locked = True
            pnl = r - COMM + extra
            mae = low[:i_out + 1].min() if not locked else r
            # piramide: segunda compra al tocar +p x escala (antes de la salida); sale igual
            if p is not None:
                ph = np.nonzero(fav[:i_out + 1] >= p * scale)[0]
                if len(ph) and ph[0] < i_out:
                    e2 = p * scale + SPREAD
                    pnl += (r - e2) - COMM
                    fl = low[ph[0]:i_out + 1]
                    mae = min(mae, (fl + (fl - e2)).min())
            nights = swap_cost(self.T[k], self.T[k + i_out] + 300, 1)
            res[(kind, a, d, lk, p)] = (pnl + nights, mae, self.T[k + i_out] + 300, lk * scale)
        return res


def build(E, P):
    rows = []
    for e in E.itertuples():
        for sc_name in ("atr", "har"):
            o = P.trade(e.t, getattr(e, sc_name))
            if o is None:
                continue
            for ex, (pnl, mae, t_out, risk_oz) in o.items():
                rows.append((e.t, e.year, e.state, e.ev, sc_name) + ex + (pnl, mae, t_out, risk_oz))
    R = pd.DataFrame(rows, columns=["t", "year", "state", "ev", "scale", "kind", "a", "d", "lock", "pyr",
                                    "pnl", "mae", "t_out", "risk_oz"])
    R["pyr"] = R.pyr.fillna(0.0)
    R["exit"] = R.kind + "_" + R.a.astype(str) + "_" + R.d.astype(str) + "_L" + R.lock.astype(str)
    R["r_mult"] = R.pnl / R.risk_oz
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


def path(seq, f, bal):
    """seq: filas (r_mult, mae/risk_oz, peso). Lote = equity*f*peso/riesgo; minimo 0,01 ignorado (5 000 $)."""
    eq, peak, dd = bal, bal, 0.0
    for r, m, w in seq:
        risk = eq * f * w
        dd = max(dd, (peak - (eq + min(0.0, m) * risk)) / peak)
        eq += r * risk; peak = max(peak, eq); dd = max(dd, (peak - eq) / peak)
        if eq <= bal * 0.05:
            return eq, 1.0
    return eq, dd


def score(T, f, bal=5000, n=2000, seed=7):
    T = T.sort_values("t").copy()
    T["m"] = pd.to_datetime(T.t, unit="s").dt.to_period("M")
    T["mr"] = T.mae / T.risk_oz
    months = [g[["r_mult", "mr", "w"]].values for _, g in T.groupby("m")]
    one = np.array([path(mm, f, bal)[0] / bal - 1 for mm in months])
    rng = np.random.default_rng(seed)
    r12 = [path(np.vstack([months[i] for i in rng.integers(0, len(months), 12)]), f, bal) for _ in range(n)]
    m12 = np.array([x[0] for x in r12]) / bal; d12 = np.array([x[1] for x in r12])
    real = path(np.vstack(months), f, bal)
    return dict(ops_mes=round(len(T) / len(months), 1), R_op=round(T.r_mult.mean(), 3), mes_med=np.median(one),
                p_mes30=(one >= .3).mean(), peor_mes=one.min(), x12_med=np.median(m12), p_x2_12m=(m12 >= 2).mean(),
                p_dd50=(d12 >= .5).mean(), real_x=real[0] / bal, real_dd=real[1])


VARIANTS = {
    # nombre: (escala, piramide, peso por estado {+2, 0, -2}, peso en dia de evento)
    "base_atr":             ("atr", 0.0, {2: 1, 0: 0, -2: 0}, 1.0),
    "har":                  ("har", 0.0, {2: 1, 0: 0, -2: 0}, 1.0),
    "har_ev50":             ("har", 0.0, {2: 1, 0: 0, -2: 0}, 0.5),
    "har_ev50_neutra50":    ("har", 0.0, {2: 1, 0: .5, -2: 0}, 0.5),
    "har_ev50_todas":       ("har", 0.0, {2: 1, 0: .5, -2: .5}, 0.5),
    "har_ev50_neutra50_p1": ("har", 1.0, {2: 1, 0: .5, -2: 0}, 0.5),
    "har_ev50_neutra50_p15": ("har", 1.5, {2: 1, 0: .5, -2: 0}, 0.5),
    "atr_neutra50_p1":      ("atr", 1.0, {2: 1, 0: .5, -2: 0}, 1.0),
}


def main():
    B = pd.read_pickle(os.path.join(DATA, "bars_all.pkl"))
    D = pd.read_pickle(os.path.join(DATA, "econ", "econ_daily2.pkl"))
    E = events(B, D)
    fp = os.path.join(RESULTS, "bigone_plus_all.pkl")
    if os.path.exists(fp):
        R = pd.read_pickle(fp)
    else:
        R = build(E, Paths(B)); R.to_pickle(fp)
    print("R medio por estado (salida time_L2, sin piramide, escala atr):")
    print(R[(R.exit == "time_nan_nan_L2.0") & (R.pyr == 0) & (R.scale == "atr")].groupby(["state", "year"]).r_mult.mean().unstack().round(2))
    rows, picks = [], []
    for name, (sc, p, wst, wev) in VARIANTS.items():
        sub = R[(R.scale == sc) & (R.pyr == p) & R.state.isin([s for s, w in wst.items() if w > 0])].copy()
        # la salida se elige por estado (cada estado su propia validacion movil)
        T = pd.concat([walk_forward(g) for _, g in sub.groupby("state")], ignore_index=True)
        T["w"] = T.state.map(wst) * np.where(T.ev == 1, wev, 1.0)
        picks.append(T.assign(variant=name))
        print(f"  {name}: salidas elegidas", T.groupby(["state", "year"]).chosen.first().to_dict())
        for f in (0.02, 0.03, 0.05):
            rows.append(dict(variante=name, riesgo=f"{f * 100:.0f}%", **score(T, f)))
    pd.concat(picks).to_pickle(os.path.join(RESULTS, "bigone_plus_trades.pkl"))
    pd.set_option("display.width", 250)
    print(pd.DataFrame(rows).round(3).to_string(index=False))


if __name__ == "__main__":
    main()
