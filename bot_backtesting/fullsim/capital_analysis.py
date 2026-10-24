"""¿Cuanto capital? Minimo, ideal y maximo para la cartera Big One + momentum EE.UU. + NFP con escalera.

Para cada capital inicial se simula la cuenta (2022-10 -> 2026-10, precios del broker, riesgo 5 % y 8 %):
  * realista: cada tercio de la escalera se redondea a 0,01 con minimo 0,01 (lote total >= 0,03)
  * ideal: lote continuo, sin redondeo ni minimo
Eficiencia = multiplo realista / ideal; riesgo efectivo medio y maximo (el minimo puede forzar mas riesgo).
Tambien informa el lote tipico por operacion al final del periodo, para ver cuando se acerca al volumen
maximo por orden y a la liquidez de la reapertura.
Uso: python -m bot_backtesting.fullsim.capital_analysis
"""
import numpy as np
import pandas as pd

from bot_backtesting.fullsim.broker_accounts import trades_fixed

T = trades_fixed(ladder=True)
T = T[(T.t >= pd.Timestamp("2022-10-01").timestamp())].sort_values("t").reset_index(drop=True)


def run(bal0, f, exact):
    ev = sorted([(r.t, 0, i) for i, r in T.iterrows()] + [(r.t_out, 1, i) for i, r in T.iterrows()])
    eq, peak, lots, risks, dd, lots_hist = bal0, bal0, {}, [], 0.0, []
    for t, kind, i in ev:
        r = T.loc[i]
        if kind == 0:
            raw = eq * f * r.w / (r.risk_oz * 100)
            lot = raw if exact else 3 * max(0.01, np.floor(raw / 3 / 0.01 + 1e-9) * 0.01)
            lots[i] = lot; risks.append(lot * r.risk_oz * 100 / eq); lots_hist.append((t, lot))
        else:
            eq += r.pnl * lots[i] * 100; peak = max(peak, eq); dd = max(dd, 1 - eq / peak)
    return eq / bal0, dd, np.mean(risks), np.max(risks), lots_hist


rows = []
for f in (0.05, 0.08):
    for bal in (1000, 2000, 3000, 5000, 7500, 10000, 25000, 50000, 100000):
        xr, ddr, rm, rM, lh = run(bal, f, False)
        xi, ddi, _, _, _ = run(bal, f, True)
        last = [l for t, l in lh if t >= pd.Timestamp("2026-01-01").timestamp()]
        first = [l for t, l in lh if t < pd.Timestamp("2023-01-01").timestamp()]
        rows.append(dict(riesgo=f, capital=bal, x_real=xr, x_ideal=xi, eficiencia=xr / xi, caida_real=ddr, riesgo_medio=rm, riesgo_max=rM,
                         lote_med_inicio=np.median(first), lote_med_2026=np.median(last)))
pd.set_option("display.width", 250)
print(pd.DataFrame(rows).round(3).to_string(index=False))
