"""Momentum de la ultima media hora (Baltussen et al., JFE 2021) en indices EE.UU. del broker (solo analisis).
Señal: retorno desde la apertura NY (16:30 servidor) hasta las 22:30 servidor (15:30 NY); posicion en su
direccion de 22:30 a 23:00 servidor (cierre NY). Neto del spread medido. Train 2021-23 / test 2024-26.
Variante: solo si |señal| > 1 desviacion (dias de movimiento fuerte). Uso: python -m bot_backtesting.fullsim.last_half_hour"""
import os
import numpy as np
import pandas as pd
from bot_backtesting.fullsim.multiasset import COST, matrix

for name in ("sp500", "nas100", "dj30", "xau"):
    days, O, C, st = matrix(name)
    yr = pd.to_datetime(days * 86400, unit="s").year.values
    a, b = (198, 270) if name != "xau" else (12, 240)       # 16:30 / 22:30 servidor (oro: 01:00 -> 20:00)
    e, x = (270, 276) if name != "xau" else (240, 246)     # 22:30 -> 23:00 (oro: 20:00 -> 20:30)
    sig = (C[:, b - 1] - O[:, a]) / O[:, a] * 100
    r = (C[:, x - 1] - O[:, e]) / O[:, e] * 100
    for lab, m in (("todos", np.ones(len(days), bool)), ("|señal|>1sd", np.abs(sig) > np.nanstd(sig[yr <= 2023]))):
        pnl = np.sign(sig) * r - COST[name]
        for tn, mt in (("2021-23", yr <= 2023), ("2024-26", yr > 2023)):
            z = pnl[m & mt]; z = z[~np.isnan(z)]
            print(f"{name:7s} {lab:12s} {tn}: n={len(z):4d} neto {z.mean():+.4f}% (t {z.mean() / z.std() * np.sqrt(len(z)):+.2f})")
