"""Banco de patrones GEOMETRICOS clasicos del oro (XAUUSD+, broker) en M15, M5 y M1. Solo analisis.

Sigue docs/experimento-2/investigacion/patrones-protocolo-2026-10-26.md. Todos los parametros estan
fijados ANTES de mirar resultados (no se ajustan con la mitad B):

  ATR = ATR de Wilder de 14 velas del propio marco.
  Pivotes: (zz) zigzag por ATR, giro >= 1,5 ATR desde el extremo (pivote confirmado en la vela del giro);
           (fr) fractales de k = 3 velas a cada lado (confirmado 3 velas despues), forzados a alternar
           (dos maximos seguidos: se queda el mas alto). Solo se usan pivotes confirmados en velas cerradas.
  V / V inv.: caida (subida) >= X ATR en <= N velas hasta un minimo (maximo) de las ultimas N velas y
           cierre que recupera >= Y % del tramo. Dos juegos: V3 (X=3, N=8, Y=50 %) y V2 (X=2, N=4, Y=60 %).
           ATR medido N velas antes del extremo (antes del tramo).
  W / M:   L1 (pivote) - cuello H (pivote) - L2 (minimo desde H) con |L2-L1| <= 0,5 ATR, cuello >= 1 ATR
           por encima del mayor minimo, >= 2 velas entre puntos; vigente hasta max(20, 3 x ancho L1-H) velas
           desde H. Entrada al cerrar por encima del cuello (M: espejo).
  HCH:     HI (pivote) - N1 - CABEZA - N2 (pivotes) - HD = maximo desde N2; cabeza >= 0,5 ATR sobre ambos
           hombros, |HI-HD| <= 1 ATR, hombros >= 0,5 ATR sobre el cuello; linea de cuello N1-N2 extrapolada;
           vigente hasta max(20, 2 x ancho N1-N2) velas desde N2. Entrada al cerrar bajo el cuello
           (HCH invertido: espejo, compra).
  Triangulo: ultimos 4 pivotes con 2 maximos descendentes y 2 minimos ascendentes (convergente), lineas por
           ellos; ruptura por cierre fuera de la linea superior (compra) o inferior (venta); vigente tantas
           velas como dura el triangulo.
  Bandera: impulso = cierre - minimo de las 6 velas previas >= 2,5 ATR (ultimo bar que lo cumple); luego
           3..15 velas de consolidacion que no retroceden > 50 % del impulso; entrada al cerrar sobre el
           maximo del impulso + bandera (bajista: espejo).
  Compresion: rango de las 12 velas previas <= 2 x ATR(96) medido antes de la caja, y la mitad reciente
           mas estrecha que la anterior; entrada al cerrar fuera de la caja (arriba compra, abajo venta).
  Ruptura falsa: caja de 20 velas con ancho <= 4 ATR; una vela perfora el techo >= 0,1 ATR (por mecha o
           cierre) y en esa vela o en las 3 siguientes cierra de nuevo dentro -> venta (suelo: espejo, compra).

Lados: seguir (direccion clasica del patron) y reves. Contextos: todo; bloque horario de la entrada
(asia 01-10, londres 10-15, nueva_york 15-20, tarde 20-23:45, hora servidor); tendencia diaria
s = +2 / 0 / -2; volatilidad alta / baja (ATR14 / mediana de 500 velas del ATR14 > 1 o <= 1).
Salidas: E1 1 ATR / 1 ATR; E2 2 ATR / 1 ATR (ambas con tope 48 velas); E3 tiempo 4 y 12 velas;
E4 escalera en tercios con freno comun 1 ATR (tercio 1 sale a 12 velas, tercios 2 y 3 a 2 y 3 ATR,
tope 48 velas). Todo se cierra antes de las 23:45 del mismo dia. Objetivo y freno en la misma vela:
freno. Sin entradas 23:45-01:05 ni viernes desde las 22:00.

Ejecucion: M15/M5 entran en la apertura de la vela siguiente, costo = max(0,23; spread de la vela + 0,06)
$/oz (sin ticks). M1 usa los ticks reales: entrada "cierre" = primer tick tras el cierre de la vela senal
(compra al ask, venta al bid) y entrada "toque" = primer tick que cruza el nivel de confirmacion dentro
de la vela (solo patrones con nivel previo); salidas sobre el bid (compras) / ask (ventas) tick a tick,
+ comision 0,06. Una operacion a la vez por (patron, marco, entrada, lado, salida).

Filtro: BH 10 % en A sobre TODAS las variantes; B neto > 0 con t > 2; anos (M15) o trimestres (M5/M1)
positivos >= todos menos uno; n >= 100; y prueba de fechas al azar (entradas a la misma hora del dia en
dias al azar de la misma mitad) + remuestreo por bloques de dias.
Uso: python -m bot_backtesting.fullsim.pat_geometricos   (lanzar con prioridad BelowNormal)
"""
import glob
import os
import sys
import time as _time

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.econ_intraday import _p, bh

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
OUT = os.path.join(HERE, "results")
COMM = 0.06
COST_MIN = 0.23
HMAX = 48
TFSEC = {"M15": 900, "M5": 300, "M1": 60}
EXITS = ("E1", "E2", "E3n4", "E3n12", "E4")
CTXS = ("todo", "h:asia", "h:londres", "h:nueva_york", "h:tarde", "s:+2", "s:0", "s:-2", "vol:alta", "vol:baja")
T_2345 = 23 * 3600 + 45 * 60
T_0105 = 3600 + 5 * 60
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 300); pd.set_option("display.max_columns", 40)


# ----------------------------------------------------------------------------------------- datos
def load(tf):
    if tf == "M1":
        X = pd.read_pickle(os.path.join(DATA, "broker_m1_ticks.pkl")); X["sp"] = X.spread_mean
    else:
        X = pd.read_pickle(os.path.join(DATA, f"broker_{tf.lower()}_full.pkl")); X["sp"] = X.spread * 0.01
    X = X.sort_values("time").drop_duplicates("time").reset_index(drop=True)
    o, h, l, c = (X[k].values.astype(float) for k in ("open", "high", "low", "close"))
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))
    X["atr"] = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().values
    X["atrL"] = pd.Series(tr).rolling(96, min_periods=50).mean().values
    X["vrel"] = X.atr / X.atr.rolling(500, min_periods=100).median()
    X["day"] = X.time // 86400; X["tod"] = X.time % 86400
    d1 = X.groupby("day").close.last()
    st = (np.sign(d1 - d1.shift(21)) + np.sign(d1 - d1.shift(63))).shift(1)
    X["s"] = X.day.map(st).values
    # ultima vela valida (tod < 23:45) del mismo dia
    ok = (X.tod < T_2345).values
    idx = np.where(ok, np.arange(len(X)), -1)
    last = pd.Series(idx).groupby(X.day.values).transform("max").values
    X["lim"] = last
    return X


# ----------------------------------------------------------------------------------------- pivotes
def zigzag(h, l, atr, thr=1.5):
    """Pivotes (idx, precio, tipo +1 max / -1 min, vela de confirmacion)."""
    piv = []; d = 0; ext = h[0]; ei = 0; lo = l[0]; li = 0
    for t in range(1, len(h)):
        a = atr[t]
        if d >= 0:
            if h[t] > ext: ext, ei = h[t], t
            if d == 0 and l[t] < lo: lo, li = l[t], t
        if d <= 0:
            if l[t] < lo: lo, li = l[t], t
            if d == 0 and h[t] > ext: ext, ei = h[t], t
        if d >= 0 and l[t] < ext - thr * a and (d == 1 or ei < t):
            piv.append((ei, ext, 1, t)); d = -1; lo, li = l[t], t
        elif d <= 0 and h[t] > lo + thr * a and (d == -1 or li < t):
            piv.append((li, lo, -1, t)); d = 1; ext, ei = h[t], t
    return piv


def fractals(h, l, k=3):
    n = len(h); piv = []
    for j in range(k, n - k):
        if h[j] > h[j - k:j].max() and h[j] >= h[j + 1:j + k + 1].max():
            piv.append((j, h[j], 1, j + k))
        if l[j] < l[j - k:j].min() and l[j] <= l[j + 1:j + k + 1].min():
            piv.append((j, l[j], -1, j + k))
    piv.sort(key=lambda p: (p[3], p[0]))
    return piv


# ----------------------------------------------------------------------------------------- patrones
def pivot_patterns(X, piv, tag):
    """Niveles armados por vela (conocidos al cierre de t-1). Devuelve {nombre: (dir, lev, inst)}."""
    h, l, n = X.high.values, X.low.values, len(X)
    atr = X.atr.values
    names = [("W", 1), ("M", -1), ("HCHi", 1), ("HCH", -1), ("TRI_up", 1), ("TRI_dn", -1)]
    L = {k: np.full(n, np.nan) for k, _ in names}; I = {k: np.full(n, -1, np.int64) for k, _ in names}
    seq = []; pi = 0; npv = len(piv)
    for t in range(2, n):
        while pi < npv and piv[pi][3] <= t - 1:
            p = piv[pi]; pi += 1
            if seq and seq[-1][2] == p[2]:
                if (p[2] == 1 and p[1] > seq[-1][1]) or (p[2] == -1 and p[1] < seq[-1][1]):
                    seq[-1] = p
            else:
                seq.append(p)
                if len(seq) > 8: seq.pop(0)
        if len(seq) < 4:
            continue
        a = atr[t - 1]
        # ---- W (compra) y M (venta)
        for typ, key in ((1, "W"), (-1, "M")):
            if seq[-1][2] == typ: Hp, L1 = seq[-1], seq[-2]
            else: Hp, L1 = seq[-2], seq[-3]
            hi = Hp[0]
            if t - hi < 3: continue
            w = l[hi + 1:t] if typ == 1 else h[hi + 1:t]
            j = int(np.argmin(w)) if typ == 1 else int(np.argmax(w))
            L2 = w[j]; l2i = hi + 1 + j
            if l2i - hi < 2 or hi - L1[0] < 2: continue
            if abs(L2 - L1[1]) > 0.5 * a: continue
            neck_h = (Hp[1] - max(L1[1], L2)) if typ == 1 else (min(L1[1], L2) - Hp[1])
            if neck_h < 1.0 * a: continue
            if t - hi > max(20, 3 * (hi - L1[0])): continue
            L[key][t] = Hp[1]; I[key][t] = hi
        # ---- HCH (venta, typ maximos) y HCH invertido (compra)
        for typ, key in ((1, "HCH"), (-1, "HCHi")):
            # N2 = ultimo pivote del tipo contrario
            if seq[-1][2] == -typ: k0 = -1
            else: k0 = -2
            if len(seq) < -k0 + 3: continue
            N2, HD_, N1, HI = seq[k0], seq[k0 - 1], seq[k0 - 2], seq[k0 - 3]
            head = HD_
            n2i = N2[0]
            if t - n2i < 3: continue
            w = h[n2i + 1:t] if typ == 1 else l[n2i + 1:t]
            j = int(np.argmax(w)) if typ == 1 else int(np.argmin(w))
            RS = w[j]; rsi = n2i + 1 + j
            if rsi - n2i < 2: continue
            sg = typ
            if sg * (head[1] - (max(HI[1], RS) if sg == 1 else min(HI[1], RS))) < 0.5 * a: continue
            if abs(HI[1] - RS) > 1.0 * a: continue
            sh = min(HI[1], RS) if sg == 1 else max(HI[1], RS)
            nk = max(N1[1], N2[1]) if sg == 1 else min(N1[1], N2[1])
            if sg * (sh - nk) < 0.5 * a: continue
            if t - n2i > max(20, 2 * (n2i - N1[0])): continue
            m = (N2[1] - N1[1]) / (n2i - N1[0])
            L[key][t] = N2[1] + m * (t - n2i); I[key][t] = n2i
        # ---- triangulo convergente
        q = seq[-4:]
        hs = [p for p in q if p[2] == 1]; ls_ = [p for p in q if p[2] == -1]
        if len(hs) == 2 and len(ls_) == 2:
            H1, H2 = hs; L1_, L2_ = ls_
            if H2[1] < H1[1] and L2_[1] > L1_[1] and t - q[-1][0] <= q[-1][0] - q[0][0] and t - q[-1][0] >= 2:
                mu = (H2[1] - H1[1]) / (H2[0] - H1[0]); ml = (L2_[1] - L1_[1]) / (L2_[0] - L1_[0])
                up = H2[1] + mu * (t - H2[0]); lo = L2_[1] + ml * (t - L2_[0])
                if up > lo:
                    L["TRI_up"][t] = up; I["TRI_up"][t] = q[-1][0]
                    L["TRI_dn"][t] = lo; I["TRI_dn"][t] = q[-1][0]
    return {f"{k}_{tag}": (d, L[k], I[k]) for k, d in names}


def other_patterns(X):
    o, h, l, c = (X[k].values for k in ("open", "high", "low", "close"))
    atr, atrL, n = X.atr.values, X.atrL.values, len(X)
    out = {}
    # ---- V y V invertida
    for nm, Xa, N, Y in (("V3", 3.0, 8, 0.5), ("V2", 2.0, 4, 0.6)):
        Lv = np.full(n, np.nan); Iv = np.full(n, -1, np.int64)
        Lt = np.full(n, np.nan); It = np.full(n, -1, np.int64)
        for t in range(2 * N + 2, n):
            w = l[t - N:t]; j = int(np.argmin(w)); Li = t - N + j
            drop = h[Li - N:Li + 1].max() - l[Li]
            if drop >= Xa * atr[Li - N]:
                Lv[t] = l[Li] + Y * drop; Iv[t] = Li
            w = h[t - N:t]; j = int(np.argmax(w)); Hi = t - N + j
            ll = l[Hi - N:Hi + 1]; rise = h[Hi] - ll.min()
            if rise >= Xa * atr[Hi - N]:
                Lt[t] = h[Hi] - Y * rise; It[t] = Hi
        out[nm] = (1, Lv, Iv); out[nm + "inv"] = (-1, Lt, It)
    # ---- banderas
    for d, key in ((1, "BAND_alc"), (-1, "BAND_baj")):
        Lb = np.full(n, np.nan); Ib = np.full(n, -1, np.int64)
        lastj = -10 ** 9
        for t in range(8, n):
            j = t - 1
            if d == 1:
                imp = c[j] - l[j - 6:j + 1].min()
            else:
                imp = h[j - 6:j + 1].max() - c[j]
            if imp >= 2.5 * atr[j]:
                lastj = j; size = imp
                top = h[j - 6:j + 1].max() if d == 1 else l[j - 6:j + 1].min()
                continue
            if lastj < 0: continue
            m = t - lastj - 1          # velas de consolidacion ya cerradas
            if m < 3 or m > 15: continue
            seg_l = l[lastj + 1:t]; seg_h = h[lastj + 1:t]
            if d == 1:
                if seg_l.min() < top - 0.5 * size: lastj = -10 ** 9; continue
                Lb[t] = max(top, seg_h.max())
            else:
                if seg_h.max() > top + 0.5 * size: lastj = -10 ** 9; continue
                Lb[t] = min(top, seg_l.min())
            Ib[t] = lastj
        out[key] = (d, Lb, Ib)
    # ---- compresion
    hm = pd.Series(h).rolling(12).max().shift(1).values; lm = pd.Series(l).rolling(12).min().shift(1).values
    h6a = pd.Series(h).rolling(6).max().shift(7).values; l6a = pd.Series(l).rolling(6).min().shift(7).values
    h6b = pd.Series(h).rolling(6).max().shift(1).values; l6b = pd.Series(l).rolling(6).min().shift(1).values
    aL = np.r_[np.full(13, np.nan), atrL[:-13]]
    okc = ((hm - lm) <= 2.0 * aL) & ((h6b - l6b) < (h6a - l6a))
    ar = np.arange(n)
    out["COMP_up"] = (1, np.where(okc, hm, np.nan), ar.copy())
    out["COMP_dn"] = (-1, np.where(okc, lm, np.nan), ar.copy())
    return out


def fakeouts(X):
    """Senales directas (vela de senal, direccion) de ruptura falsa."""
    h, l, c, atr, n = X.high.values, X.low.values, X.close.values, X.atr.values, len(X)
    top = pd.Series(h).rolling(20).max().shift(1).values; bot = pd.Series(l).rolling(20).min().shift(1).values
    res = {"FALSA_techo": [], "FALSA_suelo": []}
    for side, key in ((1, "FALSA_techo"), (-1, "FALSA_suelo")):
        busy = -1
        for j in range(21, n):
            if not np.isfinite(top[j]) or top[j] - bot[j] > 4 * atr[j - 1] or j <= busy: continue
            if side == 1 and h[j] > top[j] + 0.1 * atr[j - 1]:
                for t in range(j, min(j + 4, n)):
                    if c[t] < top[j]: res[key].append((t, -1, top[j])); break
                busy = j + 3
            if side == -1 and l[j] < bot[j] - 0.1 * atr[j - 1]:
                for t in range(j, min(j + 4, n)):
                    if c[t] > bot[j]: res[key].append((t, 1, bot[j])); break
                busy = j + 3
    return res


def signals(X, tf):
    """DataFrame de senales: pat, mode (cierre/toque), t (vela de senal), d (direccion del patron), lev."""
    h, l, c = X.high.values, X.low.values, X.close.values
    cp = np.r_[np.nan, c[:-1]]
    P = {}
    P.update(pivot_patterns(X, zigzag(h, l, X.atr.values, 1.5), "zz"))
    P.update(pivot_patterns(X, fractals(h, l, 3), "fr"))
    P.update(other_patterns(X))
    rows = []
    for nm, (d, lev, inst) in P.items():
        ok = np.isfinite(lev)
        for mode in (("cierre", "toque") if tf == "M1" else ("cierre",)):
            if d == 1:
                cond = (c > lev) if mode == "cierre" else (h > lev)
                cond &= (cp <= lev)
            else:
                cond = (c < lev) if mode == "cierre" else (l < lev)
                cond &= (cp >= lev)
            ts = np.nonzero(ok & cond)[0]
            if not len(ts): continue
            _, first = np.unique(inst[ts], return_index=True)
            ts = np.sort(ts[first])
            rows.append(pd.DataFrame(dict(pat=nm, mode=mode, t=ts, d=d, lev=lev[ts])))
    for nm, lst in fakeouts(X).items():
        if lst:
            A = np.array(lst)
            rows.append(pd.DataFrame(dict(pat=nm, mode="cierre", t=A[:, 0].astype(int), d=A[:, 1].astype(int), lev=A[:, 2])))
    S = pd.concat(rows, ignore_index=True)
    return S


# ----------------------------------------------------------------------------------------- simulacion
def _first(mask):
    any_ = mask.any(1); idx = np.where(any_, mask.argmax(1), 10 ** 6)
    return idx


def sim_bars(X, e, d, a, tf):
    """Entrada a la apertura de la vela e. Devuelve {salida: (pnl $/oz, vela de salida)}."""
    o, h, l, c, sp, lim = (X[k].values for k in ("open", "high", "low", "close", "sp", "lim"))
    n = len(X); K = np.arange(HMAX)
    idx = np.minimum(e[:, None] + K, n - 1)
    end = np.minimum(lim[e], e + HMAX - 1)
    valid = idx <= end[:, None]
    s = d[:, None].astype(float)
    O = o[idx] * s; C = c[idx] * s
    Hh = np.where(s > 0, h[idx], -l[idx]); Ll = np.where(s > 0, l[idx], -h[idx])
    E = o[e] * d
    cost = np.maximum(COST_MIN, sp[e] + COMM)
    lastk = end - e
    res = {}

    def bracket(k_tp, cap):
        capk = np.minimum(lastk, cap - 1)
        vv = valid & (K[None, :] <= capk[:, None])
        SL = E - a; TP = E + k_tp * a if k_tp else None
        isl = _first((Ll <= SL[:, None]) & vv)
        itp = _first((Hh >= TP[:, None]) & vv) if k_tp else np.full(len(e), 10 ** 6)
        r = np.arange(len(e))
        px = C[r, capk].copy(); kk = capk.copy()
        m_tp = itp < isl; m_sl = (isl <= itp) & (isl < 10 ** 6)
        if k_tp: px[m_tp] = TP[m_tp]; kk[m_tp] = itp[m_tp]
        slp = np.minimum(SL, O[r, np.minimum(isl, HMAX - 1)])
        px[m_sl] = slp[m_sl]; kk[m_sl] = isl[m_sl]
        return px - E, e + kk

    p1, x1 = bracket(1, HMAX); res["E1"] = (p1 - cost, x1)
    p2, x2 = bracket(2, HMAX); res["E2"] = (p2 - cost, x2)
    r = np.arange(len(e))
    for N in (4, 12):
        kk = np.minimum(lastk, N - 1)
        res[f"E3n{N}"] = (C[r, kk] - E - cost, e + kk)
    q1, y1 = bracket(0, 12); q2, y2 = bracket(2, HMAX); q3, y3 = bracket(3, HMAX)
    res["E4"] = ((q1 + q2 + q3) / 3 - cost, np.maximum(np.maximum(y1, y2), y3))
    tm = X.time.values
    return {k: (v[0], tm[np.minimum(v[1], n - 1)] + TFSEC[tf]) for k, v in res.items()}


_TCACHE = {}


def ticks_day(day):
    if day in _TCACHE: return _TCACHE[day]
    _TCACHE.clear()
    f = os.path.join(DATA, "ticks", "XAUUSD+", pd.Timestamp(day * 86400, unit="s").strftime("%Y-%m-%d") + ".pkl.gz")
    T = pd.read_pickle(f) if os.path.exists(f) else None
    v = None if T is None or not len(T) else (T.time_msc.values, T.bid.values, T.ask.values)
    _TCACHE[day] = v
    return v


def sim_ticks(X, S):
    """M1 con ticks. S: senales con t, mode, d_trade, a. Devuelve arrays por salida + tiempo de entrada."""
    tm_bar = X.time.values
    n = len(S)
    out = {k: (np.full(n, np.nan), np.full(n, np.nan)) for k in EXITS}
    tent = np.full(n, np.nan)
    order = np.argsort(tm_bar[S.t.values], kind="stable")
    tv, mv, dv, av, lv, pdv = S.t.values, S["mode"].values, S.d_trade.values, S.a.values, S.lev.values, S.d.values
    for ii in order:
        t = tv[ii]; t0 = int(tm_bar[t]); day = t0 // 86400
        TT = ticks_day(day)
        if TT is None: continue
        tms, bid, ask = TT
        if mv[ii] == "cierre":
            i0 = np.searchsorted(tms, (t0 + 60) * 1000)
            if i0 >= len(tms) or tms[i0] >= (t0 + 120) * 1000: continue
        else:
            a0 = np.searchsorted(tms, t0 * 1000); a1 = np.searchsorted(tms, (t0 + 60) * 1000)
            seg = bid[a0:a1]
            hit = np.nonzero(seg > lv[ii])[0] if pdv[ii] == 1 else np.nonzero(seg < lv[ii])[0]
            if not len(hit): continue
            i0 = a0 + hit[0]
        te = tms[i0] // 1000; tod = te % 86400
        if tod < T_0105 or tod >= T_2345 or (((te // 86400) + 3) % 7 == 4 and tod >= 22 * 3600): continue
        capms = min(tms[i0] + HMAX * 60000, (day * 86400 + T_2345 - 60) * 1000)
        i1 = min(np.searchsorted(tms, capms), len(tms) - 1)
        if i1 <= i0: continue
        d = dv[ii]; a = av[ii]
        if d == 1: E = ask[i0]; P = bid[i0:i1 + 1]
        else: E = -bid[i0]; P = -ask[i0:i1 + 1]
        TS = tms[i0:i1 + 1]
        tent[ii] = te

        def brk(k, capm):
            j_cap = min(np.searchsorted(TS, tms[i0] + capm * 60000), len(P) - 1)
            js = np.nonzero(P[:j_cap + 1] <= E - a)[0]; jsl = js[0] if len(js) else 10 ** 9
            if k:
                jt = np.nonzero(P[:j_cap + 1] >= E + k * a)[0]; jtp = jt[0] if len(jt) else 10 ** 9
            else:
                jtp = 10 ** 9
            j = min(jsl, jtp, j_cap)
            return P[j] - E, TS[j] / 1000

        p, x = brk(1, HMAX); out["E1"][0][ii], out["E1"][1][ii] = p - COMM, x
        p, x = brk(2, HMAX); out["E2"][0][ii], out["E2"][1][ii] = p - COMM, x
        for N in (4, 12):
            j = min(np.searchsorted(TS, tms[i0] + N * 60000), len(P) - 1)
            out[f"E3n{N}"][0][ii], out[f"E3n{N}"][1][ii] = P[j] - E - COMM, TS[j] / 1000
        q1, y1 = brk(0, 12); q2, y2 = brk(2, HMAX); q3, y3 = brk(3, HMAX)
        out["E4"][0][ii], out["E4"][1][ii] = (q1 + q2 + q3) / 3 - COMM, max(y1, y2, y3)
    return out, tent


def build_trades(tf):
    t0 = _time.time()
    X = load(tf)
    S = signals(X, tf)
    print(f"[{tf}] {len(X)} velas, {len(S)} senales ({_time.time() - t0:.0f}s)", flush=True)
    n = len(X); tm = X.time.values; tod = X.tod.values
    S = S[S.t < n - 2].reset_index(drop=True)
    rows = []
    for side in ("seguir", "reves"):
        Q = S.copy(); Q["side"] = side; Q["d_trade"] = Q.d * (1 if side == "seguir" else -1)
        if tf == "M1":
            Q["a"] = np.where(Q["mode"] == "cierre", X.atr.values[Q.t], X.atr.values[Q.t - 1])
            res, tent = sim_ticks(X, Q)
            Q["t_in"] = tent
        else:
            e = Q.t.values + 1
            okb = (tm[e] - tm[e - 1] == TFSEC[tf]) & (tod[e] >= T_0105) & (tod[e] < T_2345) & \
                  ~((((tm[e] // 86400) + 3) % 7 == 4) & (tod[e] >= 22 * 3600)) & (e <= X.lim.values[e])
            Q = Q[okb].reset_index(drop=True)
            Q["a"] = X.atr.values[Q.t]
            e = Q.t.values + 1
            res = sim_bars(X, e, Q.d_trade.values, Q.a.values, tf)
            Q["t_in"] = tm[e].astype(float)
        for k in EXITS:
            R = Q[["pat", "mode", "t", "d", "side", "a", "t_in"]].copy()
            R["exit"] = k; R["pnl"] = res[k][0]; R["t_out"] = res[k][1]
            rows.append(R[np.isfinite(R.pnl) & np.isfinite(R.t_in)])
        print(f"[{tf}] simulado lado {side} ({_time.time() - t0:.0f}s)", flush=True)
    T = pd.concat(rows, ignore_index=True)
    T["tf"] = tf; T["R"] = T.pnl / T.a
    T["s"] = X.s.values[T.t]; T["vrel"] = X.vrel.values[T.t]
    hr = (T.t_in.astype(np.int64) % 86400) / 3600
    T["hblk"] = np.select([hr < 10, hr < 15, hr < 20], ["asia", "londres", "nueva_york"], "tarde")
    # una operacion a la vez por grupo
    T = T.sort_values(["pat", "mode", "side", "exit", "t_in"]).reset_index(drop=True)
    keep = np.zeros(len(T), bool)
    for _, g in T.groupby(["pat", "mode", "side", "exit"], sort=False).indices.items():
        ti, to = T.t_in.values[g], T.t_out.values[g]; last = -1
        for j, ix in enumerate(g):
            if ti[j] >= last: keep[ix] = True; last = to[j]
    T = T[keep].reset_index(drop=True)
    mid = (tm[0] + tm[-1]) / 2
    T["A"] = T.t_in < mid
    dt = pd.to_datetime(T.t_in, unit="s")
    T["per"] = dt.dt.year.astype(str) if tf == "M15" else (dt.dt.year.astype(str) + "Q" + dt.dt.quarter.astype(str))
    T["day"] = (T.t_in // 86400).astype(np.int64)
    return T, X


def ctx_mask(T, ctx):
    if ctx == "todo": return np.ones(len(T), bool)
    k, v = ctx.split(":")
    if k == "h": return (T.hblk == v).values
    if k == "s": return (T.s == int(v)).values
    return (T.vrel > 1).values if v == "alta" else (T.vrel <= 1).values


def tst(x):
    if len(x) < 20 or x.std() == 0: return np.nan
    return x.mean() / x.std(ddof=1) * np.sqrt(len(x))


def evaluate(T):
    rows = []
    for (tf, pat, mode, side, ex), g in T.groupby(["tf", "pat", "mode", "side", "exit"]):
        for ctx in CTXS:
            G = g[ctx_mask(g, ctx)]
            a = G[G.A]; b = G[~G.A]
            pa, pb = a.pnl.values, b.pnl.values
            per = G.groupby("per").pnl.sum()
            rows.append(dict(tf=tf, pat=pat, mode=mode, side=side, exit=ex, ctx=ctx,
                             nA=len(pa), mA=pa.mean() if len(pa) else np.nan, RA=a.R.mean() if len(pa) else np.nan,
                             winA=(pa > 0).mean() if len(pa) else np.nan, tA=tst(pa),
                             nB=len(pb), mB=pb.mean() if len(pb) else np.nan, RB=b.R.mean() if len(pb) else np.nan,
                             winB=(pb > 0).mean() if len(pb) else np.nan, tB=tst(pb),
                             per_pos=int((per > 0).sum()), per_n=len(per)))
    V = pd.DataFrame(rows)
    V["pA"] = [(_p(t) if np.isfinite(t) else 1.0) for t in V.tA]
    V["f2_bh"] = bh(V.pA.values, 0.10) & (V.mA > 0)
    V["f3_B"] = (V.mB > 0) & (V.tB > 2)
    V["f4_per"] = V.per_pos >= V.per_n - 1
    V["f5_n"] = (V.nA + V.nB) >= 100
    return V


def random_dates_p(T, X, row, reps=200, seed=7):
    """Prob. de suerte: mismas horas del dia, dias al azar de la misma mitad B, misma salida/lado (solo M15/M5)."""
    rng = np.random.default_rng(seed)
    g = T[(T.tf == row.tf) & (T.pat == row.pat) & (T["mode"] == row["mode"]) & (T.side == row.side) & (T.exit == row.exit)]
    G = g[ctx_mask(g, row.ctx) & ~g.A.values]
    obs = G.pnl.mean()
    if row.tf == "M1":
        return np.nan, obs
    tm = X.time.values; tsec = TFSEC[row.tf]
    days = np.unique(tm[tm >= G.t_in.min()] // 86400)
    tod = (G.t_in.values.astype(np.int64) % 86400)
    d_tr = G.d.values * (1 if row.side == "seguir" else -1)
    ms = []
    for _ in range(reps):
        cand = rng.choice(days, len(G)) * 86400 + tod
        e = np.searchsorted(tm, cand); e = np.clip(e, 1, len(tm) - 2)
        ok = tm[e] == cand
        if ok.sum() < 10: continue
        r = sim_bars(X, e[ok], d_tr[ok], X.atr.values[e[ok] - 1], row.tf)[row.exit][0]
        ms.append(r.mean())
    ms = np.array(ms)
    return (ms >= obs).mean() if len(ms) else np.nan, obs


def block_boot_p(T, row, reps=2000, seed=11):
    """Remuestreo por bloques de dias (mitad B): prob. de media <= 0."""
    rng = np.random.default_rng(seed)
    g = T[(T.tf == row.tf) & (T.pat == row.pat) & (T["mode"] == row["mode"]) & (T.side == row.side) & (T.exit == row.exit)]
    G = g[ctx_mask(g, row.ctx) & ~g.A.values]
    if len(G) < 10: return np.nan
    by = G.groupby("day").pnl.agg(["sum", "size"])
    s, c = by["sum"].values, by["size"].values; k = len(s)
    ms = np.empty(reps)
    for i in range(reps):
        j = rng.integers(0, k, k); ms[i] = s[j].sum() / c[j].sum()
    return (ms <= 0).mean()


def main():
    os.makedirs(OUT, exist_ok=True)
    tfs = sys.argv[1:] or ["M15", "M5", "M1"]
    Ts, Xs = [], {}
    for tf in tfs:
        f = os.path.join(OUT, f"pat_geo_trades_{tf}.pkl")
        T, X = build_trades(tf); T.to_pickle(f); Ts.append(T); Xs[tf] = X
    T = pd.concat(Ts, ignore_index=True)
    V = evaluate(T)
    V.to_pickle(os.path.join(OUT, "pat_geo_variants.pkl"))
    nv = len(V)
    print("=" * 120)
    print(f"VARIANTES PROBADAS: {nv}  (patron x marco x entrada x contexto x salida x lado)")
    print(f"senales/operaciones simuladas: {len(T)}")
    print(f"f2 BH10% en A con neto>0: {V.f2_bh.sum()} | + f3 B neto>0 t>2: {(V.f2_bh & V.f3_B).sum()} | "
          f"+ f4 periodos: {(V.f2_bh & V.f3_B & V.f4_per).sum()} | + f5 n>=100: {(V.f2_bh & V.f3_B & V.f4_per & V.f5_n).sum()}")
    cols = ["tf", "pat", "mode", "side", "exit", "ctx", "nA", "mA", "RA", "winA", "tA", "pA", "nB", "mB", "RB", "winB", "tB", "per_pos", "per_n", "f2_bh", "f3_B", "f4_per", "f5_n"]
    Vq = V[V.nA >= 30]
    top = Vq.sort_values("tA", ascending=False).head(30).copy()
    print("\nMEJORES 30 EN A (por t_A, nA >= 30):"); print(top[cols].round(3).to_string(index=False))
    top_t = top.head(10).copy()
    top_t["boot_pB"] = [block_boot_p(T, r) for _, r in top_t.iterrows()]
    top_t["azar_p"] = [random_dates_p(T, Xs[r.tf], r)[0] if r.tf in Xs else np.nan for _, r in top_t.iterrows()]
    print("\nTop 10 con remuestreo B por dias (p media<=0) y fechas al azar (p azar>=obs):")
    print(top_t[cols[:6] + ["mA", "tA", "mB", "tB", "boot_pB", "azar_p"]].round(3).to_string(index=False))
    P = V[V.f2_bh & V.f3_B]
    if len(P):
        P = P.copy()
        P["boot_pB"] = [block_boot_p(T, r) for _, r in P.iterrows()]
        P["azar_p"] = [random_dates_p(T, Xs[r.tf], r)[0] if r.tf in Xs else np.nan for _, r in P.iterrows()]
        P["f6"] = (P.boot_pB < 0.05) & ((P.azar_p < 0.05) | P.azar_p.isna())
        print("\nPASAN f2+f3 (con f4, f5, f6):"); print(P[cols + ["boot_pB", "azar_p", "f6"]].round(3).to_string(index=False))
        P.to_pickle(os.path.join(OUT, "pat_geo_pass.pkl"))
    # acierto alto con expectativa negativa
    W = Vq[(Vq.winA >= 0.6) & (Vq.mA < 0)].sort_values("winA", ascending=False)
    print(f"\nACIERTO >= 60 % EN A CON EXPECTATIVA NEGATIVA: {len(W)} variantes (nA >= 30); las 15 de mayor acierto:")
    print(W[cols[:6] + ["nA", "winA", "mA", "RA", "winB", "mB"]].head(15).round(3).to_string(index=False))
    # resumen por patron (contexto todo, salida y lado)
    Z = V[(V.ctx == "todo")]
    print("\nRESUMEN contexto 'todo' (neto $/oz A | B):")
    print(Z.pivot_table(index=["tf", "pat", "mode"], columns=["side", "exit"], values="mA").round(2).to_string())
    print(Z.pivot_table(index=["tf", "pat", "mode"], columns=["side", "exit"], values="mB").round(2).to_string())
    print(Z.pivot_table(index=["tf", "pat", "mode"], columns=["side"], values="nA", aggfunc="max").to_string())


if __name__ == "__main__":
    main()
