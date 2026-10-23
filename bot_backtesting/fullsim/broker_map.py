"""Mapa horario del oro con PRECIOS REALES DEL BROKER (M15 XAUUSD+, 2022-08 -> 2026-10). Solo analisis.

Entrada a la apertura de cada hora (01..22 servidor), salida 1/3/6/9 h despues (sin cruzar la
medianoche), compra o venta. Costo 0,29 $/oz (spread medido 0,17 + comision 0,12), en % del precio.
Grupos: todos; tendencia diaria +2 / 0 / -2; y según lo que hizo ASIA ese dia (01:00 -> hora de
entrada): sube > 0,5 desv., baja < -0,5 desv., plano. Tramos: A = 2022-08..2024-06, B = 2024-07..2026-10.
Falsos positivos: BH 10 % en A y confirmacion en B (neto > 0, t > 2), y al reves (elegido en B,
confirmado en A), para no depender de que tramo se elige primero.
Uso: python -m bot_backtesting.fullsim.broker_map
"""
import os

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.econ_intraday import _p, bh

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
COST_OZ = 0.29
SPLIT = pd.Timestamp("2024-07-01").timestamp() // 86400


def matrices():
    X = pd.read_pickle(os.path.join(DATA, "broker_m15_full.pkl"))
    day = X.time.values // 86400; slot = (X.time.values % 86400) // 900
    days = np.unique(day); di = np.searchsorted(days, day)
    O = np.full((len(days), 96), np.nan); C = O.copy()
    O[di, slot] = X.open.values; C[di, slot] = X.close.values
    d1 = pd.Series(X.close.values).groupby(day).last()
    st = (np.sign(d1 - d1.shift(21)) + np.sign(d1 - d1.shift(63))).shift(1).reindex(days).values
    return days, O, C, st


def scan():
    days, O, C, st = matrices()
    A = days < SPLIT; dow = (days + 3) % 7
    rows = []
    for h in range(1, 23):
        k = h * 4
        asia = (O[:, k] - O[:, 4]) / O[:, 4] * 100 if h > 1 else np.full(len(days), np.nan)
        sd = np.nanstd(asia[A]) if h > 1 else np.nan
        groups = [("todos", dow < 5), ("tend+2", st == 2), ("tend0", st == 0), ("tend-2", st == -2)]
        if h > 2:
            groups += [("asia_sube", asia > 0.5 * sd), ("asia_baja", asia < -0.5 * sd), ("asia_plana", np.abs(asia) <= 0.5 * sd),
                       ("tend+2&asia_sube", (st == 2) & (asia > 0.5 * sd)), ("tend+2&asia_baja", (st == 2) & (asia < -0.5 * sd))]
        for nh in (1, 3, 6, 9):
            if k + nh * 4 > 96:
                continue
            e = O[:, k]; x = C[:, k + nh * 4 - 1]
            for side in (1, -1):
                r = ((x - e) * side - COST_OZ) / e * 100
                for g, m in groups:
                    a, b = r[m & A], r[m & ~A]
                    a, b = a[~np.isnan(a)], b[~np.isnan(b)]
                    if len(a) < 40 or len(b) < 40:
                        continue
                    rows.append(dict(hora=h, horas=nh, lado="compra" if side == 1 else "venta", grupo=g,
                                     m_A=a.mean(), t_A=a.mean() / a.std() * np.sqrt(len(a)), n_A=len(a),
                                     m_B=b.mean(), t_B=b.mean() / b.std() * np.sqrt(len(b)), n_B=len(b)))
    R = pd.DataFrame(rows)
    R["bh_A"] = bh(R.t_A.apply(_p).values) & (R.m_A > 0)
    R["bh_B"] = bh(R.t_B.apply(_p).values) & (R.m_B > 0)
    R["ok_AB"] = R.bh_A & (R.m_B > 0) & (R.t_B > 2)
    R["ok_BA"] = R.bh_B & (R.m_A > 0) & (R.t_A > 2)
    return R


def main():
    R = scan()
    R.to_pickle(os.path.join(DATA, "econ", "broker_map.pkl"))
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 200)
    print(f"pruebas {len(R)} | elegidas en A y confirmadas en B: {int(R.ok_AB.sum())} | elegidas en B y confirmadas en A: {int(R.ok_BA.sum())}")
    print(R[R.ok_AB | R.ok_BA].sort_values("t_A", ascending=False).round(4).to_string(index=False))
    print("\nVENTAS en horario EE.UU. (entrada 14..20 h), mejores por t_A:")
    v = R[(R.lado == "venta") & R.hora.between(14, 20)].sort_values("t_A", ascending=False).head(25)
    print(v.round(4).to_string(index=False))


if __name__ == "__main__":
    main()
