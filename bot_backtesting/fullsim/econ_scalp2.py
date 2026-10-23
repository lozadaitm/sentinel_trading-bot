"""Banco de SCALPING, ronda 2 (huecos de la ronda 1). Solo analisis. Costo real RAW: comision 0,06 $/oz.

  SC9  ejecucion PASIVA: orden limite de compra/venta a k desv. del promedio de 15 min (se llena si el
       ask/bid la toca en el minuto siguiente); objetivo limite en el promedio; si no, cierre a mercado a 15 min
  SC10 entre mercados al minuto con ticks del broker: ¿el indice del dolar (USDX) o la plata (XAGUSD) se
       adelantan al oro? movimiento > 3 desv. en 1 min -> oro en la direccion implicada, 1/5 min
  SC11 triangulo XAUEUR+ vs XAUUSD+/EURUSD+: desvio del sintetico > costo -> oro hacia el sintetico, 1-5 min
  SC12 aperturas de Londres (10:00) y Nueva York (16:30) con ticks: ruptura del rango de los primeros
       5 min durante los 30 siguientes, a favor y en contra, 30 min
  SC13 modelo lineal honesto (ridge) con todo junto a 1 min: retornos 1/5/15, desequilibrio, spread,
       volatilidad relativa, hora; entrena ene-may, juzga jun-oct; opera el decil extremo, 5 min
  SC14 saltos no programados con historia larga (M5 Dukascopy 2021-2025 lejos del rollover + broker 2025-26):
       |ret 5 min| > k desv. robusta, sin noticia +-15 min -> seguir/revertir 15-30 min
  SC15 subasta LBMA de la mañana (venta 12:20 -> 12:35) y de la tarde (16:55 -> 17:10) con historia 2021-2026
Uso: python -m bot_backtesting.fullsim.econ_scalp2 [SC9 ...]
"""
import glob
import os
import sys

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.econ_scalp import ASK, BID, MID, N, SPLIT, T, DN, UP, events_2026, one_min, report, trade

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
COMM = 0.06


def SC9():
    print("SC9 ejecucion pasiva (ordenes limite) a k desv. del promedio de 15 min")
    idx = one_min(); m1 = MID[idx]
    mu = pd.Series(m1).rolling(15).mean().values; sd = pd.Series(np.diff(np.r_[m1[0], m1])).rolling(60).std().values * np.sqrt(15)
    for k in (1.5, 2.0, 3.0):
        rows = []
        j = 60
        while j < len(idx) - 2:
            for side in (1, -1):
                lim = mu[j] - side * k * sd[j]
                a = idx[j] + 1; b = min(idx[j] + 12, len(T) - 1)
                hit = np.nonzero(ASK[a:b] <= lim)[0] if side == 1 else np.nonzero(BID[a:b] >= lim)[0]
                if not len(hit):
                    continue
                i0 = a + hit[0]; tgt = mu[j]; end = min(i0 + 180, len(T) - 1)
                ex = np.nonzero(BID[i0 + 1:end] >= tgt)[0] if side == 1 else np.nonzero(ASK[i0 + 1:end] <= tgt)[0]
                if len(ex):
                    px_out = tgt
                else:
                    px_out = BID[end] if side == 1 else ASK[end]
                rows.append((T[i0], (px_out - lim) * side - COMM, side))
                j += 15
                break
            j += 1
        D = pd.DataFrame(rows, columns=["t", "pnl", "side"])
        report(f"limite a {k} desv., objetivo el promedio", D)


def _load_ticks(sym):
    files = sorted(glob.glob(os.path.join(DATA, "ticks", sym, "*.pkl.gz")))
    if not files:
        return None
    parts = []
    for fp in files:
        X = pd.read_pickle(fp)
        t = X.time_msc.values // 1000 // 60 * 60
        g = pd.DataFrame({"t": t, "mid": (X.bid.values + X.ask.values) / 2}).groupby("t").mid.last()
        parts.append(g)
    return pd.concat(parts)


def SC10():
    print("SC10 entre mercados al minuto (ticks del broker)")
    idx = one_min(); tm = T[idx] - 55; m1 = pd.Series(MID[idx], index=tm)
    for sym, sign in (("USDX", -1), ("XAGUSD", 1)):
        s = _load_ticks(sym)
        if s is None:
            print(f"  {sym}: sin ticks"); continue
        s = s.reindex(tm).ffill()
        r = s.diff().values
        sd = pd.Series(r).rolling(240).std().shift(1).values
        for k in (3, 5):
            sig_m = np.abs(r) > k * sd
            sig = idx[sig_m]; side = (np.sign(r[sig_m]) * sign).astype(int)
            for hold in (12, 60):
                report(f"{sym} k={k} -> oro {hold * 5 // 60} min", trade(sig, side, hold))


def SC11():
    print("SC11 triangulo XAUEUR+ vs XAUUSD+/EURUSD+ (al minuto)")
    a, b = _load_ticks("XAUEUR+"), _load_ticks("EURUSD+")
    if a is None or b is None:
        print("  sin ticks"); return
    idx = one_min(); tm = T[idx] - 55
    syn = (a.reindex(tm).ffill() * b.reindex(tm).ffill()).values
    dev = syn - MID[idx]                                        # >0: el oro en dolares esta barato frente al sintetico
    for thr in (0.3, 0.5, 1.0):
        m = np.abs(dev) > thr
        sig = idx[m]; side = np.sign(dev[m]).astype(int)
        for hold in (12, 60):
            report(f"desvio > {thr} $ -> oro hacia el sintetico {hold * 5 // 60} min", trade(sig, side, hold))
    print(f"  desvio medio absoluto {np.nanmean(np.abs(dev)):.3f} $, p99 {np.nanquantile(np.abs(dev), 0.99):.3f} $")


def SC12():
    print("SC12 aperturas (ruptura del rango de 5 min)")
    for h, mi, lab in ((10, 0, "Londres 10:00"), (16, 30, "NY 16:30"), (15, 20, "COMEX 15:20")):
        rows_f, rows_c = [], []
        for d in np.unique(T // 86400):
            t0 = d * 86400 + h * 3600 + mi * 60
            i0 = np.searchsorted(T, t0); i5 = np.searchsorted(T, t0 + 300); i35 = np.searchsorted(T, t0 + 2100)
            if i35 >= len(T) or T[i0] != t0:
                continue
            hi, lo = MID[i0:i5].max(), MID[i0:i5].min()
            seg = MID[i5:i35]
            up = np.nonzero(seg > hi)[0]; dn = np.nonzero(seg < lo)[0]
            if not len(up) and not len(dn):
                continue
            if len(up) and (not len(dn) or up[0] < dn[0]):
                k, s = i5 + up[0], 1
            else:
                k, s = i5 + dn[0], -1
            rows_f.append((k, s)); rows_c.append((k, -s))
        for rows, nm in ((rows_f, "a favor"), (rows_c, "en contra")):
            if rows:
                ks, ss = zip(*rows)
                report(f"{lab} {nm} 30 min", trade(np.array(ks), np.array(ss), 360))


def SC13():
    print("SC13 modelo lineal honesto a 1 min (entrena ene-may, juzga jun-oct)")
    idx = one_min(); m1 = MID[idx]
    r = lambda k: np.r_[np.full(k, np.nan), m1[k:] - m1[:-k]]
    imb = pd.Series(UP - DN).rolling(12).sum().values[idx] / np.maximum(1, pd.Series(UP + DN).rolling(12).sum().values[idx])
    vol = pd.Series(np.abs(r(1))).rolling(15).mean().values / pd.Series(np.abs(r(1))).rolling(240).mean().values
    sp = (ASK - BID)[idx]; tod = (T[idx] % 86400) / 86400 * 2 * np.pi
    X = np.column_stack([r(1), r(5), r(15), imb, vol, sp, np.sin(tod), np.cos(tod)])
    y = np.r_[m1[5:] - m1[:-5], np.full(5, np.nan)]
    ok = ~np.isnan(X).any(1) & ~np.isnan(y)
    tr = ok & (T[idx] < SPLIT); te = ok & (T[idx] >= SPLIT)
    mu, sdv = X[tr].mean(0), X[tr].std(0)
    Z = (X - mu) / sdv
    b = np.linalg.solve(Z[tr].T @ Z[tr] + 100 * np.eye(Z.shape[1]), Z[tr].T @ y[tr])
    p = Z @ b
    print(f"  correlacion prevista/real: entrenamiento {np.corrcoef(p[tr], y[tr])[0, 1]:+.3f}, prueba {np.corrcoef(p[te], y[te])[0, 1]:+.3f}")
    hi, lo = np.nanquantile(p[tr], [0.99, 0.01])
    m = (p > hi) | (p < lo)
    sig = idx[m & ok]; side = np.where(p[m & ok] > 0, 1, -1)
    report("decil 1 % extremo, 5 min", trade(sig, side, 60))


def _m5_long():
    du = pd.read_pickle(os.path.join(DATA, "cross_xau.pkl"))
    br = pd.read_pickle(os.path.join(DATA, "broker_m5_full.pkl"))
    du = du[du.time < br.time.min()]
    X = pd.concat([du[["time", "open", "high", "low", "close"]], br[["time", "open", "high", "low", "close"]]]).sort_values("time")
    return X.reset_index(drop=True)


def SC14():
    print("SC14 saltos no programados en 5 min, historia 2021-2026 (lejos del rollover)")
    X = _m5_long(); t = X.time.values; c = X.close.values; o = X.open.values
    r = c - o
    sd = pd.Series(np.abs(r)).rolling(288).median().shift(1).values * 1.4826
    E = pd.read_csv(os.path.join(os.path.dirname(__file__), "events_us.csv"))
    ev = []
    for e in E.itertuples():
        utc = pd.Timestamp(f"{e.date} {e.time_utc}"); ny = utc.tz_localize("UTC").tz_convert("America/New_York")
        ev.append(int(utc.timestamp()) + (3 if ny.dst().total_seconds() else 2) * 3600)
    ev = np.sort(np.array(ev))
    j = np.searchsorted(ev, t); near = (np.abs(ev[np.clip(j, 0, len(ev) - 1)] - t) < 900) | (np.abs(ev[np.clip(j - 1, 0, len(ev) - 1)] - t) < 900)
    tod = t % 86400; far_roll = (tod > 1.5 * 3600) & (tod < 23 * 3600)
    yr = pd.to_datetime(t, unit="s").year
    for k in (5, 8):
        m = (np.abs(r) > k * sd) & ~near & far_roll
        for hb in (3, 6):
            ii = np.nonzero(m)[0]; ii = ii[ii + hb + 1 < len(c)]
            fwd = (c[ii + hb] - c[ii]) * np.sign(r[ii]) - 0.17 - COMM      # entra al cierre de la vela del salto
            s = pd.Series(fwd).groupby(yr[ii]).mean().round(2).to_dict()
            print(f"  k={k} seguir {hb * 5} min: n={len(ii)} media {fwd.mean():+.2f} $/oz (t {fwd.mean() / fwd.std() * np.sqrt(len(fwd)):+.2f}) por año {s}")


def SC15():
    print("SC15 subastas LBMA, VENTA, neto 0,17 + 0,06 $/oz, historia 2021-2026 (M5)")
    X = _m5_long().set_index("time")
    for (h0, m0, h1, m1), lab in (((12, 20, 12, 35), "mañana 12:20->12:35"), ((12, 15, 12, 30), "mañana 12:15->12:30"),
                                  ((16, 55, 17, 10), "tarde 16:55->17:10")):
        rows = []
        for t in X.index[(X.index % 86400) == h0 * 3600 + m0 * 60]:
            e = (t // 86400) * 86400 + h1 * 3600 + m1 * 60 - 300
            if e in X.index:
                rows.append((pd.Timestamp(t, unit="s").year, -(X.at[e, "close"] - X.at[t, "open"]) - 0.17 - COMM))
        D = pd.DataFrame(rows, columns=["y", "pnl"])
        print(f"  {lab}: por año", D.groupby("y").pnl.mean().round(2).to_dict(), f"total {D.pnl.mean():+.2f} n {len(D)}")


if __name__ == "__main__":
    for w in sys.argv[1:] or ["SC15", "SC14", "SC12", "SC13", "SC9", "SC10", "SC11"]:
        globals()[w]()
