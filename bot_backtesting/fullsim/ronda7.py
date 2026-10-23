"""Ronda 7 (24-oct): ideas de la investigacion bibliografica, reglas fijadas de antemano. Solo simulacion.

  G1 venta del oro en horario pit de COMEX (15:30 -> 20:30 servidor): todos los dias / tendencia <= 0 / -2
  G2 salida de la Big One por hora (01:00 -> 06, 09, 10, 11, 12:30) con tendencia +2
  G3 feriados de China (Shanghai Gold Exchange cerrada): ¿la reapertura rinde menos?
  G5 prima de riesgo de varianza (GVZ implicita - HAR previsto) para el tamaño de la Big One
Uso: python -m bot_backtesting.fullsim.ronda7
"""
import os

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.entrylab import DATA, RESULTS, Evaluator, _tsmom_state, atr, ev, summarize

B = pd.read_pickle(os.path.join(DATA, "bars_all.pkl"))
M15 = B["M15"]; A15 = atr(M15)
TT = pd.to_datetime(M15.time.values, unit="s")
STATE = _tsmom_state(B)

# Feriados largos de China (SGE cerrada): Año Nuevo chino, 1 de mayo y Semana Dorada
CN = []
for a, b in (("2021-02-11", "2021-02-17"), ("2022-01-31", "2022-02-06"), ("2023-01-21", "2023-01-27"), ("2024-02-10", "2024-02-17"),
             ("2025-01-28", "2025-02-04"), ("2026-02-15", "2026-02-23"),
             ("2021-05-01", "2021-05-05"), ("2022-04-30", "2022-05-04"), ("2023-04-29", "2023-05-03"), ("2024-05-01", "2024-05-05"),
             ("2025-05-01", "2025-05-05"), ("2026-05-01", "2026-05-05"),
             ("2021-10-01", "2021-10-07"), ("2022-10-01", "2022-10-07"), ("2023-09-29", "2023-10-06"), ("2024-10-01", "2024-10-07"),
             ("2025-10-01", "2025-10-08"), ("2026-10-01", "2026-10-08")):
    CN += list(pd.date_range(a, b))
CN_DAYS = set((pd.DatetimeIndex(CN) - pd.Timestamp("1970-01-01")).days)


def at(h, mi, side, hz, need=None):
    m = (TT.hour == h) & (TT.minute == mi) & (TT.dayofweek < 5) & ~np.isnan(A15)
    E = ev(M15.time.values[m], np.full(m.sum(), side), pd.Series(A15).shift(1).values[m], hz)
    if need is not None:
        st = STATE.reindex(E.t.values // 86400).values
        E = E[(st == need) if need in (2, -2) else (st <= 0)]
    return E.dropna().reset_index(drop=True)


def main():
    ev_ = Evaluator(B); rng = np.random.default_rng(11)
    C = {
        "G1_pit_venta_todos": at(15, 30, -1, 5.0),
        "G1_pit_venta_tend<=0": at(15, 30, -1, 5.0, "<=0"),
        "G1_pit_venta_tend-2": at(15, 30, -1, 5.0, -2),
        "G2_bigone_06h": at(1, 0, 1, 5.0, 2),
        "G2_bigone_09h": at(1, 0, 1, 8.0, 2),
        "G2_bigone_10h": at(1, 0, 1, 9.0, 2),
        "G2_bigone_11h": at(1, 0, 1, 10.0, 2),
        "G2_bigone_1230": at(1, 0, 1, 11.5, 2),
    }
    pd.set_option("display.width", 250)
    for name, E in C.items():
        R = ev_.evaluate(E, rng)
        S = summarize(name, R)
        S["ok"] = (S.pnl_is > 0) & (S.edge_is > 0) & (S.pnl_oos > 0) & (S.edge_oos > 0)
        b = S[(S.tp == 0) & (S.sl == 0)].iloc[0]                # solo por hora (referencia comparable)
        best = S.sort_values("t_is", ascending=False).iloc[0]
        print(f"{name:22s} n={len(E):5d} | solo hora: train {b.pnl_is:+.2f} $/oz ventaja {b.edge_is:+.2f} (t {b.t_is:+.1f}) "
              f"test {b.pnl_oos:+.2f} ventaja {b.edge_oos:+.2f} (t {b.t_oos:+.1f}) años+ {b.years_pos} | mejor train tp{best.tp}/sl{best.sl}: "
              f"test {best.pnl_oos:+.2f} (t {best.t_oos:+.1f}) | pasan ambos {int(S.ok.sum())}/{len(S)}", flush=True)
    # G3 feriados chinos
    D = pd.read_pickle(os.path.join(DATA, "econ", "econ_daily2.pkl"))
    D["cn"] = D.index.isin(CN_DAYS)
    D["st"] = STATE.reindex(D.index).values
    print("\nG3 reapertura (% bruto) en feriados chinos vs resto:")
    for col in ("r_open15", "r_asia"):
        print(f"  {col}:", D.groupby("cn")[col].agg(["mean", "count"]).round(4).to_dict(),
              "| solo tendencia +2:", D[D.st == 2].groupby("cn")[col].mean().round(4).to_dict())
    print("  por año (r_asia, feriado):", D[D.cn].groupby("year").r_asia.mean().round(3).to_dict())
    T = pd.read_pickle(os.path.join(RESULTS, "bigone_plus_trades.pkl")); T = T[T.variant == "har_ev50"].copy()
    T["cn"] = (T.t // 86400).astype(int).isin(CN_DAYS)
    print("  Big One HAR R por feriado chino:", T.groupby("cn").r_mult.agg(["mean", "size"]).round(3).to_dict())
    # G5 prima de varianza
    g = pd.read_csv(os.path.join(DATA, "econ", "macro", "GVZCLS.csv")); g.columns = ["date", "gvz"]
    g["gvz"] = pd.to_numeric(g.gvz, errors="coerce"); g["d"] = (pd.to_datetime(g.date) - pd.Timestamp("1970-01-01")).dt.days
    gv = g.set_index("d").gvz.reindex(range(int(g.d.min()), int(D.index.max()) + 1)).ffill().shift(2)
    D["vrp"] = gv.reindex(D.index).values / np.sqrt(252) - D.rvhat_3
    A = pd.read_pickle(os.path.join(RESULTS, "bigone_plus_all.pkl"))
    A = A[(A.scale == "har") & (A.pyr == 0) & (A.state == 2) & (A.exit == "trail_2.0_0.5_L1.0")].copy()
    A["vrp"] = D.vrp.reindex((A.t // 86400).astype(int).values).values
    A["tr"] = np.where(A.year <= 2023, "2021-23", "2024-26")
    A["q"] = A.groupby("tr").vrp.transform(lambda s: pd.qcut(s, 3, labels=["baja", "media", "alta"]))
    print("\nG5 Big One (salida fija trail 2/0,5, candado 1) R por tercil de prima de varianza:")
    print(A.pivot_table(index="q", columns="tr", values="r_mult", aggfunc=["mean", "size"], observed=True).round(3).to_string())
    D["tr"] = np.where(D.year <= 2023, "2021-23", "2024-26")
    D["q"] = D.groupby("tr").vrp.transform(lambda s: pd.qcut(s, 3, labels=["baja", "media", "alta"]))
    print("  reapertura r_asia (%) por tercil de prima de varianza (todos los dias):")
    print(D.pivot_table(index="q", columns="tr", values="r_asia", aggfunc="mean", observed=True).round(4).to_string())


if __name__ == "__main__":
    main()
