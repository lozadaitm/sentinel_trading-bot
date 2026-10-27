"""Deteccion del minimo con M1 y ticks del broker (solo 2026: unico periodo con esos datos). Exploratorio.
Operaciones Big One / Momentum de results/recargas_trades.pkl (año 2026). Camino en M1 bid del broker
(data/broker_m1_ticks.pkl: OHLC + cantidad de ticks por minuto) y desequilibrio de ticks de
data/ticks_5s.pkl (subidas vs bajadas). Recarga 1x, salida con la pata (hora o precio del candado),
spread 0,17 + comision 0,06 + desliz. 0,05 $/oz. Solo se recarga antes del candado.
Reglas (en perdida >= k ATR15):
  TCAP  : minuto con ticks >= r x mediana de 30 min (r = 1,5-2; el conteo del broker se satura ~1 000/min), mecha inferior >= 50 %, cierre en la mitad alta
  TEXH  : agotamiento: ticks de 5 min < 0,8 x los 10 previos, precio a <= 0,5 ATR15 del minimo corriente
  IMB   : desequilibrio de ticks del minuto >= x (mas subidas que bajadas) a <= 0,3 ATR15 del minimo
  MTF1  : vela M15 de rechazo (mecha >= 50 %, cierre en tercio alto) + cierre M1 sobre su maximo
Nulo: misma cantidad de recargas en minutos al azar en perdida de esas operaciones. Mitades 2026-H1/H2.
Uso: python -m bot_backtesting.fullsim.minimo_m1
"""
import os

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.recargas_minimo import DATA, RESULTS, SP, COMM, SLIP, LOCKC, alpha_p, low_priority

NREP = 2000


def main():
    low_priority()
    rng = np.random.default_rng(3)
    trs = [t for t in pd.read_pickle(os.path.join(RESULTS, "recargas_trades.pkl")) if t["year"] == 2026]
    M = pd.read_pickle(os.path.join(DATA, "broker_m1_ticks.pkl")).set_index("time").sort_index()
    T5 = pd.read_pickle(os.path.join(DATA, "ticks_5s.pkl"))
    imb = T5.groupby(T5.index // 60 * 60)[["up", "dn"]].sum()
    imb = ((imb.up - imb.dn) / (imb.up + imb.dn).clip(lower=1)).rename("imb")
    M = M.join(imb)
    rows, rnd = [], {}
    for i, tr in enumerate(trs):
        n = tr["N"] * 5
        g = np.arange(tr["t"], tr["t"] + n * 60, 60)
        m = M.reindex(g)
        if m.close.isna().mean() > 0.1:
            continue
        m = m.ffill().bfill()
        s = tr["side"]
        if s == 1:
            o, h, l, c = m.open.values, m.high.values, m.low.values, m.close.values
            ib = m.imb.fillna(0).values
        else:
            o, h, l, c = -(m.open.values + SP), -(m.low.values + SP), -(m.high.values + SP), -(m.close.values + SP)
            ib = -m.imb.fillna(0).values
        tk = m.ticks.values.astype(float)
        e, a15, ad = tr["e"], tr["atr15"], tr["atrd"]
        lbm = tr["lb"] * 5 if tr["lb"] < tr["N"] else n
        exitp = tr["lockm"] - LOCKC if tr["lb"] < tr["N"] else tr["cu"][-1]
        pnl = lambda k: ((exitp - (o[k] + SP + SLIP) - COMM) / ad * tr["w"])
        rm = np.minimum.accumulate(l)
        med30 = pd.Series(tk).rolling(30, min_periods=10).median().values
        t5 = pd.Series(tk).rolling(5).sum().values
        t10 = pd.Series(tk).shift(5).rolling(10).sum().values / 2
        rg = np.maximum(h - l, 1e-9)
        loss = np.arange(n - 1) + 1
        loss = loss[(loss < lbm) & (c[loss - 1] < e)]
        rnd[i] = np.array([pnl(k) for k in loss])
        cand = {}
        for k in (1, 2):
            dd = (e - l) >= k * a15
            for r in (1.5, 2.0):
                cand[f"TCAP_k{k}_r{r}"] = dd & (tk >= r * med30) & ((np.minimum(o, c) - l) / rg >= 0.5) & ((c - l) / rg >= 0.5)
            cand[f"TEXH_k{k}"] = ((e - c) >= k * a15) & (t5 < 0.8 * t10) & (c - rm <= 0.5 * a15)
            for x in (0.1, 0.2):
                cand[f"IMB_k{k}_x{x}"] = ((e - c) >= k * a15) & (ib >= x) & (c - rm <= 0.3 * a15)
            # MTF1: rechazo en la M15 cerrada mas reciente
            q = np.zeros(n, bool)
            for j in range(14, n, 15):
                hh, ll, oo, cc = h[j - 14:j + 1].max(), l[j - 14:j + 1].min(), o[j - 14], c[j]
                r = hh - ll
                if r > 0 and (e - ll) >= k * a15 and (min(oo, cc) - ll) / r >= 0.5 and (cc - ll) / r >= 0.66:
                    for jj in range(j + 1, min(j + 16, n)):
                        if c[jj] > hh:
                            q[jj] = True; break
            cand[f"MTF1_k{k}"] = q
        rec = dict(i=i, d=tr["d"], leg=tr["leg"], h2=tr["d"] >= pd.Timestamp("2026-07-01").timestamp() // 86400,
                   base=tr["w"] * tr["base_pnl"] / ad, fmin=(e - l.min()) / ad)
        for name, sig in cand.items():
            ks = np.nonzero(sig[:-1])[0]
            ks = ks[(ks + 1 < lbm) & (c[ks] < e)]
            if len(ks):
                k = ks[0] + 1
                rec[name] = pnl(k)
                rec[name + "_dist"] = (o[k] - l[k:].min()) / ad
            else:
                rec[name] = np.nan
        rows.append(rec)
    D = pd.DataFrame(rows)
    names = [c for c in D.columns if c.startswith(("TCAP", "TEXH", "IMB", "MTF1")) and not c.endswith("_dist")]
    out = []
    for leg in ("big_one", "momentum"):
        for nm in names:
            for per, msk in (("2026", D.leg == leg), ("H1", (D.leg == leg) & ~D.h2), ("H2", (D.leg == leg) & D.h2)):
                g = D[msk]
                f = g[nm].notna()
                if f.sum() < 5:
                    continue
                obs = g.loc[f, nm].sum()
                sims = np.zeros(NREP)
                for i in g.loc[f, "i"]:
                    pool = rnd[i]
                    if len(pool):
                        sims += pool[rng.integers(0, len(pool), NREP)]
                p = ((sims >= obs).sum() + 1) / (NREP + 1)
                al, pa = alpha_p(g[nm].fillna(0).values, g.base.values)
                out.append(dict(leg=leg, regla=nm, per=per, n_ops=len(g), disparos=int(f.sum()), R_por_disp=g.loc[f, nm].mean(),
                                azar=sims.mean() / f.sum(), p_azar=p, alfa=al, p_alfa=pa,
                                dist_min=g.loc[f, nm + "_dist"].median(), cerca=(g.loc[f, nm + "_dist"] <= 0.1).mean(),
                                en_perdedoras=(g.loc[f, "base"] < 0).mean()))
    S = pd.DataFrame(out)
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 300)
    print(f"operaciones 2026 con M1: {len(D)} (Big One {(D.leg == 'big_one').sum()}, Momentum {(D.leg == 'momentum').sum()})")
    print(S.round(3).to_string(index=False))
    S.to_pickle(os.path.join(RESULTS, "minimo_m1_summary.pkl"))


if __name__ == "__main__":
    main()
