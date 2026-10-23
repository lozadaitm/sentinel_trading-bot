"""Banco de modelos econometricos por aspecto del bot (solo analisis). Train 2021-23 / test 2024-26.

  M1  razon de varianzas (Lo-MacKinlay) por horizonte, sesion, tendencia y volatilidad:
      ¿el oro sigue tendencia o revierte a 15 min / 1 h / 4 h / 1 dia?  -> logica de M5 y Op1
  M2  estacionalidad intradia de la volatilidad (hora de la semana)    -> lote/distancias por hora
  M3  colas de la excursion en contra (cuantiles y cola de Hill)        -> lote maximo sin quemar
  M4  probabilidad de tocar +a antes que -b vs. la del azar             -> geometria TP/cobertura
  M7  oro-plata cointegrados (modelo de correccion de error)            -> prediccion por desvio
  M8  estudio de eventos NFP/IPC/FOMC (volatilidad y deriva por minuto) -> ventanas de bloqueo
Uso: python -m bot_backtesting.fullsim.econ_bank [M1 M2 ...]
"""
import os
import sys

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.entrylab import DATA, _tsmom_state

pd.set_option("display.width", 250); pd.set_option("display.max_rows", 300)
B = pd.read_pickle(os.path.join(DATA, "bars_all.pkl"))
m5 = B["M5"].reset_index(drop=True)
T5 = m5.time.values; C5 = m5.close.values; H5 = m5.high.values; L5 = m5.low.values
lr = np.r_[np.nan, np.diff(np.log(C5))]
gap = np.r_[False, np.diff(T5) != 300]                  # saltos (fin de semana, pausa diaria)
lr[gap] = np.nan
year = pd.to_datetime(T5, unit="s").year.values
hour = (T5 // 3600) % 24
day = T5 // 86400
D = pd.read_pickle(os.path.join(DATA, "econ", "econ_daily2.pkl"))
TR = year <= 2023


def vr(x, q):
    """Razon de varianzas VR(q) y su z robusta a heterocedasticidad (Lo-MacKinlay)."""
    x = x[~np.isnan(x)]; n = len(x); mu = x.mean(); e = x - mu
    s1 = (e ** 2).sum() / n
    cs = np.convolve(x, np.ones(q), "valid") - q * mu
    sq = (cs ** 2).sum() / (n * q)
    v = sq / s1
    th = 0.0
    e2 = e ** 2; den = (e2.sum()) ** 2
    for j in range(1, q):
        dj = (e2[j:] * e2[:-j]).sum() * n / den
        th += (2 * (q - j) / q) ** 2 * dj
    return v, (v - 1) / np.sqrt(th / n)


def M1():
    print("=" * 90, "\nM1 razon de varianzas (VR>1 tendencia, <1 reversion; z robusta)")
    rows = []
    for q, lab in ((3, "15m"), (12, "1h"), (48, "4h"), (288, "1d")):
        for nm, m in (("2021-23", TR), ("2024-26", ~TR)):
            v, zz = vr(lr[m], q); rows.append(dict(horizonte=lab, tramo=nm, VR=v, z=zz))
    print(pd.DataFrame(rows).round(3).pivot(index="horizonte", columns="tramo", values=["VR", "z"]).to_string())
    # por sesion (retornos de 5 min dentro de la sesion, q=12 -> 1 h)
    print("\nVR(1 h) por sesion (hora servidor) y tramo:")
    rows = []
    for nm, hs in (("asia 01-09", range(1, 9)), ("londres 09-15", range(9, 15)), ("NY 15-20", range(15, 20)), ("cierre 20-24", range(20, 24))):
        for tn, m in (("2021-23", TR), ("2024-26", ~TR)):
            x = np.where(np.isin(hour, list(hs)) & m, lr, np.nan)
            # solo bloques contiguos dentro de la sesion: anular retornos fuera
            v, zz = vr(x, 12); rows.append(dict(sesion=nm, tramo=tn, VR=v, z=zz))
    print(pd.DataFrame(rows).round(3).pivot(index="sesion", columns="tramo", values=["VR", "z"]).to_string())
    print("\nVR(1 h) por tendencia diaria y por volatilidad prevista (tercil):")
    st = _tsmom_state(B).reindex(day).values
    q = D.rvhat_3.rank(pct=True).reindex(day).values
    rows = []
    for lab, mm in (("tend +2", st == 2), ("tend 0", st == 0), ("tend -2", st == -2),
                    ("vol baja", q <= 1 / 3), ("vol media", (q > 1 / 3) & (q <= 2 / 3)), ("vol alta", q > 2 / 3)):
        for tn, m in (("2021-23", TR), ("2024-26", ~TR)):
            v, zz = vr(np.where(mm & m, lr, np.nan), 12); rows.append(dict(grupo=lab, tramo=tn, VR=v, z=zz))
    print(pd.DataFrame(rows).round(3).pivot(index="grupo", columns="tramo", values=["VR", "z"]).to_string())


def M2():
    print("=" * 90, "\nM2 volatilidad por hora (|ret 5 min| medio, relativo a la media del dia); estabilidad train/test")
    a = pd.DataFrame({"h": hour, "y": TR, "v": np.abs(lr)}).dropna()
    p = a.groupby(["h", "y"]).v.mean().unstack()
    p = p / p.mean()
    p.columns = ["2024-26", "2021-23"]
    print(p[["2021-23", "2024-26"]].round(2).T.to_string())
    print("correlacion del perfil horario train vs test:", round(p["2021-23"].corr(p["2024-26"]), 3))


def M3():
    print("=" * 90, "\nM3 excursion en contra maxima (en ATR diario previo) por horizonte; entradas cada hora")
    atr_d = (D.h - D.l).rolling(14).mean().shift(1)
    ad = atr_d.reindex(day).values
    rows = []
    idx = np.arange(0, len(T5) - 12 * 24 * 10, 12)
    for hz_h, lab in ((4, "4 h"), (24, "1 dia"), (72, "3 dias"), (120, "5 dias"), (240, "10 dias")):
        n = hz_h * 12
        for side in (1, -1):
            out = []
            for i in idx:
                if np.isnan(ad[i]) or T5[min(i + n, len(T5) - 1)] - T5[i] > hz_h * 3600 * 3:
                    continue
                if side == 1:
                    out.append((C5[i] - L5[i + 1:i + n + 1].min()) / ad[i])
                else:
                    out.append((H5[i + 1:i + n + 1].max() - C5[i]) / ad[i])
            x = np.array(out); xs = np.sort(x)[::-1]; k = max(10, len(x) // 100)
            hill = 1 / np.mean(np.log(xs[:k] / xs[k]))       # indice de cola (mayor = cola mas fina)
            rows.append(dict(horizonte=lab, lado="compra" if side == 1 else "venta", n=len(x),
                             p50=np.quantile(x, .5), p90=np.quantile(x, .9), p99=np.quantile(x, .99),
                             p999=np.quantile(x, .999), maximo=x.max(), cola_hill=hill))
    print(pd.DataFrame(rows).round(2).to_string(index=False))


def M4():
    print("=" * 90, "\nM4 P(tocar +a antes que -b) en ATR M15 vs azar b/(a+b); entradas cada 15 min, max 3 dias")
    m15 = B["M15"]
    from bot_backtesting.fullsim.entrylab import atr
    a15 = atr(m15)
    t15 = m15.time.values
    rng = np.random.default_rng(3)
    pick = rng.choice(np.nonzero(~np.isnan(a15))[0][100:-1000], 20000, replace=False)
    rows = []
    geo = ((1, 1), (1, 2), (1, 3), (2, 1), (3, 1), (0.5, 2.5), (2, 2))
    for side in (1, -1):
        res = {g: [] for g in geo}
        for i in pick:
            k = np.searchsorted(T5, t15[i] + 900); e = C5[k - 1]; s = a15[i]
            hh, ll = H5[k:k + 864], L5[k:k + 864]
            up = (hh - e) if side == 1 else (e - ll)
            dn = (e - ll) if side == 1 else (hh - e)
            for g in geo:
                iu = np.argmax(up >= g[0] * s) if (up >= g[0] * s).any() else 10 ** 9
                idn = np.argmax(dn >= g[1] * s) if (dn >= g[1] * s).any() else 10 ** 9
                if iu == idn == 10 ** 9:
                    continue
                res[g].append((iu < idn, year[k] <= 2023))
        for g in geo:
            x = np.array(res[g])
            for tn, m in (("2021-23", x[:, 1] == 1), ("2024-26", x[:, 1] == 0)):
                rows.append(dict(lado="compra" if side == 1 else "venta", objetivo=g[0], contra=g[1], tramo=tn,
                                 p=x[m, 0].mean(), azar=g[1] / (g[0] + g[1]), n=m.sum()))
    R = pd.DataFrame(rows); R["dif"] = R.p - R.azar
    print(R.round(3).to_string(index=False))


def M7():
    print("=" * 90, "\nM7 oro-plata: desvio de la relacion (cointegracion) y retorno del oro siguiente")
    x = pd.read_pickle(os.path.join(DATA, "cross_xag.pkl")); x["d"] = x.time // 86400
    s = x.groupby("d").close.last().reindex(D.index)
    g, a = np.log(D.c), np.log(s)
    tr = D.year <= 2023
    b = np.polyfit(a[tr].dropna(), g[tr & a.notna()], 1)
    sp = g - (b[0] * a + b[1])
    # estacionariedad: AR(1) del desvio (medio-vida)
    ss = sp.dropna(); rho = np.corrcoef(ss[1:].values, ss[:-1].values)[0, 1]
    print(f"beta={b[0]:.2f}  rho AR1={rho:.4f}  media vida={np.log(.5) / np.log(rho):.0f} dias")
    z = (sp - sp.rolling(60).mean()) / sp.rolling(60).std()
    for h, lab in ((1, "dia siguiente"), (5, "semana")):
        fwd = D.ret[::-1].rolling(h).sum()[::-1].shift(-1)
        for tn, m in (("2021-23", tr), ("2024-26", ~tr)):
            q = pd.qcut(z[m], 5, labels=False)
            print(f"  {lab} {tn}: ret % por quintil de z (bajo->alto):", fwd[m].groupby(q).mean().round(3).tolist(),
                  " corr", round(z[m].corr(fwd[m]), 3))


def M8():
    print("=" * 90, "\nM8 eventos: |ret 5 min| relativo a la misma hora en dias sin evento, de -60 a +240 min")
    E = pd.read_csv(os.path.join(os.path.dirname(__file__), "events_us.csv"))
    off = pd.Series(T5).groupby(day).first()           # no se usa; tiempos via time_utc + offset servidor
    # hora servidor = UTC+2/+3: se busca el minuto con mayor |ret| dentro de +-60 min de la hora UTC+2 y +3
    s = pd.Series(np.abs(lr), index=T5)
    base = pd.DataFrame({"h": hour, "mi": (T5 // 60) % 60, "v": np.abs(lr)}).groupby(["h", "mi"]).v.median()
    rows = []
    for e in E.itertuples():
        t_utc = int(pd.Timestamp(f"{e.date} {e.time_utc}").timestamp())
        best = None
        for o in (7200, 10800):
            t0 = t_utc + o
            if t0 in s.index and t0 + 300 in s.index:
                v = s.get(t0, 0) + s.get(t0 + 300, 0)
                if best is None or v > best[1]:
                    best = (t0, v)
        if best is None:
            continue
        t0 = best[0]
        for k in range(-12, 49):
            tt = t0 + k * 300
            if tt in s.index:
                hh, mi = (tt // 3600) % 24, (tt // 60) % 60
                rows.append((e.event, k * 5, s[tt] / base.get((hh, mi), np.nan)))
    R = pd.DataFrame(rows, columns=["ev", "min", "rel"])
    p = R.groupby(["ev", "min"]).rel.median().unstack(0)
    print(p.loc[[-60, -30, -15, -5, 0, 5, 10, 15, 30, 60, 90, 120, 180, 240]].round(2).to_string())




def D2():
    print("=" * 90, "\nD2 duracion: $/oz bruto de las entradas reales del M5 (m5race) si se cierran a k minutos fijos")
    from bot_backtesting.fullsim.entrylab import RESULTS
    import pickle
    R = pickle.load(open(os.path.join(RESULTS, "m5race_m5_both.pkl"), "rb"))
    X = pd.DataFrame([t for r in R for t in r["trades"]])
    sg = np.where(X.side == "BUY", 1, -1)
    k0 = np.searchsorted(T5, X.open_time.values)
    rows = []
    for k in (1, 2, 3, 6, 12, 24, 48, 96):
        kk = np.minimum(k0 + k, len(T5) - 1)
        g = (C5[kk - 1] - m5.open.values[k0]) * sg
        for tn, m in (("2021-23", X.open_time.values < 1.7e9), ("total", np.ones(len(X), bool))):
            rows.append(dict(minutos=k * 5, tramo=tn, bruto=g[m].mean(), t=g[m].mean() / g[m].std() * np.sqrt(m.sum())))
    print(pd.DataFrame(rows).pivot(index="minutos", columns="tramo", values=["bruto", "t"]).round(3).to_string())
    print("real del bot por motivo de cierre ($/oz neto, minutos medios):")
    X["oz"] = X.net / (X.volume * 100)
    print(X.groupby("close_reason").agg(n=("oz", "size"), neto=("oz", "mean"), minutos=("minutes", "mean")).round(2).to_string())


def C2():
    print("=" * 90, "\nC2 cola de la excursion en contra a 1 y 5 dias, en unidades de volatilidad PREVISTA (HAR) vs ATR diario")
    atr_d = (D.h - D.l).rolling(14).mean().shift(1).reindex(day).values
    har = (D.rvhat_3 / 100 * D.c.shift(1)).reindex(day).values
    q = D.rvhat_3.rank(pct=True).reindex(day).values
    idx = np.arange(0, len(T5) - 12 * 24 * 6, 12)
    for hz_h in (24, 120):
        n = hz_h * 12
        mae = np.array([max(C5[i] - L5[i + 1:i + n + 1].min(), H5[i + 1:i + n + 1].max() - C5[i]) for i in idx])
        for nm, sc in (("ATR diario", atr_d[idx]), ("HAR", har[idx])):
            x = mae / sc; ok = np.isfinite(x)
            print(f"  {hz_h // 24} d, {nm:<10}: p99={np.quantile(x[ok], .99):.2f} p99.9={np.quantile(x[ok], .999):.2f}  "
                  "p99 por tercil de vol prevista:", [round(np.quantile(x[ok & (q[idx] > a) & (q[idx] <= b)], .99), 2) for a, b in ((0, 1/3), (1/3, 2/3), (2/3, 1))])


if __name__ == "__main__":
    which = sys.argv[1:] or ["M1", "M2", "M3", "M4", "M7", "M8", "D2", "C2"]
    for w in which:
        globals()[w]()
