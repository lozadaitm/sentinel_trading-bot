"""Prueba contra la mineria de datos (SPA de Hansen y Reality Check de White, paquete `arch`).

Universo: TODAS las reglas probadas en entrylab/cand (results/entry_*.pkl y cand_*.pkl). Para cada
regla y cada combinacion de salida (tp, sl) -> serie diaria de ganancia neta $/oz (0 los dias sin
operacion). Pregunta: ¿la mejor de todas supera a «no operar» mas alla de lo que daria el azar por
haber probado tantas? Se corre en 2021-23 (donde se eligio) y en 2024-26 (fuera de muestra).
Requiere `arch` (venv de investigacion). Uso: python -m bot_backtesting.fullsim.spa_test
"""
import glob
import os

import numpy as np
import pandas as pd
from arch.bootstrap import SPA

RESULTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")


def panel():
    cols = {}
    for f in sorted(glob.glob(os.path.join(RESULTS, "entry_*.pkl")) + glob.glob(os.path.join(RESULTS, "cand_*.pkl"))):
        name = os.path.basename(f)[:-4]
        R = pd.read_pickle(f)
        if not {"tp", "sl", "pnl", "day"} <= set(R.columns):
            continue
        for (tp, sl), g in R.groupby(["tp", "sl"]):
            cols[f"{name}|{tp}|{sl}"] = g.groupby("day").pnl.sum()
    P = pd.DataFrame(cols).sort_index()
    days = pd.RangeIndex(int(P.index.min()), int(P.index.max()) + 1)
    wd = [d for d in days if (d + 3) % 7 < 5]
    return P.reindex(wd).fillna(0.0)


def main():
    P = panel()
    yr = pd.to_datetime(P.index.values * 86400, unit="s").year
    print(f"estrategias (regla x salida): {P.shape[1]}, dias: {P.shape[0]}")
    for lab, m in (("2021-23", yr <= 2023), ("2024-26", yr > 2023)):
        X = P[m]
        losses = -X.values                                   # SPA trabaja con perdidas; referencia = 0 (no operar)
        bench = np.zeros(len(X))
        spa = SPA(bench, losses, block_size=10, reps=2000, seed=3)
        spa.compute()
        best = X.mean().sort_values(ascending=False)
        print(f"\n{lab}: SPA p-valores (inferior/consistente/superior) = {np.round(spa.pvalues.values, 4).tolist()}")
        print("  mejores 8 por $/oz diario:", ", ".join(f"{k} {v:+.3f}" for k, v in best.head(8).items()))
        bo = [c for c in X.columns if c.startswith("entry_asia_long_if_up|")]
        spa2 = SPA(bench, -X[bo].values, block_size=10, reps=2000, seed=3); spa2.compute()
        print(f"  solo la familia Big One ({len(bo)} salidas): p = {np.round(spa2.pvalues.values, 4).tolist()}")
        sub = X.drop(columns=[c for c in X.columns if "asia" in c or "drift_asia" in c])
        spa3 = SPA(bench, -sub.values, block_size=10, reps=2000, seed=3); spa3.compute()
        print(f"  todo MENOS las variantes de la reapertura asiatica ({sub.shape[1]}): p = {np.round(spa3.pvalues.values, 4).tolist()}")


if __name__ == "__main__":
    main()
