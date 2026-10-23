"""Ronda 2 sobre precios del broker: herramientas de tamaño y satelites rehechos sin el artefacto.

  * Big One y momentum EE.UU. con escala ATR M15 / ATR diario / HAR (validacion movil por familia de escala)
  * momentum EE.UU.: umbral 0,3 / 0,5 / 0,7 / 1,0 desv.; todas las tendencias; salida 21:00 o 23:45
  * satelites de noticias: a T+60 min seguir el salto de FOMC/NFP, ir contra el del IPC; 24 h
  * Big One a medio riesgo en dias de noticia
  * cartera: riesgo fijo 2-3 % y piso de Grossman-Zhou
Uso: python -m bot_backtesting.fullsim.broker_round2
"""
import os

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.broker_rule import RESULTS, account, asia_side, build, walk_forward


def news_entries(kinds, follow):
    X = pd.read_pickle(os.path.join(os.path.dirname(__file__), "data", "broker_m15_full.pkl"))
    C = pd.Series(X.close.values, index=X.time.values); O = pd.Series(X.open.values, index=X.time.values)
    E = pd.read_csv(os.path.join(os.path.dirname(__file__), "events_us.csv"))
    out = []
    for e in E[E.event.isin(kinds)].itertuples():
        utc = pd.Timestamp(f"{e.date} {e.time_utc}")
        ny = utc.tz_localize("UTC").tz_convert("America/New_York")
        t0 = int(utc.timestamp()) + (3 if ny.dst().total_seconds() else 2) * 3600
        t0 -= t0 % 900
        a, b = t0 - 900, t0 + 3600 - 900
        if a not in O.index or b not in C.index or t0 + 3600 not in O.index:
            continue
        jump = C[b] - O[a]
        if jump == 0:
            continue
        out.append((t0 + 3600, int(np.sign(jump)) * (1 if follow else -1)))
    return out


def wf_by_scale(R, scale):
    return walk_forward(R[R.scale == scale])


def main():
    pd.set_option("display.width", 250)
    specs = {
        "bigone": dict(h=1, nb=36, fn=lambda d, k, T, O, idx, D: 1),
        "ny_mom_03": dict(h=15, nb=24, fn=asia_side(0.3)),
        "ny_mom_05": dict(h=15, nb=24, fn=asia_side(0.5)),
        "ny_mom_07": dict(h=15, nb=24, fn=asia_side(0.7)),
        "ny_mom_10": dict(h=15, nb=24, fn=asia_side(1.0)),
        "ny_mom_05_2345": dict(h=15, nb=35, fn=asia_side(0.5)),
        "news_fomc": dict(h=None, nb=96, entries=news_entries(["FOMC"], True)),
        "news_nfp": dict(h=None, nb=96, entries=news_entries(["NFP"], True)),
        "news_ipc": dict(h=None, nb=96, entries=news_entries(["CPI"], False)),
    }
    # momentum EE.UU. sin filtro de tendencia
    base_fn = asia_side(0.5)

    def any_trend(d, k, T, O, idx, D):
        s = D.at[d, "s"]; D.at[d, "s"] = 2
        r = base_fn(d, k, T, O, idx, D); D.at[d, "s"] = s
        return r
    specs["ny_mom_05_todas"] = dict(h=15, nb=24, fn=any_trend)
    R = {}
    for name, sp in specs.items():
        fp = os.path.join(RESULTS, f"broker_r2_{name}.pkl")
        if os.path.exists(fp):
            R[name] = pd.read_pickle(fp)
        else:
            R[name] = build(name, sp.get("h"), sp["nb"], sp.get("fn"), entries=sp.get("entries"))
            R[name].to_pickle(fp)
    rows = []
    W = {}
    for name, x in R.items():
        for sc in ("atr15", "atrd", "har"):
            if name == "bigone":
                w = pd.concat([wf_by_scale(g, sc).assign(w={2: 1.0, 0: .5, -2: .5}[s]) for s, g in x.groupby("state") if s in (2, 0, -2)])
            else:
                w = wf_by_scale(x, sc).assign(w=1.0)
            W[(name, sc)] = w
            rows.append(dict(regla=name, escala=sc, n=len(w), R=w.r_mult.mean(),
                             **{str(y): w[w.year == y].r_mult.mean() for y in (2024, 2025, 2026)}))
    S = pd.DataFrame(rows)
    print(S.round(3).to_string(index=False))
    # escala elegida TAMBIEN por validacion movil (salida x escala con los 2 años anteriores): sin mirar adelante
    for name, x in R.items():
        if name == "bigone":
            W[(name, "auto")] = pd.concat([walk_forward(g).assign(w={2: 1.0, 0: .5, -2: .5}[s]) for s, g in x.groupby("state") if s in (2, 0, -2)])
        else:
            W[(name, "auto")] = walk_forward(x).assign(w=1.0)
        w = W[(name, "auto")]
        print(f"auto {name:16s} n={len(w):4d} R={w.r_mult.mean():+.3f} por año",
              w.groupby("year").r_mult.mean().round(3).to_dict(), "escalas elegidas", w.groupby("year").chosen.first().str.split("_").str[0].to_dict())
    best = {n: "auto" for n in R}
    # carteras
    bo = W[("bigone", best["bigone"])].copy()
    bo_ev = bo.copy(); bo_ev["w"] = bo_ev.w * np.where(bo_ev.ev == 1, 0.5, 1.0)
    ny = W[("ny_mom_05", best["ny_mom_05"])]
    news = pd.concat([W[(n, best[n])] for n in ("news_fomc", "news_nfp", "news_ipc")])
    out = []
    for label, parts in (("bigone", [bo]), ("bigone_ev50", [bo_ev]), ("bigone_ev50+ny", [bo_ev, ny]),
                         ("bigone_ev50+ny+noticias", [bo_ev, ny, news])):
        T = pd.concat(parts, ignore_index=True)
        for sch in (("fijo", 0.02), ("fijo", 0.03), ("gz", 0.5, 0.06), ("gz", 0.5, 0.08)):
            out.append(dict(cartera=label, esquema=str(sch), ops_mes=len(T) / 34, **account(T, sch)))
    print(pd.DataFrame(out).round(3).to_string(index=False))


if __name__ == "__main__":
    main()
