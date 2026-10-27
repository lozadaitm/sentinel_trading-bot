"""Linea D (proyectar entradas: limite / stop de entrada / escalonado / TWAP) - piezas comunes.
Solo simulacion, sin MT5, 2026 excluido (las operaciones de 2026 se descartan antes de calcular nada).

Idea: la MISMA operacion e2 (pata, lado, peso, hora de salida, tamano) pero con otro precio/momento de entrada.
  * raw_cache(E, tag): camino fino en BID (velas M5; recorte de la primera vela M15 de la Big One al rango del
    broker, igual que opt_base.trade_path) desde la vela M15 anterior a la senal hasta la hora de salida.
  * sim(E, cache, plan): aplica un 'plan de entrada' a cada operacion y gestiona cada tramo llenado con la escalera
    vigente (tercios hora / TP 2 / TP 3 ATR15, candado -1 ATR_D, cierre a la hora). Devuelve el DataFrame listo
    para compare() (pnl en $/oz del lote COMPLETO: un tramo no llenado simplemente no suma).
Planes (dict):
  kind='limit' : orden limite a px -/+ x (x en ATR15, ATR_D o $) colocada al entrar, valida N min.
                 Compra llena si ask = bid_low + spread(max de los minutos de la vela) <= limite - pen.
                 Llenado al limite (o al open si ya abre por debajo), sin deslizamiento (si comision).
                 Vela del llenado (conservador): despues de llenar el precio solo va en contra (adv = low)
                 y lo mejor alcanzable es el cierre de esa vela (fav = cierre).
                 Si no llena: fb='lost' (se pierde) o fb='mkt' (a mercado al open de la vela siguiente al
                 vencimiento: bid + spread + deslizamiento).
  kind='stop'  : orden stop de entrada a px +/- x (confirmacion). Llena al nivel + deslizamiento; vela del
                 llenado conservadora igual que arriba. fb='lost' o 'mkt'.
  kind='twap'  : tramos a mercado en el open de las velas k (minutos desde la entrada).
  levels       : lista de (x, fraccion) para escalonar la misma orden (suma de fracciones = 1).
  anchor       : 'new' -> TP y candado medidos desde el precio de cada tramo; 'orig' -> desde el px original.
  legs         : patas a las que se aplica (las demas quedan como la base).
Uso: libreria. Autocomprobacion (reproduce la base exacta):
  .venv/Scripts/python -m bot_backtesting.fullsim.opt_D_common
"""
import os
import pickle

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.opt_base import (COMM, SLIP, RESULTS, SEL, VAL, base_trades, entries, low_priority,
                                              m15, path, spread_at, swap_cost)

PEN = 0.05          # $/oz que el ask debe atravesar el limite para contar como llenado (toque = no llena)


def _end_ok(E):
    return E[(E.t >= SEL[0].timestamp()) & (E.t < VAL[1].timestamp())].reset_index(drop=True)


def raw_cache(E, tag, force=False, pre=900):
    """Lista de dicts (una por operacion) con tt, o, h, l, c (BID), smax (spread max dentro de la vela) e i_in
    (indice de la primera vela >= hora real de entrada)."""
    fp = os.path.join(RESULTS, f"optD_raw_{tag}.pkl")
    if os.path.exists(fp) and not force:
        with open(fp, "rb") as f:
            return pickle.load(f)
    E = _end_ok(E)
    X, _ = m15()
    out = []
    for r in E.itertuples(index=False):
        tt, o, h, l, c, dur = path(r.t - pre, r.t_out)
        tt = np.asarray(tt); o, h, l, c = (np.array(v, float) for v in (o, h, l, c))
        if r.leg == "big_one" and len(tt):
            lo, hi = X.low.values[r.k15], X.high.values[r.k15]
            m = (tt >= r.t) & (tt < r.t + 900)
            l = np.where(m, np.maximum(l, lo), l); h = np.where(m, np.minimum(h, hi), h)
        smax = np.max(np.stack([spread_at(tt + 60 * k) for k in range(5)]), 0) if len(tt) else np.array([])
        i_in = int(np.searchsorted(tt, r.t_in - (r.t_in % 60)))
        out.append(dict(tt=tt, o=o, h=h, l=l, c=c, smax=smax, i_in=i_in))
    with open(fp, "wb") as f:
        pickle.dump((E, out), f)
    return E, out


def ladder(R, r, j0, px, fill_bar, imp, anchor="new", tps=(None, 2.0, 3.0), lock_k=1.0):
    """Escalera vigente desde la vela j0 con precio px. fill_bar=True: vela de llenado conservadora.
    imp = mejora de precio frente al px original ($/oz, >0 = mejor). Devuelve (pnl $/oz sin swap, locked, mae)."""
    o, h, l, c = R["o"][j0:], R["h"][j0:], R["l"][j0:], R["c"][j0:]
    n = len(o)
    if n == 0:
        return np.nan, False, np.nan
    sp = r.spr_out
    if r.side == 1:
        fav, adv, opn, cls = h - px, l - px, o - px, c - px
    else:
        fav, adv, opn, cls = px - (l + sp), px - (h + sp), px - (o + sp), px - (c + sp)
    if fill_bar:
        fav = fav.copy(); opn = opn.copy()
        fav[0] = cls[0]; opn[0] = 0.0
    shift = imp if anchor == "orig" else 0.0
    lockd = lock_k * r.atrd - shift
    lk = np.nonzero(adv <= -lockd)[0]
    i_lock = lk[0] if len(lk) else n
    pn = []
    lock_px = min(opn[i_lock], -lockd) if i_lock < n else None
    lock_extra = r.spr_out + COMM + SLIP
    for tp in tps:
        hit_i = None
        if tp is not None:
            d = tp * r.atr15 + shift
            hit = np.nonzero(fav[:i_lock + 1] >= d)[0]
            hit = hit[hit < i_lock]
            if len(hit):
                hit_i = hit[0]
        if hit_i is not None:
            pn.append(tp * r.atr15 + shift - COMM)
        elif i_lock < n:
            pn.append(lock_px - COMM - lock_extra)
        else:
            pn.append(cls[-1] - COMM - SLIP)
    mae = float(min(adv[:min(i_lock, n - 1) + 1].min(), lock_px if lock_px is not None else 0.0))
    return float(np.mean(pn)), i_lock < n, mae


def _unit(r, u):
    if u.startswith("col:"):
        return float(getattr(r, u[4:]))
    return r.atr15 if u == "a15" else (r.atrd if u == "ad" else 1.0)


def entry_fills(R, r, plan):
    """Lista de tramos llenados [(frac, j0, px, fill_bar, t_fill)] segun el plan."""
    kind = plan.get("kind", "base")
    i0 = R["i_in"]; tt = R["tt"]
    if kind == "base" or len(tt) <= i0:
        return [(1.0, i0, r.px, False, r.t_in)]
    side = r.side
    if kind == "twap":
        out = []
        for k_min, fr in plan["levels"]:
            if k_min == 0:
                out.append((fr, i0, r.px, False, r.t_in)); continue
            j = int(np.searchsorted(tt, r.t_in - r.t_in % 60 + k_min * 60))
            if j >= len(tt):
                continue
            px = R["o"][j] + spread_at(tt[j]) + SLIP if side == 1 else R["o"][j] - SLIP
            out.append((fr, j, px, False, tt[j]))
        return out
    N = plan["N"] * 60
    t_end = r.t_in + N
    # velas candidatas: empiezan >= entrada y terminan <= vencimiento
    j_hi = int(np.searchsorted(tt, t_end - 300, side="right"))
    j_hi = max(j_hi, i0 + 1)
    pen = plan.get("pen", PEN)
    u = plan.get("u", "a15")
    out = []
    for x, fr in plan["levels"]:
        d = x * _unit(r, u)
        filled = None
        for j in range(i0, min(j_hi, len(tt))):
            sp = R["smax"][j]
            if kind == "limit":
                if side == 1:
                    lim = r.px - d
                    if R["o"][j] + spread_at(tt[j]) <= lim - pen:
                        filled = (j, R["o"][j] + spread_at(tt[j]), False); break
                    if R["l"][j] + sp <= lim - pen:
                        filled = (j, lim, True); break
                else:
                    lim = r.px + d
                    if R["o"][j] >= lim + pen:
                        filled = (j, R["o"][j], False); break
                    if R["h"][j] >= lim + pen:
                        filled = (j, lim, True); break
            else:   # stop de entrada (confirmacion a favor)
                if side == 1:
                    lv = r.px + d
                    if R["o"][j] + spread_at(tt[j]) >= lv:
                        filled = (j, R["o"][j] + spread_at(tt[j]) + SLIP, False); break
                    if R["h"][j] + sp >= lv:
                        filled = (j, lv + SLIP, True); break
                else:
                    lv = r.px - d
                    if R["o"][j] <= lv:
                        filled = (j, R["o"][j] - SLIP, False); break
                    if R["l"][j] <= lv:
                        filled = (j, lv - SLIP, True); break
        if filled is not None:
            j, px, fb = filled
            out.append((fr, j, px, fb, tt[j]))
        elif plan.get("fb", "lost") == "mkt":
            j = min(j_hi, len(tt) - 1)
            if j < len(tt) - 1:
                px = R["o"][j] + spread_at(tt[j]) + SLIP if side == 1 else R["o"][j] - SLIP
                out.append((fr, j, px, False, tt[j]))
    return out


def sim(E, raws, plan=None, legs=("big_one", "momentum", "nfp"), anchor=None):
    """Aplica el plan a las patas indicadas. Devuelve DataFrame tipo base_trades (pnl, locked, mae, R, fillf)."""
    plan = plan or {"kind": "base"}
    anchor = anchor or plan.get("anchor", "new")
    pn, lo, ma, ff = [], [], [], []
    for r, R in zip(E.itertuples(index=False), raws):
        p = plan if r.leg in legs else {"kind": "base"}
        fills = entry_fills(R, r, p)
        tot, lk, mae, frs = 0.0, False, 0.0, 0.0
        for fr, j0, px, fb, tf in fills:
            imp = (r.px - px) if r.side == 1 else (px - r.px)
            v, l_, m_ = ladder(R, r, j0, px, fb, imp, anchor)
            if not np.isfinite(v):
                continue
            sw = swap_cost(tf, r.t_out, r.side)
            tot += fr * (v + sw); frs += fr; lk = lk or l_; mae = min(mae, m_)
        pn.append(tot if frs > 0 else np.nan); lo.append(lk); ma.append(mae); ff.append(frs)
    T = E.copy()
    T["pnl"], T["locked"], T["mae"], T["fillf"] = pn, lo, ma, ff
    T["R"] = T.pnl / T.atrd
    return T[np.isfinite(T.pnl)].reset_index(drop=True)


def load():
    """(E, raws, B) de sel+val, con B = base reproducida por este simulador."""
    E = entries()
    E, raws = raw_cache(E, "e2")
    B = sim(E, raws)
    return E, raws, B


def _selfcheck():
    low_priority()
    E, raws, B = load()
    ref = _end_ok(pd.read_pickle(os.path.join(RESULTS, "opt_base_trades.pkl")))
    m = B.merge(ref[["t", "leg", "pnl"]], on=["t", "leg"], suffixes=("", "_ref"))
    dif = (m.pnl - m.pnl_ref).abs()
    print("operaciones", len(B), "ref", len(ref), "dif max $/oz", round(dif.max(), 6), "n dif>1e-6", int((dif > 1e-6).sum()))


if __name__ == "__main__":
    _selfcheck()
