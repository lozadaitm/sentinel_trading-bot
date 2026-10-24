"""Ultimo intento de operaciones CORTAS en el oro: scalping ALINEADO con las ventajas probadas (solo simulacion).

Ventanas y sesgo (precios del broker):
  asia : 01:15 -> 09:45, dias de tendencia diaria +2, sesgo COMPRA
  eeuu : 15:00 -> 20:45, sesgo = direccion de Asia (01:00 -> 15:00) si |Asia| > 0,5 desv. y tendencia != 0
Disparadores (una operacion a la vez por ventana): cada vela / retroceso (3 velas contra el sesgo > 0,5 ATR)
/ ruptura (cierre sobre el maximo de 12 velas a favor) / control: contra el sesgo.
Mantener 3 / 6 / 12 velas. Costo 0,17 $/oz (spread tipico 0,11 + comision RAW 0,06).
Escalas: M15 (2022-08 -> 2026-10, por año), M5 (2025-05 -> 2026-10) y M1 de los ticks (2026; mitades).
Uso: python -m bot_backtesting.fullsim.gold_bias_scalp
"""
import os

import numpy as np
import pandas as pd

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
COST = 0.17
pd.set_option("display.width", 250)


def bars(tf):
    if tf == "M15":
        X = pd.read_pickle(os.path.join(DATA, "broker_m15_full.pkl"))
    elif tf == "M5":
        X = pd.read_pickle(os.path.join(DATA, "broker_m5_full.pkl"))
    else:
        G = pd.read_pickle(os.path.join(DATA, "ticks_5s.pkl"))
        mid = (G.bid + G.ask) / 2
        idx = pd.to_datetime(G.index.values, unit="s")
        X = mid.groupby(G.index.values // 60 * 60).agg(["first", "max", "min", "last"]).reset_index()
        X.columns = ["time", "open", "high", "low", "close"]
    return X[["time", "open", "high", "low", "close"]].sort_values("time").reset_index(drop=True)


def daily_state():
    X = pd.read_pickle(os.path.join(DATA, "broker_m15_full.pkl"))
    d = X.close.groupby(X.time // 86400).last()
    return (np.sign(d - d.shift(21)) + np.sign(d - d.shift(63))).shift(1)


def run(tf):
    X = bars(tf); t = X.time.values; o, h, l, c = (X[k].values for k in ("open", "high", "low", "close"))
    bar = {"M15": 900, "M5": 300, "M1": 60}[tf]
    tr = np.r_[h[0] - l[0], np.maximum(h[1:] - l[1:], np.maximum(abs(h[1:] - c[:-1]), abs(l[1:] - c[:-1])))]
    atr = pd.Series(tr).rolling(14).mean().shift(1).values
    st = daily_state()
    day = t // 86400; tod = t % 86400
    s_day = st.reindex(day).values
    first = pd.Series(np.arange(len(t))).groupby(day).transform(lambda s: s.iloc[0]).values
    # precio a la 01:00 y a las 15:00 de cada dia
    p01 = pd.Series(o, index=t).reindex(day * 86400 + 3600).values
    p15 = pd.Series(o, index=t).reindex(day * 86400 + 15 * 3600).values
    asia = (p15 - p01) / p01 * 100
    sd = np.nanstd(asia[t < pd.Timestamp("2024-07-01").timestamp()]) if tf == "M15" else 0.464
    bias = np.zeros(len(t))
    wa = (tod >= 3600 + 900) & (tod < 9 * 3600 + 2700) & (s_day == 2)
    bias[wa] = 1
    we = (tod >= 15 * 3600) & (tod < 20 * 3600 + 2700) & (np.abs(asia) > 0.5 * sd) & (s_day != 0) & ~np.isnan(asia)
    bias[we] = np.sign(asia[we])
    win = np.where(wa, "asia", np.where(we, "eeuu", ""))
    back3 = c - np.r_[np.full(3, np.nan), c[:-3]]
    hi12 = pd.Series(h).rolling(12).max().shift(1).values; lo12 = pd.Series(l).rolling(12).min().shift(1).values
    rows = []
    for trig in ("cada_vela", "retroceso", "ruptura", "control_contra"):
        if trig == "cada_vela":
            sig = bias != 0
        elif trig == "retroceso":
            sig = (bias != 0) & (back3 * bias < -0.5 * atr)
        elif trig == "ruptura":
            sig = (bias == 1) & (c > hi12) | (bias == -1) & (c < lo12)
        else:
            sig = bias != 0
        side = bias * (-1 if trig == "control_contra" else 1)
        for hold in (3, 6, 12):
            nxt = -1
            for i in np.nonzero(sig)[0]:
                if i <= nxt or i + hold + 1 >= len(t):
                    continue
                j = i + 1                                      # entra a la apertura de la vela siguiente
                if t[j + hold - 1] - t[j] > (hold + 2) * bar:
                    continue
                pnl = (c[j + hold - 1] - o[j]) * side[i] - COST
                rows.append((win[i], trig, hold, pd.Timestamp(t[j], unit="s").year, t[j], pnl))
                nxt = j + hold - 1
    R = pd.DataFrame(rows, columns=["ventana", "disparo", "velas", "year", "t", "pnl"])
    if tf == "M15":
        out = R.pivot_table(index=["ventana", "disparo", "velas"], columns="year", values="pnl", aggfunc="mean").round(2)
        out["total"] = R.groupby(["ventana", "disparo", "velas"]).pnl.mean().round(2)
        out["n"] = R.groupby(["ventana", "disparo", "velas"]).size()
        out["años+"] = (R.groupby(["ventana", "disparo", "velas", "year"]).pnl.mean() > 0).groupby(level=[0, 1, 2]).sum()
    else:
        mid = R.t.median()
        R["mitad"] = np.where(R.t < mid, "A", "B")
        out = R.pivot_table(index=["ventana", "disparo", "velas"], columns="mitad", values="pnl", aggfunc=["mean", "size"]).round(2)
    print(f"\n=== {tf} (neto $/oz por operacion) ===")
    print(out.to_string())


if __name__ == "__main__":
    for tf in ("M15", "M5", "M1"):
        run(tf)
