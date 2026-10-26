"""Banco de patrones, equipo FORMAS: mineria automatica de motivos SIN NOMBRE en M15 / M5 / M1 (solo analisis).

Sigue docs/experimento-2/investigacion/patrones-protocolo-2026-10-26.md.

Formas (decision al CIERRE de la vela i, entrada a la apertura de i+1):
  * km_C   : cierres de las ultimas L velas relativos al cierre de la vela i, / ATR(14) del marco.
             k-means (k = 30) entrenado SOLO con la mitad A.
  * km_OHLC: O, H, L, C de las L velas relativos al cierre de la vela i, / ATR. k-means k = 30 en A.
  * sax3   : la ventana se parte en w = min(L, 4) tramos; simbolo = cambio del tramo / ATR discretizado
             en 3 letras equiprobables (cortes = cuantiles de A). Palabras de hasta 81.
  * sax5   : igual con w = min(L, 3) y 5 letras (hasta 125 palabras).
  * knn    : analogos. Para cada momento, los k (50 / 200) vecinos mas cercanos (forma km_C) dentro de
             la mitad A (en M1 la base A se toma cada 3 minutos); la puntuacion es el neto medio de los vecinos con esa salida y ese lado. Se opera
             si la puntuacion esta en el 20 % / 5 % superior de A y es > 0. En A se excluyen los vecinos
             del mismo dia (sin fuga); en B se usa la base A tal cual (sin reentrenar).
  L = 3, 5, 8, 12, 20 (knn: 5, 12, 20).
Contextos: todos; bloque horario de la entrada (asia 01-08, londres 09-14, eeuu 15-19, cierre 20-23);
  tendencia diaria s = +2 / 0 / -2 (sign(C-C[-21]) + sign(C-C[-63]) diaria del M15, desplazada 1 dia).
Salidas (fijas): E1 TP 1 / SL 1 ATR; E2 TP 2 / SL 1 ATR; E3 tiempo 4 y 12 velas; E4 escalera (tercios:
  tiempo 12 velas / TP 2 ATR / TP 3 ATR, los tres con freno 1 ATR). Horizonte maximo 48 velas; cierre
  forzado antes de las 23:45 o ante un hueco. TP y SL en la misma vela -> freno. Costo = spread de la vela
  de entrada (M15/M5: columna spread x 0,01; M1: spread medio del minuto desde ticks) + 0,06 $/oz.
Filtro: una operacion por racha (solo la primera vela de cada racha del grupo); t con errores agrupados
  por dia; BH 10 % sobre TODAS las variantes en A; B neto > 0 y t > 2; los finalistas se re-simulan de
  forma secuencial (una posicion a la vez) y se exige B neto > 0 con t > 2, periodos positivos (años en
  M15, trimestres en M5/M1) todos menos uno, n >= 100 y bootstrap por dias. M1: re-simulacion con ticks.
Control de permutacion: se desplazan circularmente los retornos futuros (todas las salidas a la vez,
  conserva la autocorrelacion) y se repite TODA la busqueda (formas fijas, knn re-puntuado) PERM veces.
Uso: python -m bot_backtesting.fullsim.pat_formas [PERM]   (correr con prioridad BelowNormal)
"""
import os
import sys
import time as _time

os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")
os.environ.setdefault("MKL_NUM_THREADS", "2")

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.econ_intraday import _p, bh  # noqa: F401

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
OUT = os.path.join(DATA, "econ")
COMM = 0.06
LS = (3, 5, 8, 12, 20)
LS_KNN = (5, 12, 20)
KM_K = 30
HMAX = 48
COLS = [f"{e}_{s}" for e in ("E1", "E2", "E3_4", "E3_12", "E4") for s in ("compra", "venta")]
CTX = ["todos", "asia", "londres", "eeuu", "cierre", "tend+2", "tend0", "tend-2"]
FRAMES = {"M15": ("broker_m15_full.pkl", 900), "M5": ("broker_m5_full.pkl", 300), "M1": ("broker_m1_ticks.pkl", 60)}
MIN_N, MIN_DAYS = 30, 10
T0 = _time.time()


def log(*a):
    print(f"[{_time.time() - T0:7.0f}s]", *a, flush=True)


# ----------------------------------------------------------------------------------------- datos
def trend_by_day():
    X = pd.read_pickle(os.path.join(DATA, "broker_m15_full.pkl")).sort_values("time")
    d1 = pd.Series(X.close.values).groupby(X.time.values // 86400).last()
    return (np.sign(d1 - d1.shift(21)) + np.sign(d1 - d1.shift(63))).shift(1)


def load(fr):
    f, dt = FRAMES[fr]
    X = pd.read_pickle(os.path.join(DATA, f)).sort_values("time").drop_duplicates("time").reset_index(drop=True)
    sp = X.spread.values * 0.01 if "spread" in X else X.spread_mean.values
    return X.time.values.astype(np.int64), X.open.values, X.high.values, X.low.values, X.close.values, sp, dt


def atr14(h, l, c):
    pc = np.r_[np.nan, c[:-1]]
    tr = np.nanmax(np.c_[h - l, np.abs(h - pc), np.abs(l - pc)], axis=1)
    return pd.Series(tr).rolling(14).mean().values


class Frame:
    """Todo lo de un marco: velas, validez, contextos, mitades y resultados de cada salida."""

    def __init__(self, fr, st_day):
        self.fr = fr
        t, o, h, l, c, sp, dt = load(fr)
        self.t, self.o, self.h, self.l, self.c, self.sp, self.dt = t, o, h, l, c, sp, dt
        n = len(t); self.n = n
        self.maxgap = dt if dt >= 300 else 3 * dt
        gap = np.r_[np.inf, np.diff(t)]
        self.gapok = gap <= self.maxgap
        self.atr = atr14(h, l, c)
        day = t // 86400; sod = t % 86400; dow = (day + 3) % 7
        self.day = day
        # entrada en i+1
        nxt = np.r_[np.arange(1, n), n - 1]
        et = t[nxt]; esod = et % 86400; edow = (et // 86400 + 3) % 7
        ok = (np.arange(n) < n - 1) & self.gapok[nxt] & (esod >= 3900) & (esod < 85500) & ~((edow == 4) & (esod >= 79200))
        ok &= np.isfinite(self.atr) & (self.atr > 0) & (et // 86400 == day)
        self.entry_ok = ok
        eh = esod // 3600
        st = pd.Series(st_day).reindex(day).values
        self.ctx = {"todos": np.ones(n, bool), "asia": (eh >= 1) & (eh <= 8), "londres": (eh >= 9) & (eh <= 14),
                    "eeuu": (eh >= 15) & (eh <= 19), "cierre": eh >= 20,
                    "tend+2": st == 2, "tend0": st == 0, "tend-2": st == -2}
        days = np.unique(day)
        self.A = day < np.median(days)
        self.dayi = np.searchsorted(days, day); self.ND = len(days)
        if dt >= 900:
            self.period = pd.to_datetime(t, unit="s").year.values
        else:
            tt = pd.to_datetime(t, unit="s"); self.period = (tt.year * 10 + (tt.month - 1) // 3 + 1).values
        self._outcomes()
        self.valid = self.entry_ok & np.isfinite(self.R[:, 0])

    def _outcomes(self):
        n, t, o, h, l, c, a = self.n, self.t, self.o, self.h, self.l, self.c, self.atr
        J = np.arange(HMAX)
        R = np.full((n, len(COLS)), np.nan, np.float32); EX = np.zeros((n, len(COLS)), np.int16)
        RA = np.full((n, len(COLS)), np.nan, np.float32)
        idx_all = np.nonzero(self.entry_ok)[0]
        for ch in np.array_split(idx_all, max(1, len(idx_all) // 20000)):
            k = np.minimum(ch[:, None] + 1 + J[None, :], n - 1)
            okp = (ch[:, None] + 1 + J[None, :] <= n - 1) & (self.t[k] // 86400 == self.day[ch][:, None]) & (t[k] % 86400 < 85500)
            okp &= np.c_[np.ones(len(ch), bool), self.gapok[k[:, 1:]]]
            okp = np.cumprod(okp, axis=1).astype(bool)
            nv = okp.sum(1); lastj = np.maximum(nv - 1, 0)
            e = o[ch + 1]; A = a[ch]
            Hr = np.where(okp, (h[k] - e[:, None]) / A[:, None], np.nan)
            Lr = np.where(okp, (l[k] - e[:, None]) / A[:, None], np.nan)
            Cr = np.where(okp, (c[k] - e[:, None]) / A[:, None], np.nan)
            rows = np.arange(len(ch))
            cfin = Cr[rows, lastj]

            def first(mask):
                anyh = mask.any(1); j = np.where(anyh, mask.argmax(1), HMAX + 1)
                return j

            def tpsl(side, tp, sl, horizon=HMAX):
                up = Hr if side == 1 else -Lr          # a favor
                dn = -Lr if side == 1 else Hr          # en contra
                cut = J[None, :] < horizon
                jt = first((up >= tp) & cut); js = first((dn >= sl) & cut)
                hz = np.minimum(lastj, horizon - 1)
                g = np.where((js <= jt) & (js <= HMAX), -sl, np.where(jt <= HMAX, tp, side * Cr[rows, hz]))
                ex = np.where((js <= jt) & (js <= HMAX), js, np.where(jt <= HMAX, jt, hz))
                return g, ex

            def timed(side, N):
                hz = np.minimum(lastj, N - 1)
                return side * Cr[rows, hz], hz

            cost = self.sp[ch + 1] + COMM
            col = 0
            for ename in ("E1", "E2", "E3_4", "E3_12", "E4"):
                for side in (1, -1):
                    if ename == "E1":
                        g, ex = tpsl(side, 1.0, 1.0)
                    elif ename == "E2":
                        g, ex = tpsl(side, 2.0, 1.0)
                    elif ename == "E3_4":
                        g, ex = timed(side, 4)
                    elif ename == "E3_12":
                        g, ex = timed(side, 12)
                    else:
                        g1, x1 = tpsl(side, 1e9, 1.0, horizon=12)
                        g2, x2 = tpsl(side, 2.0, 1.0); g3, x3 = tpsl(side, 3.0, 1.0)
                        g = (g1 + g2 + g3) / 3; ex = np.maximum(np.maximum(x1, x2), x3)
                    net = g * A - cost
                    bad = nv == 0
                    R[ch, col] = np.where(bad, np.nan, net); RA[ch, col] = np.where(bad, np.nan, net / A)
                    EX[ch, col] = ex
                    col += 1
        self.R, self.RA, self.EX = R, RA, EX

    # ------------------------------------------------------------------ formas
    def win_ok(self, L):
        bad = (~self.gapok).astype(int)
        s = pd.Series(bad).rolling(L - 1).sum().values if L > 1 else np.zeros(self.n)
        return (s == 0) & np.isfinite(self.atr)

    def feat_C(self, L, rows):
        k = rows[:, None] - (L - 1) + np.arange(L - 1)[None, :]
        return np.clip((self.c[k] - self.c[rows][:, None]) / self.atr[rows][:, None], -12, 12).astype(np.float32)

    def feat_OHLC(self, L, rows):
        k = rows[:, None] - (L - 1) + np.arange(L)[None, :]
        cc = self.c[rows][:, None]; aa = self.atr[rows][:, None]
        parts = [(self.o[k] - cc) / aa, (self.h[k] - cc) / aa, (self.l[k] - cc) / aa, ((self.c[k] - cc) / aa)[:, :-1]]
        return np.clip(np.concatenate(parts, axis=1), -12, 12).astype(np.float32)

    def feat_seg(self, L, w, rows):
        bnd = np.linspace(0, L, w + 1).round().astype(int)
        start = rows - (L - 1)
        out = []
        for s in range(w):
            a0, a1 = bnd[s], bnd[s + 1] - 1
            p0 = self.o[start + a0] if s == 0 else self.c[start + a0 - 1]
            out.append((self.c[start + a1] - p0) / self.atr[rows])
        return np.stack(out, 1)


# ------------------------------------------------------------------------------- k-means (numpy)
def kmeans(X, k, seed=7, iters=40):
    rng = np.random.default_rng(seed)
    S = X[rng.choice(len(X), min(len(X), 40000), replace=False)].astype(np.float64)
    C = [S[rng.integers(len(S))]]
    d2 = ((S - C[0]) ** 2).sum(1)
    for _ in range(k - 1):
        C.append(S[rng.choice(len(S), p=d2 / d2.sum())]); d2 = np.minimum(d2, ((S - C[-1]) ** 2).sum(1))
    C = np.array(C)
    for _ in range(iters):
        lab = assign(S, C)
        Cn = np.array([S[lab == j].mean(0) if (lab == j).any() else C[j] for j in range(k)])
        if np.allclose(Cn, C):
            break
        C = Cn
    return C.astype(np.float32)


def assign(X, C):
    out = np.empty(len(X), np.int32); cc = (C ** 2).sum(1)
    for s in range(0, len(X), 50000):
        x = X[s:s + 50000]
        out[s:s + 50000] = np.argmin(cc[None, :] - 2 * x @ C.T, axis=1)
    return out


# ------------------------------------------------------------------------------------ estadistica
def pval(t):
    """p bilateral normal vectorizado: erfc(|t|/raiz 2) (Numerical Recipes erfcc, error relativo < 1,2e-7)."""
    z = np.abs(np.nan_to_num(np.asarray(t, float))) / np.sqrt(2); u = 1 / (1 + 0.5 * z)
    return u * np.exp(-z * z - 1.26551223 + u * (1.00002368 + u * (0.37409196 + u * (0.09678418 + u * (-0.18628806 + u * (
        0.27886807 + u * (-1.13520398 + u * (1.48851587 + u * (-0.82215223 + u * 0.17087277)))))))))


def gstats(lab, G, sel, R, RA, F, cols):
    """Por grupo y columna: n, media $/oz, media R, acierto, t agrupado por dia, dias."""
    m = np.nonzero(sel & (lab >= 0))[0]
    shape = (G, len(cols))
    if not len(m):
        z = np.zeros(shape)
        return dict(n=z, m=z, mR=z, hit=z, t=z, nd=z)
    g = lab[m].astype(np.int64)
    key = g * F.ND + F.dayi[m]
    uk, inv = np.unique(key, return_inverse=True)
    nd = np.bincount(inv).astype(float); gk = uk // F.ND
    n = np.bincount(gk, nd, G); N2 = np.bincount(gk, nd * nd, G); ndays = np.bincount(gk, None, G)
    Rm = R[m][:, cols].astype(float); RAm = RA[m][:, cols].astype(float)
    res = {k: np.zeros(shape) for k in ("m", "mR", "hit", "t")}
    with np.errstate(invalid="ignore", divide="ignore"):
        for j in range(len(cols)):
            r = Rm[:, j]
            Sd = np.bincount(inv, r)
            S = np.bincount(gk, Sd, G); S2 = np.bincount(gk, Sd * Sd, G); SN = np.bincount(gk, Sd * nd, G)
            mu = S / n
            var = S2 - 2 * mu * SN + mu * mu * N2
            res["m"][:, j] = mu; res["t"][:, j] = mu / (np.sqrt(np.maximum(var, 1e-18)) / n)
            res["hit"][:, j] = np.bincount(g, (r > 0).astype(float), G) / n
            res["mR"][:, j] = np.bincount(g, RAm[:, j], G) / n
    res["n"] = np.repeat(n[:, None], len(cols), 1); res["nd"] = np.repeat(ndays[:, None], len(cols), 1)
    return res


def runstart(lab):
    prev = np.r_[-1, lab[:-1]]
    return (lab >= 0) & (lab != prev)


# --------------------------------------------------------------------------------- busqueda
def labelings(F):
    """Etiquetas de forma por barra (fijas: no dependen de los retornos). Devuelve lista de (metodo, L, G, lab, modelo)."""
    out = []
    for L in LS:
        wok = F.win_ok(L) & (np.arange(F.n) >= L)
        rows = np.nonzero(wok)[0]
        tr = rows[F.A[rows] & F.valid[rows]]
        for name, fn in (("km_C", F.feat_C), ("km_OHLC", F.feat_OHLC)):
            Xa = fn(L, tr); C = kmeans(Xa, KM_K)
            lab = np.full(F.n, -1, np.int32); lab[rows] = assign(fn(L, rows), C)
            out.append((name, L, KM_K, lab, C))
        for name, a, w in (("sax3", 3, min(L, 4)), ("sax5", 5, min(L, 3))):
            S = F.feat_seg(L, w, rows); Sa = F.feat_seg(L, w, tr)
            cuts = [np.quantile(Sa[:, s], np.arange(1, a) / a) for s in range(w)]
            word = np.zeros(len(rows), np.int64)
            for s in range(w):
                word = word * a + np.searchsorted(cuts[s], S[:, s])
            lab = np.full(F.n, -1, np.int32); lab[rows] = word
            out.append((name, L, a ** w, lab, cuts))
        log(F.fr, f"formas L={L} listas")
    return out


def knn_index(F, L, K=200, chunk=256):
    """Vecinos (k=200, ordenados) de cada barra operable dentro de la base A (mismo dia excluido)."""
    wok = F.win_ok(L) & (np.arange(F.n) >= L) & F.valid
    q = np.nonzero(wok)[0]; db = q[F.A[q]]
    if F.dt < 300:
        db = db[::3]                                   # M1: base A cada 3 minutos (costo de computo)
    Xd = F.feat_C(L, db); xx = (Xd ** 2).sum(1); dbday = F.day[db]
    IDX = np.empty((len(q), K), np.int32)
    for s in range(0, len(q), chunk):
        rr = q[s:s + chunk]; Q = F.feat_C(L, rr)
        D = (Q ** 2).sum(1)[:, None] + xx[None, :] - 2 * Q @ Xd.T
        for dd in np.unique(F.day[rr]):
            lo, hi = np.searchsorted(dbday, dd), np.searchsorted(dbday, dd, side="right")
            if hi > lo:
                D[F.day[rr] == dd, lo:hi] = np.inf
        p = np.argpartition(D, K, axis=1)[:, :K]
        o = np.argsort(np.take_along_axis(D, p, 1), axis=1)
        IDX[s:s + chunk] = np.take_along_axis(p, o, 1)
    return q, db, IDX


def knn_scores(R, q, db, IDX):
    """Puntuacion (neto medio de los vecinos) por columna, k = 50 y 200."""
    Rdb = R[db]; V = np.isfinite(Rdb); Rz = np.where(V, Rdb, 0).astype(np.float32)
    S50 = np.full((len(q), len(COLS)), np.nan, np.float32); S200 = S50.copy()
    for s in range(0, len(q), 40000):
        I = IDX[s:s + 40000]
        for c in range(len(COLS)):
            g = Rz[I, c]; v = V[I, c]
            with np.errstate(invalid="ignore", divide="ignore"):
                S50[s:s + 40000, c] = g[:, :50].sum(1) / v[:, :50].sum(1)
                S200[s:s + 40000, c] = g.sum(1) / v.sum(1)
    return S50, S200


def evaluate(F, labs, knn, R, RA, keep_rows):
    """Recorre todas las variantes del marco. Devuelve arrays (pA, mA, mB, tB) y, si keep_rows, filas completas."""
    valid = F.valid & np.isfinite(R[:, 0])
    arrs, rows = [], []
    allc = list(range(len(COLS)))

    def push(meta, G, lab, cols):
        rs = runstart(lab)
        for cx in CTX:
            sel = valid & rs & F.ctx[cx]
            a = gstats(lab, G, sel & F.A, R, RA, F, cols); b = gstats(lab, G, sel & ~F.A, R, RA, F, cols)
            okA = (a["n"] >= MIN_N) & (a["nd"] >= MIN_DAYS) & np.isfinite(a["t"])
            pA = np.where(okA, pval(a["t"]), 1.0)
            arrs.append(np.stack([pA.ravel(), np.nan_to_num(a["m"]).ravel(), np.nan_to_num(b["m"]).ravel(),
                                  np.where(b["n"] >= 5, np.nan_to_num(b["t"]), 0).ravel()], 1))
            if keep_rows:
                gg, cc = np.meshgrid(np.arange(G), cols, indexing="ij")
                df = pd.DataFrame(dict(grupo=gg.ravel(), salida=np.array(COLS)[cc.ravel()],
                                       n_A=a["n"].ravel(), m_A=a["m"].ravel(), R_A=a["mR"].ravel(), hit_A=a["hit"].ravel(),
                                       t_A=a["t"].ravel(), n_B=b["n"].ravel(), m_B=b["m"].ravel(), R_B=b["mR"].ravel(),
                                       hit_B=b["hit"].ravel(), t_B=b["t"].ravel(), p_A=pA.ravel()))
                for k, v in meta.items():
                    df[k] = v
                df["ctx"] = cx
                rows.append(df)

    for name, L, G, lab, _ in labs:
        push(dict(marco=F.fr, metodo=name, L=L, param=""), G, lab, allc)
    for L, (q, db, IDX) in knn.items():
        S50, S200 = knn_scores(R, q, db, IDX)
        qa = F.A[q]
        for kk, S in ((50, S50), (200, S200)):
            for qq in (0.80, 0.95):
                for c in allc:
                    sc = S[:, c]; thr = np.nanquantile(sc[qa], qq)
                    sig = (sc > thr) & (sc > 0)
                    lab = np.full(F.n, -1, np.int32); lab[q[sig]] = 0
                    push(dict(marco=F.fr, metodo="knn", L=L, param=f"k{kk}_q{int(qq * 100)}_{COLS[c]}"), 1, lab, [c])
    A = np.concatenate(arrs)
    return A, (pd.concat(rows, ignore_index=True) if keep_rows else None)


# --------------------------------------------------------------------------- finalistas
def seq_trades(F, bars, col):
    """Una posicion a la vez: toma la barra si la anterior ya salio."""
    out, last = [], -1
    for i in bars:
        if i < last:
            continue
        out.append(i); last = i + 1 + int(F.EX[i, col])
    return np.array(out, int)


def tstat_day(r, d):
    s = pd.Series(r).groupby(d).sum(); nn = pd.Series(np.ones(len(r))).groupby(d).sum()
    n = len(r); mu = r.mean()
    se = np.sqrt(((s - nn * mu) ** 2).sum()) / n
    return mu / se if se > 0 else np.nan


def boot_p(r, d, reps=2000, seed=3):
    """P(media <= 0) remuestreando dias completos (bootstrap por bloques diarios)."""
    if len(r) < 5:
        return np.nan
    s = pd.Series(r).groupby(d).sum().values; nn = pd.Series(np.ones(len(r))).groupby(d).sum().values
    rng = np.random.default_rng(seed); k = rng.integers(0, len(s), (reps, len(s)))
    mu = s[k].sum(1) / nn[k].sum(1)
    return float((mu <= 0).mean())


_TICKS = {}


def ticks_day(day):
    if day not in _TICKS:
        f = os.path.join(DATA, "ticks", "XAUUSD+", pd.to_datetime(day * 86400, unit="s").strftime("%Y-%m-%d") + ".pkl.gz")
        _TICKS.clear()
        _TICKS[day] = pd.read_pickle(f) if os.path.exists(f) else None
    return _TICKS[day]


def tick_trade(F, i, col):
    """Re-simula en ticks una operacion M1: entrada al primer tick de la vela i+1 (ask compra / bid venta)."""
    T = ticks_day(int(F.day[i]))
    if T is None or not len(T):
        return np.nan
    ename, sname = COLS[col].rsplit("_", 1); side = 1 if sname == "compra" else -1
    t0 = int(F.t[i + 1]) * 1000; a = F.atr[i]
    tm = T.time_msc.values; j0 = np.searchsorted(tm, t0)
    end = min(t0 + HMAX * 60000, (int(F.day[i]) * 86400 + 85500) * 1000)
    j1 = np.searchsorted(tm, end)
    if j0 >= j1:
        return np.nan
    bid, ask = T.bid.values[j0:j1], T.ask.values[j0:j1]; tt = tm[j0:j1]
    e = ask[0] if side == 1 else bid[0]
    px = bid if side == 1 else ask                    # precio al que se cierra
    fav = (px - e) * side

    def leg(tp, sl, nmin):
        lim = np.searchsorted(tt, t0 + nmin * 60000)
        lim = max(1, min(lim, len(tt)))
        hit = np.nonzero((fav[:lim] >= tp * a) | (fav[:lim] <= -sl * a))[0]
        return fav[hit[0]] if len(hit) else fav[lim - 1]

    if ename == "E1":
        g = leg(1, 1, HMAX)
    elif ename == "E2":
        g = leg(2, 1, HMAX)
    elif ename == "E3_4":
        g = leg(1e9, 1e9, 4)
    elif ename == "E3_12":
        g = leg(1e9, 1e9, 12)
    else:
        g = (leg(1e9, 1, 12) + leg(2, 1, HMAX) + leg(3, 1, HMAX)) / 3
    return g - COMM


def finalist(F, row, labs, knn_real):
    col = COLS.index(row.salida)
    if row.metodo == "knn":
        q, S50, S200 = knn_real[row.L]
        kk, qq, _ = row.param.split("_", 2); S = S50 if kk == "k50" else S200; qq = int(qq[1:]) / 100
        sc = S[:, col]; thr = np.nanquantile(sc[F.A[q]], qq)
        lab = np.full(F.n, -1, np.int32); lab[q[(sc > thr) & (sc > 0)]] = 0; g = 0
    else:
        lab = next(x[3] for x in labs if x[0] == row.metodo and x[1] == row.L); g = int(row.grupo)
    bars = np.nonzero((lab == g) & F.valid & F.ctx[row.ctx])[0]
    tr = seq_trades(F, bars, col)
    r = F.R[tr, col].astype(float)
    if F.fr == "M1":
        rt = np.array([tick_trade(F, i, col) for i in tr])
        okt = np.isfinite(rt); r = np.where(okt, rt, r)
    A = F.A[tr]; d = F.dayi[tr]
    per = pd.Series(r).groupby(F.period[tr]).mean()
    out = dict(n_seq=len(tr), nA_seq=int(A.sum()), mA_seq=r[A].mean() if A.any() else np.nan,
               tA_seq=tstat_day(r[A], d[A]) if A.sum() > 2 else np.nan,
               nB_seq=int((~A).sum()), mB_seq=r[~A].mean() if (~A).any() else np.nan,
               tB_seq=tstat_day(r[~A], d[~A]) if (~A).sum() > 2 else np.nan,
               hitB_seq=(r[~A] > 0).mean() if (~A).any() else np.nan,
               per_pos=int((per > 0).sum()), per_tot=int(len(per)), bootB=boot_p(r[~A], d[~A]))
    out["pasa_todo"] = bool(out["mB_seq"] > 0 and out["tB_seq"] > 2 and out["per_pos"] >= out["per_tot"] - 1
                            and out["n_seq"] >= 100 and out["bootB"] < 0.05)
    return out


# ------------------------------------------------------------------------------------- main
def main():
    perm = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    st = trend_by_day()
    realA, realRows, permA = [], [], {r: [] for r in range(1, perm + 1)}
    keep = {}
    for fr in (sys.argv[2].split(",") if len(sys.argv) > 2 else ("M15", "M5", "M1")):
        F = Frame(fr, st)
        log(fr, f"velas {F.n}, operables {int(F.valid.sum())}, A {int((F.valid & F.A).sum())}")
        labs = labelings(F)
        knn = {}
        for L in LS_KNN:
            knn[L] = knn_index(F, L); log(fr, f"knn L={L} vecinos listos")
        Aarr, rows = evaluate(F, labs, knn, F.R, F.RA, True)
        realA.append(Aarr); realRows.append(rows); log(fr, f"variantes {len(Aarr)}")
        rng = np.random.default_rng({"M15": 11, "M5": 22, "M1": 33}[fr])
        for r in range(1, perm + 1):
            off = int(rng.integers(int(F.n * 0.1), int(F.n * 0.9)))
            Rs, RAs = np.roll(F.R, off, axis=0), np.roll(F.RA, off, axis=0)
            Ap, _ = evaluate(F, labs, knn, Rs, RAs, False)
            permA[r].append(Ap)
            if r % 5 == 0:
                log(fr, f"permutacion {r}/{perm}")
        knn_real = {}
        for L, (q, db, IDX) in knn.items():
            S50, S200 = knn_scores(F.R, q, db, IDX); knn_real[L] = (q, S50, S200)
        del knn
        keep[fr] = (F, labs, knn_real)

    D = pd.concat(realRows, ignore_index=True)
    D["bh_A"] = bh(D.p_A.values) & (D.m_A > 0).values
    D["conf_B"] = D.bh_A & (D.m_B > 0) & (D.t_B > 2)
    log(f"TOTAL variantes {len(D)} | con n_A>={MIN_N}: {int((D.p_A < 1).sum())} | BH en A: {int(D.bh_A.sum())} | "
        f"confirman B: {int(D.conf_B.sum())}")
    # permutaciones
    P = []
    for r in range(1, perm + 1):
        X = np.concatenate(permA[r])
        w = bh(X[:, 0]) & (X[:, 1] > 0)
        P.append(dict(rep=r, bh_A=int(w.sum()), conf_B=int((w & (X[:, 2] > 0) & (X[:, 3] > 2)).sum()),
                      min_p=float(X[:, 0].min()), log10p_min=float(np.log10(max(X[(X[:, 1] > 0), 0].min(), 1e-300)))))
    P = pd.DataFrame(P)
    log("PERMUTACION:\n" + P.to_string(index=False))
    pd.to_pickle(dict(D=D, P=P), os.path.join(OUT, "pat_formas_parcial.pkl"))
    # finalistas: hasta 300 que pasan BH en A + las 40 mejores de A con neto > 0 (estas solo para la tabla)
    cand = pd.concat([D[D.bh_A].sort_values("p_A").head(300), D[D.m_A > 0].sort_values("p_A").head(40)])
    cand = cand[~cand.index.duplicated()]
    fin = []
    for _, row in cand.iterrows():
        F, labs, knn_real = keep[row.marco]
        try:
            fin.append({**row.to_dict(), **finalist(F, row, labs, knn_real)})
        except Exception as e:  # noqa: BLE001
            log("finalista con error", row.marco, row.metodo, row.L, row.grupo, e)
    FIN = pd.DataFrame(fin)
    if len(FIN):
        FIN["pasa_todo"] = FIN.pasa_todo & FIN.bh_A
    # modelos para reconocer la forma en vivo
    models = {fr: {(x[0], x[1]): x[4] for x in keep[fr][1]} for fr in keep}
    pd.to_pickle(dict(D=D, P=P, FIN=FIN, models=models), os.path.join(OUT, "pat_formas.pkl"))
    pd.set_option("display.width", 300); pd.set_option("display.max_columns", 40); pd.set_option("display.max_rows", 200)
    cols = ["marco", "metodo", "L", "param", "grupo", "ctx", "salida", "n_A", "m_A", "R_A", "hit_A", "t_A", "p_A",
            "n_B", "m_B", "hit_B", "t_B"]
    print("\nMEJORES 40 EN A (neto > 0, por p):")
    print(D[D.m_A > 0].sort_values("p_A").head(40)[cols].to_string(index=False))
    if len(FIN):
        print("\nFINALISTAS (secuencial):")
        fc = cols + ["n_seq", "mA_seq", "tA_seq", "nB_seq", "mB_seq", "tB_seq", "hitB_seq", "per_pos", "per_tot", "bootB", "pasa_todo"]
        print(FIN.sort_values("p_A").head(60)[fc].round(4).to_string(index=False))
        print(f"\nPASAN TODO: {int(FIN.pasa_todo.sum())}")
    print("\nACIERTO vs EXPECTATIVA (variantes con n_A >= 100):")
    Z = D[D.n_A >= 100].copy(); Z["tramo"] = pd.cut(Z.hit_A, [0, .4, .5, .6, .7, .8, 1.0])
    print(Z.groupby("tramo", observed=True).agg(variantes=("m_A", "size"), neto_A_medio=("m_A", "mean"),
                                                 pct_neto_pos=("m_A", lambda x: (x > 0).mean()), neto_B_medio=("m_B", "mean")).to_string())
    print(Z.sort_values("hit_A", ascending=False).head(15)[cols].to_string(index=False))
    print("\nResumen por marco/metodo:")
    print(D.groupby(["marco", "metodo"]).agg(variantes=("p_A", "size"), con_n=("p_A", lambda x: int((x < 1).sum())),
                                             bh=("bh_A", "sum"), confB=("conf_B", "sum")).to_string())
    log("fin")


if __name__ == "__main__":
    main()
