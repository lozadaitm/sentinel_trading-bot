"""Linea E, paso 2: vecindario y pesos de las patas que sobrevivieron la criba (R >= 0 en 2023 y 2024 en sel) y
tres patas de calendario mas con la misma familia de mecanismo (fijadas antes de mirar). Solo 'sel'. Todo se registra.

Sobrevivientes de opt_E_patas: idx_tom (cambio de mes en indices EE.UU.), idx_prefomc (deriva previa al FOMC),
jpy_mom (USDJPY 10 -> 15 siguiendo 02 -> 10; quedo en 2024 en -0,00003 R, se mira igual), btc_weekend (solo un
año de historia en sel: vigilancia por construccion).
Nuevas de la misma familia: eu_tom (cambio de mes en GER40 / UK100 / EU50, entrada y salida 18:15 servidor),
idx_prehol (compra del indice el dia habil previo a un feriado bursatil de EE.UU.: 22:45 de d-2 -> 22:45 de d-1),
g_prefomc (oro comprado 21:00 del dia previo al FOMC -> 20:45 del dia del FOMC, camino M5).
Vecindario: dias de entrada/salida, horas, candado 1 o 2 ATR_D (las de varios dias), solo salida por hora
(sin TP), umbral y horas de jpy_mom, simbolo a simbolo; pesos 0,25 / 0,5 / 1 / 1,5 del riesgo e2.
Correr:  .venv/Scripts/python -m bot_backtesting.fullsim.opt_E_vecinos
Salida:  results/opt_E_vecinos.csv  y  results/opt_E_frames2.pkl (operaciones)
"""
import os
import pickle

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.opt_base import RESULTS, SEL, VAL, register, low_priority
from bot_backtesting.fullsim.opt_E_common import (Sym, leg_frame, base, combine, compare_mix, corr_daily, year_R)
from bot_backtesting.fullsim.opt_E_patas import (days_of, plan_signal, gold_frame, leg_rows, IDX, H)

FR2 = os.path.join(RESULTS, "opt_E_frames2.pkl")
EU = ("GER40", "UK100", "EU50")


def plan_tom(S, back=0, fwd=3, h_in=22.75, h_out=22.75):
    """Entrada h_in del dia habil (ultimo del mes - back); salida h_out del dia habil numero fwd del mes nuevo."""
    days = days_of(S)
    m = pd.Series(pd.to_datetime(days * 86400, unit="s").to_period("M"))
    out = []
    for i in range(back, len(days) - fwd):
        if m[i] != m[i + 1]:
            out.append((days[i - back] * 86400 + int(h_in * H), days[i + fwd] * 86400 + int(h_out * H), 1))
    return out


def fomc_days():
    E = pd.read_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "events_us.csv"))
    return (pd.to_datetime(E[E.event == "FOMC"].date) - pd.Timestamp("1970-01-01")).dt.days.values


def plan_prefomc(S, h_in=21, h_out=20.75, back=1):
    days = days_of(S); ds = set(days.tolist()); pos = {d: i for i, d in enumerate(days)}
    out = []
    for d in fomc_days():
        if d not in ds or pos[d] - back < 0:
            continue
        p = days[pos[d] - back]
        out.append((p * 86400 + int(h_in * H), d * 86400 + int(h_out * H), 1))
    return out


def nyse_holidays():
    from pandas.tseries.holiday import (AbstractHolidayCalendar, GoodFriday, Holiday, USLaborDay, USMartinLutherKingJr,
                                        USMemorialDay, USPresidentsDay, USThanksgivingDay, nearest_workday)

    class NYSE(AbstractHolidayCalendar):
        rules = [Holiday("NY", month=1, day=1, observance=nearest_workday), USMartinLutherKingJr, USPresidentsDay,
                 GoodFriday, USMemorialDay, Holiday("J19", month=6, day=19, start_date="2022-01-01",
                                                    observance=nearest_workday),
                 Holiday("J4", month=7, day=4, observance=nearest_workday), USLaborDay, USThanksgivingDay,
                 Holiday("XM", month=12, day=25, observance=nearest_workday)]
    h = NYSE().holidays("2022-01-01", "2026-12-31")
    return set(((h - pd.Timestamp("1970-01-01")).days).tolist())


def plan_prehol(S, h=22.75):
    hol = nyse_holidays()
    days = days_of(S)
    out = []
    for i in range(2, len(days)):
        d = days[i]
        # proximo dia habil (lun-vie) despues de days[i-1] es feriado -> days[i-1] es el dia previo al feriado
        nxt = days[i - 1] + 1
        while (nxt + 3) % 7 >= 5:
            nxt += 1
        if nxt in hol:
            out.append((days[i - 2] * 86400 + int(h * H), days[i - 1] * 86400 + int(h * H), 1))
    return sorted(set(out))


def gold_prefomc(h_in=21, h_out=20.75):
    from bot_backtesting.fullsim.opt_base import m15
    X, _ = m15()
    allday = np.array(sorted(set((X.time.values // 86400).tolist())))
    allday = allday[((allday + 3) % 7) < 5]
    pos = {d: i for i, d in enumerate(allday)}
    out = []
    for d in fomc_days():
        if d in pos and pos[d] > 0 and d * 86400 < VAL[1].timestamp():
            out.append((allday[pos[d] - 1] * 86400 + int(h_in * H), d * 86400 + int(h_out * H), 1))
    return out


def variants():
    """dict nombre -> (lista de frames). Cada variante = una fila del registro por peso."""
    V = {}
    mg = dict(lad=dict(tps=(None, 2.0, 3.0), lock_k=1.0), lock2=dict(tps=(None, 2.0, 3.0), lock_k=2.0),
              time=dict(tps=(None, None, None), lock_k=1.0))
    for mgn, kw in mg.items():
        for back, fwd in ((0, 3), (0, 2), (0, 4), (1, 3), (1, 2)):
            nm = f"idx_tom:b{back}f{fwd}:{mgn}"
            V[nm] = [leg_frame(Sym(s), plan_tom(Sym(s), back, fwd), f"{nm}:{s}", **kw) for s in IDX]
        for s in IDX:
            V[f"idx_tom:b0f3:{mgn}:{s}"] = [leg_frame(Sym(s), plan_tom(Sym(s)), f"idx_tom:{s}", **kw)]
        V[f"idx_tom:b0f3:{mgn}:h16.5"] = [leg_frame(Sym(s), plan_tom(Sym(s), 0, 3, 16.5, 16.5), f"tom:{s}", **kw) for s in IDX]
        V[f"eu_tom:b0f3:{mgn}"] = [leg_frame(Sym(s), plan_tom(Sym(s), 0, 3, 18.25, 18.25), f"eu_tom:{s}", **kw) for s in EU]
        V[f"eu_tom:b1f3:{mgn}"] = [leg_frame(Sym(s), plan_tom(Sym(s), 1, 3, 18.25, 18.25), f"eu_tom:{s}", **kw) for s in EU]
        for hin, hout, back in ((21, 20.75, 1), (16.5, 20.75, 1), (22.75, 20.75, 1), (21, 20.5, 1), (16.5, 20.75, 0),
                                (21, 20.75, 2)):
            nm = f"idx_prefomc:{hin}-{hout}-b{back}:{mgn}"
            V[nm] = [leg_frame(Sym(s), plan_prefomc(Sym(s), hin, hout, back), f"{nm}:{s}", **kw) for s in IDX]
        for s in IDX:
            V[f"idx_prefomc:21-20.75-b1:{mgn}:{s}"] = [leg_frame(Sym(s), plan_prefomc(Sym(s)), f"prefomc:{s}", **kw)]
        V[f"idx_prehol:{mgn}"] = [leg_frame(Sym(s), plan_prehol(Sym(s)), f"prehol:{s}", **kw) for s in IDX]
    S = Sym("USDJPY+")
    for thr in (0.3, 0.5, 0.7):
        for hin, hold in ((9, 5), (10, 5), (11, 5), (10, 4), (10, 6)):
            nm = f"jpy_mom:thr{thr}:h{hin}+{hold}"
            V[nm] = [leg_frame(S, plan_signal(S, 2, hin, hin, hin + hold, thr_sd=thr), nm)]
    S = Sym("BTCUSD")
    for hin, dout, hout in ((22, 3, 0.75), (20, 3, 0.75), (23, 3, 0.75), (22, 2, 22), (22, 3, 10)):
        nm = f"btc_weekend:fri{hin}-d{dout}h{hout}"
        plan = [(d * 86400 + int(hin * H), (d + dout) * 86400 + int(hout * H), 1) for d in days_of(S) if (d + 3) % 7 == 4]
        V[nm] = [leg_frame(S, plan, nm)]
    for hin, hout in ((21, 20.75), (16.5, 20.75), (22.75, 20.75), (21, 20.5)):
        nm = f"g_prefomc:{hin}-{hout}"
        V[nm] = [gold_frame(nm, gold_prefomc(hin, hout))]
    return {k: [f for f in v if f is not None and len(f)] for k, v in V.items()}


def main():
    low_priority()
    if os.path.exists(FR2):
        V = pickle.load(open(FR2, "rb"))
    else:
        V = variants()
        pickle.dump(V, open(FR2, "wb"))
    B = base()
    rows = []
    a1 = SEL[1].timestamp()
    for nm, frames in V.items():
        if not frames:
            continue
        A = pd.concat(frames, ignore_index=True); A = A[A.t < a1]
        yr = year_R(A)
        for w in (0.25, 0.5, 1.0, 1.5):
            P = leg_rows(frames, w)
            C = combine(B, P)
            res = compare_mix(C, B, "sel", label=f"E:{nm}:w{w}", boot=True)
            res.update(dict(R_sel=float(A.R.mean()), n_leg=len(A), R_2023=float(yr.get(2023, np.nan)),
                            R_2024=float(yr.get(2024, np.nan)), corr_sel=corr_daily(P, B, "sel"),
                            locked=float(A.locked.mean())))
            register("E", f"vec:{nm}:w{w}", res, params=dict(w=w))
            rows.append(dict(variante=nm, w=w, **{k: res[k] for k in (
                "n_leg", "R_sel", "R_2023", "R_2024", "corr_sel", "locked", "mar_c", "mar_ratio", "dd_c", "cagr_c",
                "peor_dia_c", "peor_mes_c", "p", "mar_lote_mayor")}))
        r = rows[-3]
        print(f"{nm:42s} n {len(A):4d} R {A.R.mean():+.3f} 23 {yr.get(2023, np.nan):+.3f} 24 {yr.get(2024, np.nan):+.3f}"
              f" corr {r['corr_sel']:+.3f} | w0.5 x{r['mar_ratio']:.3f} p {r['p']:.2f} | w1 x{rows[-2]['mar_ratio']:.3f}"
              f" p {rows[-2]['p']:.2f} | w1.5 x{rows[-1]['mar_ratio']:.3f}", flush=True)
    pd.DataFrame(rows).to_csv(os.path.join(RESULTS, "opt_E_vecinos.csv"), index=False)


if __name__ == "__main__":
    main()
