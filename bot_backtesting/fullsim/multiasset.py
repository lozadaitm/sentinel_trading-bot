"""¿Existe una «Big One» en otros simbolos del broker? Barrido de horario por activo (solo analisis).

Para cada activo (data/cross_*.pkl, M5 Dukascopy en hora servidor): entrar a la hora h en punto, salir
1/3/6/9 h despues (sin cruzar la medianoche del servidor, asi no hay swap), compra o venta, en todos
los dias o segun la tendencia diaria propia (s = signo(C-C21)+signo(C-C63) del dia anterior).
Retorno NETO en % (spread mediano medido en el broker + comision). Falsos positivos: BH 10 % en
train 2021-23 y confirmacion obligatoria en test 2024-26 (neto > 0 y t > 2).
Uso: python -m bot_backtesting.fullsim.multiasset [activo ...]
"""
import os
import sys

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.econ_intraday import bh, _p
from bot_backtesting.fullsim.entrylab import DATA

# costo ida y vuelta en % del precio: spread mediano medido (24-oct, copy_ticks) + comision
COST = {"xau": 0.0027 + 0.003, "xag": 0.0367 + 0.003, "sp500": 0.0047, "nas100": 0.0027, "dj30": 0.0023, "ger40": 0.0063,
        "uk100": 0.0065, "jp225": 0.0201, "copper": 0.0615, "eurusd": 0.0009 + 0.010, "xpt": 0.5485,
        # divisas: spread a la 01:00 medido (gbp, aud, jpy); nzd/chf/cad estimado; comision ~0,010 %
        "gbpusd": 0.0015 + 0.010, "audusd": 0.0043 + 0.010, "usdjpy": 0.0013 + 0.010, "nzdusd": 0.006 + 0.010,
        "usdchf": 0.002 + 0.010, "usdcad": 0.002 + 0.010}
HZ = (12, 36, 72, 108)


def matrix(name):
    x = pd.read_pickle(os.path.join(DATA, f"cross_{name}.pkl"))
    day = x.time.values // 86400; slot = (x.time.values % 86400) // 300
    days = np.unique(day); di = np.searchsorted(days, day)
    O = np.full((len(days), 288), np.nan); C = O.copy()
    O[di, slot] = x.open.values; C[di, slot] = x.close.values
    c = pd.Series(np.nanmax(np.where(np.isnan(C), -np.inf, np.arange(288)), axis=1))
    last = C[np.arange(len(days)), np.clip(c.values.astype(int), 0, 287)]
    s = pd.Series(last)
    st = (np.sign(s - s.shift(21)) + np.sign(s - s.shift(63))).shift(1).values
    return days, O, C, st


def scan(name):
    days, O, C, st = matrix(name)
    yr = pd.to_datetime(days * 86400, unit="s").year.values
    dow = (days + 3) % 7
    tr = yr <= 2023
    rows = []
    for h in range(0, 24):
        k = h * 12
        for n in HZ:
            if k + n > 287:
                continue
            e = O[:, k]; x = C[:, k + n - 1]
            for side in (1, -1):
                r = ((x - e) / e * 100) * side - COST[name]
                for grp, m in (("todos", dow < 5), ("tend+2", st == 2), ("tend0", st == 0), ("tend-2", st == -2)):
                    a = r[m & tr]; b = r[m & ~tr]
                    a = a[~np.isnan(a)]; b = b[~np.isnan(b)]
                    if len(a) < 60 or len(b) < 60:
                        continue
                    ta = a.mean() / a.std() * np.sqrt(len(a)); tb = b.mean() / b.std() * np.sqrt(len(b))
                    rows.append(dict(activo=name, hora=h, horas=n // 12, lado=side, grupo=grp, m_tr=a.mean(), t_tr=ta,
                                     m_te=b.mean(), t_te=tb, n_tr=len(a), n_te=len(b)))
    R = pd.DataFrame(rows)
    R["bh"] = bh(R.t_tr.apply(_p).values) & (R.m_tr > 0)
    R["confirma"] = R.bh & (R.m_te > 0) & (R.t_te > 2)
    return R


def main():
    names = sys.argv[1:] or [n for n in COST if os.path.exists(os.path.join(DATA, f"cross_{n}.pkl"))]
    pd.set_option("display.width", 250)
    allR = []
    for n in names:
        R = scan(n); allR.append(R)
        print(f"{n:7s} pruebas {len(R):4d} | pasan BH en train {int(R.bh.sum()):3d} | confirman en test {int(R.confirma.sum()):3d}", flush=True)
        if R.confirma.any():
            print(R[R.confirma].sort_values("t_te", ascending=False).head(12).round(4).to_string(index=False))
    pd.concat(allR).to_pickle(os.path.join(DATA, "econ", "multiasset_scan.pkl"))


if __name__ == "__main__":
    main()
