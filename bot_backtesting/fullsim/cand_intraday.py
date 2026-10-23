"""Candidatas intradia salidas de econ_intraday, evaluadas con el probador de entradas (azar
emparejado misma hora/lado, costos y swap, train 2021-23 / test 2024-26). Solo simulacion.

  mes_ini        : compra el primer dia habil del mes a la 01:00, cierre 23:00 (S4: +0,3 %/dia)
  mes_vuelta     : compra el ultimo dia habil del mes a las 20:00, cierre el primero a las 23:00
  hora_ext_k     : tras una hora con |ret| > k x vol horaria tipica, ir EN CONTRA 1 h y 3 h (S5)
  fomc_sigue / nfp_sigue : a T+60 min seguir el salto de la noticia, mantener 24 h (S3)
  ipc_contra     : a T+60 min ir en contra del salto del IPC, mantener 24 h (S3)
Uso: python -m bot_backtesting.fullsim.cand_intraday
"""
import os

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.entrylab import DATA, RESULTS, Evaluator, atr, ev, summarize

B = pd.read_pickle(os.path.join(DATA, "bars_all.pkl"))
m15 = B["M15"]; A15 = atr(m15); T15 = m15.time.values
m5 = B["M5"]; T5 = m5.time.values; C5 = m5.close.values


def scale_at(t):
    j = np.searchsorted(T15, t) - 1
    return A15[max(j - 1, 0)]


def month_events():
    d = B["D1"]; t = pd.to_datetime(d.time.values, unit="s")
    wd = t.dayofweek < 5
    dd = pd.DataFrame({"t": d.time.values[wd], "m": t[wd].to_period("M")})
    first = dd.groupby("m").t.min().values; last = dd.groupby("m").t.max().values
    e1 = [(x + 3600, scale_at(x + 3600)) for x in first]
    e2 = [(x + 20 * 3600, scale_at(x + 20 * 3600)) for x in last]
    E1 = ev([a for a, _ in e1], [1] * len(e1), [b for _, b in e1], 22.0)
    E2 = ev([a for a, _ in e2], [1] * len(e2), [b for _, b in e2], 27.0)
    return E1.dropna(), E2.dropna()


def hour_extreme(k, hz):
    r1 = np.full(len(C5), np.nan); r1[12:] = C5[12:] - C5[:-12]
    gap = np.r_[np.full(12, True), (T5[12:] - T5[:-12]) != 3600]
    sd = pd.Series(np.abs(np.r_[np.nan, np.diff(C5)])).rolling(12 * 24 * 5).mean().values * np.sqrt(12) * 1.25
    m = ((T5 % 3600) == 3300) & ~gap & (np.abs(r1) > k * sd)
    t = T5[m] + 300
    return ev(t, -np.sign(r1[m]).astype(int), [scale_at(x) for x in t], hz).dropna()


def event_drift(kinds, follow):
    E = pd.read_csv(os.path.join(os.path.dirname(__file__), "events_us.csv"))
    E = E[E.event.isin(kinds)]
    Cs = pd.Series(C5, index=T5)
    rows = []
    for e in E.itertuples():
        t = int(pd.Timestamp(f"{e.date} {e.time_utc}").timestamp())
        cands = [z for z in (t + 7200, t + 10800) if z - 900 in Cs.index and z + 3600 in Cs.index]
        if not cands:
            continue
        t0 = max(cands, key=lambda z: abs(Cs[z + 300] - Cs[z - 300]) if (z + 300 in Cs.index and z - 300 in Cs.index) else -1)
        jump = Cs[t0 + 3600 - 300] - Cs[t0 - 900]
        if jump == 0:
            continue
        side = int(np.sign(jump)) * (1 if follow else -1)
        rows.append((t0 + 3600, side, scale_at(t0 + 3600)))
    return ev([r[0] for r in rows], [r[1] for r in rows], [r[2] for r in rows], 24.0)


def main():
    E1, E2 = month_events()
    C = {"mes_ini": E1, "mes_vuelta": E2}
    for k in (3.0, 4.0, 5.0):
        for hz in (1.0, 3.0):
            C[f"hora_ext_{k:g}_{hz:g}h"] = hour_extreme(k, hz)
    C["fomc_sigue"] = event_drift(["FOMC"], True)
    C["nfp_sigue"] = event_drift(["NFP"], True)
    C["ipc_contra"] = event_drift(["CPI"], False)
    ev_ = Evaluator(B); rng = np.random.default_rng(11)
    pd.set_option("display.width", 250)
    allS = []
    for name, E in C.items():
        R = ev_.evaluate(E, rng)
        R.to_pickle(os.path.join(RESULTS, f"cand_{name}.pkl"))
        S = summarize(name, R)
        S["ok"] = (S.pnl_is > 0) & (S.edge_is > 0) & (S.pnl_oos > 0) & (S.edge_oos > 0)
        allS.append(S)
        b = S.sort_values("t_is", ascending=False).iloc[0]
        print(f"{name:18s} eventos {len(E):5d} | mejor train: tp {b.tp} sl {b.sl} pnl {b.pnl_is:+.2f} ventaja {b.edge_is:+.2f} "
              f"(t {b.t_is:+.1f}) | test pnl {b.pnl_oos:+.2f} ventaja {b.edge_oos:+.2f} (t {b.t_oos:+.1f}) años+ {b.years_pos} "
              f"| combinaciones que pasan ambos tramos: {int(S.ok.sum())}/{len(S)}", flush=True)
    A = pd.concat(allS, ignore_index=True)
    A.to_pickle(os.path.join(RESULTS, "cand_summary.pkl"))
    print(A[A.ok].sort_values("t_is", ascending=False).round(2).to_string(index=False))


if __name__ == "__main__":
    main()
