"""Linea A (mejores salidas) - piezas comunes. Solo simulacion, sin MT5, 2026 excluido.

Que hace:
  * cache_paths(E, tag): calcula UNA vez el camino intra-vela (trade_path de opt_base) de cada operacion de
    sel+val, alargado EXT horas despues de la hora de salida (para probar extensiones), y lo guarda en
    results/optA_paths_<tag>.pkl. Las operaciones de 2026 se descartan antes de calcular nada.
  * manage(P, r, rules, ...): gestor generico con la logica de leg_ladder (candado, lado en contra primero
    dentro de cada vela) pero con una regla de salida por tercio: 'time', 'tp', 'trail' (trailing que solo
    cierra en ganancia neta), 'sar', 'exh' (agotamiento), 'stall' (estancamiento) y extension de la hora.
  * run_cached(cache, rules, ...): aplica el gestor a todas las operaciones cacheadas y devuelve el
    DataFrame listo para compare() (pnl, mae, locked, R, t_out real de la ultima salida).

Restriccion dura: ninguna regla cierra en perdida antes de la hora. Los stops de ganancia tienen un piso
= comision + deslizamiento + swap (si cruza la noche) + 0,10 $/oz de margen, asi que su nivel asegura P&L
neto > 0. Unica excepcion posible: hueco de precio por debajo del nivel (se llena al open, conservador).
Uso: libreria (from bot_backtesting.fullsim.opt_A_common import *). Autocomprobacion:
  .venv/Scripts/python -m bot_backtesting.fullsim.opt_A_common
"""
import os
import pickle

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.opt_base import (COMM, SLIP, RESULTS, VAL, SEL, entries, leg_ladder, low_priority,
                                              m15, swap_cost, trade_path, random_entries)

EXT = 6 * 3600          # horas extra de camino guardadas despues de la hora de salida
FLOOR_PAD = 0.10        # $/oz de margen sobre los costos para el piso de los stops en ganancia
CFG = {"stop_slip": 0.0, "barclose": False}
# barclose=True: el stop de ganancia se mueve SOLO al cierre de cada vela (con el maximo de las velas ya cerradas);
# dentro de la vela el nivel queda fijo -> simulacion exacta con velas de esa resolucion (sin suponer el orden
# interno). barclose=False: ademas se permite que el cierre de la vela cruce el nivel recalculado con su maximo
# (supone maximo antes del cierre; optimista con velas gruesas porque ignora retrocesos dentro de la vela).  # deslizamiento EXTRA de las salidas por stop/mercado en ganancia (prueba de robustez)


def _end_ok(E):
    """Solo sel+val: 2026 guardado."""
    return E[(E.t >= SEL[0].timestamp()) & (E.t < VAL[1].timestamp())].reset_index(drop=True)


def cache_paths(E, tag, force=False):
    fp = os.path.join(RESULTS, f"optA_paths_{tag}.pkl")
    if os.path.exists(fp) and not force:
        with open(fp, "rb") as f:
            E, Ps = pickle.load(f)
        return list(zip(E.itertuples(index=False), Ps))
    E = _end_ok(E)
    X, _ = m15()
    XT, XA = X.time.values, X.atr15.values
    out = []
    for r in E.itertuples(index=False):
        rr = r._replace(t_out=r.t_out + EXT)
        P = trade_path(rr)
        P["nb"] = int(np.searchsorted(P["time"], r.t_out))
        j = np.clip(np.searchsorted(XT, P["time"], side="right") - 1, 0, len(XT) - 1)
        P["a15"] = XA[j]                                  # ATR15 vivo (de la vela M15 en curso, conocido al abrirla)
        out.append(P)
    with open(fp, "wb") as f:
        pickle.dump((E, out), f)
    return list(zip(E.itertuples(index=False), out))


def cache_paths_m15(E, tag, force=False):
    """Igual que cache_paths pero con velas M15 del broker (resolucion gruesa): prueba de sensibilidad."""
    fp = os.path.join(RESULTS, f"optA_paths15_{tag}.pkl")
    if os.path.exists(fp) and not force:
        with open(fp, "rb") as f:
            E, Ps = pickle.load(f)
        return list(zip(E.itertuples(index=False), Ps))
    E = _end_ok(E)
    X, _ = m15()
    XT, XO, XH, XL, XC, XA = (X[c].values for c in ("time", "open", "high", "low", "close", "atr15"))
    out = []
    for r in E.itertuples(index=False):
        i0, i1 = np.searchsorted(XT, r.t), np.searchsorted(XT, r.t_out + EXT)
        o, h, l, c = XO[i0:i1], XH[i0:i1], XL[i0:i1], XC[i0:i1]
        sp = r.spr_out
        if r.side == 1:
            fav, adv, opn, cls = h - r.px, l - r.px, o - r.px, c - r.px
        else:
            fav, adv, opn, cls = r.px - (l + sp), r.px - (h + sp), r.px - (o + sp), r.px - (c + sp)
        P = dict(time=XT[i0:i1], fav=fav, adv=adv, opn=opn, cls=cls, dur=np.full(i1 - i0, 900), a15=XA[i0:i1])
        P["nb"] = int(np.searchsorted(P["time"], r.t_out))
        out.append(P)
    with open(fp, "wb") as f:
        pickle.dump((E, out), f)
    return list(zip(E.itertuples(index=False), out))


# ------------------------------------------------------------------ gestor generico
def _unit(r, u):
    return r.atr15 if u == "a15" else r.atrd


def _stop_exit(lv_prev, lv_new, P, i0, i1, floor):
    """Primer cruce de un stop de ganancia en [i0, i1). lv_prev[i]: nivel vigente al abrir la vela i (de velas
    anteriores); lv_new[i]: nivel tras actualizar con el maximo de la vela i (el cierre de la vela es posterior).
    Devuelve (indice, precio de llenado) o (None, None)."""
    adv, cls, opn = P["adv"][i0:i1], P["cls"][i0:i1], P["opn"][i0:i1]
    a = lv_prev[i0:i1]; b = lv_new[i0:i1]
    h1 = np.isfinite(a) & (adv <= a)
    h2 = np.isfinite(b) & (cls <= b) & (not CFG["barclose"])
    h = np.nonzero(h1 | h2)[0]
    if not len(h):
        return None, None
    k = h[0]
    if h1[k]:
        px = min(opn[k], a[k]) if opn[k] < a[k] else a[k]     # hueco: al open (conservador)
    else:
        px = b[k]
    return i0 + k, px


def _trail_levels(P, r, n, act, dist, u, floor, tight=0.0, live=False, cap=None):
    """Niveles de un trailing: se arma cuando el maximo favorable llega a act*U; nivel = max(pico - dist*U(t), piso).
    tight: la distancia se encoge linealmente con el tiempo transcurrido (dist*(1 - tight*frac)).
    live: U = ATR15 vivo (Chandelier) en vez del ATR fijo de la entrada."""
    U0 = _unit(r, u)
    fav = P["fav"][:n]
    pk = np.maximum.accumulate(fav)
    if live and u == "a15":
        Ut = P["a15"][:n]
    else:
        Ut = np.full(n, U0)
    frac = np.arange(n) / max(n - 1, 1)
    d = dist * Ut * np.maximum(1 - tight * frac, 0.15)
    armed = pk >= act * U0
    lv_new = np.where(armed, np.maximum(pk - d, floor), np.nan)
    lv_prev = np.r_[np.nan, lv_new[:-1]]
    return lv_prev, lv_new


def _sar_levels(P, r, n, act, u, floor, af0=0.02, step=0.02, afmax=0.2):
    """Parabolico (SAR) sobre el camino favorable, armado desde act*U, nunca por debajo del piso."""
    U0 = _unit(r, u)
    fav, adv = P["fav"][:n], P["adv"][:n]
    lv_new = np.full(n, np.nan)
    on, sar, ep, af = False, 0.0, 0.0, af0
    for i in range(n):
        if not on:
            if fav[i] >= act * U0:
                on, ep, af = True, fav[i], af0
                sar = max(floor, min(adv[max(0, i - 2):i + 1].min(), fav[i] - act * U0))
                lv_new[i] = max(sar, floor)
            continue
        if fav[i] > ep:
            ep = fav[i]; af = min(af + step, afmax)
        sar = sar + af * (ep - sar)
        lv_new[i] = max(sar, floor)
    lv_prev = np.r_[np.nan, lv_new[:-1]]
    return lv_prev, lv_new


def manage(P, r, rules=({"k": "time"}, {"k": "tp", "m": 2.0}, {"k": "tp", "m": 3.0}), lock_k=1.0, fracs=None,
           ext=None, undo_lock=None):
    """rules: una regla por tercio. Claves:
       time                                  -> cierra a la hora
       tp   m, u('a15'|'ad')                 -> objetivo limite m*U
       trail act, dist, u, tight, live, tp   -> trailing en ganancia (tp opcional: objetivo ademas)
       sar  act, u, af0, step, afmax          -> parabolico en ganancia
       exh  act, u, kr, look                  -> tras +act*U, cierra al cierre de la 1a vela fina contra el
                                                 movimiento con rango > kr x media de las 'look' previas (si gana)
       stall act, u, nbars                    -> tras +act*U, si nbars velas sin nuevo maximo, cierra (si gana)
       early m, u                            -> si a la hora va en ganancia pero dejo de subir... (no usado)
    ext: dict(h=horas, dist=, u=, need_s=bool, minp=) -> a la hora, si el tercio (aun abierto) va en ganancia
         > minp*U (y la tendencia s acompana si need_s) sigue hasta h horas con trailing en ganancia.
    undo_lock: dict(back=x) -> REQUIERE CERRAR EN PERDIDA: tras el candado, si el precio vuelve a -back*ATR_D,
         cierra la cobertura (en rojo) y el tercio queda desnudo hasta la hora (con nuevo candado a -lock_k).
    Devuelve (pnl $/oz, mae, locked, t_last_exit, detalle)."""
    nb = P["nb"]
    if nb == 0:
        return np.nan, np.nan, False, r.t_out, []
    ntot = len(P["fav"])
    fracs = fracs or [1 / len(rules)] * len(rules)
    lockd = lock_k * r.atrd
    lk = np.nonzero(P["adv"][:nb] <= -lockd)[0]
    i_lock = lk[0] if len(lk) else nb
    floor = COMM + SLIP + FLOOR_PAD + max(0.0, -r.swap)
    lock_px = min(P["opn"][i_lock], -lockd) if i_lock < nb else None
    lock_extra = r.spr_out + COMM + SLIP
    tend = P["time"] + P["dur"]
    pnls, kinds, texit = [], [], []
    for rule in rules:
        k = rule["k"]
        u = rule.get("u", "a15")
        U = _unit(r, u)
        # ventana donde la regla puede cerrar: hasta el candado (incluido para stops: su nivel > -lockd)
        lim_stop = min(i_lock + 1, nb)
        res = None   # (indice, pnl_bruto_sin_comm, tipo)
        if k == "tp":
            hit = np.nonzero(P["fav"][:min(i_lock, nb)] >= rule["m"] * U)[0]
            if len(hit):
                res = (hit[0], rule["m"] * U + SLIP, "tp")       # limite: sin deslizamiento (se resta abajo)
        elif k in ("trail", "sar"):
            if k == "trail":
                lp, ln = _trail_levels(P, r, nb, rule["act"], rule["dist"], u, floor, rule.get("tight", 0.0),
                                       rule.get("live", False))
            else:
                lp, ln = _sar_levels(P, r, nb, rule["act"], u, floor, rule.get("af0", .02), rule.get("step", .02),
                                     rule.get("afmax", .2))
            i, px = _stop_exit(lp, ln, P, 0, lim_stop, floor)
            if rule.get("tp") is not None:
                hit = np.nonzero(P["fav"][:min(i_lock, nb)] >= rule["tp"] * U)[0]
                if len(hit) and (i is None or hit[0] < i):
                    i, px = None, None
                    res = (hit[0], rule["tp"] * U + SLIP, "tp")
            if i is not None:
                res = (i, px, "trail")
        elif k in ("exh", "stall"):
            fav, cls = P["fav"][:lim_stop], P["cls"][:lim_stop]
            if len(fav):
                pk = np.maximum.accumulate(fav)
                armed = pk >= rule["act"] * U
                if k == "exh":
                    rng = P["fav"][:lim_stop] - P["adv"][:lim_stop]
                    look = rule.get("look", 12)
                    mr = pd.Series(rng).rolling(look, min_periods=3).mean().shift(1).values
                    against = P["cls"][:lim_stop] < P["opn"][:lim_stop]
                    cond = armed & against & (rng > rule["kr"] * mr) & (cls - SLIP > floor - SLIP)
                else:
                    nbar = rule["nbars"]
                    last_new = np.zeros(len(fav), int)
                    for i in range(1, len(fav)):
                        last_new[i] = i if fav[i] > pk[i - 1] else last_new[i - 1]
                    cond = armed & (np.arange(len(fav)) - last_new >= nbar) & (cls > floor)
                cond[min(i_lock, len(cond) - 1):] = False if i_lock < nb else cond[min(i_lock, len(cond) - 1):]
                h = np.nonzero(cond)[0]
                if len(h):
                    res = (h[0], cls[h[0]], "mkt")
        # ----- resultado del tercio
        if res is not None:
            i, gross, kind = res
            p = gross - COMM - SLIP - (CFG["stop_slip"] if kind != "tp" else 0.0)
            te = tend[i]
        elif i_lock < nb:
            if undo_lock:
                p, te, kind = _undo(P, r, nb, i_lock, lock_px, lockd, undo_lock)
            else:
                p, te, kind = lock_px - COMM - lock_extra, tend[nb - 1], "lock"
        else:
            p, te, kind = P["cls"][nb - 1] - COMM - SLIP, tend[nb - 1], "time"
            if ext and k != "time_only":
                p, te, kind = _extend(P, r, nb, ntot, floor, ext, p, te)
        sw = swap_cost(r.t_in, te, r.side) if te > r.t_out else r.swap
        pnls.append(p + sw); kinds.append(kind); texit.append(te)
    pnl = float(np.dot(fracs, pnls))
    mae = float(min(P["adv"][:min(i_lock, nb - 1) + 1].min(), lock_px if lock_px is not None else 0.0))
    return pnl, mae, i_lock < nb, max(max(texit), r.t_out), list(zip(kinds, pnls))


def _extend(P, r, nb, ntot, floor, ext, p_time, te_time):
    """Extension de la hora de salida con trailing en ganancia (el tercio no tiene candado: va en ganancia)."""
    if nb >= ntot:
        return p_time, te_time, "time"
    U = _unit(r, ext.get("u", "a15"))
    cur = P["cls"][nb - 1]
    if cur < ext.get("minp", 0.0) * U or cur <= floor:
        return p_time, te_time, "time"
    if ext.get("need_s") and not (r.state == 2 * r.side):
        return p_time, te_time, "time"
    tend = P["time"] + P["dur"]
    j1 = min(ntot, nb + int(np.searchsorted(P["time"][nb:], r.t_out + ext["h"] * 3600)))
    # el nuevo swap por cruzar la noche se suma al piso
    fl = floor
    if swap_cost(r.t_in, r.t_out + ext["h"] * 3600, r.side) < r.swap:
        fl = floor + (r.swap - swap_cost(r.t_in, r.t_out + ext["h"] * 3600, r.side))
    fav = P["fav"][nb - 1:j1]
    pk = np.maximum.accumulate(np.r_[cur, fav[1:]])
    lv_new = np.maximum(pk - ext["dist"] * U, fl)
    sub = {k: P[k][nb - 1:j1] for k in ("adv", "cls", "opn")}
    lv_prev = np.r_[np.nan, lv_new[:-1]]
    i, px = _stop_exit(lv_prev, lv_new, sub, 1, len(fav), fl)
    if i is not None:
        return px - COMM - SLIP, tend[nb - 1 + i], "ext_trail"
    return P["cls"][j1 - 1] - COMM - SLIP, tend[j1 - 1], "ext_time"


def _undo(P, r, nb, i_lock, lock_px, lockd, cfg):
    """REQUIERE CERRAR EN PERDIDA. Tras el candado, si el precio vuelve a -back*ATR_D se cierra la cobertura
    (su resultado L + back es negativo: perdida realizada) y el tercio sigue desnudo; si vuelve a caer a
    -lock_k*ATR_D se cubre otra vez. Devuelve (pnl, t_salida, tipo)."""
    back = cfg["back"] * r.atrd
    lock_extra = r.spr_out + COMM + SLIP
    L, i, realized, kind = lock_px, i_lock, -lock_extra, "lock"
    tend_last = P["time"][nb - 1] + P["dur"][nb - 1]
    while True:
        rec = np.nonzero(P["fav"][i + 1:nb] >= -back)[0]
        if not len(rec):
            return L + realized - COMM, tend_last, kind
        j = i + 1 + rec[0]
        realized += (L + back) - SLIP                  # cierre de la cobertura en rojo
        kind = "undo"
        lk = np.nonzero(P["adv"][j + 1:nb] <= -lockd)[0]
        if not len(lk):
            return P["cls"][nb - 1] - COMM - SLIP + realized, tend_last, kind
        i = j + 1 + lk[0]
        L = min(P["opn"][i], -lockd)
        realized -= lock_extra


def run_cached(cache, rules=None, lock_k=1.0, size_lock=True, **kw):
    """Aplica manage a todas las operaciones cacheadas. Si size_lock, el ATR de dimensionar = lock_k*ATR_D
    (riesgo igual por candado: lote = riesgo/distancia real del candado)."""
    rows = []
    for r, P in cache:
        if rules is None:
            res = manage(P, r, lock_k=lock_k, **kw)
        else:
            res = manage(P, r, rules=rules, lock_k=lock_k, **kw)
        d = r._asdict()
        d.update(pnl=res[0], mae=res[1], locked=res[2], t_out=res[3], kinds="|".join(k for k, _ in res[4]))
        rows.append(d)
    T = pd.DataFrame(rows)
    if size_lock and lock_k != 1.0:
        T["atrd_real"] = T.atrd
        T["atrd"] = T.atrd * lock_k
    T["R"] = T.pnl / T.atrd
    return T[np.isfinite(T.pnl)].reset_index(drop=True)


BASE_RULES = ({"k": "time"}, {"k": "tp", "m": 2.0}, {"k": "tp", "m": 3.0})


def by_leg(rules_by_leg):
    """Envoltorio: reglas distintas por pata. rules_by_leg = {'big_one': rules, 'momentum': ..., 'nfp': ...}."""
    def f(P, r, **kw):
        return manage(P, r, rules=rules_by_leg.get(r.leg, BASE_RULES), **kw)
    return f


def run_fn(cache, fn, lock_k=1.0, **kw):
    rows = []
    for r, P in cache:
        res = fn(P, r, lock_k=lock_k, **kw)
        d = r._asdict()
        d.update(pnl=res[0], mae=res[1], locked=res[2], t_out=res[3], kinds="|".join(k for k, _ in res[4]))
        rows.append(d)
    T = pd.DataFrame(rows)
    T["R"] = T.pnl / T.atrd
    return T[np.isfinite(T.pnl)].reset_index(drop=True)


def years(C, B, ys=(2023, 2024)):
    """MAR por año dentro de sel (candidato / base)."""
    from bot_backtesting.fullsim.opt_base import evaluate
    out = {}
    for y in ys:
        per = (pd.Timestamp(f"{y}-01-01"), pd.Timestamp(f"{y + 1}-01-01"))
        mc, mb = evaluate(C, per), evaluate(B, per)
        out[y] = (mc["mar"], mb["mar"], mc["mar"] / mb["mar"])
    return out


def _selfcheck():
    low_priority()
    import time
    t0 = time.time()
    E = entries()
    C = cache_paths(E, "e2")
    print("cache", len(C), f"{time.time()-t0:.0f}s")
    # reproduce leg_ladder
    d = []
    for r, P in C[:400]:
        Pb = {k: (v[:P["nb"]] if isinstance(v, np.ndarray) else v) for k, v in P.items()}
        a = leg_ladder(Pb, r)[0]
        b = manage(P, r)[0]
        d.append(a - b)
    print("max |leg_ladder - manage|:", np.nanmax(np.abs(d)))
    T = run_cached(C, BASE_RULES)
    from bot_backtesting.fullsim.opt_base import evaluate
    for p in ("sel", "val"):
        print(p, {k: round(float(v), 3) for k, v in evaluate(T, p).items()})
    print(f"{time.time()-t0:.0f}s")


if __name__ == "__main__":
    _selfcheck()
