"""Base comun de la sesion de optimizacion del e2 (27-oct-2026). Solo simulacion, sin MT5.

Que da este modulo a cada linea de investigacion (A..G):
  * entries()      : las operaciones e2 vigentes (Big One 01:01 -> 10:00, Momentum 15:00 -> 21:00, NFP T+60 -> 24 h)
                     con lado, peso, ATR_D, ATR15, tendencia s, dia de noticia y precio de entrada con costos.
  * path(tr)       : el camino de precios DENTRO de la operacion en la resolucion mas fina disponible:
                     M1 del broker (2026-01 ->), M5 del broker (2025-05-29 ->), M5 de Dukascopy + desfase
                     diario al broker (antes). Precios bid; residuo frente al broker ~0,03 $/oz.
  * ladder_e2(...) : la gestion vigente (tercios hora / TP 2 / TP 3 ATR15, candado -1 ATR_D, cierre a la hora).
  * evaluate(...)  : cartera completa al 8 % con lotes reales (tercio = floor(lote/3; 0,01), minimo 0,01),
                     MAR = CAGR / caida maxima, peor dia, peor mes.
  * compare(...)   : candidato vs base, vs base con lote mayor al mismo riesgo (misma caida), bootstrap
                     pareado por bloques de dias (p de mejora de MAR), regla de aceptacion.
  * register(...)  : cada variante probada se anota en results/opt_registry.csv (para BH y Deflated Sharpe).
Periodos: ELEGIR 2022-10 -> 2024-12, VALIDAR 2025, PRUEBA 2026 (guardado: exige E2OPT_FINAL=1).
Costos: spread por minuto del dia (mediana de ticks del broker 2026), comision 0,06 $/oz ida y vuelta
(3 $/lote/lado), deslizamiento 0,05 $/oz por orden a mercado (entrada, salida por hora, candado; los TP son
limite y no deslizan), swap por noche, Big One a las 01:01 (+0,0061 x ATR_D sobre el open de las 01:00 = 0,64 $/oz en 2026, medido con
ticks y escalado por ATR_D, memoria broker-sesion-trading-0101).
Uso como libreria:  from bot_backtesting.fullsim.opt_base import *
Autocomprobacion:   python -m bot_backtesting.fullsim.opt_base
"""
import ctypes
import os
import sys
import time as _time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
RESULTS = os.path.join(HERE, "results")
REGISTRY = os.path.join(RESULTS, "opt_registry.csv")

# ------------------------------------------------------------------ periodos
SEL = (pd.Timestamp("2022-10-01"), pd.Timestamp("2025-01-01"))
VAL = (pd.Timestamp("2025-01-01"), pd.Timestamp("2026-01-01"))
TEST = (pd.Timestamp("2026-01-01"), pd.Timestamp("2026-10-24"))
PERIODS = {"sel": SEL, "val": VAL, "test": TEST, "selval": (SEL[0], VAL[1])}

# ------------------------------------------------------------------ costos
COMM = 0.06              # $/oz ida y vuelta (3 $/lote/lado, 100 oz)
SLIP = 0.05              # $/oz por orden a mercado
BO_DELAY = 0.0061        # x ATR_D: entrar 01:01 en vez del open 01:00 (ticks 2026: 0,64 $/oz con ATR_D mediano 104)
SWAP_LONG, SWAP_SHORT, TRIPLE_DOW = -0.774, 0.367, 2
RISK, BAL = 0.08, 10000.0


def low_priority():
    """BELOW_NORMAL: los bots en vivo comparten la maquina."""
    if sys.platform == "win32":
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)


def period(name):
    if name in ("test", "all") and os.environ.get("E2OPT_FINAL") != "1":
        raise RuntimeError("2026 esta guardado: solo para la evaluacion final (E2OPT_FINAL=1)")
    if name == "all":
        return SEL[0], TEST[1]
    return PERIODS[name]


def swap_cost(t0, t1, side):
    d0, d1 = int(t0 // 86400), int(t1 // 86400)
    nights = 0
    for d in range(d0, d1):
        dow = (d + 3) % 7
        if dow >= 5:
            continue
        nights += 3 if dow == TRIPLE_DOW else 1
    return nights * (SWAP_LONG if side == 1 else SWAP_SHORT)


# ------------------------------------------------------------------ datos
_CACHE = {}


def _spread_profile():
    s = pd.read_csv(os.path.join(DATA, "ticks", "spread_XAUUSD+.csv"))
    p = s.groupby("minuto")["median"].median().reindex(range(1440)).interpolate().bfill().ffill()
    return p.values


def spread_at(t):
    """Spread $/oz tipico del minuto del dia (servidor). Vectorizado."""
    if "spr" not in _CACHE:
        _CACHE["spr"] = _spread_profile()
    return _CACHE["spr"][(np.asarray(t) % 86400) // 60]


def m15():
    if "m15" not in _CACHE:
        X = pd.read_pickle(os.path.join(DATA, "broker_m15_full.pkl")).sort_values("time").reset_index(drop=True)
        h, l, c = X.high.values, X.low.values, X.close.values
        tr = np.r_[h[0] - l[0], np.maximum(h[1:] - l[1:], np.maximum(abs(h[1:] - c[:-1]), abs(l[1:] - c[:-1])))]
        X["atr15"] = pd.Series(tr).rolling(14).mean().shift(1).values
        X["d"] = X.time // 86400
        D = X.groupby("d").agg(O=("open", "first"), H=("high", "max"), L=("low", "min"), C=("close", "last"))
        D["atrd"] = (D.H - D.L).rolling(14).mean().shift(1)
        D["s"] = (np.sign(D.C - D.C.shift(21)) + np.sign(D.C - D.C.shift(63))).shift(1)
        _CACHE["m15"] = (X, D)
    return _CACHE["m15"]


def fine():
    """Velas finas continuas (time, open, high, low, close, src): duka M5 + desfase diario -> broker M5 -> broker M1."""
    if "fine" in _CACHE:
        return _CACHE["fine"]
    X, _ = m15()
    duka = pd.read_pickle(os.path.join(DATA, "frames_duka.pkl"))["M5"]
    b5 = pd.read_pickle(os.path.join(DATA, "broker_m5_full.pkl"))
    b1 = pd.read_pickle(os.path.join(DATA, "broker_m1_ticks.pkl"))
    # desfase diario duka -> broker: mediana de (close broker M15 - close duka M15) por dia, sin el rollover
    d15 = pd.read_pickle(os.path.join(DATA, "frames_duka.pkl"))["M15"]
    m = X[["time", "close"]].merge(d15[["time", "close"]], on="time", suffixes=("_b", "_d"))
    m = m[(m.time % 86400) >= 7200]
    off = (m.close_b - m.close_d).groupby(m.time // 86400).median()
    off = off.reindex(range(int(duka.time.min() // 86400), int(duka.time.max() // 86400) + 1)).ffill().bfill()
    t5 = b5.time.min()
    t1 = b1.time.min()
    a = duka[duka.time < t5].copy()
    o = off.reindex(a.time // 86400).values
    for c in ("open", "high", "low", "close"):
        a[c] = a[c].values + o
    a["src"] = 0
    b = b5[(b5.time >= t5) & (b5.time < t1)][["time", "open", "high", "low", "close"]].copy(); b["src"] = 1
    c1 = b1[["time", "open", "high", "low", "close"]].copy(); c1["src"] = 2
    F = pd.concat([a[["time", "open", "high", "low", "close", "src"]], b, c1]).sort_values("time").reset_index(drop=True)
    # en el rollover duka (01:00-01:05) trae el bid hundido: se recorta al rango del M15 del broker
    _CACHE["fine"] = F
    _CACHE["fine_arr"] = tuple(F[c].values for c in ("time", "open", "high", "low", "close", "src"))
    return F


def path(t_from, t_to):
    """Velas finas con time en [t_from, t_to). Devuelve (time, o, h, l, c, dur) con dur = segundos de cada vela."""
    fine()
    T, O, H, L, C, S = _CACHE["fine_arr"]
    i0, i1 = np.searchsorted(T, t_from), np.searchsorted(T, t_to)
    dur = np.where(S[i0:i1] == 2, 60, 300)
    return T[i0:i1], O[i0:i1], H[i0:i1], L[i0:i1], C[i0:i1], dur


# ------------------------------------------------------------------ entradas e2
def _us_holidays():
    from pandas.tseries.holiday import USFederalHolidayCalendar
    h = set(USFederalHolidayCalendar().holidays("2021-01-01", "2027-12-31").normalize())
    for y in range(2021, 2028):
        tg = [d for d in h if d.month == 11 and d.year == y and d.day >= 22 and d.dayofweek == 3]
        for d in tg:
            h.add(d + pd.Timedelta(days=1))
        h.add(pd.Timestamp(f"{y}-12-24")); h.add(pd.Timestamp(f"{y}-12-31"))
    return {int(d.value // 86_400_000_000_000) for d in h}


def _news():
    E = pd.read_csv(os.path.join(HERE, "events_us.csv"))
    evd = set((pd.to_datetime(E.date) - pd.Timestamp("1970-01-01")).dt.days)
    nfp = []
    for e in E[E.event == "NFP"].itertuples():
        utc = pd.Timestamp(f"{e.date} {e.time_utc}")
        ny = utc.tz_localize("UTC").tz_convert("America/New_York")
        t0 = int(utc.timestamp()) + (3 if ny.dst().total_seconds() else 2) * 3600
        nfp.append(t0 - t0 % 900)
    return evd, nfp


def entries(holidays=True):
    """Una fila por operacion e2. Columnas:
    leg, t (inicio vela M15 de la senal), t_in (hora real de entrada), t_out (hora de salida), side, w, state,
    ev, atrd, atr15, px (precio de entrada efectivo con spread, deslizamiento y retraso 01:01), mid0 (bid de la
    vela de entrada), spr_in, spr_out, swap ($/oz por la noche si cruza), day."""
    if "entries" in _CACHE and holidays:
        return _CACHE["entries"].copy()
    X, D = m15()
    T, O, C = X.time.values, X.open.values, X.close.values
    idx = pd.Series(np.arange(len(T)), index=T)
    evd, nfp = _news()
    hol = _us_holidays() if holidays else set()
    rows = []

    def ok(k, nb):
        d = T[k] // 86400
        if (d + 3) % 7 >= 5 or d not in D.index or not np.isfinite(D.at[d, "atrd"]) or not np.isfinite(X.atr15.iat[k]):
            return False
        return k + nb <= len(T) and T[k + nb - 1] - T[k] <= nb * 900 + 3 * 86400

    for k in np.nonzero(T % 86400 == 3600)[0]:                      # Big One
        if not ok(k, 36):
            continue
        d = T[k] // 86400; s = D.at[d, "s"]
        w = (1.0 if s == 2 else 0.5) * (0.5 if d in evd else 1.0)
        rows.append(("big_one", T[k], T[k] + 60, T[k + 35] + 900, 1, w, s, int(d in evd), D.at[d, "atrd"], X.atr15.iat[k], O[k], k))
    for k in np.nonzero(T % 86400 == 15 * 3600)[0]:                 # Momentum EE.UU.
        if not ok(k, 24):
            continue
        d = T[k] // 86400; s = D.at[d, "s"]
        if s not in (2, -2) or d in hol:
            continue
        k1 = idx.get(d * 86400 + 3600)
        if k1 is None:
            continue
        a = (O[k] - O[k1]) / O[k1] * 100
        if abs(a) <= 0.5 * 0.464:
            continue
        rows.append(("momentum", T[k], T[k], T[k + 23] + 900, int(np.sign(a)), 1.0, s, int(d in evd), D.at[d, "atrd"], X.atr15.iat[k], O[k], k))
    for t0 in nfp:                                                    # NFP
        a, b, te = t0 - 900, t0 + 3600 - 900, t0 + 3600
        if a not in idx.index or b not in idx.index or te not in idx.index:
            continue
        k = idx[te]
        if not ok(k, 96) or (te // 86400) in hol:
            continue
        j = C[idx[b]] - O[idx[a]]
        if j == 0:
            continue
        d = te // 86400
        rows.append(("nfp", te, te, T[k + 95] + 900, int(np.sign(j)), 1.0, D.at[d, "s"], 1, D.at[d, "atrd"], X.atr15.iat[k], O[k], k))
    E = pd.DataFrame(rows, columns=["leg", "t", "t_in", "t_out", "side", "w", "state", "ev", "atrd", "atr15", "mid0", "k15"])
    E["spr_in"] = spread_at(E.t_in.values)
    E["spr_out"] = spread_at(E.t_out.values - 60)
    E["px"] = np.where(E.side == 1, E.mid0 + E.spr_in + SLIP, E.mid0 - SLIP)
    E.loc[E.leg == "big_one", "px"] += BO_DELAY * E.loc[E.leg == "big_one", "atrd"]
    E["swap"] = [swap_cost(a, b, s) for a, b, s in zip(E.t_in, E.t_out, E.side)]
    E["day"] = pd.to_datetime(E.t, unit="s").dt.normalize()
    E = E.sort_values("t").reset_index(drop=True)
    if holidays:
        _CACHE["entries"] = E
    return E.copy()


def random_entries(E, seed=0, mode="day"):
    """Nulo: mismas operaciones (pata, lado, peso, duracion) en momentos al azar.
    mode='day' : misma hora del dia, dia habil al azar del mismo periodo de elegir/validar/prueba.
    mode='time': dia al azar y hora de inicio al azar (02:00-19:45, en M15) con la misma duracion; lado al azar.
    Recalcula ATR_D, ATR15, precio de entrada y costos del momento nuevo."""
    X, D = m15()
    T, O = X.time.values, X.open.values
    idx = pd.Series(np.arange(len(T)), index=T)
    rng = np.random.default_rng(seed)
    bdays = {p[0]: (pd.bdate_range(p[0], p[1] - pd.Timedelta(days=1)) - pd.Timestamp(0)).days.values for p in (SEL, VAL, TEST)}
    rows = []
    for r in E.itertuples():
        for _ in range(50):
            per = next((p for p in (VAL, TEST) if p[0].timestamp() <= r.t < p[1].timestamp()), SEL)
            days = bdays[per[0]]
            d = int(days[rng.integers(len(days))])
            tod = (r.t % 86400) if mode == "day" else int(rng.integers(8, 80)) * 900
            t = d * 86400 + tod
            k = idx.get(t)
            if k is None or d not in D.index or not np.isfinite(D.at[d, "atrd"]) or not np.isfinite(X.atr15.iat[k]):
                continue
            dur = r.t_out - r.t
            side = r.side if mode == "day" else int(rng.choice([-1, 1]))
            rows.append(r._replace(t=t, t_in=t + (r.t_in - r.t), t_out=t + dur, side=side, atrd=D.at[d, "atrd"],
                                   atr15=X.atr15.iat[k], mid0=O[k], k15=k, day=pd.Timestamp(d, unit="D"))._asdict())
            break
    R = pd.DataFrame(rows).drop(columns="Index")
    R["spr_in"] = spread_at(R.t_in.values); R["spr_out"] = spread_at(R.t_out.values - 60)
    R["px"] = np.where(R.side == 1, R.mid0 + R.spr_in + SLIP, R.mid0 - SLIP)
    R.loc[R.leg == "big_one", "px"] += BO_DELAY * R.loc[R.leg == "big_one", "atrd"]
    R["swap"] = [swap_cost(a, b, s) for a, b, s in zip(R.t_in, R.t_out, R.side)]
    return R.sort_values("t").reset_index(drop=True)


def trade_path(r):
    """Camino favorable/adverso de la operacion r (fila de entries) en $/oz desde px, por vela fina.
    Devuelve dict con time, fav (mejor precio de cierre posible dentro de la vela), adv (peor), opn, cls, dur.
    Para cortos el cierre se paga al ask (bid + spread de salida)."""
    tt, o, h, l, c, dur = path(r.t_in - (r.t_in % 60), r.t_out)
    if r.leg == "big_one" and len(tt):
        # rollover: la primera vela puede traer el bid hundido (duka); se acota al rango M15 del broker
        X, _ = m15()
        lo, hi = X.low.values[r.k15], X.high.values[r.k15]
        m = tt < r.t + 900
        l = np.where(m, np.maximum(l, lo), l); h = np.where(m, np.minimum(h, hi), h)
    sp = r.spr_out
    if r.side == 1:
        fav, adv, opn, cls = h - r.px, l - r.px, o - r.px, c - r.px
    else:
        fav, adv, opn, cls = r.px - (l + sp), r.px - (h + sp), r.px - (o + sp), r.px - (c + sp)
    return dict(time=tt, fav=fav, adv=adv, opn=opn, cls=cls, dur=dur)


# ------------------------------------------------------------------ gestion vigente
LOCK_COST = None   # se calcula por operacion: spread + comision + deslizamiento de la orden opuesta


def leg_ladder(P, r, tps=(None, 2.0, 3.0), lock_k=1.0, fracs=None):
    """Gestion vigente sobre el camino fino P (trade_path). Devuelve (pnl $/oz de la posicion completa, mae,
    locked, detalle por tercio). Dentro de cada vela: primero el lado en contra (conservador).
    Al candado: todos los tercios aun abiertos quedan congelados en -lock_k*ATR_D (o el open si hay hueco)."""
    n = len(P["fav"])
    if n == 0:
        return np.nan, np.nan, False, []
    fracs = fracs or [1 / len(tps)] * len(tps)
    lockd = lock_k * r.atrd
    lk = np.nonzero(P["adv"] <= -lockd)[0]
    i_lock = lk[0] if len(lk) else n
    out, mae_end = [], i_lock
    for tp in tps:
        if tp is None:
            out.append(("time", n - 1))
            continue
        hit = np.nonzero(P["fav"][:i_lock + 1] >= tp * r.atr15)[0]
        # vela del candado: primero el lado en contra -> si toca ambos, gana el candado
        hit = hit[hit < i_lock] if len(hit) else hit
        out.append(("tp", hit[0]) if len(hit) else ("time", n - 1))
    lock_px = min(P["opn"][i_lock], -lockd) if i_lock < n else None
    lock_extra = r.spr_out + COMM + SLIP
    pnls = []
    for (kind, i), tp in zip(out, tps):
        if kind == "tp":
            p = tp * r.atr15 - COMM
        elif i_lock < n:
            p = lock_px - COMM - lock_extra
        else:
            p = P["cls"][-1] - COMM - SLIP
        pnls.append(p)
    pnl = float(np.dot(fracs, pnls)) + r.swap
    mae = float(min(P["adv"][:min(i_lock, n - 1) + 1].min(), lock_px if lock_px is not None else 0.0))
    return pnl, mae, i_lock < n, list(zip([k for k, _ in out], pnls))


def run_trades(E, manager=leg_ladder, **kw):
    """Aplica una gestion (funcion (P, r) -> (pnl, mae, locked, ...)) a cada operacion. Agrega pnl, mae, locked, R."""
    pn, ma, lo = [], [], []
    for r in E.itertuples():
        P = trade_path(r)
        res = manager(P, r, **kw)
        pn.append(res[0]); ma.append(res[1]); lo.append(res[2])
    E = E.copy()
    E["pnl"], E["mae"], E["locked"] = pn, ma, lo
    E["R"] = E.pnl / E.atrd
    return E[np.isfinite(E.pnl)].reset_index(drop=True)


def base_trades():
    """Operaciones e2 vigentes con su resultado (cacheado en results/opt_base_trades.pkl)."""
    fp = os.path.join(RESULTS, "opt_base_trades.pkl")
    if os.path.exists(fp) and os.path.getmtime(fp) > os.path.getmtime(__file__):
        return pd.read_pickle(fp)
    B = run_trades(entries())
    B.to_pickle(fp)
    return B


# ------------------------------------------------------------------ cartera
def clip(T, per):
    a, b = period(per) if isinstance(per, str) else per
    return T[(T.t >= a.timestamp()) & (T.t < b.timestamp())]


def lots_of(bal, f, w, atrd):
    raw = bal * f * w / (atrd * 100)
    return 3 * np.maximum(0.01, np.floor(raw / 3 / 0.01 + 1e-9) * 0.01)


def evaluate(T, per="sel", f=RISK, bal0=BAL, wcol="w", lots=True):
    """Camino de cartera con interes compuesto. T necesita t, t_out, pnl ($/oz), atrd y la columna de peso.
    Peso 0 = no operar. Lotes con el balance cerrado al entrar; P&L al cerrar.
    Devuelve dict: cagr, dd, mar, peor_dia, peor_mes, n, R_medio, sharpe_d, x."""
    a, b = period(per) if isinstance(per, str) else per
    T = T[(T.t >= a.timestamp()) & (T.t < b.timestamp()) & (T[wcol] > 0)].sort_values("t")
    ti, to, pnl, w, atr = (T[c].values for c in ("t", "t_out", "pnl", wcol, "atrd"))
    ev = sorted([(ti[i], 0, i) for i in range(len(T))] + [(to[i], 1, i) for i in range(len(T))])
    eq, L, rows = bal0, np.zeros(len(T)), []
    for t, kind, i in ev:
        if kind == 0:
            L[i] = lots_of(eq, f, w[i], atr[i]) if lots else eq * f * w[i] / (atr[i] * 100)
        else:
            eq += pnl[i] * L[i] * 100
            rows.append((t, eq))
    if not rows:
        return dict(cagr=0, dd=0, mar=0, peor_dia=0, peor_mes=0, n=0, R_medio=np.nan, sharpe_d=0, x=1)
    R = pd.DataFrame(rows, columns=["t", "eqv"])
    eqs = R.eqv.values
    dd = float(np.max(1 - eqs / np.maximum.accumulate(np.r_[bal0, eqs])[1:]))
    days = pd.bdate_range(a, b - pd.Timedelta(days=1))
    Dq = R.groupby(pd.to_datetime(R.t, unit="s").dt.normalize()).eqv.last().reindex(days).ffill().fillna(bal0)
    dret = Dq.pct_change().fillna(Dq.iloc[0] / bal0 - 1)
    M = Dq.groupby(Dq.index.to_period("M")).last()
    mret = M.pct_change().fillna(M.iloc[0] / bal0 - 1)
    yrs = (b - a).days / 365.25
    x = eq / bal0
    cagr = x ** (1 / yrs) - 1
    return dict(cagr=cagr, dd=dd, mar=cagr / dd if dd > 0 else np.inf, peor_dia=float(dret.min()),
                peor_mes=float(mret.min()), n=len(T), R_medio=float((T.pnl / T.atrd).mean()),
                sharpe_d=float(dret.mean() / dret.std() * np.sqrt(252)) if dret.std() > 0 else 0, x=x)


def daily_R(T, per, wcol="w"):
    """Serie diaria (dias habiles) de sum(w x R) por dia de entrada: insumo del bootstrap rapido."""
    a, b = period(per) if isinstance(per, str) else per
    T = T[(T.t >= a.timestamp()) & (T.t < b.timestamp())]
    s = (T[wcol] * T.pnl / T.atrd).groupby(T.day).sum()
    return s.reindex(pd.bdate_range(a, b - pd.Timedelta(days=1))).fillna(0.0)


def _mar_fast(X, f=RISK):
    """X: (n_sim, n_dias) R diarios -> MAR con interes compuesto diario (sin redondeo de lotes)."""
    eq = np.cumprod(1 + f * X, axis=1)
    eq = np.maximum(eq, 1e-9)
    pk = np.maximum.accumulate(np.concatenate([np.ones((X.shape[0], 1)), eq], 1), 1)[:, 1:]
    dd = (1 - eq / pk).max(1)
    cagr = eq[:, -1] ** (252 / X.shape[1]) - 1
    return cagr / np.maximum(dd, 1e-9), cagr, dd


def boot_compare(xc, xb, n=2000, block=10, seed=3, f=RISK):
    """Bootstrap pareado por bloques de dias. xc, xb: series diarias de R (mismo indice).
    Devuelve p (prob. de que el candidato NO mejore el MAR), mejora mediana, P(dd>30/40 %) de cada uno,
    peor dia/mes p05."""
    xc, xb = np.asarray(xc), np.asarray(xb)
    nd = len(xc); nb = int(np.ceil(nd / block)); rng = np.random.default_rng(seed)
    s = rng.integers(0, nd - block, size=(n, nb))
    I = (s[:, :, None] + np.arange(block)).reshape(n, -1)[:, :nd]
    mc, _, dc = _mar_fast(xc[I], f); mb, _, db = _mar_fast(xb[I], f)
    ratio = mc / np.maximum(mb, 1e-9)
    return dict(p=float((ratio <= 1).mean()), mar_ratio_med=float(np.median(ratio)),
                p_dd30_c=float((dc > .3).mean()), p_dd30_b=float((db > .3).mean()),
                p_dd40_c=float((dc > .4).mean()), p_dd40_b=float((db > .4).mean()))


def bigger_lot(B, cand_dd, per, bal0=BAL):
    """e2 base con el riesgo que da la MISMA caida maxima que el candidato (nulo 'lote mayor')."""
    lo, hi = 0.01, 0.30
    for _ in range(18):
        f = (lo + hi) / 2
        m = evaluate(B, per, f=f, bal0=bal0)
        if m["dd"] < cand_dd:
            lo = f
        else:
            hi = f
    m = evaluate(B, per, f=(lo + hi) / 2, bal0=bal0)
    m["f"] = (lo + hi) / 2
    return m


def compare(C, B, per, label="", f=RISK, bal0=BAL, wcol="w", boot=True):
    """Candidato C vs base B en el periodo. Ambos con columnas t, t_out, pnl, atrd, w, day.
    Regla de aceptacion: MAR >= 1,25 x base Y peor dia/mes no peores (tolerancia 0,1 pp)."""
    mc = evaluate(C, per, f=f, bal0=bal0, wcol=wcol)
    mb = evaluate(B, per, f=f, bal0=bal0)
    big = bigger_lot(B, mc["dd"], per, bal0=bal0)
    out = dict(label=label, per=per if isinstance(per, str) else "custom",
               mar_c=mc["mar"], mar_b=mb["mar"], mar_ratio=mc["mar"] / mb["mar"] if mb["mar"] > 0 else np.nan,
               cagr_c=mc["cagr"], cagr_b=mb["cagr"], dd_c=mc["dd"], dd_b=mb["dd"],
               cagr_lote_mayor=big["cagr"], f_lote_mayor=big["f"],
               peor_dia_c=mc["peor_dia"], peor_dia_b=mb["peor_dia"], peor_mes_c=mc["peor_mes"], peor_mes_b=mb["peor_mes"],
               n_c=mc["n"], n_b=mb["n"], sharpe_c=mc["sharpe_d"], sharpe_b=mb["sharpe_d"])
    if boot:
        bc = boot_compare(daily_R(C, per, wcol).values, daily_R(B, per).values, f=f)
        out.update(bc)
    out["pasa"] = bool(out["mar_ratio"] >= 1.25 and mc["peor_dia"] >= mb["peor_dia"] - 1e-3
                       and mc["peor_mes"] >= mb["peor_mes"] - 1e-3)
    return out


def register(line, variant, res, params=""):
    """Anota la variante en el registro global (una fila por variante y periodo evaluado)."""
    row = dict(ts=pd.Timestamp.now().isoformat(timespec="seconds"), line=line, variant=variant, params=str(params))
    row.update({k: v for k, v in res.items() if not isinstance(v, (list, dict))})
    df = pd.DataFrame([row])
    for _ in range(20):                                   # varios procesos pueden escribir a la vez
        try:
            df.to_csv(REGISTRY, mode="a", header=not os.path.exists(REGISTRY), index=False)
            return
        except PermissionError:
            _time.sleep(0.5)


# ------------------------------------------------------------------ estadistica de pruebas multiples
def bh(p, q=0.10):
    """Benjamini-Hochberg: mascara de descubrimientos a FDR q."""
    p = np.asarray(p, float); n = len(p); o = np.argsort(p)
    thr = q * np.arange(1, n + 1) / n
    ok = p[o] <= thr
    k = np.max(np.nonzero(ok)[0]) + 1 if ok.any() else 0
    m = np.zeros(n, bool); m[o[:k]] = True
    return m


def deflated_sharpe(sr, n_trials, T, skew=0.0, kurt=3.0, sr_var=None):
    """Probabilistic/Deflated Sharpe (Bailey & Lopez de Prado). sr: Sharpe por periodo (no anualizado),
    T: n de periodos, n_trials: variantes probadas, sr_var: varianza de los Sharpe de las variantes."""
    from scipy.stats import norm
    if sr_var is None:
        sr_var = 1.0 / T
    emc = 0.5772156649
    sr0 = np.sqrt(sr_var) * ((1 - emc) * norm.ppf(1 - 1 / n_trials) + emc * norm.ppf(1 - 1 / (n_trials * np.e)))
    z = (sr - sr0) * np.sqrt(T - 1) / np.sqrt(1 - skew * sr + (kurt - 1) / 4 * sr ** 2)
    return float(norm.cdf(z)), float(sr0)


def _selfcheck():
    low_priority()
    t0 = _time.time()
    E = entries()
    print("operaciones:", len(E), E.groupby("leg").size().to_dict(), f"({_time.time()-t0:.0f}s)")
    B = base_trades()
    print(f"base lista ({_time.time()-t0:.0f}s)", B.groupby("leg").R.agg(["size", "mean", "std"]).round(3).to_dict("index"))
    print("candados por pata:", B.groupby("leg").locked.mean().round(3).to_dict())
    for p in ("sel", "val", "selval"):
        m = evaluate(B, p)
        print(p, {k: round(v, 3) for k, v in m.items()})
    # calibracion contra el simulador M15 de referencia (broker_accounts.trades_fixed, escalera) en sel+val
    from bot_backtesting.fullsim.broker_accounts import trades_fixed
    R = trades_fixed(ladder=True)
    a, b = period("selval")
    R = R[(R.t >= a.timestamp()) & (R.t < b.timestamp())]
    Bs = clip(B, "selval")
    print("R medio por pata, M15 referencia (sin 01:01 ni desliz.) vs fino:")
    print(pd.DataFrame({"ref_m15": R.groupby("pata").r_mult.mean().rename({"momentum_eeuu": "momentum"}),
                        "n_ref": R.groupby("pata").size().rename({"momentum_eeuu": "momentum"}),
                        "fino": Bs.groupby("leg").R.mean(), "n_fino": Bs.groupby("leg").size()}).round(4))


if __name__ == "__main__":
    _selfcheck()
