"""Linea C (27-oct-2026): ESTRATEGIAS ALTERNATIVAS PARA LOS REGIMENES DONDE EL e2 NO RINDE.

Cada estrategia se construye como filas con el mismo formato que opt_base.entries() y se simula con el camino
intra-vela (trade_path) y la gestion de opt_base.leg_ladder (tercios por hora / TP en ATR15, candado a
-1 ATR_D, cierre a la hora). Costos reales: spread por minuto, comision, deslizamiento 0,05 en entrada a
mercado, salida por hora y candado, swap. SIN stop loss.

Familias (todas solo en los dias del regimen indicado; el regimen sale de opt_C_regimen.build_features(),
conocido antes de empezar el dia):
  S1 rango_mr : en rango (er20 bajo / adx bajo), a la hora h si el precio se alejo > k ATR_D del open de las
                01:00, se opera en contra (reversion a la media); salida a h+H o TP.
  S2 mom_fade : en rango, el Momentum 15:00 se da vuelta (va CONTRA el movimiento 01->15) en vez de seguirlo;
                variante que ademas opera los dias s=0.
  S3 volalta  : en vol alta, ventana alternativa del Momentum (15->18, 16->21, 15->19) y Big One corta (01->06).
  S4 bajista  : en regimen bajista (s=-2 o pendiente20 < x): Big One vendida 01->10, o venta EE.UU. 15->21.
  S5 riesgo   : VIX relativo alto (risk-off): compra 15->21 (refugio) / VIX bajo: nada.
Se evalua la cartera base + estrategia (o con la pata reemplazada) en 'sel'; cada variante se registra.

Correr:  .venv/Scripts/python -m bot_backtesting.fullsim.opt_C_estrategias
Salidas: results/opt_C_strat.pkl (grilla), results/opt_C_strat_rows.pkl (operaciones simuladas, cache)
"""
import os

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.opt_base import (BO_DELAY, RESULTS, SLIP, base_trades, compare, evaluate, low_priority, m15,
                                              register, run_trades, spread_at, swap_cost)
from bot_backtesting.fullsim.opt_C_regimen import _BASE, attach, build_features, quick, years_ratio

CACHE = os.path.join(RESULTS, "opt_C_strat_rows.pkl")


def _ok_day(d, D):
    return (d + 3) % 7 < 5 and d in D.index and np.isfinite(D.at[d, "atrd"])


def make_rows(leg, tod_in, tod_out, side_fn, w=1.0, bo=False):
    """Filas tipo entries(): entrada al open de la vela M15 de tod_in (segundos del dia), salida al cierre de la
    vela que termina en tod_out. side_fn(k, d) -> -1/+1/0 (0 = no operar)."""
    X, D = m15()
    T, O = X.time.values, X.open.values
    idx = pd.Series(np.arange(len(T)), index=T)
    rows = []
    for k in np.nonzero(T % 86400 == tod_in)[0]:
        d = int(T[k] // 86400)
        if not _ok_day(d, D) or not np.isfinite(X.atr15.iat[k]):
            continue
        ke = idx.get(d * 86400 + tod_out - 900)
        if ke is None:
            continue
        s = side_fn(k, d)
        if s == 0:
            continue
        rows.append(("big_one" if bo else leg, T[k], T[k] + (60 if bo else 0), T[ke] + 900, int(s), w, D.at[d, "s"], 0, D.at[d, "atrd"], X.atr15.iat[k],
                     O[k], k))
    E = pd.DataFrame(rows, columns=["leg", "t", "t_in", "t_out", "side", "w", "state", "ev", "atrd", "atr15",
                                    "mid0", "k15"])
    E["spr_in"] = spread_at(E.t_in.values)
    E["spr_out"] = spread_at(E.t_out.values - 60)
    E["px"] = np.where(E.side == 1, E.mid0 + E.spr_in + SLIP, E.mid0 - SLIP)
    if bo:
        E["px"] += E.side * BO_DELAY * E.atrd      # el retraso 01:01 cuenta siempre en contra
    E["swap"] = [swap_cost(a, b, s) for a, b, s in zip(E.t_in, E.t_out, E.side)]
    E["day"] = pd.to_datetime(E.t, unit="s").dt.normalize()
    return E


def dev_from_open(k, d):
    """(open de la vela k - open de las 01:00) / ATR_D."""
    X, D = m15()
    T, O = X.time.values, X.open.values
    k1 = np.searchsorted(T, d * 86400 + 3600)
    if k1 >= len(T) or T[k1] != d * 86400 + 3600:
        return np.nan
    return (O[k] - O[k1]) / D.at[d, "atrd"]


def strat_pool():
    """Todas las operaciones candidatas (todos los dias), simuladas una vez. Clave -> DataFrame con pnl."""
    if os.path.exists(CACHE):
        return pd.read_pickle(CACHE)
    pool = {}
    tps_set = {"t3": (None, 2.0, 3.0), "tp1": (None, 1.0, 2.0)}
    H = 3600
    # S1 reversion intradia: el lado se decide a la hora h; la magnitud se filtra despues (columna dev)
    for h in (10, 12, 16, 18):
        for dur in (3, 5):
            if h + dur > 23:
                continue
            E = make_rows(f"mr_{h}_{dur}", h * H, (h + dur) * H, lambda k, d: -np.sign(dev_from_open(k, d))
                          if np.isfinite(dev_from_open(k, d)) else 0)
            E["dev"] = [abs(dev_from_open(k, int(t // 86400))) for k, t in zip(E.k15, E.t)]
            for tn, tps in tps_set.items():
                pool[f"S1|h{h}|H{dur}|{tn}"] = run_trades(E, tps=tps)
    # S2 momentum dado vuelta (todos los dias con |ret 01->15| > 0,232 %); la tendencia se filtra despues
    def mom_side(k, d, sign=1):
        X, _ = m15()
        a = dev_from_open(k, d)
        if not np.isfinite(a):
            return 0
        T, O = X.time.values, X.open.values
        k1 = np.searchsorted(T, d * 86400 + 3600)
        r = (O[k] - O[k1]) / O[k1] * 100
        return int(sign * np.sign(r)) if abs(r) > 0.232 else 0
    for tn, tps in tps_set.items():
        pool[f"S2|fade|{tn}"] = run_trades(make_rows("mom_fade", 15 * H, 21 * H, lambda k, d: mom_side(k, d, -1)),
                                           tps=tps)
        pool[f"S2|follow|{tn}"] = run_trades(make_rows("mom_all", 15 * H, 21 * H, lambda k, d: mom_side(k, d, 1)),
                                             tps=tps)
    # S3 ventanas alternativas del Momentum (seguir) y Big One corta
    for a, b in ((15, 18), (16, 21), (15, 19), (17, 21)):
        pool[f"S3|mom_{a}_{b}"] = run_trades(make_rows(f"mom_{a}_{b}", a * H, b * H,
                                                       lambda k, d: mom_side(k, d, 1)))
    for b in (4, 6, 8, 10):                 # 10 = replica de la Big One (control)
        P = run_trades(make_rows("x", 1 * H, b * H, lambda k, d: 1, bo=True)); P["leg"] = f"bo_01_{b}"
        pool[f"S3|bo_01_{b:02d}"] = P
    # S4 bajista: Big One vendida / venta EE.UU.
    P = run_trades(make_rows("x", 1 * H, 10 * H, lambda k, d: -1, bo=True)); P["leg"] = "bo_short"
    pool["S4|bo_short"] = P
    pool["S4|ny_short"] = run_trades(make_rows("ny_short", 15 * H, 21 * H, lambda k, d: -1))
    # S5 refugio: compra 15->21
    pool["S5|ny_long"] = run_trades(make_rows("ny_long", 15 * H, 21 * H, lambda k, d: 1))
    pd.to_pickle(pool, CACHE)
    return pool


def regime_masks(T):
    """Mascaras de regimen sobre un DataFrame con caracteristicas adjuntas (attach)."""
    M = {}
    for th in (0.2, 0.25, 0.3, 0.35):
        M[f"er20<{th:g}"] = T.er20 < th
    for th in (18, 21, 24):
        M[f"adx<{th}"] = T.adx < th
    for th in (0.6, 0.7, 0.8):
        M[f"vpct>={th:g}"] = T.vpct >= th
    for th in (1.15, 1.3):
        M[f"rvr>={th:g}"] = T.rvr >= th
    M["hmm2_p>=0.5"] = T.hmm2_p >= 0.5
    M["hmm3==2"] = T.hmm3 == 2
    M["s==-2"] = T.state == -2
    M["s<=0"] = T.state <= 0
    for th in (-1.0, -0.5, 0.0):
        M[f"slope20<{th:g}"] = T.slope20 < th
    for th in (0.05, 0.15):
        M[f"vix_rel>={th:g}"] = T.vix_rel >= th
    for th in (20, 22):
        M[f"vix>={th}"] = T.vix >= th
    M["todos"] = pd.Series(True, T.index)
    return {k: v.fillna(False).values for k, v in M.items()}


def combine(B, S, w=1.0, replace=None, replace_mask_days=None):
    """Base + operaciones nuevas S (peso w). replace: pata de la base que se apaga en los dias de S."""
    B = B.copy()
    if replace is not None and len(S):
        days = set(S.day)
        if replace_mask_days is not None:
            days = replace_mask_days
        B.loc[B.leg.isin(replace) & B.day.isin(days), "w"] = 0.0
    S = S.copy()
    S["w"] = w
    cols = ["leg", "t", "t_out", "pnl", "atrd", "w", "day", "R"]
    return pd.concat([B[cols], S[cols]]).sort_values("t").reset_index(drop=True)


def main():
    low_priority()
    B = base_trades()
    _BASE["B"] = B
    F = build_features()
    pool = strat_pool()
    rows = []

    def run(lab, C, params):
        r = quick(C, lab)
        register("C", lab, r, params)
        rows.append(dict(label=lab, **params, **{k: r[k] for k in ("mar_c", "mar_ratio", "cagr_c", "dd_c",
                                                                    "peor_dia_c", "peor_mes_c", "n_c", "pasa")}))

    for key, P in pool.items():
        P = attach(P, F)
        Ms = regime_masks(P)
        fam = key.split("|")[0]
        # filtros de magnitud para S1
        devs = (0.3, 0.5, 0.7) if fam == "S1" else (None,)
        for dv in devs:
            Q = P if dv is None else P[P.dev > dv]
            Mq = regime_masks(Q)
            for mk, m in Mq.items():
                S = Q[m]
                if key.startswith("S2|follow"):
                    S = S[S.state == 0]          # el Momentum de la base ya cubre s=+-2: aqui solo s=0
                if len(S) < 15:
                    continue
                for w in (0.5, 1.0):
                    lab = f"C/strat2 {key} dev>{dv} reg:{mk} w{w:g}"
                    if fam == "S3" and key.startswith("S3|mom"):
                        # reemplaza al Momentum de la base en los dias del regimen
                        days = set(P.day[Ms[mk]])
                        C = combine(B, S[S.day.isin(set(B.day[B.leg == 'momentum']))], w,
                                    replace=["momentum"], replace_mask_days=days)
                    elif key.startswith("S3|bo"):
                        days = set(P.day[Ms[mk]])
                        bw = B[B.leg == "big_one"].set_index("day").w
                        S2 = S.copy(); S2 = S2[S2.day.isin(bw.index)]
                        C = combine(B, S2, w, replace=["big_one"], replace_mask_days=days)
                        # mismo peso que la Big One que reemplaza
                        sel = C.leg.str.startswith("bo_")
                        C.loc[sel, "w"] = C.loc[sel, "day"].map(bw).values * w
                    elif fam == "S2" and "fade" in key:
                        C = combine(B, S, w, replace=["momentum"])
                    elif key.startswith("S4|bo_short"):
                        C = combine(B, S, w, replace=["big_one"])
                    else:
                        C = combine(B, S, w)
                    run(lab, C, dict(fam=fam, key=key, dev=dv, reg=mk, w=w, n_new=len(S)))
        print("listo", key, flush=True)
    G = pd.DataFrame(rows)
    G.to_pickle(os.path.join(RESULTS, "opt_C_strat.pkl"))
    pd.set_option("display.width", 250)
    print(G.sort_values("mar_ratio", ascending=False).head(40).round(3).to_string())
    print("variantes:", len(G))


if __name__ == "__main__":
    main()
