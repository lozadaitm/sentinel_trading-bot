"""Linea E, paso 1: construir las patas candidatas (hipotesis fijadas de antemano, con mecanismo en la literatura o
en pruebas previas) y cribarlas COMO PATA DE CARTERA en 'sel' (2022-10 -> 2024-12). Todo se registra.

Cada pata usa la gestion e2 (tercios hora / TP 2 / TP 3 ATR15, candado -1 ATR_D, cierre a la hora) en su
propio simbolo; 1 R = distancia del candado. Otros simbolos: velas M15 del broker (opt_E_common.sim);
oro: camino fino M5 de opt_base (run_trades). Nada entra entre 00:00 y 01:05 servidor.

Hipotesis (grupo -> patas):
  FX fix (Krohn, Mueller y Whelan 2024: el dolar se aprecia antes de los fixes y se deprecia despues):
     fx_lon_pre   dolar comprado 60 min antes del fix de Londres (16:00 Londres) -> fix; cesta de 7 pares
     fx_lon_post  dolar vendido del fix -> fix + 120 min; cesta
     fx_tk_pre / fx_tk_post   igual con el fix de Tokio (09:55 JST)
  FX hora local (Breedon y Ranaldo 2013: cada divisa se deprecia en su propio horario):
     fx_tod_eur  EUR, GBP, CHF vendidos 09:00 -> 13:00 servidor;  fx_tod_asia JPY, AUD, NZD vendidos 02:00 -> 08:00;
     fx_tod_us   USD vendido 15:00 -> 21:00 (cesta)
  Indices EE.UU. (SP500, NAS100, DJ30, US2000):
     idx_night   compra 23:00 (cierre cash) -> 16:15 del dia siguiente (deriva nocturna; cruza el rollover, swap)
     idx_euopen  compra 09:00 -> 10:00 (la deriva nocturna se concentra en la apertura europea)
     idx_gao     signo (cierre previo 22:45 -> 17:00) -> opera 22:30 -> 23:00 (Gao et al. 2018)
     idx_balt    signo (16:30 -> 22:30) -> opera 22:30 -> 23:00 (Baltussen et al. 2021)
     idx_tom     compra 22:45 del ultimo dia habil del mes -> 22:45 del 3er dia habil (cambio de mes)
     idx_prefomc compra 21:00 del dia previo al FOMC -> 20:45 del dia del FOMC (Lucca y Moench 2015)
     nas_mom     NAS100 13:00 -> 18:00 en el signo de 02:00 -> 13:00 si |ret| > 0,5 desv. y s != 0 (banco previo)
  Otros: jpy_mom (USDJPY 10:00 -> 15:00, misma regla; banco previo), oil_eia (USOUSD miercoles: signo 17:30 ->
     17:45 y sigue hasta 20:45), xag_bigone (plata 01:15 -> 10:00 comprada, peso 1 si s=+2 si no 0,5),
     btc_weekend (BTC comprado viernes 22:00 -> lunes 00:45; poca historia).
  Oro (ventanas nuevas, camino M5): g_ny_short (venta 16:30 -> 20:30), g_ny_short_nomom (igual, solo dias sin
     Momentum), g_evening (compra 21:00 -> 23:45), g_evening_follow (21:00 -> 23:45 en el sentido 15 -> 21),
     g_pmfix (venta 16:45 -> 17:30), g_balt (signo 01:00 -> 20:00, opera 20:00 -> 20:30), g_lbma_am
     (venta 12:15 -> 12:45; control: ya se sabia negativa en 2022-24).
Criba (en sel, peso 0,5 del riesgo e2 por operacion; cestas reparten ese peso entre sus simbolos):
  R medio por año (2023 y 2024), correlacion diaria con e2, MAR de la cartera e2 + pata vs base.
Correr:  .venv/Scripts/python -m bot_backtesting.fullsim.opt_E_patas
Salidas: results/opt_E_frames.pkl (operaciones de cada pata, ambos lados), results/opt_E_screen.csv
"""
import os
import pickle
import sys
import time

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.opt_base import (RESULTS, SEL, VAL, entries, run_trades, register, low_priority, m15)
from bot_backtesting.fullsim.opt_E_common import (Sym, END, leg_frame, gold_rows, base, as_rows, gold_as_rows,
                                                  combine, compare_mix, corr_daily, london_fix_server, tokyo_server,
                                                  floor15, weekdays, year_R)

FR = os.path.join(RESULTS, "opt_E_frames.pkl")
PAIRS = {"EURUSD+": -1, "GBPUSD+": -1, "AUDUSD+": -1, "NZDUSD+": -1, "USDJPY+": 1, "USDCHF+": 1, "USDCAD+": 1}
IDX = ("SP500", "NAS100", "DJ30", "US2000")
H = 3600


def days_of(S):
    return weekdays(S, SEL[0] - pd.Timedelta(days=5), VAL[1])


# ------------------------------------------------------------------ constructores de planes
def plan_fix(S, usd_side, where, pre):
    out = []
    for d in days_of(S):
        fx = london_fix_server(d * 86400) if where == "lon" else tokyo_server(d * 86400)
        f0 = floor15(fx)
        if pre:
            out.append((f0 - H, f0, usd_side))
        else:
            out.append((f0 + (0 if where == "lon" else 900), f0 + (0 if where == "lon" else 900) + 2 * H, -usd_side))
    return out


def plan_fixed(S, h_in, h_out, side, next_day=False, dows=None):
    out = []
    for d in days_of(S):
        if dows is not None and (d + 3) % 7 not in dows:
            continue
        t0 = d * 86400 + int(h_in * H)
        t1 = (d + 1) * 86400 + int(h_out * H) if next_day else d * 86400 + int(h_out * H)
        if next_day and (d + 3) % 7 == 4:              # viernes -> lunes
            t1 += 2 * 86400
        out.append((t0, t1, side))
    return out


def plan_signal(S, sig_from, sig_to, h_in, h_out, prev_close=False, thr_sd=0.0, need_trend=False):
    """lado = signo del retorno entre sig_from y sig_to (horas). prev_close: sig_from es la vela del dia anterior."""
    out, hist = [], []
    days = days_of(S)
    for i, d in enumerate(days):
        if prev_close:
            if i == 0:
                continue
            ka = S.k_at(days[i - 1] * 86400 + int(sig_from * H))
            pa = S.C[ka] if ka is not None else None
        else:
            ka = S.k_at(d * 86400 + int(sig_from * H))
            pa = S.O[ka] if ka is not None else None
        kb = S.k_at(d * 86400 + int(sig_to * H))
        if pa is None or kb is None:
            continue
        r = S.O[kb] / pa - 1
        sd = np.std(hist[-250:]) if len(hist) >= 60 else None
        hist.append(r)
        if r == 0 or (thr_sd > 0 and (sd is None or abs(r) <= thr_sd * sd)):
            continue
        if need_trend and (d not in S.D.index or not np.isfinite(S.D.at[d, "s"]) or S.D.at[d, "s"] == 0):
            continue
        out.append((d * 86400 + int(h_in * H), d * 86400 + int(h_out * H), int(np.sign(r))))
    return out


def plan_tom(S):
    days = days_of(S)
    out = []
    m = pd.Series(pd.to_datetime(days * 86400, unit="s").to_period("M"))
    for i in range(len(days) - 3):
        if m[i] != m[i + 1]:                            # days[i] = ultimo dia habil del mes
            out.append((days[i] * 86400 + int(22.75 * H), days[i + 3] * 86400 + int(22.75 * H), 1))
    return out


def plan_prefomc(S):
    E = pd.read_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "events_us.csv"))
    fd = (pd.to_datetime(E[E.event == "FOMC"].date) - pd.Timestamp("1970-01-01")).dt.days.values
    days = set(days_of(S).tolist())
    out = []
    for d in fd:
        p = d - 1
        while (p + 3) % 7 >= 5:
            p -= 1
        if p in days and d in days:
            out.append((p * 86400 + 21 * H, d * 86400 + int(20.75 * H), 1))
    return out


def plan_eia(S):
    out = []
    for d in days_of(S):
        if (d + 3) % 7 != 2:
            continue
        ka, kb = S.k_at(d * 86400 + int(17.5 * H)), S.k_at(d * 86400 + int(17.75 * H))
        if ka is None or kb is None or S.O[kb] == S.O[ka]:
            continue
        out.append((d * 86400 + int(17.75 * H), d * 86400 + int(20.75 * H), int(np.sign(S.O[kb] - S.O[ka]))))
    return out


def plan_btc(S):
    out = []
    for d in days_of(S):
        if (d + 3) % 7 == 4:
            out.append((d * 86400 + 22 * H, (d + 3) * 86400 + int(0.75 * H), 1))
    return out


# ------------------------------------------------------------------ oro
def gold_plan(h_in, h_out, side_fn):
    X, D = m15()
    out = []
    days = sorted(set((X.time.values // 86400).tolist()))
    T = pd.Series(X.open.values, index=X.time.values)
    for d in days:
        if (d + 3) % 7 >= 5 or d * 86400 < (SEL[0] - pd.Timedelta(days=5)).timestamp() or d * 86400 >= END:
            continue
        s = side_fn(d, T, D)
        if s:
            out.append((d * 86400 + int(h_in * H), d * 86400 + int(h_out * H), s))
    return out


def gold_frame(leg, plan):
    """Ambos lados para el oro: corre run_trades con lado +1 y -1."""
    E = gold_rows(leg, plan)
    if E.empty:
        return None
    El = E.copy(); El["side"] = 1
    Es = E.copy(); Es["side"] = -1
    from bot_backtesting.fullsim.opt_base import SLIP
    for Z in (El, Es):
        Z["px"] = np.where(Z.side == 1, Z.mid0 + Z.spr_in + SLIP, Z.mid0 - SLIP)
        from bot_backtesting.fullsim.opt_base import swap_cost
        Z["swap"] = [swap_cost(a, b, s) for a, b, s in zip(Z.t_in, Z.t_out, Z.side)]
    Rl = run_trades(El).set_index("t"); Rs = run_trades(Es).set_index("t")
    G = E.set_index("t")
    G = G.join(Rl[["pnl", "locked"]].rename(columns={"pnl": "pnl_long", "locked": "lk_l"})).join(
        Rs[["pnl", "locked"]].rename(columns={"pnl": "pnl_short", "locked": "lk_s"}))
    G = G.reset_index().dropna(subset=["pnl_long", "pnl_short"])
    G["pnl"] = np.where(G.side == 1, G.pnl_long, G.pnl_short)
    G["locked"] = np.where(G.side == 1, G.lk_l, G.lk_s).astype(bool)
    G["R"] = G.pnl / G.atrd; G["R_long"] = G.pnl_long / G.atrd; G["R_short"] = G.pnl_short / G.atrd
    G["sym"] = "XAUUSD+"
    return G


def build_all():
    if os.path.exists(FR):
        with open(FR, "rb") as fh:
            return pickle.load(fh)
    L = {}
    t0 = time.time()

    def add(name, frames):
        frames = [f for f in frames if f is not None and len(f)]
        L[name] = frames
        print(f"  {name:20s} {sum(len(f) for f in frames):6d} operaciones ({time.time() - t0:.0f}s)", flush=True)

    for where in ("lon", "tk"):
        for pre in (True, False):
            nm = f"fx_{where}_{'pre' if pre else 'post'}"
            add(nm, [leg_frame(Sym(p), plan_fix(Sym(p), s, where, pre), f"{nm}:{p}") for p, s in PAIRS.items()])
    tod = {"fx_tod_eur": ({"EURUSD+": -1, "GBPUSD+": -1, "USDCHF+": 1}, 9, 13),
           "fx_tod_asia": ({"USDJPY+": 1, "AUDUSD+": -1, "NZDUSD+": -1}, 2, 8),
           "fx_tod_us": ({k: -v for k, v in PAIRS.items()}, 15, 21)}
    for nm, (pp, a, b) in tod.items():
        add(nm, [leg_frame(Sym(p), plan_fixed(Sym(p), a, b, s), f"{nm}:{p}") for p, s in pp.items()])
    add("idx_night", [leg_frame(Sym(s), plan_fixed(Sym(s), 23, 16.25, 1, next_day=True), f"idx_night:{s}") for s in IDX])
    add("idx_euopen", [leg_frame(Sym(s), plan_fixed(Sym(s), 9, 10, 1), f"idx_euopen:{s}") for s in IDX])
    add("idx_gao", [leg_frame(Sym(s), plan_signal(Sym(s), 22.75, 17, 22.5, 23, prev_close=True), f"idx_gao:{s}") for s in IDX])
    add("idx_balt", [leg_frame(Sym(s), plan_signal(Sym(s), 16.5, 22.5, 22.5, 23), f"idx_balt:{s}") for s in IDX])
    add("idx_tom", [leg_frame(Sym(s), plan_tom(Sym(s)), f"idx_tom:{s}") for s in IDX])
    add("idx_prefomc", [leg_frame(Sym(s), plan_prefomc(Sym(s)), f"idx_prefomc:{s}") for s in IDX])
    add("nas_mom", [leg_frame(Sym("NAS100"), plan_signal(Sym("NAS100"), 2, 13, 13, 18, thr_sd=0.5, need_trend=True), "nas_mom")])
    add("jpy_mom", [leg_frame(Sym("USDJPY+"), plan_signal(Sym("USDJPY+"), 2, 10, 10, 15, thr_sd=0.5), "jpy_mom")])
    add("oil_eia", [leg_frame(Sym("USOUSD"), plan_eia(Sym("USOUSD")), "oil_eia")])
    add("btc_weekend", [leg_frame(Sym("BTCUSD"), plan_btc(Sym("BTCUSD")), "btc_weekend")])
    S = Sym("XAGUSD")
    F = leg_frame(S, plan_fixed(S, 1.25, 10, 1), "xag_bigone")
    if F is not None and len(F):
        st = S.D.s.reindex(F.t.values // 86400).values
        F["wmult"] = np.where(st == 2, 1.0, 0.5)
    add("xag_bigone", [F])
    # oro
    E = entries()
    momd = set((E[E.leg == "momentum"].t // 86400).tolist())
    add("g_ny_short", [gold_frame("g_ny_short", gold_plan(16.5, 20.5, lambda d, T, D: -1))])
    add("g_ny_short_nomom", [gold_frame("g_ny_short_nomom", gold_plan(16.5, 20.5, lambda d, T, D: 0 if d in momd else -1))])
    add("g_evening", [gold_frame("g_evening", gold_plan(21, 23.75, lambda d, T, D: 1))])

    def follow(d, T, D):
        a, b = T.get(d * 86400 + 15 * H), T.get(d * 86400 + 21 * H)
        return 0 if a is None or b is None or a == b else int(np.sign(b - a))
    add("g_evening_follow", [gold_frame("g_evening_follow", gold_plan(21, 23.75, follow))])
    add("g_pmfix", [gold_frame("g_pmfix", gold_plan(16.75, 17.5, lambda d, T, D: -1))])

    def balt(d, T, D):
        a, b = T.get(d * 86400 + 1 * H), T.get(d * 86400 + 20 * H)
        return 0 if a is None or b is None or a == b else int(np.sign(b - a))
    add("g_balt", [gold_frame("g_balt", gold_plan(20, 20.5, balt))])
    add("g_lbma_am", [gold_frame("g_lbma_am", gold_plan(12.25, 12.75, lambda d, T, D: -1))])
    with open(FR, "wb") as fh:
        pickle.dump(L, fh)
    return L


def leg_rows(frames, w, Rcol="R"):
    """Filas de cartera de una pata (lista de frames). w = peso total de la pata; se reparte entre simbolos."""
    k = len(frames)
    out = []
    for F in frames:
        ww = w / k * (F["wmult"].values if "wmult" in F else 1.0)
        if F.sym.iat[0] == "XAUUSD+":
            G = F.copy()
            if Rcol != "R":
                G["pnl"] = G[Rcol] * G.atrd
            out.append(gold_as_rows(G, ww))
        else:
            out.append(as_rows(F, ww, Rcol))
    return pd.concat(out, ignore_index=True)


def screen(L, w=0.5):
    B = base()
    rows = []
    for name, frames in L.items():
        if not frames:
            continue
        A = pd.concat(frames, ignore_index=True)
        A = A[A.t < SEL[1].timestamp()]
        if A.empty:
            continue
        P = leg_rows(frames, w)
        C = combine(B, P)
        res = compare_mix(C, B, "sel", label=f"E:{name}:w{w}", boot=True)
        yr = year_R(A)
        res.update(dict(R_sel=float(A.R.mean()), n_leg=len(A), R_2022=float(yr.get(2022, np.nan)),
                        R_2023=float(yr.get(2023, np.nan)), R_2024=float(yr.get(2024, np.nan)),
                        corr_sel=corr_daily(P, B, "sel"), locked=float(A.locked.mean())))
        # cada simbolo de una cesta por separado (informativo)
        per_sym = {F.leg.iat[0]: round(float(F[F.t < SEL[1].timestamp()].R.mean()), 4) for F in frames}
        register("E", f"screen:{name}:w{w}", res, params=dict(w=w, per_sym=per_sym))
        rows.append(dict(pata=name, **{k: res[k] for k in ("n_leg", "R_sel", "R_2022", "R_2023", "R_2024", "corr_sel",
                                                          "locked", "mar_c", "mar_ratio", "dd_c", "cagr_c",
                                                          "peor_dia_c", "peor_mes_c", "p")}, per_sym=per_sym))
        print(f"{name:18s} n {len(A):5d} R {A.R.mean():+.4f} | 23 {yr.get(2023, np.nan):+.4f} 24 {yr.get(2024, np.nan):+.4f}"
              f" | corr {rows[-1]['corr_sel']:+.3f} | MAR {res['mar_c']:.2f} x{res['mar_ratio']:.3f} dd {res['dd_c']:.3f} p {res['p']:.2f}",
              flush=True)
    R = pd.DataFrame(rows)
    R.to_csv(os.path.join(RESULTS, "opt_E_screen.csv"), index=False)
    return R


def main():
    low_priority()
    L = build_all()
    w = float(sys.argv[1]) if len(sys.argv) > 1 else 0.5
    screen(L, w)


if __name__ == "__main__":
    main()
