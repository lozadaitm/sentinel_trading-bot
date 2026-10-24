"""Proyeccion de las cuentas demo propuestas (3 000 / 10 000 / 25 000) con la cartera del diseño. Solo simulacion.

Variantes:
  base       : Big One + momentum EE.UU. (entrada fija 15:00 -> 21:00) + NFP
  retrocesos : igual, pero el momentum EE.UU. entra en retrocesos M15 dentro de 15:00-20:45 (una a la vez,
               3 h cada una) = las «operaciones cortas» alineadas
Todas con salida en escalera (tercios: hora / TP 2 / TP 3 ATR M15) y candado a 1 ATR diario; riesgo 5 % y 8 %.
1) Camino real 2022-10 -> 2026-10 con lotes reales (tercios redondeados a 0,01).
2) Proyeccion 12 meses: remuestreo de los meses reales de ese camino (2 000 caminos): p10 / p50 / p90 del
   capital final, caida maxima mediana y probabilidad de terminar el año en perdida.
Uso: python -m bot_backtesting.fullsim.projection
"""
import os

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.broker_accounts import LADDER, trades_fixed
from bot_backtesting.fullsim.broker_rule import RESULTS, build, exit_label

START, END = pd.Timestamp("2022-10-01"), pd.Timestamp("2026-10-17")


def pullback_entries():
    X = pd.read_pickle(os.path.join(os.path.dirname(__file__), "data", "broker_m15_full.pkl")).sort_values("time").reset_index(drop=True)
    t = X.time.values; o, h, l, c = (X[k].values for k in ("open", "high", "low", "close"))
    d = X.close.groupby(t // 86400).last(); st = (np.sign(d - d.shift(21)) + np.sign(d - d.shift(63))).shift(1)
    tr = np.r_[h[0] - l[0], np.maximum(h[1:] - l[1:], np.maximum(abs(h[1:] - c[:-1]), abs(l[1:] - c[:-1])))]
    atr = pd.Series(tr).rolling(14).mean().shift(1).values
    pos = pd.Series(np.arange(len(t)), index=t); O = pd.Series(o, index=t)
    out = []
    for day in np.unique(t // 86400):
        s = st.get(day); b1, b15, b21 = day * 86400 + 3600, day * 86400 + 15 * 3600, day * 86400 + 21 * 3600
        if s is None or not np.isfinite(s) or s == 0 or b1 not in O.index or b15 not in O.index or b21 - 900 not in pos.index:
            continue
        a = (O[b15] - O[b1]) / O[b1] * 100
        if abs(a) <= 0.5 * 0.464:
            continue
        side = int(np.sign(a)); nxt = -1
        for i in range(pos[b15] + 3, pos[b21 - 900] + 1):
            if i <= nxt or i + 13 >= len(t):
                continue
            if (c[i] - c[i - 3]) * side < -0.5 * atr[i]:
                out.append((t[i + 1], side)); nxt = i + 12
    return out


def legs(variant):
    T = trades_fixed(ladder=True)
    if variant == "retrocesos":
        fp = os.path.join(RESULTS, "proj_ny_pull.pkl")
        R = pd.read_pickle(fp) if os.path.exists(fp) else build("ny_pull", None, 12, None, entries=pullback_entries())
        R.to_pickle(fp)
        R = R.assign(exit=exit_label(R))
        X = R[R.exit.isin(LADDER)]
        g = X.groupby("t"); P = g.first(); P["pnl"] = g.pnl.mean(); P["mae"] = g.mae.min(); P["r_mult"] = g.r_mult.mean()
        P = P[g.size() == len(LADDER)].reset_index().assign(w=1.0, pata="momentum_eeuu")
        P["t_out"] = P.t + 3 * 3600
        T = pd.concat([T[T.pata != "momentum_eeuu"], P], ignore_index=True)
    return T[(T.t >= START.timestamp()) & (T.t < END.timestamp())].sort_values("t").reset_index(drop=True)


def path(T, bal0, f):
    ev = sorted([(r.t, 0, i) for i, r in T.iterrows()] + [(r.t_out, 1, i) for i, r in T.iterrows()])
    eq, lots, rows = bal0, {}, []
    for t, kind, i in ev:
        r = T.loc[i]
        if kind == 0:
            raw = eq * f * r.w / (r.risk_oz * 100)
            lots[i] = 3 * max(0.01, np.floor(raw / 3 / 0.01 + 1e-9) * 0.01)
        else:
            eq += r.pnl * lots[i] * 100
            rows.append((pd.Timestamp(t, unit="s").to_period("M"), eq))
    M = pd.DataFrame(rows, columns=["m", "eq"]).groupby("m").eq.last()
    M = M.reindex(pd.period_range(START, END - pd.Timedelta(days=1), freq="M")).ffill().fillna(bal0)
    ret = M.pct_change().fillna(M.iloc[0] / bal0 - 1)
    return M, ret


def main():
    pd.set_option("display.width", 250)
    rows, proj = [], []
    for variant in ("base", "retrocesos"):
        T = legs(variant)
        stats = T.groupby("pata").agg(n=("r_mult", "size"), R=("r_mult", "mean"))
        print(variant, stats.round(3).to_dict("index"))
        for f in (0.05, 0.08):
            for bal in (3000, 10000, 25000):
                M, ret = path(T, bal, f)
                eqs = M.values; dd = np.max(1 - eqs / np.maximum.accumulate(np.r_[bal, eqs])[1:])
                last12 = ret.iloc[-12:]
                rows.append(dict(variante=variant, riesgo=f, cuenta=bal, x_49m=M.iloc[-1] / bal, mes_medio=(M.iloc[-1] / bal) ** (1 / len(M)) - 1,
                                 caida_max=dd, meses_neg=int((ret < 0).sum()), peor_mes=ret.min(), x_ult12=np.prod(1 + last12)))
                rng = np.random.default_rng(7)
                sims = rng.choice(ret.values, size=(2000, 12), replace=True)
                curve = bal * np.cumprod(1 + sims, axis=1)
                fin = curve[:, -1]
                ddp = np.max(1 - curve / np.maximum.accumulate(np.c_[np.full(2000, bal), curve], axis=1)[:, 1:], axis=1)
                proj.append(dict(variante=variant, riesgo=f, cuenta=bal, p10=np.quantile(fin, .1), p50=np.median(fin), p90=np.quantile(fin, .9),
                                 caida_med=np.median(ddp), p_perder=(fin < bal).mean(), p_x2=(fin >= 2 * bal).mean()))
    print("\nCAMINO REAL 2022-10 -> 2026-10 (lotes reales):")
    print(pd.DataFrame(rows).round(3).to_string(index=False))
    print("\nPROYECCION 12 MESES (remuestreo de meses reales):")
    print(pd.DataFrame(proj).round(3).to_string(index=False))


if __name__ == "__main__":
    main()
