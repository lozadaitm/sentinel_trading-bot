"""Recargas (entradas ADICIONALES en la misma direccion) cerca del minimo de la excursion en contra,
para las patas Big One (compra 01:00 -> 10:00) y Momentum EE.UU. (15:00 -> 21:00) del bot e2.
Solo simulacion; no toca el bot.

Datos: entrada, ATR15, ATR_D, tendencia s y senales con las velas M15 del broker (igual que broker_rule).
Camino dentro de la operacion: velas M5 de bars_all (Dukascopy 2022-2025 + broker 2026), llevadas al
nivel del broker con el desfase mediano de la ventana y recortadas al rango de la M15 del broker.
Dentro de una vela M5: si toca candado y objetivo, gana el candado (conservador); una recarga
nunca cobra su objetivo en la misma vela en que entra.

Base (como en el diseno): 3 tercios (hora / TP 2xATR15 / TP 3xATR15), candado a -1 ATR_D que congela
todo lo abierto (tercios + recargas) y se cierra a la hora de salida. Costos: spread 0,17 $/oz,
comision 0,06 $/oz ida y vuelta, deslizamiento 0,05 $/oz en cada recarga, 0,23 $/oz por volumen
candado. R = $/oz / ATR_D (unidad de riesgo del lote), ponderado por el peso de la pata.

Familias de recarga (todas causales):
  FIX   : orden limite a k x ATR15 o k x ATR_D en contra de la entrada (una o varias, rejilla)
  REV   : giro confirmado en M5 tras ir k x ATR15 en contra (rompe el maximo de la vela previa,
          o cierra x ATR15 por encima del minimo), entrada en la apertura siguiente
  LVL   : niveles de soporte/resistencia previos (minimo del dia anterior, minimo de la sesion previa,
          numeros redondos 10/50, racimo de pivotes M15 de 5 dias, nivel con mas mechas tocadas en
          5 dias); toque (limite) o toque + rechazo (cierre de vuelta, entrada en la apertura siguiente)
  TIME  : a los t minutos si va perdiendo
Nulos: misma cantidad de recargas en momentos al azar (a) cualquier vela antes del candado,
(b) solo velas en perdida. Contraste "lote mayor": alfa de la regresion recarga ~ base por operacion.
Uso: python -m bot_backtesting.fullsim.recargas_minimo
"""
import ctypes
import os
import sys

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.bigone_broker import load

FS = os.path.dirname(os.path.abspath(__file__))
DATA, RESULTS = os.path.join(FS, "data"), os.path.join(FS, "results")
SP, COMM, SLIP, LOCKC = 0.17, 0.06, 0.05, 0.23
IS_END = pd.Timestamp("2025-01-01").timestamp() // 86400
NREP = 1000


def low_priority():
    if sys.platform == "win32":
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)


# ---------------------------------------------------------------- operaciones y caminos
def build_trades():
    X, D = load()
    T, O, H, L, C = (X[c].values for c in ("time", "open", "high", "low", "close"))
    idx = pd.Series(np.arange(len(T)), index=T)
    E = pd.read_csv(os.path.join(FS, "events_us.csv"))
    evd = set((pd.to_datetime(E.date) - pd.Timestamp("1970-01-01")).dt.days)
    B = pd.read_pickle(os.path.join(DATA, "bars_all.pkl"))["M5"].set_index("time").sort_index()
    out = []
    for leg, h0, nb in (("big_one", 1, 36), ("momentum", 15, 24)):
        for k in np.nonzero(T % 86400 == h0 * 3600)[0]:
            d = T[k] // 86400
            if (d + 3) % 7 >= 5 or d not in D.index or not np.isfinite(D.at[d, "atrd"]) or not np.isfinite(X.atr15.iat[k]):
                continue
            if k + nb > len(T) or T[k + nb - 1] - T[k] != (nb - 1) * 900:
                continue
            s = D.at[d, "s"]
            if leg == "big_one":
                side, w = 1, (1.0 if s == 2 else 0.5) * (0.5 if d in evd else 1.0)
            else:
                k1 = idx.get(d * 86400 + 3600)
                if k1 is None or s not in (2, -2):
                    continue
                a = (O[k] - O[k1]) / O[k1] * 100
                if abs(a) <= 0.232:
                    continue
                side, w = int(np.sign(a)), 1.0
            # camino M5 ajustado al broker
            t0, t1 = T[k], T[k] + nb * 900
            m = B.loc[t0:t1 - 1]
            grid = np.arange(t0, t1, 300)
            if len(m) < 0.9 * len(grid):
                continue
            m = m.reindex(grid)
            m["close"] = m.close.ffill().bfill()
            for c in ("open", "high", "low"):
                m[c] = m[c].fillna(m.close)
            q = (grid - t0) // 900 + k
            agg_c = m.close.values.reshape(-1, 3)[:, -1]
            off = np.median(C[k:k + nb] - agg_c)
            mo, mh, ml, mc = (m[c].values + off for c in ("open", "high", "low", "close"))
            mh = np.minimum(mh, H[q]); ml = np.maximum(ml, L[q])
            mo = np.clip(mo, ml, mh); mc = np.clip(mc, ml, mh)
            mo[0] = O[k]                                         # entrada: apertura real del broker
            if side == 1:
                ou, hu, lu, cu = mo, mh, ml, mc
            else:
                ou, hu, lu, cu = -(mo + SP), -(ml + SP), -(mh + SP), -(mc + SP)
            # niveles previos (precio bid crudo)
            j0 = max(0, k - 480)
            pl, ph, po, pc = L[j0:k], H[j0:k], O[j0:k], C[j0:k]
            pdk = D.index.get_loc(d)
            prevd = D.index[pdk - 1]
            sess = slice(max(0, k - 32), k) if leg == "big_one" else slice(idx.get(d * 86400 + 3600, k), k)
            out.append(dict(leg=leg, t=t0, d=d, year=pd.Timestamp(t0, unit="s").year, side=side, w=w, s=s,
                            atr15=X.atr15.iat[k], atrd=D.at[d, "atrd"], p0=O[k],
                            ou=ou, hu=hu, lu=lu, cu=cu,
                            pdl=D.at[prevd, "L"], pdh=D.at[prevd, "H"],
                            sl=L[sess].min() if len(L[sess]) else np.nan, sh=H[sess].max() if len(H[sess]) else np.nan,
                            pl=pl, ph=ph, po=po, pc=pc))
    return out


# ---------------------------------------------------------------- base
def base(tr):
    ou, hu, lu, cu = tr["ou"], tr["hu"], tr["lu"], tr["cu"]
    e = ou[0] + SP
    N = len(ou)
    lockl = e - tr["atrd"]
    lh = np.nonzero(lu <= lockl)[0]
    lb = lh[0] if len(lh) else N
    lockm = min(ou[lb], lockl) if lb < N else np.nan
    pn = []
    for a in (None, 2.0, 3.0):
        r = None
        if a is not None:
            hh = np.nonzero(hu[:lb] >= e + a * tr["atr15"])[0]
            if len(hh):
                r = a * tr["atr15"]
        if r is None:
            r = (lockm - e - LOCKC) if lb < N else cu[-1] - e
        pn.append(r - COMM)
    mae = e - lu.min()
    tmin = int(np.argmin(lu))
    tr.update(e=e, lb=lb, lockm=lockm, lockl=lockl, base_pnl=np.mean(pn), N=N, mae=mae, tmin=tmin,
              exitm=(lockm if lb < N else cu[-1]))
    return tr


def add_pnl(tr, j, fill_u, mode):
    """P&L $/oz de una recarga que entra en la vela j al precio marca fill_u (sin spread)."""
    ea = fill_u + SP + SLIP
    lb, N = tr["lb"], tr["N"]
    if mode == "tp2":
        hh = np.nonzero(tr["hu"][j + 1:lb] >= ea + 2 * tr["atr15"])[0]
        if len(hh):
            return 2 * tr["atr15"] - COMM
    if lb < N:
        return tr["lockm"] - ea - LOCKC - COMM
    return tr["cu"][-1] - ea - COMM


# ---------------------------------------------------------------- niveles
def signed_level(tr, lvl):
    return lvl if tr["side"] == 1 else -(lvl + SP)


def zone_ok(tr, u):
    return np.isfinite(u) and (tr["e"] - 0.95 * tr["atrd"]) < u < (tr["e"] - 0.5 * tr["atr15"])


def level(tr, src):
    s, p0, a15, ad = tr["side"], tr["p0"], tr["atr15"], tr["atrd"]
    if src == "pdl":
        lv = tr["pdl"] if s == 1 else tr["pdh"]
    elif src == "ses":
        lv = tr["sl"] if s == 1 else tr["sh"]
    elif src in ("r10", "r50"):
        st = 10.0 if src == "r10" else 50.0
        lv = np.floor((p0 - 0.5 * a15) / st) * st if s == 1 else np.ceil((p0 + 0.5 * a15) / st) * st
    elif src == "piv":
        x = tr["pl"] if s == 1 else -tr["ph"]                    # minimos (o maximos con signo) de 5 dias
        if len(x) < 5:
            return np.nan
        piv = np.array([x[i] for i in range(2, len(x) - 2) if x[i] < min(x[i - 2], x[i - 1], x[i + 1], x[i + 2])])
        ref = p0 if s == 1 else -p0
        piv = piv[(piv < ref - 0.5 * a15) & (piv > ref - 0.95 * ad)]
        if len(piv) == 0:
            return np.nan
        bw = 0.1 * ad
        cnt = np.array([(np.abs(piv - v) <= bw / 2).sum() for v in piv])
        best = cnt.max()
        if best < 2:
            return np.nan
        cand = piv[cnt == best]
        v = cand.max()                                           # el mas cercano a la entrada
        lv = v if s == 1 else -v
    elif src == "wick":
        ref = p0 if s == 1 else -p0
        if s == 1:
            lo, hi = tr["pl"], np.minimum(tr["po"], tr["pc"])
        else:
            lo, hi = -tr["ph"], -np.maximum(tr["po"], tr["pc"])     # mecha superior con signo
        grid = ref - np.arange(0.5 * a15, 0.95 * ad, 0.05 * ad)
        if len(grid) == 0:
            return np.nan
        cnt = ((lo[None, :] <= grid[:, None]) & (hi[None, :] >= grid[:, None])).sum(1)
        if cnt.max() < 3:
            return np.nan
        v = grid[np.nonzero(cnt == cnt.max())[0][0]]
        lv = v if s == 1 else -v
    else:
        raise ValueError(src)
    return lv


# ---------------------------------------------------------------- reglas -> lista de (j, fill_u, tam)
def limit_add(tr, u, size):
    lu, ou = tr["lu"], tr["ou"]
    hit = np.nonzero(lu[1:] <= u)[0]
    if not len(hit):
        return []
    j = hit[0] + 1
    if j > tr["lb"] or u <= tr["lockl"] or j >= tr["N"] - 1:
        return []
    return [(j, min(ou[j], u), size)]


def rule_adds(tr, rule):
    fam = rule[0]
    e, a15, ad, N, lb = tr["e"], tr["atr15"], tr["atrd"], tr["N"], tr["lb"]
    ou, hu, lu, cu = tr["ou"], tr["hu"], tr["lu"], tr["cu"]
    if fam == "FIX":
        _, unit, ks, size = rule
        X = a15 if unit == "atr15" else ad
        out = []
        for kk in ks:
            if kk * X >= ad:
                continue
            out += limit_add(tr, e - kk * X, size / len(ks))
        return out
    if fam == "REV":
        _, kmin, how, size = rule
        m = np.minimum.accumulate(lu)
        for j in range(1, min(lb, N - 2)):
            if m[j] > e - kmin * a15 or cu[j] >= e:
                continue
            ok = cu[j] > hu[j - 1] if how == "brk" else cu[j] >= m[j] + how * a15
            if ok and j + 1 < lb:
                return [(j + 1, ou[j + 1], size)]
        return []
    if fam == "LVL":
        _, src, how, size = rule
        lv = level(tr, src)
        if not np.isfinite(lv):
            return []
        u = signed_level(tr, lv)
        if not zone_ok(tr, u):
            return []
        if how == "touch":
            return limit_add(tr, u, size)
        hit = np.nonzero(lu[1:] <= u)[0]
        if not len(hit):
            return []
        j0 = hit[0] + 1
        for j in range(j0, min(j0 + 12, lb, N - 2)):
            if cu[j] > u and cu[j] < e and j + 1 < lb:
                return [(j + 1, ou[j + 1], size)]
        return []
    if fam == "TIME":
        _, mins, size = rule
        j = mins // 5
        if j >= min(lb, N - 1) or cu[j - 1] >= e:
            return []
        return [(j, ou[j], size)]
    raise ValueError(fam)


def rules():
    R = []
    for size in (0.5, 1.0):
        for k in (1, 2, 3, 4):
            R.append(("FIX", "atr15", (k,), size))
        for k in (0.25, 0.5, 0.75):
            R.append(("FIX", "atrd", (k,), size))
        R.append(("FIX", "atrd", (0.25, 0.5, 0.75), size))
        R.append(("FIX", "atr15", (1, 2, 3), size))
        for kmin in (0, 1, 2, 3):
            for how in ("brk", 0.5, 1.0):
                R.append(("REV", kmin, how, size))
        for src in ("pdl", "ses", "r10", "r50", "piv", "wick"):
            for how in ("touch", "rej"):
                R.append(("LVL", src, how, size))
        for mins in (30, 60, 120, 180, 240):
            R.append(("TIME", mins, size))
    return R


def rname(r):
    return "_".join(str(x if not isinstance(x, tuple) else "+".join(map(str, x))) for x in r)


# ---------------------------------------------------------------- metricas
def metrics(df, col):
    x = df.groupby("d")[col].sum()
    cum = x.cumsum()
    dd = (cum.cummax().clip(lower=0) - cum).max()
    mon = x.groupby(pd.to_datetime(x.index * 86400, unit="s").to_period("M")).sum()
    return dict(R_tot=x.sum(), R_dia=x.mean(), sharpe=x.mean() / x.std() * np.sqrt(250), dd=dd,
                ret_dd=x.sum() / dd if dd > 0 else np.nan, peor_dia=x.min(), peor_mes=mon.min(), mes_medio=mon.mean())


def alpha_p(add, base):
    """alfa de add = a + b*base (por operacion); p unilateral de a > 0."""
    from math import erf, sqrt
    if np.allclose(add, 0) or len(add) < 10:
        return np.nan, 1.0
    b = np.polyfit(base, add, 1)
    res = add - np.polyval(b, base)
    se = res.std(ddof=2) * np.sqrt(1 / len(add) + base.mean() ** 2 / ((base - base.mean()) ** 2).sum())
    t = b[1] / se
    return b[1], 0.5 * (1 - erf(t / sqrt(2)))   # normal (n grande)


def bh(p, q=0.10):
    p = np.asarray(p, float)
    o = np.argsort(p)
    n = len(p)
    thr = q * np.arange(1, n + 1) / n
    ok = p[o] <= thr
    k = np.nonzero(ok)[0].max() + 1 if ok.any() else 0
    res = np.zeros(n, bool)
    res[o[:k]] = True
    return res


def null_tables(trs):
    """Para cada operacion: P&L de recarga en la apertura de cada vela (tiempo y tp2), y mascaras."""
    for tr in trs:
        n = min(tr["lb"], tr["N"] - 1)
        js = np.arange(1, n)
        tr["nt"] = {m: np.array([add_pnl(tr, j, tr["ou"][j], m) for j in js]) for m in ("time", "tp2")}
        tr["nloss"] = tr["ou"][js] < tr["e"]


def main():
    low_priority()
    fp = os.path.join(RESULTS, "recargas_trades.pkl")
    if os.path.exists(fp):
        trs = pd.read_pickle(fp)
    else:
        trs = [base(t) for t in build_trades()]
        null_tables(trs)
        pd.to_pickle(trs, fp)
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40); pd.set_option("display.max_rows", 500)
    meta = pd.DataFrame([{k: tr[k] for k in ("leg", "t", "d", "year", "side", "w", "atr15", "atrd", "base_pnl", "mae", "tmin", "lb", "N", "e", "exitm")} for tr in trs])
    meta["R"] = meta.w * meta.base_pnl / meta.atrd
    meta["lock"] = meta.lb < meta.N
    meta["is_"] = meta.d < IS_END

    # 1) base y MAE
    print("=== 1) BASE (camino M5) por pata y año: R ponderado medio, tasa de candado ===")
    print(meta.groupby(["leg", "year"]).agg(n=("R", "size"), R=("R", "mean"), lock=("lock", "mean")).round(3).to_string())
    print("\nMAE (en contra maxima hasta la salida, sin cortar por candado):")
    for leg, g in meta.groupby("leg"):
        q = [0.1, 0.25, 0.5, 0.75, 0.9]
        print(f" {leg}: MAE/ATR15 cuantiles {np.round(np.quantile(g.mae / g.atr15, q), 2)} | MAE/ATR_D {np.round(np.quantile(g.mae / g.atrd, q), 2)}"
              f" | minuto del minimo {np.quantile(g.tmin * 5, q).astype(int)} | MAE>=1ATR_D {(g.mae >= g.atrd).mean():.2f}")
        win = g.base_pnl > 0
        print(f"    ganadoras MAE/ATR_D mediana {np.median(g.mae[win] / g.atrd[win]):.2f}; perdedoras {np.median(g.mae[~win] / g.atrd[~win]):.2f}")
    # oraculo
    orc = []
    for tr in trs:
        if tr["lb"] < tr["N"]:
            orc.append(0.0)
        else:
            orc.append((tr["exitm"] - (tr["lu"].min() + SP) - COMM) / tr["atrd"] * tr["w"])
    meta["oracle"] = orc
    print("\nORACULO (recarga 1x en el minimo exacto, salida por hora; inalcanzable):")
    print(meta.groupby("leg").agg(R_base=("R", "mean"), R_oraculo_extra=("oracle", "mean")).round(3).to_string())

    # 2) reglas
    RL = rules()
    rng = np.random.default_rng(11)
    rows, store = [], {}
    for r in RL:
        for mode in ("time", "tp2"):
            name = rname(r) + "_" + mode
            add = np.zeros(len(trs)); nadd = np.zeros(len(trs), int); size = np.zeros(len(trs))
            for i, tr in enumerate(trs):
                for j, fu, sz in rule_adds(tr, r):
                    add[i] += sz * add_pnl(tr, j, fu, mode); nadd[i] += 1; size[i] += sz
            addR = add / meta.atrd.values * meta.w.values
            store[name] = (addR, nadd, size)
            for leg in ("big_one", "momentum"):
                for per, msk in (("IS", meta.is_.values), ("OOS", ~meta.is_.values)):
                    sel = (meta.leg.values == leg) & msk
                    fired = sel & (nadd > 0)
                    obs = addR[fired].sum()
                    # nulos
                    nl = []
                    for kind in ("any", "loss"):
                        sims = np.zeros(NREP)
                        for i in np.nonzero(fired)[0]:
                            tr = trs[i]
                            pool = tr["nt"][mode] if kind == "any" else tr["nt"][mode][tr["nloss"]]
                            if len(pool) == 0:
                                continue
                            per_add = size[i] / nadd[i]
                            draws = pool[rng.integers(0, len(pool), (NREP, nadd[i]))].sum(1) * per_add
                            sims += draws / tr["atrd"] * tr["w"]
                        nl.append(((sims >= obs).sum() + 1) / (NREP + 1) if fired.any() else 1.0)
                        nl.append(sims.mean() / max(fired.sum(), 1))
                    sub = meta[sel].assign(add=addR[sel], tot=meta.R[sel] + addR[sel])
                    mb, mt = metrics(sub, "R"), metrics(sub, "tot")
                    al, pa = alpha_p(addR[sel], meta.R.values[sel])
                    lk_extra = (size[sel] * meta.lock.values[sel]).sum() / max(meta.lock.values[sel].sum(), 1)
                    rows.append(dict(var=name, fam=r[0], leg=leg, per=per, n=sel.sum(), disparos=fired.mean(),
                                     add_R_por_disparo=obs / max(fired.sum(), 1), nulo_any=nl[1], p_any=nl[0], nulo_loss=nl[3], p_loss=nl[2],
                                     alfa=al, p_alfa=pa, base_ret_dd=mb["ret_dd"], tot_ret_dd=mt["ret_dd"],
                                     base_sh=mb["sharpe"], tot_sh=mt["sharpe"], base_dd=mb["dd"], tot_dd=mt["dd"],
                                     base_R=mb["R_tot"], tot_R=mt["R_tot"], base_peor_dia=mb["peor_dia"], tot_peor_dia=mt["peor_dia"],
                                     base_peor_mes=mb["peor_mes"], tot_peor_mes=mt["peor_mes"], extra_mes=(mt["mes_medio"] - mb["mes_medio"]),
                                     lote_extra_en_candado=lk_extra))
        print(".", end="", flush=True)
    S = pd.DataFrame(rows)
    S["mejora_ret_dd"] = S.tot_ret_dd / S.base_ret_dd - 1
    S.to_pickle(os.path.join(RESULTS, "recargas_summary.pkl"))
    pd.to_pickle((meta, store), os.path.join(RESULTS, "recargas_store.pkl"))
    print()
    for leg in ("big_one", "momentum"):
        I = S[(S.leg == leg) & (S.per == "IS")].copy()
        Ooos = S[(S.leg == leg) & (S.per == "OOS")].set_index("var")
        I["bh_loss"] = bh(I.p_loss.values); I["bh_any"] = bh(I.p_any.values); I["bh_alfa"] = bh(I.p_alfa.values)
        print(f"\n=== {leg}: IS 2022-2024, {len(I)} variantes. Pasan BH q=0,10: vs azar-en-perdida {I.bh_loss.sum()}, "
              f"vs azar {I.bh_any.sum()}, alfa vs lote mayor {I.bh_alfa.sum()}")
        print(f"  p minimos: azar-en-perdida {I.p_loss.min():.3f}, azar {I.p_any.min():.3f}, alfa {I.p_alfa.min():.4f}")
        cols = ["var", "disparos", "add_R_por_disparo", "nulo_loss", "p_loss", "alfa", "p_alfa", "base_ret_dd", "tot_ret_dd", "mejora_ret_dd", "base_sh", "tot_sh", "base_dd", "tot_dd", "tot_peor_dia", "base_peor_dia"]
        top = I.sort_values("mejora_ret_dd", ascending=False).head(12)
        print("  TOP 12 por mejora de retorno/caida en IS:")
        print(top[cols].round(3).to_string(index=False))
        print("  esas mismas en OOS 2025-2026:")
        print(Ooos.loc[top["var"], cols[1:]].round(3).to_string())
        print("  por familia (IS, mediana de mejora ret/dd y de p_loss):")
        print(I.groupby("fam").agg(mejora_med=("mejora_ret_dd", "median"), mejor=("mejora_ret_dd", "max"), p_loss_med=("p_loss", "median")).round(3).to_string())


if __name__ == "__main__":
    main()
