"""Re-entrada de "confirmacion": tras la entrada de la Big One o el Momentum (bot e2), si el precio va en
contra al menos D y luego VUELVE al precio de entrada, se abre un juego adicional de 3 tercios en la misma
direccion (misma hora de salida; TP en los mismos precios que el original, o recalculados desde la nueva
entrada). Candado a -1 ATR_D de la entrada ORIGINAL congela tambien la re-entrada (cuenta su volumen).
Solo simulacion; no toca el bot ni MT5.

Reutiliza results/recargas_trades.pkl (de recargas_minimo: camino M5 ajustado al broker, base, candado).
Coordenadas "con signo": ou/hu/lu/cu = precio de cierre (bid en compras, -ask en ventas); una entrada
nueva en la vela j se llena a marca + spread + deslizamiento. Entrada original e = ou[0] + SP;
la marca equivalente a "volver a la entrada" es e - SP.

Rejilla (una re-entrada por pata como maximo, todo causal):
  D        : 0,25/0,5/0,75/1/1,5 x ATR15 y 0,1/0,2/0,3/0,5 x ATR_D (excursion en contra desde la entrada)
  vuelta   : toque de la entrada -0,25 ATR15 / exacto / +0,25 ATR15 (orden stop) o cierre M5 >= entrada
             (entra en la apertura siguiente)
  ventana  : vuelta en cualquier momento, o dentro de 15/30/60/120 min desde la vela del minimo-umbral
  corte    : sin re-entradas en los ultimos 0/60/120 min antes de la salida
  TP       : mismos precios que el original (e+2/3 ATR15) o recalculados desde la re-entrada
  tamano   : 1/3, 1/2, 1 x el lote original (escala lineal; los p no dependen del tamano)
Nulos: re-entrada en una vela al azar del mismo dia (a) cualquiera antes del candado y del corte,
(b) solo velas cuya apertura esta a +-0,25 ATR15 de la entrada (re-entrada "en la entrada" sin exigir
caida previa). Contraste lote mayor: alfa de add ~ a + b*base. BH q=0,10 por pata sobre IS.
Uso: python -m bot_backtesting.fullsim.reentrada_confirmacion
"""
import itertools
import os

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.recargas_minimo import (COMM, IS_END, LOCKC, RESULTS, SLIP, SP, alpha_p, bh,
                                                     low_priority)

RISK = 0.08
NREP = 1000
DS = [("a15", k) for k in (0.25, 0.5, 0.75, 1.0, 1.5)] + [("ad", k) for k in (0.1, 0.2, 0.3, 0.5)]
RETS = ["t-0.25", "t0", "t+0.25", "c5"]
WINS = [None, 15, 30, 60, 120]
CUTS = [0, 60, 120]
TPS = ["same", "new"]
SIZES = [1 / 3, 0.5, 1.0]


def add_set_pnl(tr, ja, fill_u, tp):
    """$/oz medio de los 3 tercios de una re-entrada que entra en la vela ja."""
    ea = fill_u + SP + SLIP
    lb, N, A, e = tr["lb"], tr["N"], tr["atr15"], tr["e"]
    hu = tr["hu"][ja + 1:lb]
    mx = hu.max() if len(hu) else -np.inf
    fall = (tr["lockm"] - ea - LOCKC) if lb < N else (tr["cu"][-1] - ea)
    out = [fall]
    for a in (2.0, 3.0):
        tgt = (e + a * A) if tp == "same" else (ea + a * A)
        out.append(tgt - ea if (mx >= tgt and tgt > ea) else fall)
    return np.mean(out) - COMM


def find_add(tr, dkind, dk, ret, win, cut):
    """(vela de la caida, vela de la vuelta/senal, vela de entrada, precio marca de llenado) o None."""
    e, A, AD, N, lb = tr["e"], tr["atr15"], tr["atrd"], tr["N"], tr["lb"]
    ou, hu, lu, cu = tr["ou"], tr["hu"], tr["lu"], tr["cu"]
    ref = e - SP
    Dv = dk * (A if dkind == "a15" else AD)
    if Dv >= AD:
        return None
    h = np.nonzero(lu[:lb] <= ref - Dv)[0]
    if not len(h):
        return None
    jd = h[0]
    last = min(lb, N - 1) - 1                     # ultima vela de entrada posible (antes del candado y de la ultima vela)
    last = min(last, N - 1 - cut // 5)
    if ret == "c5":
        hits = np.nonzero(cu[jd:] >= ref)[0]
        if not len(hits):
            return None
        jr = jd + hits[0]
        ja, fu = jr + 1, None
    else:
        L = ref + {"t-0.25": -0.25, "t0": 0.0, "t+0.25": 0.25}[ret] * A
        hits = np.nonzero(hu[jd + 1:] >= L)[0]
        if not len(hits):
            return None
        jr = jd + 1 + hits[0]
        ja, fu = jr, None
        fu = max(ou[jr], L)
    if win is not None and (jr - jd) * 5 > win:
        return None
    if ja > last or ja >= lb:
        return None
    if fu is None:
        fu = ou[ja]
    return jd, jr, ja, fu


def null_pools(trs):
    for tr in trs:
        n = min(tr["lb"], tr["N"] - 1)
        js = np.arange(1, n)
        tr["rj"] = js
        tr["rp"] = {tp: np.array([add_set_pnl(tr, j, tr["ou"][j], tp) for j in js]) for tp in TPS}
        tr["rnear"] = np.abs(tr["ou"][js] - (tr["e"] - SP)) <= 0.25 * tr["atr15"]


def stats(day):
    cum = day.cumsum()
    dd = (cum.cummax().clip(lower=0) - cum).max()
    mon = day.groupby(pd.to_datetime(day.index * 86400, unit="s").to_period("M")).sum()
    return dict(R=day.sum(), mes_pct=mon.mean() * RISK * 100, caida_pct=dd * RISK * 100,
                ret_caida=day.sum() / dd if dd > 0 else np.nan, sharpe=day.mean() / day.std() * np.sqrt(250),
                peor_dia_pct=day.min() * RISK * 100, peor_mes_pct=mon.min() * RISK * 100)


def main():
    low_priority()
    trs = pd.read_pickle(os.path.join(RESULTS, "recargas_trades.pkl"))
    null_pools(trs)
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40); pd.set_option("display.max_rows", 500)
    meta = pd.DataFrame([{k: tr[k] for k in ("leg", "d", "year", "w", "atr15", "atrd", "base_pnl", "lb", "N", "e")} for tr in trs])
    meta["R"] = meta.w * meta.base_pnl / meta.atrd
    meta["lock"] = meta.lb < meta.N
    meta["is_"] = meta.d < IS_END
    legv, isv, Rb, W, AD = meta.leg.values, meta.is_.values, meta.R.values, meta.w.values, meta.atrd.values

    # ---------------------------------------------------------------- 1) descriptivo
    print("=== 1) DESCRIPTIVO: caida >= D y vuelta a la entrada (toque exacto), cualquier momento, sin corte ===")
    # incondicional: 1 lote desde la entrada, por hora/candado; P(TP2), P(TP3) desde la entrada
    unc = []
    for tr in trs:
        lb, N = tr["lb"], tr["N"]
        mx = tr["hu"][:lb].max()
        unc.append(dict(tp2=mx >= tr["e"] + 2 * tr["atr15"], tp3=mx >= tr["e"] + 3 * tr["atr15"],
                        r_time=((tr["lockm"] - tr["e"] - LOCKC) if lb < N else (tr["cu"][-1] - tr["e"])) - COMM))
    U = pd.DataFrame(unc)
    U["Rt"] = U.r_time / AD * W
    rows = []
    for leg in ("big_one", "momentum"):
        sel = legv == leg
        rows.append(dict(leg=leg, D="incondicional (desde la entrada)", n=sel.sum(), p_caida=np.nan, p_vuelta=np.nan,
                         min_p25=np.nan, min_med=np.nan, min_p75=np.nan, p_tp2=U.tp2[sel].mean(), p_tp3=U.tp3[sel].mean(),
                         p_candado=meta.lock[sel].mean(), R_resto=U.Rt[sel].mean(), R_azar_cerca=np.nan))
        for dkind, dk in DS:
            dips = rets = 0; mins, tp2, tp3, rr, lk, rnull = [], [], [], [], [], []
            for i in np.nonzero(sel)[0]:
                tr = trs[i]
                A, ADi = tr["atr15"], tr["atrd"]
                Dv = dk * (A if dkind == "a15" else ADi)
                if np.any(tr["lu"][:tr["lb"]] <= tr["e"] - SP - Dv):
                    dips += 1
                f = find_add(tr, dkind, dk, "t0", None, 0)
                if f is None:
                    continue
                jd, jr, ja, fu = f
                rets += 1
                mins.append((jr - jd) * 5)
                ea = fu + SP + SLIP
                mxh = tr["hu"][ja + 1:tr["lb"]]
                mxh = mxh.max() if len(mxh) else -np.inf
                tp2.append(mxh >= tr["e"] + 2 * A); tp3.append(mxh >= tr["e"] + 3 * A)
                lk.append(tr["lb"] < tr["N"])
                lb, N = tr["lb"], tr["N"]
                rr.append((((tr["lockm"] - ea - LOCKC) if lb < N else (tr["cu"][-1] - ea)) - COMM) / ADi * tr["w"])
                # nulo: misma posicion pero en una vela al azar cerca de la entrada (sin exigir caida), media
                js = tr["rj"]; nr = tr["rnear"]
                if nr.any():
                    pnl = [(((tr["lockm"] - (tr["ou"][j] + SP + SLIP) - LOCKC) if lb < N else (tr["cu"][-1] - (tr["ou"][j] + SP + SLIP))) - COMM) / ADi * tr["w"] for j in js[nr]]
                    rnull.append(np.mean(pnl))
            q = np.quantile(mins, [0.25, 0.5, 0.75]) if mins else [np.nan] * 3
            rows.append(dict(leg=leg, D=f"{dk} x {'ATR15' if dkind == 'a15' else 'ATR_D'}", n=sel.sum(), p_caida=dips / sel.sum(),
                             p_vuelta=rets / max(dips, 1), min_p25=q[0], min_med=q[1], min_p75=q[2],
                             p_tp2=np.mean(tp2) if tp2 else np.nan, p_tp3=np.mean(tp3) if tp3 else np.nan,
                             p_candado=np.mean(lk) if lk else np.nan, R_resto=np.mean(rr) if rr else np.nan,
                             R_azar_cerca=np.mean(rnull) if rnull else np.nan))
    Dd = pd.DataFrame(rows)
    print(Dd.round(3).to_string(index=False))
    Dd.to_csv(os.path.join(RESULTS, "reentrada_descriptivo.csv"), index=False)

    # ---------------------------------------------------------------- 2) rejilla
    rng = np.random.default_rng(7)
    rows, store = [], {}
    combos = list(itertools.product(DS, RETS, WINS, CUTS, TPS))
    for (dkind, dk), ret, win, cut, tp in combos:
        name = f"D{dk}{dkind}_{ret}_w{win or 'all'}_c{cut}_{tp}"
        add = np.zeros(len(trs)); fired = np.zeros(len(trs), bool); inlock = np.zeros(len(trs), bool)
        for i, tr in enumerate(trs):
            f = find_add(tr, dkind, dk, ret, win, cut)
            if f is None:
                continue
            add[i] = add_set_pnl(tr, f[2], f[3], tp); fired[i] = True; inlock[i] = tr["lb"] < tr["N"]
        addR = add / AD * W                         # tamano 1x
        store[name] = (addR, fired, inlock)
        for leg in ("big_one", "momentum"):
            for per, msk in (("IS", isv), ("OOS", ~isv)):
                sel = (legv == leg) & msk
                fi = sel & fired
                obs = addR[fi].sum()
                nl = []
                for kind in ("any", "near"):
                    sims = np.zeros(NREP); ok = 0
                    for i in np.nonzero(fi)[0]:
                        tr = trs[i]
                        lastj = tr["N"] - 1 - cut // 5
                        m = tr["rj"] <= lastj
                        if kind == "near":
                            m = m & tr["rnear"]
                        pool = tr["rp"][tp][m]
                        if not len(pool):
                            continue
                        ok += 1
                        sims += pool[rng.integers(0, len(pool), NREP)] / tr["atrd"] * tr["w"]
                    nl.append(((sims >= obs).sum() + 1) / (NREP + 1) if fi.any() else 1.0)
                    nl.append(sims.mean() / max(fi.sum(), 1))
                al, pa = alpha_p(addR[sel], Rb[sel])
                rows.append(dict(var=name, leg=leg, per=per, dkind=dkind, dk=dk, ret=ret, win=win or 0, cut=cut, tp=tp,
                                 n=sel.sum(), disparos=fi.sum(), frac=fi.sum() / sel.sum(), R_por_disparo=obs / max(fi.sum(), 1),
                                 R_sum=obs, nulo_any=nl[1], p_any=nl[0], nulo_near=nl[3], p_near=nl[2], alfa=al, p_alfa=pa,
                                 frac_en_candado=(inlock & fi).sum() / max(fi.sum(), 1)))
    S = pd.DataFrame(rows)
    S.to_pickle(os.path.join(RESULTS, "reentrada_summary.pkl"))
    pd.to_pickle((meta, store), os.path.join(RESULTS, "reentrada_store.pkl"))
    print(f"\n=== 2) REJILLA: {len(combos)} variantes por pata (x3 tamanos, escala lineal) ===")
    for leg in ("big_one", "momentum"):
        I = S[(S.leg == leg) & (S.per == "IS")].copy()
        O = S[(S.leg == leg) & (S.per == "OOS")].set_index("var")
        for c in ("p_any", "p_near", "p_alfa"):
            I["bh_" + c] = bh(I[c].values)
        print(f"\n--- {leg}: pasan BH q=0,10 en IS: vs azar {I.bh_p_any.sum()}, vs azar-en-la-entrada {I.bh_p_near.sum()}, "
              f"alfa vs lote mayor {I.bh_p_alfa.sum()} | p min: {I.p_any.min():.3f} / {I.p_near.min():.3f} / {I.p_alfa.min():.4f}")
        print(f"   R por disparo IS: mediana {I.R_por_disparo.median():.3f}; >0 en {(I.R_por_disparo > 0).mean():.0%} de variantes;"
              f" OOS: mediana {O.R_por_disparo.median():.3f}; >0 en {(O.R_por_disparo > 0).mean():.0%}")
        print(f"   alfa>0 IS {(I.alfa > 0).mean():.0%}; OOS {(O.alfa > 0).mean():.0%}; corr(alfa IS, alfa OOS) = "
              f"{np.corrcoef(I.set_index('var').alfa, O.loc[I['var']].alfa)[0, 1]:.2f}")
        for g in ("dkind", "ret", "win", "cut", "tp"):
            print("   por", g, I.groupby(g).agg(R_disp_IS=("R_por_disparo", "median"), alfa_IS=("alfa", "median"), p_alfa=("p_alfa", "median")).round(3).T.to_string().replace("\n", "\n      "))
        cols = ["disparos", "R_por_disparo", "nulo_any", "p_any", "nulo_near", "p_near", "alfa", "p_alfa", "frac_en_candado"]
        top = I.sort_values("p_alfa").head(10)
        print("   TOP 10 IS por p_alfa:")
        print(top[["var"] + cols].round(4).to_string(index=False))
        print("   las mismas en OOS:")
        print(O.loc[top["var"], cols].round(4).to_string())

    # ---------------------------------------------------------------- 3) cartera al 8 % para la mejor de IS por pata
    print("\n=== 3) CARTERA Big One + Momentum al 8 %: mejor variante IS (p_alfa) por pata, 3 tamanos, vs lote mayor ===")
    out, yrs = [], []
    for leg in ("big_one", "momentum"):
        I = S[(S.leg == leg) & (S.per == "IS")]
        v = I.sort_values("p_alfa").iloc[0]["var"]
        addR1, fired, inlock = store[v]
        legm = legv == leg
        for sz in SIZES:
            addR = addR1 * sz
            for per, msk in (("IS 2022-2024", isv), ("OOS 2025-2026", ~isv), ("todo", np.ones(len(isv), bool))):
                base = np.where(msk, Rb, 0.0)
                lm = legm & msk
                tot = base + np.where(lm, addR, 0.0)
                k = 1 + addR[lm].sum() / Rb[lm].sum()
                big = base * np.where(lm, k, 1.0)
                for lab, x in (("base", base), (f"re-entrada x{sz:.2f}", tot), (f"lote mayor x{k:.2f}", big)):
                    day = pd.Series(x, index=meta.d.values)[msk].groupby(level=0).sum()
                    out.append(dict(pata=leg, var=v, tam=round(sz, 2), periodo=per, cartera=lab, **stats(day)))
        yrs.append(pd.DataFrame({"y": meta.year.values[legm], "a": addR1[legm]}).groupby("y").a.sum().rename(f"{leg}: {v} (1x)"))
        lk = meta.lock.values & legm
        print(f"  {leg} {v}: dias con candado {lk.sum()}, con re-entrada dentro {(lk & fired).sum()} "
              f"({(lk & fired).sum() / max(lk.sum(), 1):.0%}); R medio de la re-entrada en esos dias (1x) {addR1[lk & fired].mean() if (lk & fired).any() else 0:.3f}")
    C = pd.DataFrame(out).drop_duplicates(["pata", "tam", "periodo", "cartera"])
    print(C.round(3).to_string(index=False))
    C.to_csv(os.path.join(RESULTS, "reentrada_cartera.csv"), index=False)
    print("\nR anadido por año (1x):")
    print(pd.concat(yrs, axis=1).round(2).to_string())
    print("\nBase por año:")
    print(meta.groupby(["year", "leg"]).R.sum().unstack().round(2).to_string())


if __name__ == "__main__":
    main()
