"""Banco de SCALPING sobre ticks reales del broker (rejilla de 5 s, 2026-01 -> 2026-10). Solo analisis.

Ejecucion honesta: se entra en el bloque de 5 s SIGUIENTE a la señal (latencia), comprando al ask y
vendiendo al bid reales de ese bloque, + comision 0,12 $/oz. Tramos: A = ene-may, B = jun-oct 2026.
Se exige ganancia neta > 0 en A y en B (y se informa t). Pruebas:
  SC1 razon de varianzas del mid a 5 s / 1 min / 5 min / 15 min (¿hay algo que no sea ruido?)
  SC2 desequilibrio de ticks (regla del tick) del ultimo minuto -> seguir 5 / 15 min (decil extremo)
  SC3 salto no programado (|ret 1 min| > k x desv. robusta de 60 min, actividad alta) -> seguir / revertir 15-60 min
  SC4 noticia programada (NFP/IPC/FOMC 2026): seguir el movimiento de T-1 a T+2 min, 30/60/120 min
  SC5 numeros redondos (multiplos de 25 $): primer toque del dia tras 30 min a > 5 $ -> rebote o ruptura; placebo +7 $
  SC6 barrida del maximo/minimo de 60 min que vuelve adentro en 2 min -> ir en contra 15 / 30 min
  SC7 estacionalidad por franja de 5 min (aperturas Tokio, Shanghai, Londres, COMEX, NY, fixings LBMA)
  SC8 compresion de rango (15 min en el decil bajo del dia) -> ruptura del rango, 30 min
Uso: python -m bot_backtesting.fullsim.econ_scalp [SC1 ...]
"""
import os
import sys

import numpy as np
import pandas as pd

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
COMM = 0.12
G = pd.read_pickle(os.path.join(DATA, "ticks_5s.pkl"))
T = G.index.values.astype(np.int64); BID = G.bid.values.astype(float); ASK = G.ask.values.astype(float)
MID = (BID + ASK) / 2; N = G.n.values; UP = G.up.values; DN = G.dn.values
SPLIT = pd.Timestamp("2026-06-01").timestamp()
pd.set_option("display.width", 250)


def trade(i_sig, side, hold_blocks):
    """P&L neto $/oz entrando en el bloque siguiente a i_sig y saliendo hold_blocks despues."""
    i0 = np.asarray(i_sig) + 1; i1 = i0 + hold_blocks
    ok = (i1 < len(T)) & (T[np.minimum(i1, len(T) - 1)] - T[np.minimum(i0, len(T) - 1)] <= hold_blocks * 5 + 120)
    i0, i1, side = i0[ok], i1[ok], np.asarray(side)[ok]
    pnl = np.where(side == 1, BID[i1] - ASK[i0], BID[i0] - ASK[i1]) - COMM
    return pd.DataFrame({"t": T[i0], "pnl": pnl, "side": side})


def report(name, D):
    if D.empty:
        print(f"  {name:50s} sin operaciones"); return
    a, b = D[D.t < SPLIT].pnl, D[D.t >= SPLIT].pnl
    f = lambda x: f"{x.mean():+.3f} (t {x.mean() / x.std() * np.sqrt(len(x)):+.1f}, n {len(x)})" if len(x) > 5 else "n<6"
    ok = len(a) > 5 and len(b) > 5 and a.mean() > 0 and b.mean() > 0
    print(f"  {name:50s} A {f(a):28s} B {f(b):28s} {'<-- ambos > 0' if ok else ''}")


def one_min():
    """Serie de 1 minuto (indices de bloque al cierre de cada minuto)."""
    m = (T % 60) == 55
    return np.nonzero(m)[0]


def SC1():
    print("SC1 razon de varianzas del mid (VR>1 tendencia, <1 reversion); por tramo")
    for step, lab in ((1, "5 s"), (12, "1 min"), (60, "5 min")):
        idx = np.arange(0, len(T), step)
        r = np.diff(MID[idx]); gap = np.diff(T[idx]) > step * 5 + 60
        r[gap] = np.nan
        for tn, m in (("A", T[idx][1:] < SPLIT), ("B", T[idx][1:] >= SPLIT)):
            x = r[m]; x = x[~np.isnan(x)]
            for q in (3, 12):
                s1 = x.var(); sq = pd.Series(x).rolling(q).sum().dropna().var() / q
                print(f"   paso {lab:6s} q={q:2d} tramo {tn}: VR={sq / s1:.3f}")


def SC2():
    print("SC2 desequilibrio de ticks del ultimo minuto (decil extremo) -> seguir")
    im = pd.Series(UP - DN).rolling(12).sum().values / np.maximum(1, pd.Series(UP + DN).rolling(12).sum().values)
    idx = one_min(); x = im[idx]
    hi, lo = np.nanquantile(x[T[idx] < SPLIT], [0.9, 0.1])
    for hold in (60, 180):
        sig = idx[(x > hi) | (x < lo)]; side = np.where(im[sig] > 0, 1, -1)
        report(f"seguir desequilibrio, {hold * 5 // 60} min", trade(sig, side, hold))
        report(f"revertir desequilibrio, {hold * 5 // 60} min", trade(sig, -side, hold))


def SC3():
    print("SC3 salto no programado en 1 min -> seguir / revertir")
    idx = one_min(); m1 = MID[idx]; r = np.r_[np.nan, np.diff(m1)]
    sd = pd.Series(np.abs(r)).rolling(60).median().shift(1).values * 1.4826
    act = pd.Series(N).rolling(12).sum().values[idx]; actmed = pd.Series(act).rolling(600).median().shift(1).values
    ev = events_2026()
    near = np.array([np.any(np.abs(ev - t) < 600) for t in T[idx]])
    for k in (4, 6):
        sig_m = (np.abs(r) > k * sd) & (act > 2 * actmed) & ~near
        sig = idx[sig_m]; side = np.sign(r[sig_m]).astype(int)
        for hold in (180, 360, 720):
            report(f"k={k} seguir {hold * 5 // 60} min", trade(sig + 12, side, hold))
            report(f"k={k} revertir {hold * 5 // 60} min", trade(sig + 12, -side, hold))


def events_2026():
    E = pd.read_csv(os.path.join(os.path.dirname(__file__), "events_us.csv"))
    E = E[E.date >= "2026-01-01"]
    out = []
    for e in E.itertuples():
        utc = pd.Timestamp(f"{e.date} {e.time_utc}")
        ny = utc.tz_localize("UTC").tz_convert("America/New_York")
        out.append(int(utc.timestamp()) + (3 if ny.dst().total_seconds() else 2) * 3600)
    return np.array(out)


def SC4():
    print("SC4 noticia programada 2026: seguir el movimiento T-1 min -> T+2 min")
    ev = events_2026()
    i_pre = np.searchsorted(T, ev - 60); i_post = np.searchsorted(T, ev + 120)
    ok = (i_post < len(T)) & (i_pre > 0)
    mv = MID[i_post[ok]] - MID[i_pre[ok]]; sig = i_post[ok][mv != 0]; side = np.sign(mv[mv != 0]).astype(int)
    for hold in (360, 720, 1440):
        report(f"seguir {hold * 5 // 60} min", trade(sig, side, hold))


def SC5():
    print("SC5 numeros redondos (25 $): primer toque del dia tras 30 min lejos (> 5 $)")
    idx = one_min(); m1 = MID[idx]; day = T[idx] // 86400
    for off, lab in ((0, "nivel real"), (7, "placebo +7 $"), (13, "placebo +13 $")):
        rows_b, rows_k = [], []
        lvl = np.round((m1 - off) / 25) * 25 + off
        dist = np.abs(m1 - lvl)
        far = pd.Series(dist > 5).rolling(30).min().shift(1).fillna(0).values.astype(bool)
        touch = (dist < 0.5) & far
        seen = set()
        for j in np.nonzero(touch)[0]:
            key = (day[j], lvl[j])
            if key in seen or j < 31:
                continue
            seen.add(key)
            came_from = np.sign(m1[j - 30] - lvl[j])          # +1: venia de arriba (soporte)
            rows_b.append((idx[j], int(came_from)))            # rebote: volver hacia donde venia
            rows_k.append((idx[j], int(-came_from)))           # ruptura: seguir
        for rows, nm in ((rows_b, "rebote"), (rows_k, "ruptura")):
            if rows:
                s, sd = zip(*rows)
                report(f"{lab:14s} {nm} 15 min", trade(np.array(s), np.array(sd), 180))


def SC6():
    print("SC6 barrida del maximo/minimo de 60 min que vuelve adentro en 2 min -> en contra")
    idx = one_min(); m1 = MID[idx]
    hi = pd.Series(m1).rolling(60).max().shift(3).values; lo = pd.Series(m1).rolling(60).min().shift(3).values
    pk = pd.Series(m1).rolling(3).max().values; tr = pd.Series(m1).rolling(3).min().values
    up = (pk > hi + 0.3) & (m1 < hi); dn = (tr < lo - 0.3) & (m1 > lo)
    sig = np.r_[idx[up], idx[dn]]; side = np.r_[-np.ones(up.sum(), int), np.ones(dn.sum(), int)]
    for hold in (180, 360):
        report(f"barrida -> contra {hold * 5 // 60} min", trade(sig, side, hold))
        report(f"barrida -> a favor {hold * 5 // 60} min", trade(sig, -side, hold))


def SC7():
    print("SC7 franjas de 5 min (hora servidor): las 10 mejores de A y su resultado en B, ambos lados, 15 min")
    i5 = np.nonzero((T % 300) == 0)[0]
    tod = (T[i5] % 86400) // 300
    rows = []
    for side in (1, -1):
        D = trade(i5, np.full(len(i5), side), 180)
        D["tod"] = (D.t % 86400) // 300
        D["tramo"] = np.where(D.t < SPLIT, "A", "B")
        g = D.groupby(["tod", "tramo"]).pnl.agg(["mean", "count", "std"]).unstack()
        g.columns = ["_".join(map(str, c)) for c in g.columns]
        g["side"] = side
        rows.append(g)
    G2 = pd.concat(rows)
    G2["tA"] = G2.mean_A / G2.std_A * np.sqrt(G2.count_A)
    top = G2.sort_values("tA", ascending=False).head(10)
    top.index = [f"{int(i) * 5 // 60:02d}:{int(i) * 5 % 60:02d}" for i in top.index]
    print(top[["side", "mean_A", "tA", "count_A", "mean_B", "count_B"]].round(3).to_string())
    print(f"   franjas probadas: {len(G2)}; con media > 0 en A y B: {int(((G2.mean_A > 0) & (G2.mean_B > 0)).sum())}")


def SC8():
    print("SC8 compresion de rango de 15 min (decil bajo) -> ruptura del rango, 30 min")
    idx = one_min(); m1 = MID[idx]
    hi = pd.Series(m1).rolling(15).max().values; lo = pd.Series(m1).rolling(15).min().values
    rng = hi - lo; q = pd.Series(rng).rolling(1440).quantile(0.1).shift(1).values
    comp = rng < q
    sig, side = [], []
    j = 16
    while j < len(idx) - 1:
        if comp[j - 1] and (m1[j] > hi[j - 1] or m1[j] < lo[j - 1]):
            sig.append(idx[j]); side.append(1 if m1[j] > hi[j - 1] else -1); j += 30
        else:
            j += 1
    report("ruptura tras compresion, a favor 30 min", trade(np.array(sig), np.array(side), 360))
    report("ruptura tras compresion, en contra 30 min", trade(np.array(sig), -np.array(side), 360))


if __name__ == "__main__":
    for w in sys.argv[1:] or ["SC1", "SC2", "SC3", "SC4", "SC5", "SC6", "SC7", "SC8"]:
        globals()[w]()
