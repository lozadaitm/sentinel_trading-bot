"""¿La senal de la Op1 tiene ventaja con ALGUNA geometria de salida?

Para cada entrada de Op1 del motor real (signals.py; primeras de cada racha), simula en M5
una salida simple: objetivo a +TP x ATR, salida a -SL x ATR, o cierre a mercado al cabo
de H horas. Mismo spread (0,20 $) y comision (0,12 $/oz) que signals.py. Si en la misma
vela M5 se tocan ambos, cuenta la salida en contra (conservador).

Compara con dos referencias de la MISMA geometria:
  * lado contrario: misma hora, direccion opuesta (¿la senal acierta la direccion?);
  * azar: velas M15 al azar del mismo periodo y lado al azar.
Una ventaja real exige superar al azar con claridad y de forma estable por ano.
Es una vara de medir: no implica adoptar stops (regla del usuario).

Uso: python -m bot_backtesting.fullsim.geometry
"""
import os

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.harness import DATA

SPREAD, COMM = 0.20, 0.12
TPS = (0.25, 0.5, 1.0, 1.5, 2.0, 3.0)
SLS = (0.5, 1.0, 1.5, 2.0, 3.0, 4.0)
HORIZONS_H = (24, 120)
SOURCES = (("sig_duka.pkl", "frames_duka.pkl"), ("sig_broker.pkl", "frames.pkl"))


def _paths(t, side, px, m5, nmax):
    """Maximos acumulados a favor / en contra y cierre, por barra M5 desde t."""
    T5 = m5.time.values
    k = np.searchsorted(T5, t)
    sl = slice(k, min(k + nmax, len(T5)))
    H, L, C = m5.high.values[sl], m5.low.values[sl], m5.close.values[sl]
    if side == 1:
        fav, adv, last = (H - SPREAD) - px, px - L, C - px
    else:
        fav, adv, last = px - (L + SPREAD), (H + SPREAD) - px, px - (C + SPREAD)
    return np.maximum.accumulate(fav), np.maximum.accumulate(adv), last


def evaluate(entries, m5):
    """DataFrame (una fila por entrada x geometria) con el resultado en $/oz."""
    nmax = max(HORIZONS_H) * 12
    rows = []
    for e in entries.itertuples():
        cf, ca, last = _paths(e.t, e.side, e.px, m5, nmax)
        if len(cf) < 12:
            continue
        for hz in HORIZONS_H:
            n = min(hz * 12, len(cf))
            f, a = cf[:n], ca[:n]
            for tp in TPS:
                i_tp = np.searchsorted(f, tp * e.atr)          # primera barra con fav >= TP
                for sl in SLS:
                    i_sl = np.searchsorted(a, sl * e.atr)
                    if i_sl < n and i_sl <= i_tp:
                        r = -sl * e.atr
                    elif i_tp < n:
                        r = tp * e.atr
                    else:
                        r = last[n - 1]
                    rows.append((e.t, e.year, hz, tp, sl, r - COMM, e.atr))
    return pd.DataFrame(rows, columns=["t", "year", "hz", "tp", "sl", "pnl", "atr"])


def main():
    rng = np.random.default_rng(3)
    sig_all, rnd_all = [], []
    for sname, fname in SOURCES:
        S = pd.read_pickle(os.path.join(DATA, sname))
        S = S.loc[:, ~S.columns.duplicated()]
        S = S[S["first"]].copy()
        fr = pd.read_pickle(os.path.join(DATA, fname))
        m5, m15 = fr["M5"], fr["M15"].reset_index(drop=True)
        S["year"] = pd.to_datetime(S.t, unit="s").dt.year
        opp = S.copy(); opp["side"] = -opp["side"]
        # el precio de entrada del lado contrario: compra al ask, vende al bid
        opp["px"] = np.where(opp.side == 1, S.px + SPREAD * (S.side == -1), S.px - SPREAD * (S.side == 1))
        # azar: velas M15 del mismo periodo, lado al azar, ATR14 de esa vela
        tr = np.r_[np.nan, np.maximum(m15.high.values[1:] - m15.low.values[1:],
                                      np.maximum(abs(m15.high.values[1:] - m15.close.values[:-1]),
                                                 abs(m15.low.values[1:] - m15.close.values[:-1])))]
        atr = pd.Series(tr).rolling(14).mean().values
        ok = np.where((m15.time.values >= S.t.min()) & (m15.time.values <= S.t.max()) & ~np.isnan(atr))[0]
        pick = rng.choice(ok, size=len(S), replace=False)
        side = rng.choice([-1, 1], size=len(S))
        R = pd.DataFrame(dict(t=m15.time.values[pick] + 900, side=side, atr=atr[pick],
                              px=m15.close.values[pick] + np.where(side == 1, SPREAD, 0.0)))
        R["year"] = pd.to_datetime(R.t, unit="s").dt.year
        for name, df, acc in (("senal", S, sig_all), ("contrario", opp, sig_all), ("azar", R, rnd_all)):
            ev = evaluate(df, m5); ev["kind"] = name; acc.append(ev)
            print(sname, name, len(df), "entradas", flush=True)
    E = pd.concat(sig_all + rnd_all, ignore_index=True)
    E.to_pickle(os.path.join(DATA, "geometry_eval.pkl"))
    E["pnl_atr"] = E.pnl / E.atr
    g = E.groupby(["hz", "tp", "sl", "kind"]).pnl.mean().unstack("kind")
    g["senal-azar"] = g["senal"] - g["azar"]
    g["senal-contrario"] = g["senal"] - g["contrario"]
    print("\nGanancia media por entrada ($/oz, tras spread y comision):")
    print(g.round(3).sort_values("senal", ascending=False).head(15).to_string())
    best = g["senal"].idxmax()
    print("\nMejor geometria para la senal:", best)
    y = E[(E.hz == best[0]) & (E.tp == best[1]) & (E.sl == best[2])].groupby(["year", "kind"]).pnl.mean().unstack()
    print(y.round(3).to_string())
    n = (E.kind == "senal").sum() // (len(TPS) * len(SLS) * len(HORIZONS_H))
    pos = (g["senal"] > 0).sum()
    print(f"\n{n} entradas; geometrias con media > 0: {pos} de {len(g)}; "
          f"senal mejor que el azar en {(g['senal-azar'] > 0).sum()} de {len(g)}")


if __name__ == "__main__":
    main()
