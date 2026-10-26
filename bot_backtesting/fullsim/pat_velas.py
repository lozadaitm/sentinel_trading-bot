"""Banco de patrones de VELAS (1 a 5 velas, rachas de 3..7) en M15 / M5 / M1 del broker. Solo analisis.

Sigue docs/experimento-2/investigacion/patrones-protocolo-2026-10-26.md al pie de la letra.

Definiciones (vela i = ultima vela del patron, ya CERRADA; A = ATR14 = media simple del rango verdadero
de las 14 velas i-14..i-1, es decir SIN la vela del patron; cuerpo b = |c - o|; rango r = h - l;
mecha sup. = h - max(o, c); mecha inf. = min(o, c) - l). Umbrales fijados a priori, no se tocaron
mirando la mitad B:

  envolvente_alc   i-1 bajista, i alcista, o[i] <= c[i-1], c[i] >= o[i-1], b[i] >= b[i-1], b[i] >= 0,5 A
  martillo (pin_alc) r >= 0,7 A, mecha inf. >= 2 b, mecha inf. >= 0,6 r       (estrella fugaz = espejo)
  doji_tras_subida b <= 0,1 r, r >= 0,3 A y c[i-1] - c[i-5] >= 2 A  (natural: venta; espejo tras bajada)
  interior_rup_alc i-1 dentro de i-2 (h < h, l > l) y c[i] > h[i-2]              (espejo: c[i] < l[i-2])
  exterior_alc     h[i] > h[i-1], l[i] < l[i-1], alcista, b[i] >= 0,5 r
  tres_soldados    3 alcistas seguidas, b >= 0,4 A cada una, cierres crecientes, cierre en el 30 % superior
  estrella_manana  i-2 bajista b >= 0,6 A; i-1 b <= 0,3 A; i alcista b >= 0,6 A y c[i] > punto medio de i-2
  harami_alc       i-1 bajista b >= 0,6 A; i alcista con cuerpo dentro del de i-1 y b[i] <= 0,5 b[i-1]
  pinza_suelo      i-1 bajista, i alcista, |l[i] - l[i-1]| <= 0,1 A, r >= 0,5 A ambas    (techo = espejo)
  rango_amplio_alc r[i] >= 2 A y alcista (natural: seguir = continuacion; al reves = reversion)
  racha_alc_N      la racha de velas alcistas que termina en i mide exactamente N (N = 3..7)
Cada patron tiene un lado «natural» (alcista = compra); «seguir» opera el natural, «reves» el opuesto.

Contextos (16, uno a la vez): todos; hora de entrada asia 01:05-09, londres 09-15, ny 15-20,
tarde 20-23:45; tendencia diaria s = +2 / 0 / -2; tras impulso >= 2 A (|c[i-1] - c[i-6]|) al alza / a la
baja; vela i en maximo / minimo de 20 velas; cerca (<= max(1 A, 0,1 x rango previo)) del maximo / minimo
del dia anterior; volatilidad alta / baja (A / mediana movil de A en 20 dias >= 1,3 / <= 0,77).

Simulacion: entrada a la apertura de la vela i+1 (contigua); sin entradas de 23:45 a 01:05 ni viernes
desde 22:00; el patron no puede contener velas del rollover. Todas las salidas se fuerzan al cierre
de la ultima vela que empieza antes de las 23:45 del mismo dia. ATR de salida = ATR14 incluyendo i.
  E1 objetivo 1 A / freno 1 A (tope 48 velas); E2 objetivo 2 A / freno 1 A (tope 48);
  E3_4 / E3_12 salida por tiempo a 4 / 12 velas (sin freno);
  E4 escalera Big One: tercios con salida a 12 velas, objetivo 2 A y objetivo 3 A; candado a -1 A sobre
     los tercios abiertos (equivale a freno 1 A).
  Freno y objetivo en la misma vela -> freno (M15/M5); en M1 se resuelve con los ticks. Freno con hueco
  -> se llena a la apertura. Costo: M15/M5 max(0,23, spread de la vela + 0,06) $/oz (el spread de la
  vela de MT5 es el minimo de la vela y subestima); M1 spread del primer tick de la vela de entrada + 0,06.
Filtro: mitad A / B cronologica por marco; BH 10 % (p de una cola, hipotesis neto > 0) sobre TODAS las variantes; B neto > 0 y t > 2; años
(M15) o trimestres (M5/M1) positivos >= todos menos uno; n >= 100; bootstrap por semanas y nulo de
entradas al azar en el mismo contexto.
Uso: python -m bot_backtesting.fullsim.pat_velas
"""
import glob
import os
import time as _time

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.econ_intraday import _p, bh

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
TICKS = os.path.join(DATA, "ticks", "XAUUSD+")
COST_OZ = 0.23
COMM = 0.06
H = 48
EXITS = ["E1", "E2", "E3_4", "E3_12", "E4"]
CHUNK = 20000
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 300)


# ----------------------------------------------------------------------------------------- datos
def daily_ctx():
    X = pd.read_pickle(os.path.join(DATA, "broker_m15_full.pkl"))
    day = X.time.values // 86400
    g = pd.DataFrame({"day": day, "h": X.high.values, "l": X.low.values, "c": X.close.values}).groupby("day")
    d = pd.DataFrame({"h": g.h.max(), "l": g.l.min(), "c": g.c.last()})
    d["s"] = (np.sign(d.c - d.c.shift(21)) + np.sign(d.c - d.c.shift(63))).shift(1)
    d["pdh"] = d.h.shift(1); d["pdl"] = d.l.shift(1)
    return d


def load(tf):
    if tf == "M1":
        X = pd.read_pickle(os.path.join(DATA, "broker_m1_ticks.pkl"))
        X["sp"] = X.spread_mean.values
        sec = 60
    else:
        X = pd.read_pickle(os.path.join(DATA, f"broker_{tf.lower()}_full.pkl"))
        X["sp"] = X.spread.values * 0.01
        sec = 900 if tf == "M15" else 300
    return X.sort_values("time").drop_duplicates("time").reset_index(drop=True), sec


# ----------------------------------------------------------------------------------------- salidas
def first(cond):
    has = cond.any(1)
    i = np.argmax(cond, 1)
    i[~has] = 10 ** 6
    return i


def outcomes(o, h, l, c, A, E, Lend, tf):
    """Para cada vela i con entrada valida: resultado bruto ($/oz, en bid) por lado (+1/-1) y salida.
    Devuelve dict[(lado, salida)] -> array y la lista de casos ambiguos (para resolver con ticks en M1)."""
    n = len(o)
    pad = lambda x: np.r_[x, np.full(H + 2, np.nan)]
    hp, lp, op, cp = pad(h), pad(l), pad(o), pad(c)
    out = {(d, x): np.full(n, np.nan) for d in (1, -1) for x in EXITS}
    legs = {(d, k): np.full(n, np.nan) for d in (1, -1) for k in ("t", "2", "3")}
    amb = []          # (i, lado, clave, j_vela, P, nivel_tp, nivel_sl, precio_alternativo_tp)
    idx = np.nonzero(E)[0]
    for s in range(0, len(idx), CHUNK):
        ii = idx[s:s + CHUNK]; e = ii + 1
        win = e[:, None] + np.arange(H)[None, :]
        alive = win <= Lend[e][:, None]
        HW = np.where(alive, hp[win], np.nan); LW = np.where(alive, lp[win], np.nan); OW = op[win]
        P = o[e]; a = A[ii]
        span = Lend[e] - e                      # ultimo desplazamiento permitido
        for d in (1, -1):
            fav = (HW - P[:, None]) if d == 1 else (P[:, None] - LW)
            adv = (P[:, None] - LW) if d == 1 else (HW - P[:, None])
            sl = first(adv >= a[:, None])
            slpx_lvl = P - d * a
            ow_sl = OW[np.arange(len(ii)), np.minimum(sl, H - 1)]
            gap = (sl > 0) & (sl < H) & ((ow_sl - slpx_lvl) * d < 0)
            slpx = np.where(gap, ow_sl, slpx_lvl)
            for N in (4, 12):
                t = np.minimum(N - 1, span)
                out[(d, f"E3_{N}")][ii] = (c[e + t] - P) * d
            for k, T, key in ((1, 48, "E1"), (2, 48, "E2"), (np.inf, 12, "t"), (2, 12, "2"), (3, 12, "3")):
                tp = first(fav >= k * a[:, None]) if np.isfinite(k) else np.full(len(ii), 10 ** 6)
                t = np.minimum(T - 1, span)
                r = (cp[e + t] - P) * d
                hit_tp = (tp <= t) & (tp < sl)
                hit_sl = (sl <= t) & (sl <= tp)
                r = np.where(hit_tp, k * a if np.isfinite(k) else 0, r)
                r = np.where(hit_sl, (slpx - P) * d, r)
                if tf == "M1" and np.isfinite(k):
                    q = np.nonzero(hit_sl & (tp == sl))[0]
                    for z in q:
                        amb.append((ii[z], d, key, e[z] + sl[z], P[z], P[z] + d * k * a[z], P[z] - d * a[z]))
                (out if key in ("E1", "E2") else legs)[(d, key)][ii] = r
    for d in (1, -1):
        out[(d, "E4")] = (legs[(d, "t")] + legs[(d, "2")] + legs[(d, "3")]) / 3
    return out, legs, amb


def resolve_m1(X, out, legs, amb):
    """Una pasada por los ticks: spread del primer tick de cada minuto y orden real objetivo/freno."""
    t0 = _time.time()
    U, SP = [], []
    byday = {}
    for z in amb:
        byday.setdefault(int(X.time.values[z[3]] // 86400), []).append(z)
    fixed = 0
    for f in sorted(glob.glob(os.path.join(TICKS, "*.pkl.gz"))):
        T = pd.read_pickle(f)
        if not len(T):
            continue
        mins = (T.time_msc.values // 60000) * 60
        sp = T.ask.values - T.bid.values
        u, fi = np.unique(mins, return_index=True)
        U.append(u); SP.append(sp[fi])
        dkey = int(mins[0] // 86400)
        for (i, d, key, j, P, lvl_tp, lvl_sl) in byday.get(dkey, []):
            tm = X.time.values[j]
            a0 = np.searchsorted(mins, tm); a1 = np.searchsorted(mins, tm + 60)
            b = T.bid.values[a0:a1]
            if not len(b):
                continue
            itp = np.nonzero((b - lvl_tp) * d >= 0)[0]; isl = np.nonzero((b - lvl_sl) * d <= 0)[0]
            if len(itp) and (not len(isl) or itp[0] < isl[0]):
                k = abs(lvl_tp - P)
                if key in ("E1", "E2"):
                    out[(d, key)][i] = k
                else:
                    legs[(d, key)][i] = k
                fixed += 1
    for d in (1, -1):
        out[(d, "E4")] = (legs[(d, "t")] + legs[(d, "2")] + legs[(d, "3")]) / 3
    print(f"  M1 ticks: {len(amb)} casos objetivo+freno en el mismo minuto, {fixed} resueltos a favor del objetivo "
          f"({_time.time() - t0:.0f} s)", flush=True)
    fs = pd.Series(np.concatenate(SP), index=np.concatenate(U))
    return fs[~fs.index.duplicated()].reindex(X.time.values).values


# ----------------------------------------------------------------------------------------- patrones
def patterns(o, h, l, c, Ap):
    up = c > o; dn = c < o
    b = np.abs(c - o); r = h - l
    uw = h - np.maximum(o, c); lw = np.minimum(o, c) - l
    S = lambda x, k: np.r_[np.full(k, np.nan if x.dtype.kind == "f" else False), x[:-k]]
    o1, h1, l1, c1, b1, r1, up1, dn1 = S(o, 1), S(h, 1), S(l, 1), S(c, 1), S(b, 1), S(r, 1), S(up, 1), S(dn, 1)
    o2, h2, l2, c2, b2, up2, dn2 = S(o, 2), S(h, 2), S(l, 2), S(c, 2), S(b, 2), S(up, 2), S(dn, 2)
    c5 = S(c, 5)
    P = {}  # nombre -> (mascara, lado natural, velas usadas)
    P["envolvente_alc"] = (dn1 & up & (o <= c1) & (c >= o1) & (b >= b1) & (b >= 0.5 * Ap), 1, 2)
    P["envolvente_baj"] = (up1 & dn & (o >= c1) & (c <= o1) & (b >= b1) & (b >= 0.5 * Ap), -1, 2)
    P["martillo_pin_alc"] = ((r >= 0.7 * Ap) & (lw >= 2 * b) & (lw >= 0.6 * r), 1, 1)
    P["estrella_fugaz_pin_baj"] = ((r >= 0.7 * Ap) & (uw >= 2 * b) & (uw >= 0.6 * r), -1, 1)
    doji = (b <= 0.1 * r) & (r >= 0.3 * Ap)
    P["doji_tras_subida"] = (doji & (c1 - c5 >= 2 * Ap), -1, 6)
    P["doji_tras_bajada"] = (doji & (c5 - c1 >= 2 * Ap), 1, 6)
    ins = (h1 < h2) & (l1 > l2)
    P["interior_ruptura_alc"] = (ins & (c > h2), 1, 3)
    P["interior_ruptura_baj"] = (ins & (c < l2), -1, 3)
    outs = (h > h1) & (l < l1) & (b >= 0.5 * r)
    P["exterior_alc"] = (outs & up, 1, 2)
    P["exterior_baj"] = (outs & dn, -1, 2)
    big = b >= 0.4 * Ap
    topc = (c - l) >= 0.7 * r; botc = (h - c) >= 0.7 * r
    P["tres_soldados"] = (up & up1 & up2 & big & S(big, 1) & S(big, 2) & (c > c1) & (c1 > c2) & topc & S(topc, 1) & S(topc, 2), 1, 3)
    P["tres_cuervos"] = (dn & dn1 & dn2 & big & S(big, 1) & S(big, 2) & (c < c1) & (c1 < c2) & botc & S(botc, 1) & S(botc, 2), -1, 3)
    P["estrella_manana"] = (dn2 & (b2 >= 0.6 * Ap) & (b1 <= 0.3 * Ap) & up & (b >= 0.6 * Ap) & (c > (o2 + c2) / 2), 1, 3)
    P["estrella_tarde"] = (up2 & (b2 >= 0.6 * Ap) & (b1 <= 0.3 * Ap) & dn & (b >= 0.6 * Ap) & (c < (o2 + c2) / 2), -1, 3)
    P["harami_alc"] = (dn1 & (b1 >= 0.6 * Ap) & up & (o >= c1) & (c <= o1) & (b <= 0.5 * b1), 1, 2)
    P["harami_baj"] = (up1 & (b1 >= 0.6 * Ap) & dn & (o <= c1) & (c >= o1) & (b <= 0.5 * b1), -1, 2)
    P["pinza_suelo"] = (dn1 & up & (np.abs(l - l1) <= 0.1 * Ap) & (r >= 0.5 * Ap) & (r1 >= 0.5 * Ap), 1, 2)
    P["pinza_techo"] = (up1 & dn & (np.abs(h - h1) <= 0.1 * Ap) & (r >= 0.5 * Ap) & (r1 >= 0.5 * Ap), -1, 2)
    P["rango_amplio_alc"] = ((r >= 2 * Ap) & up, 1, 1)
    P["rango_amplio_baj"] = ((r >= 2 * Ap) & dn, -1, 1)
    su = np.zeros(len(c), int); sd = np.zeros(len(c), int)
    for i in range(len(c)):
        su[i] = su[i - 1] + 1 if up[i] else 0
        sd[i] = sd[i - 1] + 1 if dn[i] else 0
    for N in range(3, 8):
        P[f"racha_alc_{N}"] = (su == N, 1, N)
        P[f"racha_baj_{N}"] = (sd == N, -1, N)
    return {k: (np.nan_to_num(m, nan=0).astype(bool), d, L) for k, (m, d, L) in P.items()}


# ----------------------------------------------------------------------------------------- marco
def frame(tf, D):
    t0 = _time.time()
    X, sec = load(tf)
    o, h, l, c = (X[k].values.astype(float) for k in ("open", "high", "low", "close"))
    tm = X.time.values.astype(np.int64); n = len(X)
    tod = tm % 86400; day = tm // 86400; dow = (day + 3) % 7
    pc = np.r_[np.nan, c[:-1]]
    tr = np.nanmax(np.c_[h - l, np.abs(h - pc), np.abs(l - pc)], 1)
    A = pd.Series(tr).rolling(14).mean().values              # incluye la vela i (para salidas)
    Ap = np.r_[np.nan, A[:-1]]                                # sin la vela i (para definir patrones)
    roll = (tod < 3900) | (tod >= 85500)
    rollc = np.cumsum(roll)
    contig = np.r_[False, np.diff(tm) == sec]
    contc = np.cumsum(~contig)                                # cuenta de cortes
    # ultimo indice del mismo dia con apertura antes de las 23:45
    lastok = pd.Series(np.where(tod < 85500, np.arange(n), -1)).groupby(day).transform("max").values
    e_tod = np.r_[tod[1:], -1]; e_ok = np.r_[contig[1:], False]
    E = e_ok & (e_tod >= 3900) & (e_tod < 85500) & ~((np.r_[dow[1:], -1] == 4) & (e_tod >= 79200)) & (A > 0) & (Ap > 0)
    E &= np.r_[lastok[1:], -1] >= np.r_[np.arange(1, n), n]
    out, legs, amb = outcomes(o, h, l, c, A, E, lastok, tf)
    if tf == "M1":
        fsp = resolve_m1(X, out, legs, amb)
        sp_e = np.r_[fsp[1:], np.nan]; sp_e = np.where(np.isnan(sp_e), np.r_[X.sp.values[1:], np.nan], sp_e)
        cost = sp_e + COMM
    else:
        cost = np.maximum(COST_OZ, np.r_[X.sp.values[1:], np.nan] + COMM)
    net = {kk: v - cost for kk, v in out.items()}
    # contexto
    eh = e_tod / 3600
    Dd = D.reindex(day)
    s = Dd.s.values; pdh = Dd.pdh.values; pdl = Dd.pdl.values; prng = pdh - pdl
    near = np.maximum(A, 0.1 * prng)
    c1, c6 = np.r_[np.nan, c[:-1]], np.r_[np.full(6, np.nan), c[:-6]]
    hi20 = pd.Series(h).rolling(20).max().values; lo20 = pd.Series(l).rolling(20).min().values
    bars_day = {"M15": 92, "M5": 276, "M1": 1380}[tf]
    vr = Ap / pd.Series(Ap).rolling(20 * bars_day, min_periods=5 * bars_day).median().values
    ctx = {"todos": np.ones(n, bool),
           "h_asia": (eh >= 1) & (eh < 9), "h_londres": (eh >= 9) & (eh < 15), "h_ny": (eh >= 15) & (eh < 20), "h_tarde": eh >= 20,
           "tend+2": s == 2, "tend0": s == 0, "tend-2": s == -2,
           "tras_imp_sube": (c1 - c6) >= 2 * Ap, "tras_imp_baja": (c6 - c1) >= 2 * Ap,
           "en_max20": h >= hi20, "en_min20": l <= lo20,
           "cerca_max_ayer": np.abs(c - pdh) <= near, "cerca_min_ayer": np.abs(c - pdl) <= near,
           "vol_alta": vr >= 1.3, "vol_baja": vr <= 0.77}
    Pt = patterns(o, h, l, c, Ap)
    half = tm[E].min() + (tm[E].max() - tm[E].min()) / 2
    isA = tm < half
    per = pd.to_datetime(tm, unit="s")
    per = per.year.values if tf == "M15" else (per.year.values * 10 + per.quarter.values)
    week = (day + 3) // 7
    rows, keep = [], {}
    for pn, (pm, nat, L) in Pt.items():
        clean = np.r_[np.zeros(L, bool), (rollc[L:] - rollc[:-L]) == 0] & np.r_[np.zeros(L, bool), (contc[L:] - contc[:-L]) == 0]
        base = pm & E & clean
        for cn, cm in ctx.items():
            ii = np.nonzero(base & cm)[0]
            for lado, sgn in (("seguir", 1), ("reves", -1)):
                d = nat * sgn
                for x in EXITS:
                    v = net[(d, x)][ii]; ok = ~np.isnan(v); jj = ii[ok]; v = v[ok]
                    a, bb = v[isA[jj]], v[~isA[jj]]
                    ra, rb = a / A[jj][isA[jj]], bb / A[jj][~isA[jj]]
                    st = lambda z: (z.mean() / z.std() * np.sqrt(len(z))) if len(z) >= 20 and z.std() > 0 else np.nan
                    rows.append(dict(marco=tf, patron=pn, contexto=cn, lado=lado, salida=x, dir=d,
                                     n_A=len(a), m_A=a.mean() if len(a) else np.nan, R_A=ra.mean() if len(a) else np.nan,
                                     win_A=(a > 0).mean() if len(a) else np.nan, t_A=st(a),
                                     n_B=len(bb), m_B=bb.mean() if len(bb) else np.nan, R_B=rb.mean() if len(bb) else np.nan,
                                     win_B=(bb > 0).mean() if len(bb) else np.nan, t_B=st(bb)))
                    keep[(tf, pn, cn, lado, x)] = jj
    R = pd.DataFrame(rows)
    print(f"{tf}: {n} velas, entradas validas {int(E.sum())}, mitad A hasta {pd.to_datetime(half, unit='s'):%Y-%m-%d}, "
          f"variantes {len(R)} ({_time.time() - t0:.0f} s)", flush=True)
    F = dict(net=net, A=A, isA=isA, per=per, week=week, E=E, ctx=ctx, keep=keep, time=tm)
    return R, F


# ----------------------------------------------------------------------------------------- robustez
def robust(F, key, d, x, rng):
    tf, pn, cn, lado, _ = key
    jj = F["keep"][key]; v = F["net"][(d, x)][jj]
    ys = pd.Series(v).groupby(F["per"][jj]).mean()
    neg = int((ys <= 0).sum())
    bj = jj[~F["isA"][jj]]; vb = F["net"][(d, x)][bj]
    # bootstrap por semanas de la mitad B: P(media <= 0)
    wk = F["week"][bj]; uw = np.unique(wk); groups = [vb[wk == w] for w in uw]
    sums = np.array([g.sum() for g in groups]); cnt = np.array([len(g) for g in groups])
    pick = rng.integers(0, len(uw), (2000, len(uw)))
    bm = sums[pick].sum(1) / cnt[pick].sum(1)
    p_boot = float((bm <= 0).mean())
    # nulo: mismas n entradas al azar en B dentro del mismo contexto (todas las velas validas)
    pool = np.nonzero(F["E"] & F["ctx"][cn] & ~F["isA"])[0]
    pv = F["net"][(d, x)][pool]; pv = pv[~np.isnan(pv)]
    nm = np.array([pv[rng.integers(0, len(pv), len(vb))].mean() for _ in range(2000)])
    p_null = float((nm >= vb.mean()).mean())
    return dict(periodos=len(ys), per_neg=neg, p_boot=p_boot, p_azar=p_null)


def main():
    rng = np.random.default_rng(7)
    D = daily_ctx()
    allR, Fs = [], {}
    for tf in ("M15", "M5", "M1"):
        R, F = frame(tf, D)
        allR.append(R); Fs[tf] = F
    R = pd.concat(allR, ignore_index=True)
    # La hipotesis es «neto > 0»: p de UNA cola (las variantes muy negativas por el costo no deben abrir el
    # umbral de BH). Se reporta tambien la convencion de dos colas de econ_intraday: bh(p 2 colas) & m > 0.
    R["p_A"] = np.where(R.t_A > 0, R.t_A.apply(_p) / 2, 1.0)
    R["bh_A"] = bh(R.p_A.values) & (R.m_A > 0)
    R["bh_A_2c"] = bh(R.t_A.apply(_p).values) & (R.m_A > 0)
    R["B_ok"] = R.bh_A & (R.m_B > 0) & (R.t_B > 2)
    R["B_ok_2c"] = R.bh_A_2c & (R.m_B > 0) & (R.t_B > 2)
    R["n"] = R.n_A + R.n_B
    print(f"\nVARIANTES TOTALES {len(R)} (con n_A >= 20: {int((R.n_A >= 20).sum())})")
    print(f"  BH 10 % una cola en A con neto > 0: {int(R.bh_A.sum())} | y B neto > 0 con t > 2: {int(R.B_ok.sum())}")
    print(f"  convencion dos colas: BH {int(R.bh_A_2c.sum())} | y B: {int(R.B_ok_2c.sum())} (umbral abierto por "
          f"{int(((R.t_A < -2.5) & (R.m_A < 0)).sum())} variantes con t_A < -2,5)")
    v = R[(R.n_A >= 20) & (R.n_B >= 20)]
    fa, fb = (v.t_A > 2).mean(), (v.t_B > 2).mean()
    print(f"  t_A > 2 y t_B > 2 a la vez: {int(((v.t_A > 2) & (v.t_B > 2)).sum())} de {len(v)}; esperado si A y B fueran "
          f"independientes: {fa * fb * len(v):.1f}")
    print(R.groupby("marco").agg(variantes=("patron", "size"), bh=("bh_A", "sum"), B_ok=("B_ok", "sum"),
                                 bh_2c=("bh_A_2c", "sum"), B_ok_2c=("B_ok_2c", "sum")).to_string())
    # robustez para las que pasan BH+B (cualquier convencion) y para las 25 mejores por t_A
    cand = R[R.B_ok | R.B_ok_2c | R.index.isin(R.sort_values("t_A", ascending=False).head(25).index)].copy()
    rb = [robust(Fs[r.marco], (r.marco, r.patron, r.contexto, r.lado, r.salida), r.dir, r.salida, rng) for r in cand.itertuples()]
    cand = pd.concat([cand.reset_index(drop=True), pd.DataFrame(rb)], axis=1)
    rob = (cand.per_neg <= 1) & (cand.n >= 100) & (cand.p_boot < 0.05) & (cand.p_azar < 0.05)
    cand["pasa_todo"] = cand.B_ok & rob
    cand["pasa_todo_2c"] = cand.B_ok_2c & rob
    cols = ["marco", "patron", "contexto", "lado", "salida", "n_A", "m_A", "R_A", "win_A", "t_A", "p_A", "bh_A",
            "n_B", "m_B", "R_B", "win_B", "t_B"]
    print("\nMEJORES 25 EN A (por t_A) y su resultado en B:")
    print(R.sort_values("t_A", ascending=False).head(25)[cols].round(3).to_string(index=False))
    print("\nCANDIDATAS (BH en A + B) Y TOP-25 CON ROBUSTEZ:")
    print(cand[cols + ["periodos", "per_neg", "p_boot", "p_azar", "pasa_todo"]].round(3).to_string(index=False))
    hi = R[(R.n_A >= 50) & (R.win_A >= 0.6) & (R.m_A < 0)].sort_values("win_A", ascending=False)
    print(f"\nACIERTO >= 60 % EN A CON EXPECTATIVA NEGATIVA: {len(hi)} variantes; las 20 de mayor acierto:")
    print(hi.head(20)[cols].round(3).to_string(index=False))
    # correlacion acierto vs expectativa
    v = R[R.n_A >= 50]
    print(f"\ncorrelacion acierto_A vs neto_A (n_A >= 50, {len(v)} variantes): {v.win_A.corr(v.m_A):+.3f}; "
          f"por salida:\n{v.groupby('salida').apply(lambda g: pd.Series(dict(acierto=g.win_A.mean(), neto=g.m_A.mean(), R=g.R_A.mean(), corr=g.win_A.corr(g.m_A)))).round(3).to_string()}")
    print("\nRESUMEN por marco y salida (media sobre variantes con n_A >= 50):")
    print(v.groupby(["marco", "salida"]).agg(variantes=("m_A", "size"), neto_A=("m_A", "mean"), R_A=("R_A", "mean"),
                                             acierto_A=("win_A", "mean"), pos_A=("m_A", lambda z: (z > 0).mean())).round(3).to_string())
    os.makedirs(os.path.join(DATA, "econ"), exist_ok=True)
    R.to_pickle(os.path.join(DATA, "econ", "pat_velas.pkl")); cand.to_pickle(os.path.join(DATA, "econ", "pat_velas_cand.pkl"))
    for r in cand[cand.pasa_todo | cand.pasa_todo_2c].itertuples():
        F = Fs[r.marco]; jj = F["keep"][(r.marco, r.patron, r.contexto, r.lado, r.salida)]
        g = pd.DataFrame({"per": F["per"][jj], "v": F["net"][(r.dir, r.salida)][jj]}).groupby("per").v.agg(["size", "mean"])
        print(f"\n{r.marco} {r.patron} {r.contexto} {r.lado} {r.salida}, neto $/oz por periodo:\n{g.round(3).to_string()}")
    print(f"\nPASAN TODOS LOS FILTROS (BH una cola): {int(cand.pasa_todo.sum())} | con la convencion de dos colas: "
          f"{int(cand.pasa_todo_2c.sum())}")
    print(cand[cand.pasa_todo | cand.pasa_todo_2c][cols + ["bh_A_2c", "per_neg", "p_boot", "p_azar"]].round(4).to_string(index=False))


if __name__ == "__main__":
    main()
