"""Modelos econometricos para ENTRADAS INTRADIA nuevas (solo analisis). Train 2021-23 / test 2024-26.
Todo en retorno neto de costo: costo = 0,32 $/oz (spread + comision) convertido a % del precio.

  S1 mapa de estacionalidad: retorno por franja de 15 min (y por dia de la semana y tendencia),
     a 15 min / 1 h / 3 h. Control de falsos positivos: Benjamini-Hochberg sobre train y
     confirmacion obligatoria en test con el mismo signo.
  S2 sesion -> sesion: ¿el retorno de una sesion predice la siguiente? (Asia -> Londres -> NY -> cierre)
     regresion con errores robustos y version de señal (seguir / ir en contra si |ret| > 1 sd).
  S3 deriva previa a eventos (24 h -> 15 min antes de NFP/IPC/FOMC) y deriva posterior (+1 h -> +24 h).
  S4 calendario diario: dia de la semana, cambio de mes, dia previo/posterior a feriado de EE.UU.
  S5 reversion tras movimientos extremos de 1 h condicionada a la volatilidad prevista y a la hora.
Uso: python -m bot_backtesting.fullsim.econ_intraday [S1 S2 S3 S4 S5]
"""
import os
import sys

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.entrylab import DATA, _tsmom_state

pd.set_option("display.width", 250); pd.set_option("display.max_rows", 400)
COST = 0.32
B = pd.read_pickle(os.path.join(DATA, "bars_all.pkl"))
m5 = B["M5"]
D = pd.read_pickle(os.path.join(DATA, "econ", "econ_daily2.pkl"))
day = (m5.time.values // 86400)
slot = (m5.time.values % 86400) // 300
days = np.unique(day)
di = np.searchsorted(days, day)
O = np.full((len(days), 288), np.nan); C = O.copy(); H = O.copy(); L = O.copy()
O[di, slot] = m5.open.values; C[di, slot] = m5.close.values; H[di, slot] = m5.high.values; L[di, slot] = m5.low.values
YEAR = pd.to_datetime(days * 86400, unit="s").year.values
TRD = YEAR <= 2023
DOW = (days + 3) % 7
STATE = _tsmom_state(B).reindex(days).values


def ret_net(k, n, side=1):
    """retorno neto % de entrar en la franja k (apertura) y salir n barras despues (cierre)."""
    e = O[:, k]; x = C[:, k + n - 1] if k + n - 1 < 288 else np.full(len(days), np.nan)
    return ((x - e) * side - COST) / e * 100


def bh(p, q=0.10):
    p = np.asarray(p); n = len(p); o = np.argsort(p); thr = q * np.arange(1, n + 1) / n
    ok = p[o] <= thr; k = np.nonzero(ok)[0].max() + 1 if ok.any() else 0
    out = np.zeros(n, bool); out[o[:k]] = True
    return out


def tstat(x):
    x = x[~np.isnan(x)]
    return (x.mean() / x.std() * np.sqrt(len(x))) if len(x) > 20 else np.nan, len(x)


def _p(t):
    from math import erfc, sqrt
    return erfc(abs(t) / sqrt(2)) if np.isfinite(t) else 1.0


def S1():
    print("=" * 100, "\nS1 estacionalidad por franja de 15 min (neto de costo, % del precio). Se busca |media| que cubra el costo")
    rows = []
    for k in range(12, 288 - 36, 3):                          # franjas de 15 min desde la 01:00
        for n, lab in ((3, "15m"), (12, "1h"), (36, "3h")):
            for grp, mask in [("todos", np.ones(len(days), bool))] + [(f"dow{d}", DOW == d) for d in range(5)] + \
                             [("tend+2", STATE == 2), ("tend0", STATE == 0), ("tend-2", STATE == -2)]:
                for side in (1, -1):
                    r = ret_net(k, n, side)
                    t1, n1 = tstat(r[TRD & mask]); t2, n2 = tstat(r[~TRD & mask])
                    rows.append(dict(hora=f"{k * 5 // 60:02d}:{k * 5 % 60:02d}", hz=lab, grupo=grp, lado=side,
                                     m_tr=np.nanmean(r[TRD & mask]), t_tr=t1, m_te=np.nanmean(r[~TRD & mask]), t_te=t2, n_tr=n1, n_te=n2))
    R = pd.DataFrame(rows)
    R["p_tr"] = R.t_tr.apply(_p)
    R["bh"] = bh(R.p_tr.values) & (R.m_tr > 0)
    R["confirma"] = R.bh & (R.m_te > 0) & (R.t_te > 2)
    print(f"pruebas {len(R)} | pasan BH(10%) en train con neto>0: {R.bh.sum()} | confirman en test (neto>0, t>2): {R.confirma.sum()}")
    print(R[R.bh].sort_values("t_tr", ascending=False).head(40).round(4).to_string(index=False))
    R.to_pickle(os.path.join(DATA, "econ", "s1_seasonality.pkl"))


def S2():
    print("=" * 100, "\nS2 sesion -> sesion (retorno % bruto); señal: seguir/contrariar si |ret previa| > 1 sd (neto de costo)")
    sess = {"asia": (12, 108), "londres": (108, 180), "ny": (180, 240), "cierre": (240, 287)}
    R = {}
    for s, (a, b) in sess.items():
        R[s] = (C[:, b - 1] - O[:, a]) / O[:, a] * 100
    R = pd.DataFrame(R); R["prev_dia"] = pd.Series((C[:, 286] - O[:, 12]) / O[:, 12] * 100).shift(1)
    pairs = [("prev_dia", "asia"), ("asia", "londres"), ("asia", "ny"), ("londres", "ny"), ("asia", "cierre"), ("ny", "cierre"),
             ("londres", "cierre")]
    for x, y in pairs:
        for tn, m in (("2021-23", TRD), ("2024-26", ~TRD)):
            d = R[m][[x, y]].dropna()
            b = np.polyfit(d[x], d[y], 1)[0]; c = d[x].corr(d[y])
            sd = R[TRD][x].std()
            a, bb = sess[y]
            px = O[m, a]
            sig = np.sign(d[x]) * (d[x].abs() > sd)
            net_f = (sig * d[y] - COST / px[d.index - d.index.min()] * 100 * (sig != 0))[sig != 0] if False else None
            g = d[y][d[x].abs() > sd] * np.sign(d[x][d[x].abs() > sd])
            cost_pct = COST / np.nanmean(px) * 100
            print(f"  {x:>8} -> {y:<8} {tn}: beta {b:+.3f} corr {c:+.3f} | seguir tras |{x}|>1sd: n={len(g)} neto {g.mean() - cost_pct:+.4f}% "
                  f"(t {g.mean() / g.std() * np.sqrt(len(g)):+.2f})")


def S3():
    print("=" * 100, "\nS3 deriva alrededor de eventos (% bruto y neto); pre: T-24h -> T-15m; post: T+60m -> T+24h")
    E = pd.read_csv(os.path.join(os.path.dirname(__file__), "events_us.csv"))
    T5 = m5.time.values; Cs = pd.Series(m5.close.values, index=T5)
    rows = []
    for e in E.itertuples():
        t = int(pd.Timestamp(f"{e.date} {e.time_utc}").timestamp())
        # hora servidor: UTC+2 o +3; se usa la que exista en los datos y produzca el mayor salto
        cands = [t + 7200, t + 10800]
        t0 = max(cands, key=lambda z: abs(Cs.get(z + 300, np.nan) - Cs.get(z - 300, np.nan)) if (z + 300 in Cs.index and z - 300 in Cs.index) else -1)
        def px(z):
            i = np.searchsorted(T5, z); return Cs.iloc[min(i, len(Cs) - 1)]
        pre = (px(t0 - 900) - px(t0 - 86400)) / px(t0 - 86400) * 100
        jump = (px(t0 + 3600) - px(t0 - 900)) / px(t0 - 900) * 100
        post = (px(t0 + 86400) - px(t0 + 3600)) / px(t0 + 3600) * 100
        rows.append(dict(ev=e.event, year=int(e.date[:4]), pre=pre, salto=jump, post=post, cost=COST / px(t0) * 100))
    R = pd.DataFrame(rows); R["tr"] = np.where(R.year <= 2023, "2021-23", "2024-26")
    R["post_sigue"] = np.sign(R.salto) * R.post - R.cost
    R["pre_neto_compra"] = R.pre - R.cost
    g = R.groupby(["ev", "tr"]).agg(n=("pre", "size"), pre=("pre", "mean"), pre_t=("pre", lambda x: x.mean() / x.std() * np.sqrt(len(x))),
                                    pre_neto=("pre_neto_compra", "mean"), post_sigue=("post_sigue", "mean"),
                                    post_t=("post_sigue", lambda x: x.mean() / x.std() * np.sqrt(len(x))))
    print(g.round(3).to_string())


def S4():
    print("=" * 100, "\nS4 calendario diario (retorno % cierre a cierre): dia de la semana, cambio de mes")
    d = D.copy()
    dt = pd.to_datetime(d.index.values * 86400, unit="s")
    d["dom"] = dt.day; d["mes_fin"] = dt.is_month_end | (pd.Series(dt).shift(-1).dt.month != dt.month).values
    d["mes_ini"] = pd.Series(dt).dt.month.ne(pd.Series(dt).shift(1).dt.month).values
    d["tr"] = np.where(d.year <= 2023, "2021-23", "2024-26")
    for col in ("dow", "mes_fin", "mes_ini"):
        print(d.groupby([col, "tr"]).ret.agg(["mean", "count", lambda x: x.mean() / x.std() * np.sqrt(len(x))]).round(3).unstack().to_string())


def S5():
    print("=" * 100, "\nS5 tras una hora extrema (|ret 1 h| > k x vol horaria prevista): ¿sigue o revierte la hora siguiente? neto de costo")
    T5 = m5.time.values
    c = m5.close.values; o = m5.open.values
    r1 = np.full(len(c), np.nan); r1[12:] = (c[12:] - c[:-12])
    nxt = np.full(len(c), np.nan); nxt[:-12] = c[12:] - c[:-12]
    sd = pd.Series(np.abs(np.r_[np.nan, np.diff(c)])).rolling(12 * 24 * 5).mean().values * np.sqrt(12) * 1.25
    yr = pd.to_datetime(T5, unit="s").year.values; hh = (T5 // 3600) % 24
    on_hour = (T5 % 3600) == 3300                        # al cierre de cada hora
    for k in (2, 3, 4):
        m = on_hour & (np.abs(r1) > k * sd) & ~np.isnan(nxt)
        for tn, mt in (("2021-23", yr <= 2023), ("2024-26", yr > 2023)):
            x = (np.sign(r1) * nxt)[m & mt]
            print(f"  k={k} {tn}: n={len(x)}  seguir neto {x.mean() - COST:+.3f} $/oz (t {x.mean() / x.std() * np.sqrt(len(x)):+.2f}) | "
                  f"contrariar neto {-x.mean() - COST:+.3f}")
        for hs, lab in ((range(1, 9), "asia"), (range(9, 15), "londres"), (range(15, 20), "ny"), (range(20, 24), "cierre")):
            mm = m & np.isin(hh, list(hs))
            a = (np.sign(r1) * nxt)[mm & (yr <= 2023)]; b = (np.sign(r1) * nxt)[mm & (yr > 2023)]
            if len(a) > 20 and len(b) > 20:
                print(f"       {lab:<8} train {a.mean():+.3f} (n {len(a)})  test {b.mean():+.3f} (n {len(b)})  [bruto $/oz, + = sigue]")


if __name__ == "__main__":
    for w in sys.argv[1:] or ["S2", "S3", "S4", "S5", "S1"]:
        globals()[w]()
