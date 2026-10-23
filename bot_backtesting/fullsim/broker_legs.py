"""Patas nuevas y variantes sobre precios del broker (M15, 2022-08 -> 2026-10). Solo simulacion.

  A) ¿Varias Big One a la vez?  escalonada (01:00/01:15/01:30/01:45, 1/4 cada una) y escalera de salidas
     (una entrada repartida en 3 salidas) frente a una sola posicion: media y desvio del R diario.
  B) Rebote asiatico: R de la Big One segun lo que hizo EE.UU. el dia anterior (15:00 -> 23:45).
  C) Londres: 10:00 -> 15:00 en la direccion de Asia (01:00 -> 10:00).
  D) Noticias de calendario fijo: peticiones de desempleo (jueves 08:30 NY) e ISM manufacturero
     (primer dia habil 10:00 NY): a T+60 seguir el salto 24 h.
  E) Big One por dia de la semana (lunes = reapertura tras el fin de semana).
Uso: python -m bot_backtesting.fullsim.broker_legs
"""
import os

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.broker_rule import RESULTS, build, exit_label, walk_forward

pd.set_option("display.width", 250)
M15 = pd.read_pickle(os.path.join(os.path.dirname(__file__), "data", "broker_m15_full.pkl"))
O = pd.Series(M15.open.values, index=M15.time.values); C = pd.Series(M15.close.values, index=M15.time.values)


def ret(t0, t1):
    if t0 in O.index and t1 - 900 in C.index:
        return C[t1 - 900] - O[t0]
    return np.nan


def daily_stats(D, lab):
    x = D.groupby("d").r_mult.mean()
    yr = pd.to_datetime(x.index * 86400, unit="s").year
    print(f"  {lab:34s} R medio por dia {x.mean():+.3f} desvio {x.std():.3f} razon {x.mean() / x.std():+.3f} | por año",
          x.groupby(yr).mean().round(3).to_dict())


def part_a():
    print("A) varias Big One a la vez (salida 10:00, candado 1 ATR diario, mismas reglas)")
    days = sorted(set(M15.time.values // 86400))
    R = {}
    for m in (0, 15, 30, 45):
        ent = [(d * 86400 + 3600 + m * 60, 1) for d in days]
        fp = os.path.join(RESULTS, f"broker_legs_bo_{m:02d}.pkl")
        R[m] = pd.read_pickle(fp) if os.path.exists(fp) else build(f"bo{m}", None, 36 - m // 15, None, entries=ent)
        R[m].to_pickle(fp)
    ex = "atrd_time_0_0_L1"
    single = R[0][exit_label(R[0]) == ex]
    daily_stats(single, "una sola a la 01:00")
    st = pd.concat([R[m][exit_label(R[m]) == ex] for m in R])
    daily_stats(st, "escalonada 4 x 1/4 (01:00..01:45)")
    lad = R[0][exit_label(R[0]).isin(["atrd_tp_2_0_L1", "atrd_tp_3_0_L1", ex])]
    daily_stats(lad, "escalera de salidas (TP2/TP3/hora)")
    al = R[0][R[0].state == 2]
    for lab, m in (("una, solo dias alcistas", exit_label(al) == ex),):
        daily_stats(al[m], lab)


def part_b():
    print("\nB) Big One (01:00 -> 10:00, bruto $/oz) segun EE.UU. del dia anterior (15:00 -> 23:45)")
    rows = []
    for t in O.index[(O.index % 86400) == 3600]:
        d = t // 86400
        prev = d - (3 if (d + 3) % 7 == 0 else 1)
        rows.append(dict(y=pd.Timestamp(t, unit="s").year, bo=ret(t, t + 9 * 3600), ny_prev=ret(prev * 86400 + 15 * 3600, prev * 86400 + 24 * 3600 - 900)))
    X = pd.DataFrame(rows).dropna()
    X["q"] = pd.qcut(X.ny_prev, 3, labels=["EE.UU. bajo", "medio", "EE.UU. subio"])
    print(X.pivot_table(index="q", columns="y", values="bo", aggfunc="mean", observed=True).round(2).to_string())


def part_c():
    print("\nC) Londres 10:00 -> 15:00 en la direccion de Asia (01:00 -> 10:00), neto 0,29 $/oz")
    rows = []
    for t in O.index[(O.index % 86400) == 3600]:
        a = ret(t, t + 9 * 3600); l = ret(t + 9 * 3600, t + 14 * 3600)
        rows.append(dict(y=pd.Timestamp(t, unit="s").year, a=a, l=l))
    X = pd.DataFrame(rows).dropna()
    for k in (0.0, 0.5, 1.0):
        m = X.a.abs() > k * X.a.std()
        net = np.sign(X.a) * X.l - 0.29
        print(f"  |Asia| > {k} desv.: por año", net[m].groupby(X.y[m]).mean().round(2).to_dict(), f"total {net[m].mean():+.2f} n {m.sum()}")


def sched_entries(kind):
    out = []
    for d in pd.date_range("2022-08-15", "2026-10-15"):
        if kind == "claims" and d.dayofweek == 3:
            hh, mm = 8, 30
        elif kind == "ism" and d.dayofweek < 5 and d == pd.date_range(d.replace(day=1), periods=7, freq="B")[0]:
            hh, mm = 10, 0
        else:
            continue
        ny = pd.Timestamp(d.date()).replace(hour=hh, minute=mm).tz_localize("America/New_York")
        t0 = int(ny.tz_convert("UTC").tz_localize(None).timestamp()) + (3 if ny.dst().total_seconds() else 2) * 3600
        t0 -= t0 % 900
        a, b = t0 - 900, t0 + 3600
        if a in O.index and b - 900 in C.index and b in O.index:
            j = C[b - 900] - O[a]
            if j:
                out.append((b, int(np.sign(j))))
    return out


def part_d():
    print("\nD) noticias de calendario fijo, seguir el salto a T+60 durante 24 h (validacion movil)")
    for kind in ("claims", "ism"):
        fp = os.path.join(RESULTS, f"broker_legs_{kind}.pkl")
        R = pd.read_pickle(fp) if os.path.exists(fp) else build(kind, None, 96, None, entries=sched_entries(kind))
        R.to_pickle(fp)
        W = walk_forward(R)
        print(f"  {kind}: n={len(W)} R={W.r_mult.mean():+.3f} por año", W.groupby("year").r_mult.mean().round(3).to_dict(),
              "| salida por hora sin elegir:", R[R.exit == "atrd_time_0_0_L1"].groupby("year").r_mult.mean().round(3).to_dict())


def part_e():
    print("\nE) Big One (bruto $/oz 01:00 -> 10:00) por dia de la semana")
    rows = [dict(y=pd.Timestamp(t, unit="s").year, dow=((t // 86400) + 3) % 7, bo=ret(t, t + 9 * 3600)) for t in O.index[(O.index % 86400) == 3600]]
    X = pd.DataFrame(rows).dropna()
    print(X.pivot_table(index="dow", columns="y", values="bo", aggfunc="mean").round(2).to_string())


if __name__ == "__main__":
    part_b(); part_c(); part_e(); part_d(); part_a()
