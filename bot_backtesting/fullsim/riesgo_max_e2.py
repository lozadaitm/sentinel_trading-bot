"""¿Cuanto riesgo por operacion aguantan las cuentas del bot e2? (solo simulacion, sin MT5).

Reglas e2 vigentes (docs/experimento-2/diseno-bot-tres-patas-2026-10-25.md):
  Big One (peso 1 si s=+2, 0,5 si no; x0,5 en dia NFP/IPC/FOMC) + Momentum EE.UU. + NFP; escalera de tercios
  (hora / TP 2 / TP 3 ATR15), candado a 1 ATR_D, cierre a la hora de salida.
  lote_total = balance x riesgo x peso / (ATR_D x 100); tercio = floor(lote/3, 0,01) con minimo 0,01.
Ajustes:
  * Entrada real de la Big One a las 01:01 (el broker no acepta ordenes a las 01:00): -14 % de su ventaja
    (medido con ticks, memoria broker-sesion-trading-0101). Se resta 0,14 x R medio de la pata a cada operacion.
  * Recorte de ventaja h in {100 %, 75 %, 50 %}: a cada pata se le resta (1-h) x su R medio (la dispersion
    no cambia, solo se corre la media). Simula que la ventaja real sea menor que la medida.
Salidas:
  1) Camino historico 2022-10 -> 2026-10 por riesgo y cuenta: CAGR, mes medio, caida maxima (operacion a
     operacion y a fin de mes), peor dia, peor mes, racha bajo el maximo mas larga, margen minimo.
  2) Proyeccion 12 meses: remuestreo de meses y remuestreo por bloques de 10 dias, re-dimensionando los lotes
     con el balance simulado (el minimo 0,01 importa en 3 000): P(perder), P(caida > 30/40/50 %).
  3) Kelly / riesgo de maximo crecimiento: g(f) = media diaria de log(1 + f x sum(w x R)), con bandas por
     remuestreo por bloques de dias.
  4) Margen: peor nivel de margen historico (cobertura cobrada completa en ambos lados, conservador; el broker
     informa margin_hedged = 0) y escenario de estres sintetico.
Uso: python -m bot_backtesting.fullsim.riesgo_max_e2   (prioridad baja, un solo proceso)
"""
import ctypes
import os
import sys

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.broker_accounts import trades_fixed
from bot_backtesting.fullsim.broker_rule import DATA, RESULTS

START, END = pd.Timestamp("2022-10-01"), pd.Timestamp("2026-10-24")
RISKS = (0.04, 0.06, 0.08, 0.10, 0.12, 0.15, 0.20, 0.25, 0.30)
BALS = (3000, 10000, 25000)
EDGES = (1.0, 0.75, 0.5)
BO_DELAY = 0.14            # perdida de ventaja de la Big One por entrar a las 01:01
LEVERAGE = 500
STOP_OUT = 0.20            # nivel de stop-out del broker (auditoria de margen); se reporta tambien 50 %
N_SIM = 4000
BLOCK = 10


def low_priority():
    if sys.platform == "win32":
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)  # BELOW_NORMAL


def load():
    T = trades_fixed(ladder=True)
    T = T[(T.t >= START.timestamp()) & (T.t < END.timestamp())].copy()
    T.loc[(T.pata == "big_one") & (T.ev == 1), "w"] *= 0.5                # x0,5 en dia de noticia (regla e2)
    bo = T.pata == "big_one"
    T.loc[bo, "r_mult"] -= BO_DELAY * T.loc[bo, "r_mult"].mean()          # entrada 01:01
    X = pd.read_pickle(os.path.join(DATA, "broker_m15_full.pkl"))
    T["px"] = T.t.map(pd.Series(X.open.values, index=X.time.values))
    return T.sort_values("t").reset_index(drop=True)


def with_edge(T, h):
    T = T.copy()
    mu = T.groupby("pata").r_mult.transform("mean")
    T["r_mult"] = T.r_mult - (1 - h) * mu
    T["pnl"] = T.r_mult * T.risk_oz
    return T


def lots_of(bal, f, w, risk_oz):
    raw = bal * f * w / (risk_oz * 100)
    return 3 * np.maximum(0.01, np.floor(raw / 3 / 0.01 + 1e-9) * 0.01)


# ---------------------------------------------------------------- 1) camino historico
def history(T, bal0, f):
    ev = sorted([(r.t, 0, i) for i, r in T.iterrows()] + [(r.t_out, 1, i) for i, r in T.iterrows()])
    eq, lots, open_, rows, min_ml, min_ml_eq = bal0, {}, set(), [], np.inf, np.inf
    for t, kind, i in ev:
        r = T.loc[i]
        if kind == 0:
            lots[i] = lots_of(eq, f, r.w, r.risk_oz)
            open_.add(i)
            # peor momento: todas las abiertas en su peor punto (mae), cobertura cobrada en ambos lados
            fl = sum(min(0.0, T.at[j, "mae"]) * lots[j] * 100 for j in open_)
            mg = sum(2 * lots[j] * 100 * T.at[j, "px"] / LEVERAGE for j in open_)
            ml = (eq + fl) / mg
            if ml < min_ml:
                min_ml = ml
        else:
            eq += r.pnl * lots[i] * 100
            open_.discard(i)
            rows.append((t, eq))
    R = pd.DataFrame(rows, columns=["t", "eq"])
    R["ts"] = pd.to_datetime(R.t, unit="s")
    eqs = R["eq"].values
    peak = np.maximum.accumulate(np.r_[bal0, eqs])[1:]
    dd_trade = np.max(1 - eqs / peak)
    D = R.groupby(R.ts.dt.normalize())["eq"].last()
    D = D.reindex(pd.bdate_range(START, END)).ffill().fillna(bal0)
    dret = D.pct_change().fillna(D.iloc[0] / bal0 - 1)
    M = D.groupby(D.index.to_period("M")).last()
    mret = M.pct_change().fillna(M.iloc[0] / bal0 - 1)
    dd_month = np.max(1 - M.values / np.maximum.accumulate(np.r_[bal0, M.values])[1:])
    # racha bajo el maximo (dias naturales)
    pk = np.maximum.accumulate(np.r_[bal0, eqs]); under, longest, t0 = False, 0, None
    for k, (tt, e) in enumerate(zip(R.ts, eqs)):
        if e < pk[k + 1] - 1e-9:
            if not under:
                under, t0 = True, prev_t if k else tt
        elif under:
            under = False; longest = max(longest, (tt - t0).days)
        prev_t = tt
    if under:
        longest = max(longest, (R.ts.iloc[-1] - t0).days)
    yrs = (END - START).days / 365.25
    x = eq / bal0
    return dict(x=x, cagr=x ** (1 / yrs) - 1, mes=x ** (1 / len(M)) - 1, dd_op=dd_trade, dd_mes=dd_month,
                peor_dia=dret.min(), peor_mes=mret.min(), meses_neg=int((mret < 0).sum()), bajo_max_dias=longest,
                ml_min=min_ml), mret


# ---------------------------------------------------------------- 2) remuestreo con re-dimensionado
def day_arrays(T):
    """Por dia habil: hasta 3 operaciones (w, risk_oz, pnl). Dias sin operaciones = filas vacias."""
    days = pd.bdate_range(START, END)
    T = T.assign(day=pd.to_datetime(T.t, unit="s").dt.normalize())
    K = int(T.groupby("day").size().max())
    W = np.zeros((len(days), K)); RK = np.ones((len(days), K)); P = np.zeros((len(days), K)); MK = np.zeros((len(days), K), bool)
    pos = {d: i for i, d in enumerate(days)}
    for d, g in T.groupby("day"):
        i = pos.get(d)
        if i is None:
            continue
        n = len(g)
        W[i, :n] = g.w.values; RK[i, :n] = g.risk_oz.values; P[i, :n] = g.pnl.values; MK[i, :n] = True
    return days, W, RK, P, MK


def simulate(idx, W, RK, P, MK, bal0, f):
    """idx: (n_sim, n_days) indices de dia. Lotes con el balance al inicio del dia."""
    n = idx.shape[0]
    eq = np.full(n, float(bal0)); peak = eq.copy(); dd = np.zeros(n)
    for k in range(idx.shape[1]):
        j = idx[:, k]
        w, rk, p, mk = W[j], RK[j], P[j], MK[j]
        lot = lots_of(eq[:, None], f, w, rk) * mk
        eq = np.maximum(eq + (lot * p * 100).sum(1), 0.0)
        peak = np.maximum(peak, eq)
        dd = np.maximum(dd, 1 - eq / peak)
    return eq / bal0, dd


def boot_idx(days, kind, rng, n=N_SIM, horizon=252):
    nd = len(days)
    if kind == "dias":
        nb = int(np.ceil(horizon / BLOCK))
        starts = rng.integers(0, nd - BLOCK, size=(n, nb))
        return (starts[:, :, None] + np.arange(BLOCK)).reshape(n, -1)[:, :horizon]
    per = pd.Series(np.arange(nd), index=days).groupby(days.to_period("M")).apply(lambda s: s.values)
    per = [a for a in per.values if len(a) >= 15]                 # meses completos
    pick = rng.integers(0, len(per), size=(n, 12))
    L = max(len(a) for a in per)
    pad = np.array([np.r_[a, np.full(L - len(a), -1)] for a in per])
    out = pad[pick].reshape(n, -1)
    return out


def boot(T, bal0, f, kind, seed=7):
    days, W, RK, P, MK = day_arrays(T)
    # dia "vacio" para el relleno de meses cortos
    W = np.vstack([W, np.zeros(W.shape[1])]); RK = np.vstack([RK, np.ones(RK.shape[1])])
    P = np.vstack([P, np.zeros(P.shape[1])]); MK = np.vstack([MK, np.zeros(MK.shape[1], bool)])
    idx = boot_idx(days, kind, np.random.default_rng(seed))
    x, dd = simulate(idx, W, RK, P, MK, bal0, f)
    return dict(p10=np.quantile(x, .1), p50=np.median(x), p90=np.quantile(x, .9), p_perder=(x < 1).mean(),
                p_dd30=(dd > .3).mean(), p_dd40=(dd > .4).mean(), p_dd50=(dd > .5).mean(), dd_med=np.median(dd))


# ---------------------------------------------------------------- 3) Kelly
FGRID = np.round(np.arange(0.01, 0.801, 0.005), 3)


def daily_X(T):
    days = pd.bdate_range(START, END)
    X = (T.w * T.r_mult).groupby(pd.to_datetime(T.t, unit="s").dt.normalize()).sum()
    return X.reindex(days).fillna(0.0).values


def growth(X):
    G = np.log(np.clip(1 + np.outer(X, FGRID), 1e-12, None)).mean(0)   # por dia
    return G


def kelly(T, n=1000, seed=11):
    X = daily_X(T)
    G = growth(X)
    f_star = FGRID[np.argmax(G)]
    rng = np.random.default_rng(seed); nd = len(X); nb = int(np.ceil(nd / BLOCK)); fs = []
    for _ in range(n):
        s = rng.integers(0, nd - BLOCK, nb)
        Xb = X[(s[:, None] + np.arange(BLOCK)).ravel()[:nd]]
        fs.append(FGRID[np.argmax(growth(Xb))])
    fs = np.array(fs)
    out = dict(f_kelly=f_star, f_p05=np.quantile(fs, .05), f_p50=np.median(fs), f_p95=np.quantile(fs, .95),
               peor_dia_R=X.min())
    for f in RISKS:
        out[f"g_anual_{int(f*100)}"] = np.exp(G[np.argmin(abs(FGRID - f))] * 252) - 1
    out["g_anual_kelly"] = np.exp(G.max() * 252) - 1
    # riesgo que da la mitad del crecimiento a la mitad del riesgo de Kelly (referencia: 1/2 Kelly)
    return out, G


# ---------------------------------------------------------------- 4) margen, estres sintetico
def stress(T, bal, f, k_lock=1.0, W=2.0, so=STOP_OUT):
    """Peor dia sintetico: patas abiertas con peso total W, todas bloqueadas a -k_lock x ATR_D, lotes con el
    ATR_D/precio MAS BAJO del historico (lotes mas grandes) y precio actual; cobertura cobrada en ambos lados.
    Devuelve nivel de margen y equity restante."""
    ratio = (T.risk_oz / T.px).min()
    px = T.px.iloc[-1]
    atr = ratio * px
    legs = [1.0] * int(W) + ([W - int(W)] if W % 1 else [])
    lots = [lots_of(bal, f, w, atr) for w in legs]
    loss = sum(l * atr * k_lock * 100 for l in lots)
    eq = bal - loss
    margin = sum(2 * l * 100 * px / LEVERAGE for l in lots)
    return dict(ml=eq / margin, eq_rest=eq / bal, f_ef=sum(l * atr * 100 for l in lots) / bal)


def main():
    low_priority()
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 60)
    T0 = load()
    print("operaciones:", len(T0), T0.groupby("pata").r_mult.agg(["size", "mean", "std"]).round(4).to_dict("index"))
    print("ATR_D/precio min/med/max:", (T0.risk_oz / T0.px).quantile([0, .5, 1]).round(4).tolist(), "precio ult:", T0.px.iloc[-1])
    hist, boots, kel, stres = [], [], [], []
    for h in EDGES:
        T = with_edge(T0, h)
        kd, _ = kelly(T)
        kel.append(dict(ventaja=h, **kd)); print("kelly", h, {k: round(v, 3) for k, v in kd.items()}, flush=True)
        for bal in BALS:
            for f in RISKS:
                if h == 1.0:
                    s, _ = history(T, bal, f)
                    hist.append(dict(cuenta=bal, riesgo=f, **s))
                for kind in ("meses", "dias"):
                    b = boot(T, bal, f, kind)
                    boots.append(dict(ventaja=h, cuenta=bal, riesgo=f, remuestreo=kind, **b))
            print("listo", h, bal, flush=True)
    for bal in BALS:
        for f in RISKS:
            for W, k in ((2.0, 1.0), (2.0, 1.5), (3.0, 1.0), (3.0, 1.5)):
                stres.append(dict(cuenta=bal, riesgo=f, patas=W, golpe_R=k, **stress(T0, bal, f, k, W)))
    H, B, K, S = (pd.DataFrame(x) for x in (hist, boots, kel, stres))
    pd.to_pickle((H, B, K, S), os.path.join(RESULTS, "riesgo_max_e2.pkl"))
    print("\nCAMINO HISTORICO (ventaja medida, Big One a las 01:01):"); print(H.round(3).to_string(index=False))
    print("\nREMUESTREO 12 MESES:"); print(B.round(3).to_string(index=False))
    print("\nKELLY:"); print(K.round(3).to_string(index=False))
    print("\nESTRES DE MARGEN:"); print(S.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
