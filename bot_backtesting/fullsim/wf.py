"""Validacion MOVIL y mezcla por escenario de las reglas de entrylab.

Para cada ano de prueba Y (2023..2026) se elige SOLO con los dos anos anteriores (Y-2, Y-1):
  1. Por regla: la salida (tp, sl) con mejor ganancia media en entrenamiento (exige ganancia > 0
     y ventaja sobre el azar > 0 alli); si ninguna cumple, la regla no opera en Y.
  2. Mezcla por escenario: escenario = tendencia diaria (s = signo(C-C21)+signo(C-C63) del dia
     previo: alcista +2, bajista -2, mixta) x volatilidad (ATR M15 frente a su mediana de 60 dias:
     alta/baja) x sesion (servidor 01-09 Asia, 09-15 Londres, 15-24 Nueva York). En cada
     escenario se elige la mejor (regla, salida) con >= MIN_N operaciones en entrenamiento y se
     aplica en Y a las senales de ESE escenario.
Lo que se reporta en Y nunca se uso para elegir.

Uso: python -m bot_backtesting.fullsim.wf [regla ...]
"""
import glob
import os
import sys

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.entrylab import DATA, RESULTS, atr

TEST_YEARS = (2023, 2024, 2025, 2026)
MIN_N = 30


def regimes(B, t):
    """Escenario de cada instante t (epoch servidor)."""
    d1 = B["D1"]; c = d1.close
    s = (np.sign(c - c.shift(21)) + np.sign(c - c.shift(63))).shift(1)
    trend = pd.Series(s.values, index=d1.time.values // 86400).reindex(t // 86400).values
    tr_lbl = np.where(trend == 2, "alcista", np.where(trend == -2, "bajista", "mixta"))
    m15 = B["M15"]; a = atr(m15)
    ratio = a / pd.Series(a).rolling(96 * 60, min_periods=96 * 20).median().values
    j = np.clip(np.searchsorted(m15.time.values + 900, t) - 1, 0, len(a) - 1)
    vol = np.where(ratio[j] >= 1.0, "volalta", "volbaja")
    h = pd.to_datetime(t, unit="s").hour
    ses = np.where(h < 9, "asia", np.where(h < 15, "londres", "nyork"))
    return pd.Series([f"{x}|{y}|{z}" for x, y, z in zip(tr_lbl, vol, ses)], index=range(len(t)))


def load(names=None):
    out = []
    for f in sorted(glob.glob(os.path.join(RESULTS, "entry_*.pkl"))):
        name = os.path.basename(f)[6:-4]
        if name == "summary" or (names and name not in names):
            continue
        R = pd.read_pickle(f)
        R["rule"] = name
        out.append(R)
    return pd.concat(out, ignore_index=True)


def per_rule(A):
    rows = []
    for rule, g in A.groupby("rule"):
        for Y in TEST_YEARS:
            tr = g[g.year.isin([Y - 2, Y - 1])]
            te = g[g.year == Y]
            if tr.empty or te.empty:
                continue
            st = tr.groupby(["tp", "sl"]).agg(pnl=("pnl", "mean"), edge=("edge", "mean"))
            st = st[(st.pnl > 0) & (st.edge > 0)]
            if st.empty:
                rows.append(dict(rule=rule, year=Y, opera=False, n=0, pnl=0.0, total=0.0))
                continue
            tp, sl = st.pnl.idxmax()
            x = te[(te.tp == tp) & (te.sl == sl)]
            rows.append(dict(rule=rule, year=Y, opera=True, tp=tp, sl=sl, n=len(x), pnl=x.pnl.mean(),
                             edge=x.edge.mean(), total=x.pnl.sum()))
    return pd.DataFrame(rows)


def mix(A):
    rows = []
    for Y in TEST_YEARS:
        tr = A[A.year.isin([Y - 2, Y - 1])]
        te = A[A.year == Y]
        st = tr.groupby(["reg", "rule", "tp", "sl"]).agg(n=("pnl", "size"), pnl=("pnl", "mean"), edge=("edge", "mean"))
        st = st[(st.n >= MIN_N) & (st.pnl > 0) & (st.edge > 0)].reset_index()
        if st.empty:
            continue
        best = st.loc[st.groupby("reg").pnl.idxmax()]
        for b in best.itertuples():
            x = te[(te.reg == b.reg) & (te.rule == b.rule) & (te.tp == b.tp) & (te.sl == b.sl)]
            rows.append(dict(year=Y, reg=b.reg, rule=b.rule, tp=b.tp, sl=b.sl, n_train=b.n, pnl_train=b.pnl,
                             n=len(x), pnl=x.pnl.mean() if len(x) else np.nan, total=x.pnl.sum()))
    return pd.DataFrame(rows)


def main():
    B = pd.read_pickle(os.path.join(DATA, "bars_all.pkl"))
    A = load(sys.argv[1:] or None)
    A["edge"] = A.pnl - A.rnd
    A = A.dropna(subset=["rnd"])
    ev_t = A.drop_duplicates(["rule", "t"])[["rule", "t"]].reset_index(drop=True)
    ev_t["reg"] = regimes(B, ev_t.t.values).values
    A = A.merge(ev_t, on=["rule", "t"], how="left")
    P = per_rule(A)
    P.to_pickle(os.path.join(RESULTS, "wf_per_rule.pkl"))
    pd.set_option("display.width", 220)
    s = P[P.opera].groupby("rule").agg(anos=("year", "size"), anos_pos=("total", lambda v: int((v > 0).sum())),
                                       n=("n", "sum"), total=("total", "sum"))
    s["pnl_medio"] = s.total / s.n
    print("== Por regla (validacion movil 2023-2026; $/oz por operacion, lote de 1 oz) ==")
    print(s.sort_values("total", ascending=False).round(2).to_string())
    M = mix(A)
    M.to_pickle(os.path.join(RESULTS, "wf_mix.pkl"))
    print("\n== Mezcla por escenario (elegida con los 2 anos previos) ==")
    if M.empty:
        print("sin escenarios que cumplan")
        return
    y = M.groupby("year").agg(escenarios=("reg", "size"), n=("n", "sum"), total=("total", "sum"))
    y["pnl_medio"] = y.total / y.n
    print(y.round(2).to_string())
    print("\nque eligio cada ano (escenario -> regla):")
    for Y, g in M.groupby("year"):
        print(Y, "; ".join(f"{r.reg}: {r.rule} tp{r.tp}/sl{r.sl} n={r.n} {r.pnl:+.2f}" for r in g.itertuples()))


if __name__ == "__main__":
    main()
