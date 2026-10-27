"""Linea E, paso 3: cartera e2 + patas de calendario elegidas en 'sel', nulos y validacion (2025) una sola vez.

Patas candidatas (salen de opt_E_vecinos; reglas y parametros fijados con datos <= 2024):
  tom     : cambio de mes en indices EE.UU. (SP500, NAS100, DJ30, US2000 a partes iguales): compra 22:45 servidor
            del ultimo dia habil del mes, salida 22:45 del 3er dia habil del mes nuevo. Gestion e2.
  prefomc : compra de los mismos 4 indices a las 21:00 del dia habil previo al FOMC, salida 20:45 del dia del
            FOMC (15 min antes del comunicado). Gestion e2.
  prehol  : compra de los 4 indices 22:45 del penultimo dia habil antes de un feriado bursatil -> 22:45 del
            ultimo dia habil antes del feriado. Gestion e2.
Carteras: e2 + cada pata y e2 + combinaciones, con peso total por pata w (fraccion del riesgo e2 de 8 %).
Nulos (para cada finalista, en sel y en val):
  (a) dias al azar: los mismos N eventos por periodo en dias habiles al azar (misma hora, misma duracion en
      dias habiles, compra) -> percentil del MAR de la cartera (>= 200 sorteos);
  (b) lado al azar: los mismos eventos con lado al azar (R_long / R_short ya simulados) -> percentil;
  (c) lote mayor (compare_mix); (d) correlacion diaria con e2 en sel y val; 2023 vs 2024.
Correr:  .venv/Scripts/python -m bot_backtesting.fullsim.opt_E_cartera [sel|val]
  'sel' elige y corre los nulos en sel; 'val' evalua los finalistas fijados en FINAL (una vez) y sus nulos.
"""
import os
import sys

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.opt_base import RESULTS, SEL, VAL, register, low_priority, period, evaluate
from bot_backtesting.fullsim.opt_E_common import (Sym, leg_frame, sim, base, combine, compare_mix, corr_daily,
                                                  evaluate_mix, as_rows, daily, year_R)
from bot_backtesting.fullsim.opt_E_patas import days_of, leg_rows, IDX, H, gold_frame, plan_signal
from bot_backtesting.fullsim.opt_E_vecinos import plan_tom, plan_prefomc, plan_prehol, gold_prefomc

LAD = dict(tps=(None, 2.0, 3.0), lock_k=1.0)


def leg_tom():
    return [leg_frame(Sym(s), plan_tom(Sym(s), 0, 3), f"tom:{s}", **LAD) for s in IDX]


def leg_prefomc():
    return [leg_frame(Sym(s), plan_prefomc(Sym(s), 21, 20.75, 1), f"prefomc:{s}", **LAD) for s in IDX]


def leg_prehol():
    return [leg_frame(Sym(s), plan_prehol(Sym(s)), f"prehol:{s}", **LAD) for s in IDX]


def leg_gfomc():
    return [gold_frame("g_prefomc", gold_prefomc(21, 20.75))]


def leg_jpy():
    S = Sym("USDJPY+")
    return [leg_frame(S, plan_signal(S, 2, 10, 10, 15, thr_sd=0.7), "jpy_mom", **LAD)]


LEGS = {"tom": leg_tom, "prefomc": leg_prefomc, "prehol": leg_prehol, "gfomc": leg_gfomc, "jpy": leg_jpy}


def rows_of(legs, ws):
    return [leg_rows(legs[k], w) for k, w in ws.items() if w > 0]


def random_days_frames(frames, per, rng):
    """Mismos eventos del periodo en dias habiles al azar: misma hora de entrada y de salida y la misma
    duracion en dias habiles. Compra. El mismo sorteo de dias para los 4 indices (como el evento real)."""
    a, b = period(per)
    allday = days_of(Sym(frames[0].sym.iat[0]))
    pos = {d: i for i, d in enumerate(allday)}
    cand = allday[(allday * 86400 >= a.timestamp()) & (allday * 86400 < b.timestamp())]
    F0 = frames[0][(frames[0].t >= a.timestamp()) & (frames[0].t < b.timestamp())]
    picks = []
    for r in F0.itertuples():
        d_in, d_out = int(r.t // 86400), int(r.t_out // 86400)
        if d_in not in pos or d_out not in pos:
            continue
        hold = pos[d_out] - pos[d_in]
        d = int(cand[rng.integers(len(cand))])
        j = min(pos[d] + hold, len(allday) - 1)
        picks.append((d * 86400 + r.t % 86400, int(allday[j]) * 86400 + r.t_out % 86400))
    out = []
    for F in frames:
        S = Sym(F.sym.iat[0])
        rows = []
        for t0, t1 in picks:
            z = sim(S, t0, t1, 1, **LAD)
            if z is not None:
                rows.append(dict(leg=F.leg.iat[0], sym=S.sym, t=int(t0), t_out=int(z["t_end"]), side=1, R=z["R"]))
        G = pd.DataFrame(rows)
        if len(G):
            G["day"] = pd.to_datetime(G.t, unit="s").dt.normalize()
            out.append(G)
    return out


def random_days_gold(frames, per, rng):
    """Oro: los mismos eventos en dias habiles al azar (misma hora, misma duracion), compra; camino M5."""
    from bot_backtesting.fullsim.opt_base import m15
    a, b = period(per)
    X, _ = m15()
    allday = np.array(sorted(set((X.time.values // 86400).tolist())))
    allday = allday[((allday + 3) % 7) < 5]
    cand = allday[(allday * 86400 >= a.timestamp()) & (allday * 86400 < b.timestamp())]
    F0 = frames[0][(frames[0].t >= a.timestamp()) & (frames[0].t < b.timestamp())]
    plan = []
    for r in F0.itertuples():
        d = int(cand[rng.integers(len(cand))])
        plan.append((d * 86400 + r.t % 86400, d * 86400 + (r.t_out - r.t) + r.t % 86400, 1))
    G = gold_frame("g_rand", plan)
    return [G] if G is not None else []


def random_days_any(name, frames, per, rng):
    if name == "gfomc":
        return random_days_gold(frames, per, rng)
    if name == "jpy":                 # pata de direccion: dias al azar con lado al azar
        a, b = period(per)
        F = frames[0]; S = Sym(F.sym.iat[0])
        cand = days_of(S); cand = cand[(cand * 86400 >= a.timestamp()) & (cand * 86400 < b.timestamp())]
        n = int(((F.t >= a.timestamp()) & (F.t < b.timestamp())).sum())
        plan = [(int(d) * 86400 + 10 * H, int(d) * 86400 + 15 * H, int(rng.choice([-1, 1])))
                for d in rng.choice(cand, size=n, replace=False)]
        return [leg_frame(S, plan, "jpy_rand", both=False, **LAD)]
    return random_days_frames(frames, per, rng)


def random_side_frames(frames, rng):
    out = []
    for F in frames:
        G = F.copy()
        s = rng.choice([-1, 1], size=len(G))
        G["R"] = np.where(s == 1, G.R_long, G.R_short)
        if "atrd" in G and G.sym.iat[0] == "XAUUSD+":       # oro: leg_rows usa pnl ($/oz)
            G["pnl"] = G.R * G.atrd
        out.append(G)
    return out


def nulls(legs, ws, per, B, n=200, seed=11):
    """Percentil del MAR de la cartera real frente a (a) dias al azar y (b) lado al azar (solo las patas nuevas)."""
    real = evaluate_mix(combine(B, *rows_of(legs, ws)), per)["mar"]
    rng = np.random.default_rng(seed)
    md, ms = [], []
    for _ in range(n):
        L2 = {k: random_days_any(k, legs[k], per, rng) for k, w in ws.items() if w > 0}
        md.append(evaluate_mix(combine(B, *rows_of(L2, ws)), per)["mar"])
        L3 = {k: random_side_frames(legs[k], rng) for k, w in ws.items() if w > 0}
        ms.append(evaluate_mix(combine(B, *rows_of(L3, ws)), per)["mar"])
    md, ms = np.array(md), np.array(ms)
    return dict(mar_real=real, pct_dias=float((md < real).mean()), mar_dias_med=float(np.median(md)),
                mar_dias_p95=float(np.quantile(md, .95)), pct_lado=float((ms < real).mean()),
                mar_lado_med=float(np.median(ms)), mar_lado_p95=float(np.quantile(ms, .95)))


def by_year(C, B):
    out = {}
    for y in (2023, 2024):
        p = (pd.Timestamp(f"{y}-01-01"), pd.Timestamp(f"{y + 1}-01-01"))
        out[y] = evaluate_mix(C, p)["mar"] / evaluate(B, p)["mar"]
    return out


GRID_TOM = [dict(tom=w) for w in (0.5, 1.0, 1.5)] + [dict(prefomc=w) for w in (0.5, 1.0, 1.5)] +     [dict(prehol=w) for w in (0.5, 1.0, 1.5)] + [dict(tom=a, prefomc=b) for a in (0.5, 1.0) for b in (0.5, 1.0)] +     [dict(tom=a, prefomc=b, prehol=c) for a in (0.5, 1.0) for b in (0.5, 1.0) for c in (0.5, 1.0)]   # 1a pasada (ya corrida)
GRID = [dict(prehol=a, prefomc=b, gfomc=c) for a in (0, 0.5, 1.0) for b in (0, 0.5, 1.0) for c in (0, 0.5, 1.0)
        if a + b + c > 0 and not (b == 0 and c == 0)] +        [dict(prehol=1.0, prefomc=0.5, gfomc=0.5, jpy=0.5), dict(prehol=1.0, gfomc=1.0, jpy=0.5),
        dict(prehol=1.0, prefomc=1.0, gfomc=1.0, jpy=1.0), dict(jpy=0.5), dict(jpy=1.0)]
# finalistas fijados con 'sel' (27-oct): ver informe opt-E-cartera-2026-10-27.md
FINAL = [dict(gfomc=1.0), dict(prehol=1.0), dict(prefomc=1.0, gfomc=1.0), dict(prehol=1.0, prefomc=1.0),
         dict(prehol=1.0, prefomc=1.0, gfomc=1.0)]


def main():
    low_priority()
    per = sys.argv[1] if len(sys.argv) > 1 else "sel"
    B = base()
    legs = {k: [f for f in fn() if f is not None and len(f)] for k, fn in LEGS.items()}
    if per == "lado":                       # solo el nulo de lado al azar (correccion para el oro, 27-oct)
        for ws in FINAL:
            if "gfomc" not in ws:
                continue
            lab = "+".join(f"{k}{w}" for k, w in ws.items())
            for p in ("sel", "val"):
                rng = np.random.default_rng(11)
                real = evaluate_mix(combine(B, *rows_of(legs, ws)), p)["mar"]
                ms = np.array([evaluate_mix(combine(B, *rows_of({k: random_side_frames(legs[k], rng) for k in ws},
                                                                 ws)), p)["mar"] for _ in range(200)])
                z = dict(mar_real=real, pct_lado=float((ms < real).mean()), mar_lado_med=float(np.median(ms)),
                         mar_lado_p95=float(np.quantile(ms, .95)))
                register("E", f"nulo_lado_oro:{lab}:{p}", z, params=ws)
                print(lab, p, {k: round(v, 3) for k, v in z.items()}, flush=True)
        for k in ("prehol", "prefomc", "gfomc"):
            A = pd.concat(legs[k]); y = pd.to_datetime(A.t, unit="s").dt.year
            print(k, "R medio por año", A.R.groupby(y).mean().round(3).to_dict(), "n", A.R.groupby(y).size().to_dict())
        return
    grid = GRID if per == "sel" else FINAL
    rows = []
    for ws in grid:
        lab = "+".join(f"{k}{w}" for k, w in ws.items())
        P = rows_of(legs, ws)
        C = combine(B, *P)
        res = compare_mix(C, B, per, label=f"E:cartera:{lab}")
        Pn = pd.concat(P, ignore_index=True)
        res["corr"] = corr_daily(Pn, B, per)
        if per == "sel":
            yy = by_year(C, B); res["ratio_2023"], res["ratio_2024"] = yy[2023], yy[2024]
        register("E", f"cartera:{lab}:{per}", res, params=ws)
        res["ratio_2023"] = res.get("ratio_2023"); res["ratio_2024"] = res.get("ratio_2024")
        rows.append(dict(cartera=lab, **{k: res.get(k) for k in ("mar_c", "mar_ratio", "cagr_c", "dd_c", "peor_dia_c",
                                                                "peor_mes_c", "p", "corr", "mar_lote_mayor",
                                                                "ratio_2023", "ratio_2024", "pasa")}))
        print(rows[-1], flush=True)
    R = pd.DataFrame(rows)
    R.to_csv(os.path.join(RESULTS, f"opt_E_cartera_{per}.csv"), index=False)
    if per == "sel" and "vec" in sys.argv:
        # vecindario de prehol (hora de entrada/salida y simbolo a simbolo), peso 1
        for h in (16.5, 21.0, 22.75):
            for syms in (IDX,) + tuple((x,) for x in IDX):
                fr = [leg_frame(Sym(x), plan_prehol(Sym(x), h), f"prehol:{x}", **LAD) for x in syms]
                C = combine(B, leg_rows(fr, 1.0))
                res = compare_mix(C, B, "sel", label=f"E:prehol_vec:h{h}:{'+'.join(syms)}")
                A = pd.concat(fr); yr = year_R(A)
                res.update(R_2023=float(yr.get(2023, np.nan)), R_2024=float(yr.get(2024, np.nan)))
                register("E", f"prehol_vec:h{h}:{'+'.join(syms)}:w1", res, params=dict(h=h, syms=syms))
                print(f"prehol h{h} {'+'.join(syms):26s} R23 {res['R_2023']:+.3f} R24 {res['R_2024']:+.3f} "
                      f"x{res['mar_ratio']:.3f} p {res['p']:.2f} mes {res['peor_mes_c']:.3f}", flush=True)
        return
    for ws in FINAL:
        lab = "+".join(f"{k}{w}" for k, w in ws.items())
        for p in ("sel", "val"):
            z = nulls(legs, ws, p, B)
            z["corr"] = corr_daily(pd.concat(rows_of(legs, ws)), B, p)
            register("E", f"nulos:{lab}:{p}", z, params=ws)
            print(lab, p, {k: round(v, 3) for k, v in z.items()}, flush=True)


if __name__ == "__main__":
    main()
