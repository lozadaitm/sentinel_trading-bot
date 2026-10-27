"""Deteccion del minimo tras la entrada (Big One / Momentum del bot e2) y recarga en la misma direccion.
Segunda ronda, despues de recargas_minimo.py (152 reglas simples, ninguna pasa). Solo simulacion.

Reutiliza results/recargas_trades.pkl (operaciones, caminos M5 ajustados al broker, base de 3 tercios
con candado, tablas del nulo al azar) y add_pnl / alpha_p / bh de recargas_minimo.

Familias nuevas:
  ML_A   : clasificador "si recargo en la proxima apertura, gano?" (logistica y GBDT en numpy) con
           ~25 rasgos causales por vela M5 en perdida; recarga en la 1.a vela con p > umbral
  ML_B   : clasificador "esto es el fondo" (llenado a <= 0,1 ATR_D del minimo final Y recarga ganadora)
  LADML  : escalera de limites en cuantiles del MAE de las GANADORAS (IS), activa solo hasta el
           minuto tipico del minimo de las ganadoras y solo si el detector de dia bueno lo permite
  LAD    : la misma escalera sin filtro
  CAP    : capitulacion M5 (vela de rango >= r x media, mecha inferior >= 50 %, cierre arriba)
  BB/KC  : perforar Bollinger / Keltner M5 y cerrar dentro
  SEC    : parada optima tipo "secretaria": observar la primera fraccion, recargar al romper ese minimo
  SEAS   : ventana horaria donde mas se produce el minimo (IS) y precio pegado al minimo corriente
  MTF    : vela M15 de rechazo + confirmacion M5 (cierre sobre el maximo de esa M15)
  DIV    : divergencia alcista de RSI(14) M5 en un nuevo minimo
Inverso: CUT = cerrar la base en un punto de control si el detector de "dia malo" lo predice.
Validacion: OOS 2025-2026 con modelos entrenados solo con años anteriores (2025 <- 2022-24,
2026 <- 2022-25); umbrales y elecciones en IS (validacion cruzada por años purgada).
Uso: python -m bot_backtesting.fullsim.minimo_lab
"""
import os

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.recargas_minimo import (FS, RESULTS, SP, COMM, SLIP, LOCKC, IS_END, add_pnl,
                                                     alpha_p, bh, low_priority)

NREP = 2000
RISK = 0.08


# ================================================================ rasgos por vela
def rsi(x, n=14):
    d = np.diff(x, prepend=x[0])
    up = pd.Series(np.clip(d, 0, None)).ewm(alpha=1 / n, adjust=False).mean().values
    dn = pd.Series(np.clip(-d, 0, None)).ewm(alpha=1 / n, adjust=False).mean().values
    return 100 - 100 / (1 + up / np.maximum(dn, 1e-9))


FEATS = ["dd", "dd15", "mae", "bounce15", "mfe", "tfrac", "since_min", "spd6", "spd12", "rng_ratio", "rng15",
         "wick", "clpos", "rsi", "z20", "d_pdl", "d_ses", "r10", "dow", "s", "w", "is_mom", "news", "ad_a15",
         "pre4", "pre96", "downs6", "first_low"]


def trade_feats(tr, news):
    ou, hu, lu, cu = tr["ou"], tr["hu"], tr["lu"], tr["cu"]
    e, a15, ad, N = tr["e"], tr["atr15"], tr["atrd"], tr["N"]
    side = tr["side"]
    rm = np.minimum.accumulate(lu)
    am = np.array([int(np.argmin(lu[:j + 1])) for j in range(N)])
    rM = np.maximum.accumulate(hu)
    rg = hu - lu
    crg = np.cumsum(rg) / np.arange(1, N + 1)
    r3 = pd.Series(rg).rolling(3, min_periods=1).mean().values
    cs = pd.Series(cu)
    m20 = cs.rolling(20, min_periods=6).mean().values
    s20 = cs.rolling(20, min_periods=6).std().values
    sig = lambda v: v if side == 1 else -(v + SP)
    pcs = tr["pc"] if side == 1 else -(tr["pc"] + SP)
    pdl = sig(tr["pdl"] if side == 1 else tr["pdh"])
    ses = sig(tr["sl"] if side == 1 else tr["sh"])
    lag = lambda x, k: np.r_[np.full(k, x[0]), x[:-k]]
    down = (cu < ou).astype(float)
    F = dict(
        dd=(e - cu) / ad, dd15=(e - cu) / a15, mae=(e - rm) / ad, bounce15=(cu - rm) / a15, mfe=(rM - e) / ad,
        tfrac=np.arange(N) / N, since_min=(np.arange(N) - am) / 12.0,
        spd6=(cu - lag(cu, 6)) / a15, spd12=(cu - lag(cu, 12)) / a15,
        rng_ratio=r3 / np.maximum(crg, 1e-9), rng15=rg * 3 / a15,
        wick=(np.minimum(ou, cu) - lu) / np.maximum(rg, 1e-9), clpos=(cu - lu) / np.maximum(rg, 1e-9),
        rsi=rsi(cu), z20=(cu - m20) / np.maximum(s20, 1e-9),
        d_pdl=(cu - pdl) / ad, d_ses=(cu - ses) / ad,
        r10=np.mod(np.abs(cu), 10.0) / 10.0,
        dow=np.full(N, (tr["d"] + 3) % 7), s=np.full(N, tr["s"]), w=np.full(N, tr["w"]),
        is_mom=np.full(N, 1.0 if tr["leg"] == "momentum" else 0.0), news=np.full(N, 1.0 if tr["d"] in news else 0.0),
        ad_a15=np.full(N, ad / a15),
        pre4=np.full(N, (ou[0] - pcs[-4]) / a15), pre96=np.full(N, (ou[0] - pcs[-96]) / ad),
        downs6=pd.Series(down).rolling(6, min_periods=1).sum().values,
        first_low=np.r_[np.nan, (lu[1:] < rm[:-1]).astype(float)],
    )
    F["z20"] = np.nan_to_num(F["z20"]); F["first_low"] = np.nan_to_num(F["first_low"])
    return np.column_stack([F[k] for k in FEATS])


def build_rows(trs, news):
    """Filas = vela j (decision al cierre de j, llenado en ou[j+1]) en perdida, antes del candado."""
    rows = []
    for i, tr in enumerate(trs):
        Fm = trade_feats(tr, news)
        N, lb, e = tr["N"], tr["lb"], tr["e"]
        js = np.arange(0, min(lb, N - 1) - 1)              # j+1 < lb y j+1 <= N-2
        js = js[tr["cu"][js] < e]
        if not len(js):
            continue
        lu = tr["lu"]
        fut_min = np.minimum.accumulate(lu[::-1])[::-1]       # minimo desde j hasta la salida
        ya = np.array([add_pnl(tr, j + 1, tr["ou"][j + 1], "time") for j in js])
        near = (tr["ou"][js + 1] - fut_min[js + 1]) <= 0.1 * tr["atrd"]
        rows.append(pd.DataFrame(dict(i=i, j=js, year=tr["year"], d=tr["d"], leg=tr["leg"], ya=(ya > 0).astype(float),
                                      yb=((ya > 0) & near).astype(float), yc=float(tr["base_pnl"] < 0),
                                      wt=1.0 / len(js))).join(pd.DataFrame(Fm[js], columns=FEATS)))
    return pd.concat(rows, ignore_index=True)


# ================================================================ modelos en numpy
class Logit:
    def fit(self, X, y, w, lam=1.0):
        self.mu, self.sd = X.mean(0), X.std(0) + 1e-9
        Z = np.c_[np.ones(len(X)), (X - self.mu) / self.sd]
        b = np.zeros(Z.shape[1])
        R = lam * np.eye(Z.shape[1]); R[0, 0] = 0
        for _ in range(25):
            p = 1 / (1 + np.exp(-Z @ b))
            g = Z.T @ (w * (p - y)) + R @ b
            H = (Z * (w * p * (1 - p))[:, None]).T @ Z + R
            st = np.linalg.solve(H, g)
            b -= st
            if np.abs(st).max() < 1e-6:
                break
        self.b = b
        return self

    def predict(self, X):
        return 1 / (1 + np.exp(-np.c_[np.ones(len(X)), (X - self.mu) / self.sd] @ self.b))


class GBDT:
    """Boosting de arboles (profundidad 3) sobre rasgos discretizados en 32 cuantiles; perdida logistica."""

    def __init__(self, ntree=150, depth=3, lr=0.05, minleaf=0.02, lam=5.0, sub=0.6, seed=0):
        self.ntree, self.depth, self.lr, self.minleaf, self.lam, self.sub = ntree, depth, lr, minleaf, lam, sub
        self.rng = np.random.default_rng(seed)

    def _bin(self, X):
        return np.column_stack([np.searchsorted(self.edges[f], X[:, f], side="right") for f in range(X.shape[1])]).astype(np.int16)

    def fit(self, X, y, w):
        self.edges = [np.unique(np.quantile(X[:, f], np.linspace(0, 1, 33)[1:-1])) for f in range(X.shape[1])]
        B = self._bin(X)
        nb = 33
        w = w / w.mean()
        p0 = np.clip((w * y).sum() / w.sum(), 1e-4, 1 - 1e-4)
        self.f0 = np.log(p0 / (1 - p0))
        F = np.full(len(y), self.f0)
        self.trees = []
        minw = self.minleaf * w.sum()
        for _ in range(self.ntree):
            p = 1 / (1 + np.exp(-F))
            g, h = w * (p - y), w * p * (1 - p)
            use = self.rng.random(len(y)) < self.sub
            tree = []                                       # nodos: (feat, thr, left, right) o ('leaf', val)
            leaf_of = np.zeros(len(y), int)

            def grow(idx, dep):
                k = len(tree); tree.append(None)
                ii = idx[use[idx]]
                G, Hh = g[ii].sum(), h[ii].sum()
                best = None
                if dep < self.depth and len(ii) > 50:
                    for f in range(B.shape[1]):
                        gb = np.bincount(B[ii, f], g[ii], nb); hb = np.bincount(B[ii, f], h[ii], nb)
                        wb = np.bincount(B[ii, f], w[ii], nb)
                        GL, HL, WL = np.cumsum(gb)[:-1], np.cumsum(hb)[:-1], np.cumsum(wb)[:-1]
                        WR = wb.sum() - WL
                        gain = GL ** 2 / (HL + self.lam) + (G - GL) ** 2 / (Hh - HL + self.lam) - G ** 2 / (Hh + self.lam)
                        gain[(WL < minw * self.sub) | (WR < minw * self.sub)] = -np.inf
                        t = int(np.argmax(gain))
                        if np.isfinite(gain[t]) and gain[t] > 0 and (best is None or gain[t] > best[0]):
                            best = (gain[t], f, t)
                if best is None:
                    tree[k] = ("leaf", -G / (Hh + self.lam))
                    leaf_of[idx] = k
                    return k
                _, f, t = best
                m = B[idx, f] <= t
                l = grow(idx[m], dep + 1); r = grow(idx[~m], dep + 1)
                tree[k] = (f, t, l, r)
                return k

            grow(np.arange(len(y)), 0)
            vals = np.array([nd[1] if nd[0] == "leaf" else 0.0 for nd in tree])
            F += self.lr * vals[leaf_of]
            self.trees.append(tree)
        return self

    def predict(self, X):
        B = self._bin(X)
        F = np.full(len(X), self.f0)
        for tree in self.trees:
            node = np.zeros(len(X), int)
            for _ in range(self.depth + 1):
                for k, nd in enumerate(tree):
                    if nd[0] == "leaf":
                        continue
                    m = node == k
                    if m.any():
                        go = B[m, nd[0]] <= nd[1]
                        node[np.nonzero(m)[0]] = np.where(go, nd[2], nd[3])
            F += self.lr * np.array([tree[k][1] for k in node])
        return 1 / (1 + np.exp(-F))


def auc(y, p, w=None):
    o = np.argsort(p)
    y = y[o]; w = np.ones(len(y)) if w is None else w[o]
    pos, neg = (w * y), (w * (1 - y))
    cneg = np.cumsum(neg)
    return (pos * (cneg - neg / 2)).sum() / max(pos.sum() * neg.sum(), 1e-12)


def predictions(R, target, kind):
    """IS: validacion cruzada dejando un año fuera (purgada por año); OOS: expansivo (solo años previos)."""
    X = np.nan_to_num(R[FEATS].values.astype(float)); y = R[target].values; w = R.wt.values   # s puede faltar (sin 63 dias previos)
    p_cv = np.full(len(R), np.nan); p_oos = np.full(len(R), np.nan)
    mk = (lambda: Logit()) if kind == "logit" else (lambda: GBDT())
    isy = [2022, 2023, 2024]
    for Y in isy:
        tr = R.year.isin([z for z in isy if z != Y]).values; te = (R.year == Y).values
        p_cv[te] = mk().fit(X[tr], y[tr], w[tr]).predict(X[te])
    for Y in (2025, 2026):
        tr = (R.year < Y).values; te = (R.year == Y).values
        p_oos[te] = mk().fit(X[tr], y[tr], w[tr]).predict(X[te])
    # 2024 estricto (entrenado con 2022-23) para el informe de AUC
    tr = (R.year < 2024).values; te = (R.year == 2024).values
    p24 = mk().fit(X[tr], y[tr], w[tr]).predict(X[te])
    return p_cv, p_oos, (te, p24)


# ================================================================ reglas manuales -> (j_llenado, precio, tam)
def first_after(tr, js):
    for j in js:
        if j + 1 < tr["lb"] and j + 1 <= tr["N"] - 2 and tr["cu"][j] < tr["e"]:
            return [(j + 1, tr["ou"][j + 1], 1.0)]
    return []


def limit_fill(tr, u, j_from, j_to, size):
    lu, ou = tr["lu"], tr["ou"]
    for j in range(max(1, j_from), min(j_to, tr["lb"], tr["N"] - 1)):
        if lu[j] <= u:
            if u <= tr["lockl"]:
                return []
            return [(j, min(ou[j], u), size)]
    return []


def hand_adds(tr, rule, ctx):
    fam = rule[0]
    ou, hu, lu, cu = tr["ou"], tr["hu"], tr["lu"], tr["cu"]
    e, a15, ad, N, lb = tr["e"], tr["atr15"], tr["atrd"], tr["N"], tr["lb"]
    rg = hu - lu
    rm = np.minimum.accumulate(lu)
    jr = range(1, min(lb, N - 1) - 1)
    if fam == "CAP":
        _, k, rr = rule
        ok = []
        for j in jr:
            if j < 6:
                continue
            avg = rg[:j].mean()
            wk = (min(ou[j], cu[j]) - lu[j]) / max(rg[j], 1e-9)
            if rg[j] >= rr * avg and wk >= 0.5 and (e - lu[j]) >= k * a15:
                ok.append(j)
        return first_after(tr, ok)
    if fam in ("BB", "KC"):
        _, m = rule
        ok = []
        for j in jr:
            if j < 12:
                continue
            win = cu[max(0, j - 20):j]
            band = win.mean() - (m * win.std() if fam == "BB" else m * rg[max(0, j - 20):j].mean())
            if lu[j] < band < cu[j] and (e - lu[j]) >= a15:
                ok.append(j)
        return first_after(tr, ok)
    if fam == "SEC":
        _, frac, how = rule
        n0 = int(frac * N)
        m0 = lu[:n0].min()
        if m0 >= e - 0.5 * a15:
            m0 = e - 0.5 * a15                               # al menos media ATR15 en contra
        if how == "touch":
            return limit_fill(tr, m0, n0, N - 1, 1.0)
        hit = [j for j in jr if j >= n0 and lu[j] <= m0]
        if not hit:
            return []
        ok = [j for j in jr if j >= hit[0] and cu[j] >= rm[j] + 0.5 * a15]
        return first_after(tr, ok)
    if fam == "SEAS":
        _, tol = rule
        w0, w1 = ctx["seas"][tr["leg"]]
        ok = [j for j in jr if w0 <= j < w1 and (e - cu[j]) >= a15 and cu[j] - rm[j] <= tol * a15]
        return first_after(tr, ok)
    if fam == "MTF":
        _, k = rule
        ok = []
        for j in jr:
            if (j + 1) % 3 or j < 2:
                continue
            h, l, o, c = hu[j - 2:j + 1].max(), lu[j - 2:j + 1].min(), ou[j - 2], cu[j]
            r = h - l
            if r <= 0 or (e - l) < k * a15:
                continue
            if (min(o, c) - l) / r >= 0.5 and (c - l) / r >= 0.66:
                for jj in range(j + 1, min(j + 4, lb - 1, N - 2)):
                    if cu[jj] > h:
                        ok.append(jj); break
                if ok:
                    break
        return first_after(tr, ok)
    if fam == "DIV":
        _, lvl = rule
        R = rsi(cu)
        ok = []
        last_low = None
        for j in jr:
            if lu[j] <= rm[j - 1]:                            # nuevo minimo corriente
                if last_low is not None and j - last_low >= 3 and R[last_low] < lvl and R[j] > R[last_low] and (e - lu[j]) >= a15:
                    ok.append(j); break
                if last_low is None or R[j] < R[last_low]:
                    last_low = j
        return first_after(tr, ok)
    if fam in ("LAD", "LADML"):
        q1, q2, tend = ctx["lad"][tr["leg"]]
        out = []
        for q in (q1, q2):
            f = limit_fill(tr, e - q * ad, 1, tend, 0.5)
            if f and fam == "LADML":
                j = f[0][0]
                pg = ctx["pgood"].get((ctx["idx"][id(tr)], j - 1), np.nan)
                if not (pg >= rule[1]):
                    continue
            out += f
        return out
    raise ValueError(fam)


def hand_rules():
    R = [("CAP", k, rr) for k in (1, 2, 3) for rr in (1.5, 2.0, 2.5)]
    R += [("BB", m) for m in (2.0, 2.5, 3.0)] + [("KC", m) for m in (1.5, 2.0)]
    R += [("SEC", f, h) for f in (0.25, 0.37, 0.5) for h in ("touch", "rev")]
    R += [("SEAS", t) for t in (0.5, 1.0)] + [("MTF", k) for k in (1, 2)] + [("DIV", l) for l in (30, 40)]
    R += [("LAD",)]
    return R


# ================================================================ evaluacion
def evaluate(trs, meta, adds_list, mode, rng):
    n = len(trs)
    addR = np.zeros(n); nadd = np.zeros(n, int); size = np.zeros(n)
    dist, near, lose = [], [], []
    for i, ad in enumerate(adds_list):
        tr = trs[i]
        for j, fu, sz in ad:
            addR[i] += sz * add_pnl(tr, j, fu, mode) / tr["atrd"] * tr["w"]
            nadd[i] += 1; size[i] += sz
            dmin = (fu - tr["lu"][j:].min()) / tr["atrd"]
            dist.append(dmin); near.append(dmin <= 0.1); lose.append(tr["base_pnl"] < 0)
    return addR, nadd, size


def null_p(trs, meta, addR, nadd, size, sel, mode, rng):
    fired = np.nonzero(sel & (nadd > 0))[0]
    obs = addR[fired].sum()
    sims = np.zeros(NREP)
    for i in fired:
        tr = trs[i]
        pool = tr["nt"][mode][tr["nloss"]]
        if not len(pool):
            continue
        sims += pool[rng.integers(0, len(pool), (NREP, nadd[i]))].sum(1) * (size[i] / nadd[i]) / tr["atrd"] * tr["w"]
    return ((sims >= obs).sum() + 1) / (NREP + 1), sims.mean() / max(len(fired), 1)


def precision(trs, adds_list, sel):
    """Que tan cerca del minimo final entra (ATR_D), % a <=0,1 ATR_D, % en operaciones perdedoras; y lo mismo al azar."""
    d, nr, ls, dn, ln = [], [], [], [], []
    for i in np.nonzero(sel)[0]:
        tr = trs[i]
        for j, fu, sz in adds_list[i]:
            m = tr["lu"][j:].min()
            d.append((fu - m) / tr["atrd"]); ls.append(tr["base_pnl"] < 0)
            js = np.arange(1, min(tr["lb"], tr["N"] - 1))[tr["nloss"]]
            fm = np.minimum.accumulate(tr["lu"][::-1])[::-1]
            dn.append(np.mean((tr["ou"][js] - fm[js]) / tr["atrd"]))
            ln.append(tr["base_pnl"] < 0)
    if not d:
        return dict(dist_min=np.nan, cerca=np.nan, en_perd=np.nan, dist_azar=np.nan)
    d = np.array(d)
    return dict(dist_min=np.median(d), cerca=(d <= 0.1).mean(), en_perd=np.mean(ls), dist_azar=np.nanmedian(dn))


def port_stats(meta, x, msk):
    day = pd.Series(np.where(msk, x, 0.0), index=meta.d.values)[msk].groupby(level=0).sum()
    cum = day.cumsum()
    dd = (cum.cummax().clip(lower=0) - cum).max()
    mon = day.groupby(pd.to_datetime(day.index * 86400, unit="s").to_period("M")).sum()
    return dict(R=day.sum(), mes=mon.mean() * RISK * 100, dd=dd * RISK * 100, ret_dd=day.sum() / dd if dd > 0 else np.nan,
                sh=day.mean() / day.std() * np.sqrt(250), peor_dia=day.min() * RISK * 100, peor_mes=mon.min() * RISK * 100)


def summarize(name, fam, trs, meta, adds_list, mode, rng):
    addR, nadd, size = evaluate(trs, meta, adds_list, mode, rng)
    rows = []
    for leg in ("big_one", "momentum"):
        for per, msk in (("IS", meta.is_.values), ("OOS", ~meta.is_.values)):
            sel = (meta.leg.values == leg) & msk
            fired = sel & (nadd > 0)
            if fired.sum() < 5:
                rows.append(dict(var=name, fam=fam, mode=mode, leg=leg, per=per, n_disp=int(fired.sum())))
                continue
            pn, nmean = null_p(trs, meta, addR, nadd, size, sel, mode, rng)
            al, pa = alpha_p(addR[sel], meta.R.values[sel])
            pm = msk  # cartera de ambas patas en ese periodo
            base = meta.R.values
            tot = base + np.where(sel, addR, 0.0)
            legm = sel
            k = 1 + addR[legm].sum() / base[legm].sum() if base[legm].sum() > 0 else np.nan
            big = base * np.where(legm, k, 1.0)
            sb, st, sg = port_stats(meta, base, pm), port_stats(meta, tot, pm), port_stats(meta, big, pm)
            pr = precision(trs, adds_list, sel)
            lk = (size[sel] * meta.lock.values[sel]).sum() / max(meta.lock.values[sel].sum(), 1)
            rows.append(dict(var=name, fam=fam, mode=mode, leg=leg, per=per, n_disp=int(fired.sum()), frac_disp=fired.sum() / sel.sum(),
                             R_por_disp=addR[fired].mean(), R_por_op=addR[sel].mean(), nulo=nmean, p_nulo=pn, alfa=al, p_alfa=pa,
                             lote_k=k, base_retdd=sb["ret_dd"], tot_retdd=st["ret_dd"], big_retdd=sg["ret_dd"],
                             base_mes=sb["mes"], tot_mes=st["mes"], base_dd=sb["dd"], tot_dd=st["dd"], big_dd=sg["dd"],
                             base_pdia=sb["peor_dia"], tot_pdia=st["peor_dia"], big_pdia=sg["peor_dia"],
                             tot_pmes=st["peor_mes"], base_pmes=sb["peor_mes"], base_sh=sb["sh"], tot_sh=st["sh"], big_sh=sg["sh"],
                             lote_en_candado=lk, **pr))
    return rows, addR


# ================================================================ corte (inverso): cerrar la base si "dia malo"
def base_cut(tr, jc):
    """P&L $/oz de la base cerrando lo que quede abierto en ou[jc] (si no hubo candado antes)."""
    ou, hu = tr["ou"], tr["hu"]
    e, lb, N = tr["e"], tr["lb"], tr["N"]
    if lb <= jc:
        return tr["base_pnl"]
    pn = []
    for a in (None, 2.0, 3.0):
        r = None
        if a is not None:
            hh = np.nonzero(hu[:jc] >= e + a * tr["atr15"])[0]
            if len(hh):
                r = a * tr["atr15"]
        if r is None:
            r = ou[jc] - e
        pn.append(r - COMM)
    return np.mean(pn)


def main():
    low_priority()
    rng = np.random.default_rng(7)
    trs = pd.read_pickle(os.path.join(RESULTS, "recargas_trades.pkl"))
    E = pd.read_csv(os.path.join(FS, "events_us.csv"))
    news = set((pd.to_datetime(E.date) - pd.Timestamp("1970-01-01")).dt.days)
    meta = pd.DataFrame([{k: tr[k] for k in ("leg", "t", "d", "year", "side", "w", "atr15", "atrd", "base_pnl", "mae", "tmin", "lb", "N", "e")} for tr in trs])
    meta["R"] = meta.w * meta.base_pnl / meta.atrd
    meta["lock"] = meta.lb < meta.N
    meta["is_"] = meta.d < IS_END
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 50); pd.set_option("display.max_rows", 500)

    fp = os.path.join(RESULTS, "minimo_rows.pkl")
    if os.path.exists(fp):
        R = pd.read_pickle(fp)
    else:
        R = build_rows(trs, news); R.to_pickle(fp)
    print(f"filas (velas M5 en perdida antes del candado): {len(R)}; ya={R.ya.mean():.3f} yb={R.yb.mean():.3f} yc={R.yc.mean():.3f}")

    # ---------------- modelos
    fpm = os.path.join(RESULTS, "minimo_preds.pkl")
    if os.path.exists(fpm):
        P = pd.read_pickle(fpm)
        if not P.get("v2"):                                   # v1 tenia NaN en 's' -> la logistica salia rota; se rehace
            for tgt in ("ya", "yc"):
                P[(tgt, "logit")] = predictions(R, tgt, "logit")
            P["v2"] = True
            pd.to_pickle(P, fpm)
    else:
        P = {}
        for tgt, kind in (("ya", "logit"), ("ya", "gbdt"), ("yb", "gbdt"), ("yc", "gbdt"), ("yc", "logit")):
            print(f"modelo {tgt}/{kind} ...", flush=True)
            P[(tgt, kind)] = predictions(R, tgt, kind)
        P["v2"] = True
        pd.to_pickle(P, fpm)
    print("\n=== Calidad de los detectores (AUC; filas ponderadas 1/filas por operacion) ===")
    for (tgt, kind), (pcv, poos, (te24, p24)) in [(k, v) for k, v in P.items() if k != "v2"]:
        for leg in ("big_one", "momentum"):
            L = (R.leg == leg).values
            a_cv = auc(R[tgt].values[L & R.year.isin([2022, 2023, 2024]).values], pcv[L & R.year.isin([2022, 2023, 2024]).values], R.wt.values[L & R.year.isin([2022, 2023, 2024]).values])
            m24 = L[te24]
            a24 = auc(R[tgt].values[te24][m24], p24[m24], R.wt.values[te24][m24])
            o = L & (R.year >= 2025).values
            a_o = auc(R[tgt].values[o], poos[o], R.wt.values[o])
            print(f" {tgt}/{kind:5s} {leg:9s}: AUC CV-IS {a_cv:.3f} | 2024 estricto {a24:.3f} | OOS 2025-26 {a_o:.3f}")
    # AUC del dia malo por punto de control (rasgos a esa hora; todas las operaciones con fila a esa hora o no)
    print("\n=== Detector de dia malo (yc) por minuto desde la entrada, OOS 2025-26 (solo velas en perdida) ===")
    pcv, poos, _ = P[("yc", "gbdt")]
    for leg in ("big_one", "momentum"):
        for mins in (15, 30, 60, 120, 180):
            j = mins // 5 - 1
            o = (R.leg == leg).values & (R.year >= 2025).values & (R.j == j).values
            if o.sum() > 30:
                print(f" {leg:9s} {mins:3d} min: n={o.sum():3d} perdedoras={R.yc.values[o].mean():.2f} AUC={auc(R.yc.values[o], poos[o]):.3f}")

    # ---------------- contexto IS para reglas manuales
    ctx = {"seas": {}, "lad": {}, "idx": {id(tr): i for i, tr in enumerate(trs)}}
    for leg, g in meta[meta.is_].groupby("leg"):
        h = np.bincount(g.tmin.values, minlength=int(g.N.max()))
        h[:3] = 0
        c6 = np.convolve(h, np.ones(6), "valid")
        w0 = int(np.argmax(c6))
        ctx["seas"][leg] = (w0, w0 + 6)
        win = g[g.base_pnl > 0]
        q1, q2 = np.quantile(win.mae / win.atrd, [0.5, 0.75])
        tend = int(np.quantile(win.tmin, 0.75))
        ctx["lad"][leg] = (q1, q2, tend)
        print(f"contexto IS {leg}: ventana del minimo {w0 * 5}-{(w0 + 6) * 5} min; escalera ganadoras MAE q50={q1:.2f} q75={q2:.2f} ATR_D, activa hasta {tend * 5} min")

    rows_all, addstore = [], {}
    # ---------------- ML: primera vela con p > umbral
    for (tgt, kind) in (("ya", "logit"), ("ya", "gbdt"), ("yb", "gbdt")):
        pcv, poos, _ = P[(tgt, kind)]
        p = np.where(R.year.values >= 2025, poos, pcv)
        for leg in ("big_one", "momentum"):
            pass
        for q in (0.5, 0.8, 0.9, 0.95, 0.98):
            thr = {leg: np.nanquantile(pcv[(R.leg == leg).values & (R.year < 2025).values], q) for leg in ("big_one", "momentum")}
            fire = p >= np.array([thr[l] for l in R.leg.values])
            first = R[fire].groupby("i").j.min()
            adds = [[] for _ in trs]
            for i, j in first.items():
                tr = trs[i]
                adds[i] = [(j + 1, tr["ou"][j + 1], 1.0)]
            for mode in ("time", "tp2"):
                name = f"ML_{tgt}_{kind}_q{q}_{mode}"
                rr, ar = summarize(name, f"ML_{tgt}_{kind}", trs, meta, adds, mode, rng)
                rows_all += rr; addstore[name] = ar
        print(".", end="", flush=True)
    # dia bueno para la escalera filtrada
    pcv, poos, _ = P[("yc", "gbdt")]
    pbad = np.where(R.year.values >= 2025, poos, pcv)
    for q in (0.5, 0.7, 0.85):
        thr = {leg: np.nanquantile(pcv[(R.leg == leg).values & (R.year < 2025).values], q) for leg in ("big_one", "momentum")}
        ctx["pgood"] = {(i, j): float(pb <= thr[l]) for i, j, pb, l in zip(R.i.values, R.j.values, pbad, R.leg.values)}
        for mode in ("time", "tp2"):
            name = f"LADML_bad<q{q}_{mode}"
            adds = [hand_adds(tr, ("LADML", 1.0), ctx) for tr in trs]
            rr, ar = summarize(name, "LADML", trs, meta, adds, mode, rng)
            rows_all += rr; addstore[name] = ar
    # ---------------- reglas manuales
    for rule in hand_rules():
        adds = [hand_adds(tr, rule, ctx) for tr in trs]
        for mode in ("time", "tp2"):
            name = "_".join(map(str, rule)) + "_" + mode
            rr, ar = summarize(name, rule[0], trs, meta, adds, mode, rng)
            rows_all += rr; addstore[name] = ar
        print(".", end="", flush=True)
    print()
    S = pd.DataFrame(rows_all)
    S.to_pickle(os.path.join(RESULTS, "minimo_summary.pkl"))
    pd.to_pickle((meta, addstore), os.path.join(RESULTS, "minimo_store.pkl"))

    cols = ["var", "n_disp", "R_por_disp", "nulo", "p_nulo", "alfa", "p_alfa", "lote_k", "base_retdd", "tot_retdd", "big_retdd",
            "base_mes", "tot_mes", "tot_dd", "big_dd", "base_pdia", "tot_pdia", "big_pdia", "dist_min", "dist_azar", "cerca", "en_perd", "lote_en_candado"]
    for leg in ("big_one", "momentum"):
        I = S[(S.leg == leg) & (S.per == "IS") & (S.n_disp >= 5)].copy()
        O = S[(S.leg == leg) & (S.per == "OOS") & (S.n_disp >= 5)].copy()
        O["bh_alfa"] = bh(O.p_alfa.fillna(1).values); O["bh_nulo"] = bh(O.p_nulo.fillna(1).values)
        I["bh_alfa"] = bh(I.p_alfa.fillna(1).values); I["bh_nulo"] = bh(I.p_nulo.fillna(1).values)
        print(f"\n######## {leg}: {len(I)} variantes. Pasan BH q=0,10 -> IS: alfa {I.bh_alfa.sum()}, azar {I.bh_nulo.sum()} | "
              f"OOS: alfa {O.bh_alfa.sum()}, azar {O.bh_nulo.sum()} | p min OOS alfa {O.p_alfa.min():.4f} azar {O.p_nulo.min():.4f}")
        print(" ambas a la vez (alfa y azar) en OOS:", O[O.bh_alfa & O.bh_nulo]["var"].tolist())
        I["score"] = I.tot_retdd / I.base_retdd - 1
        print(" TOP 10 IS por mejora ret/caida:")
        print(I.sort_values("score", ascending=False).head(10)[cols].round(3).to_string(index=False))
        top = I.sort_values("score", ascending=False).head(10)["var"]
        print(" esas en OOS:")
        print(O.set_index("var").reindex(top)[cols[1:]].round(3).to_string())
        print(" mejores por familia elegidas en IS (por p_alfa IS), en OOS:")
        best = I.sort_values("p_alfa").groupby("fam").head(1)["var"]
        print(O.set_index("var").reindex(best)[cols[1:] + ["bh_alfa", "bh_nulo"]].round(3).to_string())
        print(" TOP 8 OOS por p_alfa (solo informativo, seleccion en OOS = sesgada):")
        print(O.sort_values("p_alfa").head(8)[cols + ["bh_alfa", "bh_nulo"]].round(3).to_string(index=False))

    # ---------------- corte por dia malo
    print("\n=== CORTE: cerrar la base en el minuto c si p(dia malo) > umbral (umbral = cuantil IS); OOS 2025-26 ===")
    pcv, poos, _ = P[("yc", "gbdt")]
    pb = np.where(R.year.values >= 2025, poos, pcv)
    Rk = R.assign(pb=pb).set_index(["i", "j"])
    for leg in ("big_one", "momentum"):
        for mins in (30, 60, 120, 180):
            jc = mins // 5
            for q in (0.7, 0.9):
                thr = np.nanquantile(pcv[(R.leg == leg).values & (R.year < 2025).values & (R.j == jc - 1).values], q)
                for per, msk in (("IS", meta.is_.values), ("OOS", ~meta.is_.values)):
                    ids = np.nonzero((meta.leg.values == leg) & msk)[0]
                    dR, cut = [], []
                    for i in ids:
                        tr = trs[i]
                        v = Rk.pb.get((i, jc - 1), np.nan)
                        c = np.isfinite(v) and v > thr
                        cut.append(c)
                        dR.append((base_cut(tr, jc) - tr["base_pnl"]) / tr["atrd"] * tr["w"] if c else 0.0)
                    dR, cut = np.array(dR), np.array(cut)
                    # nulo: cortar al azar el mismo numero entre las que estan en perdida a esa hora
                    elig = [i for i in ids if (i, jc - 1) in Rk.index]
                    alld = np.array([(base_cut(trs[i], jc) - trs[i]["base_pnl"]) / trs[i]["atrd"] * trs[i]["w"] for i in elig])
                    ncut = cut.sum()
                    if ncut == 0 or len(alld) == 0:
                        continue
                    sims = np.array([alld[rng.choice(len(alld), ncut, replace=False)].sum() for _ in range(NREP)])
                    p = ((sims >= dR.sum()).sum() + 1) / (NREP + 1)
                    print(f" {leg:9s} {mins:3d}min q{q} {per}: cortes {ncut:3d}/{len(ids)} | dR total {dR.sum():+.2f} R ({dR.sum() / len(ids):+.4f}/op) | azar {sims.mean():+.2f} | p={p:.3f}")


if __name__ == "__main__":
    main()
