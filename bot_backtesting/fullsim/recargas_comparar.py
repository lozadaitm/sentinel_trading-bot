"""Comparacion final de recargas vs 'lote inicial mayor' (mismo R total) para las variantes elegidas en IS.
Lee results/recargas_store.pkl (de recargas_minimo). Cartera Big One + Momentum; riesgo 8 % por R.
Uso: python -m bot_backtesting.fullsim.recargas_comparar
"""
import os

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.recargas_minimo import RESULTS, low_priority

RISK = 0.08


def stats(day):
    cum = day.cumsum()
    dd = (cum.cummax().clip(lower=0) - cum).max()
    mon = day.groupby(pd.to_datetime(day.index * 86400, unit="s").to_period("M")).sum()
    return dict(R_tot=day.sum(), mes_pct=mon.mean() * RISK * 100, caida_R=dd, caida_pct=dd * RISK * 100,
                ret_caida=day.sum() / dd, sharpe=day.mean() / day.std() * np.sqrt(250),
                peor_dia_pct=day.min() * RISK * 100, peor_mes_pct=mon.min() * RISK * 100, meses_neg=int((mon < 0).sum()))


def main():
    low_priority()
    meta, store = pd.read_pickle(os.path.join(RESULTS, "recargas_store.pkl"))
    picks = {"big_one": ["LVL_pdl_rej_1.0_tp2", "FIX_atrd_0.5_1.0_time", "FIX_atrd_0.25+0.5+0.75_1.0_time"],
             "momentum": ["REV_0_0.5_1.0_tp2", "TIME_60_1.0_tp2", "FIX_atrd_0.5_1.0_time"]}
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
    rows, yrs = [], []
    for leg, vs in picks.items():
        for v in vs:
            addR, nadd, size = store[v]
            for per, msk in (("2022-2024 (IS)", meta.d < 20089), ("2025-2026 (OOS)", meta.d >= 20089), ("todo", meta.d > 0)):
                m = msk.values
                legm = (meta.leg == leg).values & m
                base = meta.R.where(m, 0.0)
                tot = base + np.where(legm, addR, 0.0)
                k = 1 + addR[legm].sum() / meta.R[legm].sum()          # lote mayor con el mismo R total
                big = base * np.where(legm, k, 1.0)
                for lab, x in (("base", base), (f"recarga {v}", tot), (f"lote x{k:.2f}", big)):
                    day = pd.Series(x.values if hasattr(x, "values") else x, index=meta.d).loc[m].groupby(level=0).sum()
                    rows.append(dict(pata=leg, periodo=per, cartera=lab, **stats(day)))
            g = pd.DataFrame({"y": meta.year, "a": addR})[(meta.leg == leg).values]
            yrs.append(g.groupby("y").a.sum().rename(v))
    S = pd.DataFrame(rows).drop_duplicates(["pata", "periodo", "cartera"])
    print(S.round(3).to_string(index=False))
    print("\nR anadido por la recarga, por año (suma, ponderado):")
    print(pd.concat(yrs, axis=1).round(2).to_string())
    print("\nBase por año (R suma) por pata:")
    print(meta.groupby(["year", "leg"]).R.sum().unstack().round(2).to_string())


if __name__ == "__main__":
    main()
