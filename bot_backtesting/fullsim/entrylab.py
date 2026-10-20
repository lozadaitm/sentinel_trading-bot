"""Probador de ENTRADAS: busca una entrada con ventaja real, despues de costes.

Cada regla devuelve eventos (t = cierre de la vela de decision, side +1/-1, scale = ATR de
la temporalidad de la regla). Cada evento se evalua en M5 con varias salidas (objetivo y
salida en contra en multiplos de scale, mas cierre por tiempo) con spread y comision.

Anti-suerte:
  * referencia al AZAR emparejada: para cada evento, 3 entradas en otros dias del mismo
    tramo, a la MISMA hora del dia y con el MISMO lado (descuenta la deriva del oro y los
    efectos de horario); la "ventaja" es senal - azar;
  * t de la ventaja agrupando por dia (eventos del mismo dia no son independientes);
  * seleccion SOLO con 2021-2023 (dentro de muestra); 2024-2026 (fuera de muestra) se
    reporta aparte y es el juez.

Uso: python -m bot_backtesting.fullsim.entrylab build      # arma data/bars_all.pkl
     python -m bot_backtesting.fullsim.entrylab run [familia ...]
"""
import os
import sys

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.harness import DATA, RESULTS

SPREAD, COMM = 0.20, 0.12
# Swap por onza y noche (symbol.json: -77,4 / +36,7 $/lote; 1 lote = 100 oz). Rollover a la
# medianoche del servidor, sin fines de semana, triple la noche que termina en miercoles.
SWAP_LONG, SWAP_SHORT, TRIPLE_DOW = -0.774, 0.367, 2


def swap_cost(t0, t1, side):
    """Swap $/oz acumulado por una posicion abierta de t0 a t1 (epoch servidor)."""
    d0, d1 = int(t0 // 86400), int(t1 // 86400)
    if d1 <= d0:
        return 0.0
    nights = 0
    for d in range(d0, d1):                 # el dia d termina en la medianoche d -> d+1
        dow = (d + 3) % 7                   # 1970-01-01 fue jueves (dow 3)
        if dow >= 5:
            continue
        nights += 3 if dow == TRIPLE_DOW else 1
    return nights * (SWAP_LONG if side == 1 else SWAP_SHORT)
IS_END = pd.Timestamp("2024-01-01").timestamp()
TPS = (0.5, 1.0, 2.0, 3.0, None)        # None = sin objetivo (solo tiempo / salida en contra)
SLS = (0.5, 1.0, 2.0, None)             # None = sin salida en contra (solo tiempo)


# ----------------------------------------------------------------------------- datos
def build():
    """M5 continuo: Dukascopy (2021 -> 2026-01-09) + broker (2026-01-12 ->), y M15/H1/H4/D1."""
    duka = pd.read_pickle(os.path.join(DATA, "frames_duka.pkl"))["M5"]
    brk = pd.read_pickle(os.path.join(DATA, "frames.pkl"))["M5"]
    m5 = pd.concat([duka[duka.time < brk.time.min()], brk]).drop_duplicates("time").sort_values("time")
    m5 = m5.reset_index(drop=True)[["time", "open", "high", "low", "close"]]
    idx = pd.to_datetime(m5.time, unit="s")
    out = {"M5": m5}
    for name, rule in (("M15", "15min"), ("H1", "1h"), ("H4", "4h"), ("D1", "1D")):
        r = m5.set_index(idx).resample(rule, label="left", closed="left").agg(
            {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna().reset_index()
        r["time"] = ((r["time"] - pd.Timestamp("1970-01-01")) // pd.Timedelta("1s")).astype("int64")
        out[name] = r[["time", "open", "high", "low", "close"]]
    pd.to_pickle(out, os.path.join(DATA, "bars_all.pkl"))
    for k, v in out.items():
        print(k, len(v), pd.to_datetime(v.time.iloc[0], unit="s"), "->", pd.to_datetime(v.time.iloc[-1], unit="s"))


def utc_offset_h(epoch_srv):
    """Horas que la hora de servidor va por delante de UTC (2 o 3, horario de verano de EE. UU.)."""
    t = pd.to_datetime(np.asarray(epoch_srv) - 2 * 3600, unit="s").tz_localize("UTC")
    ny = t.tz_convert("America/New_York")
    return np.where([x.dst().total_seconds() > 0 for x in ny], 3, 2)


def atr(df, n=14):
    h, l, c = df.high.values, df.low.values, df.close.values
    tr = np.r_[h[0] - l[0], np.maximum(h[1:] - l[1:], np.maximum(abs(h[1:] - c[:-1]), abs(l[1:] - c[:-1])))]
    return pd.Series(tr).rolling(n).mean().values


def ev(t, side, scale, hz, base="matched"):
    """base: 'matched' = azar a la MISMA hora del dia (anula efectos de horario);
    'anytime' = azar a cualquier hora (mide si el horario rinde mas que la deriva)."""
    return pd.DataFrame({"t": np.asarray(t, dtype="int64"), "side": np.asarray(side, dtype=int),
                         "scale": np.asarray(scale, dtype=float), "hz": hz, "base": base})


# ----------------------------------------------------------------------------- reglas
def _close_t(df, tf_s):
    return df.time.values + tf_s


def rule_donchian(B, tf, n, hz):
    """Ruptura: cierre por encima del maximo (debajo del minimo) de las n velas previas."""
    df = B[tf]; tfs = {"H1": 3600, "H4": 14400, "D1": 86400}[tf]
    hi = df.high.rolling(n).max().shift(1).values; lo = df.low.rolling(n).min().shift(1).values
    c = df.close.values; a = atr(df)
    up = c > hi; dn = c < lo
    # solo la primera vela de cada ruptura (evento), no el estado
    up &= ~np.r_[False, up[:-1]]; dn &= ~np.r_[False, dn[:-1]]
    m = (up | dn) & ~np.isnan(a)
    return ev(_close_t(df, tfs)[m], np.where(up, 1, -1)[m], a[m], hz)


def rule_ema_cross(B, tf, f, s, hz):
    df = B[tf]; tfs = {"H1": 3600, "H4": 14400, "D1": 86400}[tf]
    c = df.close
    d = np.sign(c.ewm(span=f, adjust=False).mean().values - c.ewm(span=s, adjust=False).mean().values)
    x = (d != np.r_[0, d[:-1]]) & (np.r_[0, d[:-1]] != 0)
    a = atr(df); m = x & ~np.isnan(a)
    return ev(_close_t(df, tfs)[m], d[m], a[m], hz)


def _utc_hm(df):
    """Hora UTC decimal del INICIO de cada vela y fecha UTC (por dia de sesion)."""
    off = utc_offset_h(df.time.values)
    u = pd.to_datetime(df.time.values - off * 3600, unit="s")
    return u.hour + u.minute / 60.0, u.normalize()


def rule_range_breakout(B, r0, r1, w0, w1, hz):
    """Rango UTC [r0, r1) de cada dia; primera vela M15 que CIERRA fuera del rango en [w0, w1)."""
    df = B["M15"]; hm, day = _utc_hm(df)
    a = atr(df)
    out_t, out_s, out_a = [], [], []
    g = pd.DataFrame({"hm": hm, "day": day, "h": df.high.values, "l": df.low.values, "c": df.close.values,
                      "t": df.time.values + 900, "a": a})
    for d, x in g.groupby("day"):
        rng = x[(x.hm >= r0) & (x.hm < r1)]
        win = x[(x.hm >= w0) & (x.hm < w1)]
        if len(rng) < 2 or win.empty:
            continue
        hi, lo = rng.h.max(), rng.l.min()
        hit = win[(win.c > hi) | (win.c < lo)]
        if hit.empty or np.isnan(hit.a.iloc[0]):
            continue
        r = hit.iloc[0]
        out_t.append(r.t); out_s.append(1 if r.c > hi else -1); out_a.append(r.a)
    return ev(out_t, out_s, out_a, hz)


def rule_intraday_momentum(B, f0, f1, e0, hz):
    """Signo del retorno UTC [f0, f1) del dia -> entrar en e0 en esa direccion."""
    df = B["M15"]; hm, day = _utc_hm(df)
    a = atr(df)
    g = pd.DataFrame({"hm": hm, "day": day, "o": df.open.values, "c": df.close.values,
                      "t": df.time.values + 900, "a": a})
    out_t, out_s, out_a = [], [], []
    for d, x in g.groupby("day"):
        fx = x[(x.hm >= f0) & (x.hm < f1)]
        en = x[(x.hm >= e0 - 0.25) & (x.hm < e0)]
        if len(fx) < 2 or en.empty or np.isnan(en.a.iloc[-1]):
            continue
        r = fx.c.iloc[-1] - fx.o.iloc[0]
        if r == 0:
            continue
        out_t.append(en.t.iloc[-1]); out_s.append(1 if r > 0 else -1); out_a.append(en.a.iloc[-1])
    return ev(out_t, out_s, out_a, hz)


def rule_squeeze(B, tf, n, pct, hz):
    """Compresion: ancho de Bollinger(n) en su percentil <= pct (ultimos 500) y ruptura de la banda."""
    df = B[tf]; tfs = {"M15": 900, "H1": 3600, "H4": 14400}[tf]
    c = df.close
    ma, sd = c.rolling(n).mean(), c.rolling(n).std()
    bw = (4 * sd / ma)
    rank = bw.rolling(500, min_periods=200).apply(lambda v: (v[:-1] < v[-1]).mean(), raw=True)
    sq = (rank.shift(1) <= pct).values
    up = (c > ma + 2 * sd).values & sq; dn = (c < ma - 2 * sd).values & sq
    a = atr(df); m = (up | dn) & ~np.isnan(a)
    return ev(_close_t(df, tfs)[m], np.where(up, 1, -1)[m], a[m], hz)


def rule_shock_fade(B, tf, k, hz):
    """Vela con rango >= k ATR: entrar en contra de su cuerpo al cierre."""
    df = B[tf]; tfs = {"M15": 900, "H1": 3600}[tf]
    a = atr(df); a1 = np.r_[np.nan, a[:-1]]
    rng = (df.high - df.low).values; body = (df.close - df.open).values
    m = (rng >= k * a1) & (body != 0) & ~np.isnan(a1)
    return ev(_close_t(df, tfs)[m], -np.sign(body[m]), a1[m], hz)


def rule_rsi2_trend(B, lo, hz):
    """Connors: RSI(2) H1 extremo en contra de la tendencia D1 (cierre D1 vs SMA200) -> a favor de D1."""
    h1, d1 = B["H1"], B["D1"]
    c = h1.close
    dlt = c.diff(); up = dlt.clip(lower=0).ewm(alpha=0.5, adjust=False).mean()
    dn = (-dlt.clip(upper=0)).ewm(alpha=0.5, adjust=False).mean()
    rsi = (100 - 100 / (1 + up / dn)).values
    sma = d1.close.rolling(200).mean()
    trend = np.sign(d1.close - sma).shift(1)          # tendencia del dia anterior (sin mirar el futuro)
    dmap = pd.Series(trend.values, index=d1.time.values // 86400)
    tr_h1 = dmap.reindex(h1.time.values // 86400).values
    a = atr(h1)
    long_ = (rsi < lo) & (tr_h1 == 1); short_ = (rsi > 100 - lo) & (tr_h1 == -1)
    m = (long_ | short_) & ~np.isnan(a)
    return ev(_close_t(h1, 3600)[m], np.where(long_, 1, -1)[m], a[m], hz)


# ---- tanda 2 (docs/experimento-2/investigacion/entradas-oro-evidencia-2026-10-20.md)
def _srv_hour(df):
    return pd.to_datetime(df.time.values, unit="s").hour.values


def rule_session_drift(B, h_in, h_out, side, minute=0):
    """Deriva por horario: entrar todos los dias habiles a la hora de servidor h_in:minute, salir en h_out."""
    df = B["M15"]; h = _srv_hour(df); mi = pd.to_datetime(df.time.values, unit="s").minute.values
    a = atr(df)
    dow = pd.to_datetime(df.time.values, unit="s").dayofweek.values
    m = (h == h_in) & (mi == minute) & (dow < 5) & ~np.isnan(a)
    hz = ((h_out - h_in) % 24) - minute / 60.0
    return ev(df.time.values[m], np.full(m.sum(), side), a[m], hz, base="anytime")


def _tsmom_state(B):
    """Por dia de servidor: s = signo(C-C21) + signo(C-C63) del D1 ANTERIOR (sin mirar el futuro)."""
    d = B["D1"]; c = d.close
    s = (np.sign(c - c.shift(21)) + np.sign(c - c.shift(63))).shift(1)
    return pd.Series(s.values, index=d.time.values // 86400)


def rule_drift_regime(B, h_in, h_out, side, need, minute=0):
    """Deriva por horario SOLO si el momentum diario cumple `need` (+2, -2 o '<=0')."""
    E = rule_session_drift(B, h_in, h_out, side, minute)
    st = _tsmom_state(B).reindex(E.t.values // 86400).values
    m = (st == need) if need in (2, -2) else (st <= 0)
    return E[m].reset_index(drop=True)


def rule_tsmom(B, hold_days):
    """Momentum de serie temporal diario: s = signo(C-C21) + signo(C-C63); |s| = 2 -> ese lado."""
    d = B["D1"]; c = d.close
    s = np.sign(c - c.shift(21)) + np.sign(c - c.shift(63))
    a = atr(d)
    m = (s.abs() == 2).values & ~np.isnan(a)
    return ev(d.time.values[m] + 86400, np.sign(s.values[m]), a[m], 24 * hold_days)


def rule_rod_momentum(B, pct=0.7):
    """Momentum hacia el cierre COMEX: ROD = C(20:00)/C(00:00)-1 del dia (hora servidor);
    si |ROD| > percentil pct de 60 dias, operar en su direccion de 20:00 a 20:30."""
    df = B["M15"]; t = pd.to_datetime(df.time.values, unit="s")
    g = pd.DataFrame({"day": t.normalize(), "h": t.hour, "mi": t.minute, "o": df.open.values,
                      "c": df.close.values, "tt": df.time.values})
    a = atr(df)
    rows = []
    for d, x in g.groupby("day"):
        o = x.iloc[[0]]; e = x[(x.h == 19) & (x.mi == 45)]
        if o.empty or e.empty or d.dayofweek >= 5:
            continue
        rows.append((e.tt.iloc[0] + 900, e.c.iloc[0] / o.o.iloc[0] - 1, a[e.index[0]]))
    R = pd.DataFrame(rows, columns=["t", "rod", "a"])
    thr = R.rod.abs().rolling(60, min_periods=30).quantile(pct).shift(1)
    m = (R.rod.abs() > thr) & R.a.notna()
    return ev(R.t[m], np.sign(R.rod[m]), R.a[m], 0.5)


def rule_fade_extreme_day(B, k=1.5):
    """Dia con |C-O| > k ATR(14, D1): al dia siguiente, de 03:00 a 23:00, en contra."""
    d = B["D1"]; a = atr(d)
    body = (d.close - d.open).values
    a1 = np.r_[np.nan, a[:-1]]
    m = (np.abs(body) > k * a1) & ~np.isnan(a1)
    t_in = d.time.values[m] + 86400 + 3 * 3600
    return ev(t_in, -np.sign(body[m]), a1[m] / 4, 20)


# ---- tanda 4: ideas del punto 2 (20-oct)
def rule_noise_band(B, lookback=14, mult=1.0, h0=10, h1=22):
    """Zarattini: banda = apertura del dia (primera vela) * (1 +- media de |C_tau/O - 1| en los
    `lookback` dias previos a la MISMA hora tau). Chequeo en HH:00 y HH:30 entre h0 y h1 (servidor):
    cierre fuera de la banda -> entrar en esa direccion (una vez por dia), salir a las 23:00."""
    df = B["M15"]; t = pd.to_datetime(df.time.values, unit="s")
    g = pd.DataFrame({"day": t.normalize(), "hm": t.hour * 60 + t.minute, "o": df.open.values,
                      "c": df.close.values, "tt": df.time.values + 900})
    g["o_day"] = g.groupby("day").o.transform("first")
    g["mv"] = (g.c / g.o_day - 1).abs()
    piv = g.pivot_table(index="day", columns="hm", values="mv")
    sigma = piv.rolling(lookback, min_periods=lookback).mean().shift(1)
    g["sig"] = sigma.stack().reindex(pd.MultiIndex.from_arrays([g.day, g.hm])).values
    a = atr(df)
    g["a"] = a
    chk = g[(g.hm % 30 == 15) & (g.hm >= h0 * 60) & (g.hm <= h1 * 60) & g.sig.notna() & g.a.notna()]
    up = chk.c > chk.o_day * (1 + mult * chk.sig); dn = chk.c < chk.o_day * (1 - mult * chk.sig)
    hit = chk[up | dn].copy(); hit["side"] = np.where(up[up | dn], 1, -1)
    hit = hit[hit.day.dt.dayofweek < 5].groupby("day").head(1)
    hz = (23 * 60 - (hit.hm + 15)) / 60.0
    out = ev(hit.tt, hit.side, hit.a, 1.0)
    out["hz"] = hz.values
    return out


def _events_srv(kinds):
    """Instantes (epoch servidor) de las publicaciones de events_us.csv de los tipos dados."""
    E = pd.read_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "events_us.csv"))
    E = E[E.event.isin(kinds)]
    u = pd.to_datetime(E.date + " " + E.time_utc).dt.tz_localize("UTC")
    off = np.where([x.dst().total_seconds() > 0 for x in u.dt.tz_convert("America/New_York")], 3, 2)
    return (u.dt.tz_localize(None) - pd.Timestamp("1970-01-01")) // pd.Timedelta("1s") + off * 3600


def rule_event(B, kinds, k, hz, follow=True):
    """Tras la publicacion: si la vela M15 que empieza en ella mueve |C-O| > k ATR, entrar al
    cierre de esa vela a favor (follow) o en contra."""
    df = B["M15"]; a = atr(df); T = df.time.values
    out_t, out_s, out_a = [], [], []
    for te in _events_srv(kinds).values:
        i = np.searchsorted(T, te)
        if i >= len(T) or T[i] != te or i == 0 or np.isnan(a[i - 1]):
            continue
        mv = df.close.values[i] - df.open.values[i]
        if abs(mv) > k * a[i - 1]:
            out_t.append(T[i] + 900); out_s.append(int(np.sign(mv)) * (1 if follow else -1)); out_a.append(a[i - 1])
    return ev(out_t, out_s, out_a, hz)


def _cross_m15(name, times):
    """Cierre y volumen M15 de una serie de data/cross_<name>.pkl alineados a `times` (inicio de vela)."""
    x = pd.read_pickle(os.path.join(DATA, f"cross_{name}.pkl"))
    idx = pd.to_datetime(x.time, unit="s")
    r = x.set_index(idx).resample("15min", label="left", closed="left").agg({"close": "last", "volume": "sum"})
    r.index = (r.index - pd.Timestamp("1970-01-01")) // pd.Timedelta("1s")
    r = r.reindex(times)
    r["close"] = r.close.ffill(limit=2)
    return r


def _zret(c, w, n=500):
    r = pd.Series(np.log(c)).diff(w)
    return (r / r.rolling(n, min_periods=200).std()).values


def rule_leadlag(B, name, sign, w=2, z_in=2.0, z_gold=0.5, hz=2):
    """Otro mercado se mueve |z| > z_in en w velas M15 y el oro casi no (|z| < z_gold):
    entrar en el oro en la direccion esperada (sign = +1 mismo sentido, -1 contrario)."""
    df = B["M15"]; T = df.time.values
    x = _cross_m15(name, T)
    zx = _zret(x.close.values, w); zg = _zret(df.close.values, w)
    a = atr(df)
    m = (np.abs(zx) > z_in) & (np.abs(zg) < z_gold) & ~np.isnan(a)
    m &= ~np.r_[False, m[:-1]]                    # una entrada por episodio
    return ev(T[m] + 900, sign * np.sign(zx[m]), a[m], hz)


def rule_volume_spike(B, k_vol=3.0, k_body=1.0, follow=True, hz=2):
    """Vela M15 con volumen > k_vol x mediana de 5 dias y cuerpo > k_body ATR: seguir o ir en contra."""
    df = B["M15"]; T = df.time.values
    v = _cross_m15("xau", T).volume.values
    med = pd.Series(v).rolling(96 * 5, min_periods=96).median().shift(1).values
    a = atr(df); a1 = np.r_[np.nan, a[:-1]]
    body = (df.close - df.open).values
    m = (v > k_vol * med) & (np.abs(body) > k_body * a1) & ~np.isnan(a1)
    return ev(T[m] + 900, np.sign(body[m]) * (1 if follow else -1), a1[m], hz)


def rule_vwap_fade(B, k=2.0, hz=2, h0=9, h1=21):
    """VWAP del dia (desde la primera vela, volumen de ticks): cierre a > k ATR del VWAP -> en contra."""
    df = B["M15"]; T = df.time.values; t = pd.to_datetime(T, unit="s")
    v = _cross_m15("xau", T).volume.fillna(0).values
    tp = ((df.high + df.low + df.close) / 3).values
    g = pd.DataFrame({"day": t.normalize(), "pv": tp * v, "v": v})
    vw = (g.groupby("day").pv.cumsum() / g.groupby("day").v.cumsum().replace(0, np.nan)).values
    a = atr(df); c = df.close.values
    dev = (c - vw) / a
    m = (np.abs(dev) > k) & (t.hour >= h0) & (t.hour < h1) & ~np.isnan(dev)
    m &= ~np.r_[False, m[:-1]]
    return ev(T[m] + 900, -np.sign(dev[m]), a[m], hz)


def families(B):
    F = {}
    for tf, n, hz in (("H4", 20, 72), ("H4", 55, 120), ("D1", 20, 240), ("D1", 55, 480), ("H1", 48, 24)):
        F[f"donchian_{tf}_{n}"] = lambda tf=tf, n=n, hz=hz: rule_donchian(B, tf, n, hz)
    for tf, f, s, hz in (("H4", 20, 50, 120), ("D1", 10, 50, 480), ("H1", 20, 100, 48)):
        F[f"ema_{tf}_{f}_{s}"] = lambda tf=tf, f=f, s=s, hz=hz: rule_ema_cross(B, tf, f, s, hz)
    F["asia_london"] = lambda: rule_range_breakout(B, 0, 7, 7, 10, 8)
    F["ny_orb"] = lambda: rule_range_breakout(B, 13.5, 14, 14, 16, 4)
    F["london_orb"] = lambda: rule_range_breakout(B, 7, 8, 8, 11, 6)
    F["imom_ny"] = lambda: rule_intraday_momentum(B, 13.5, 14, 19.5, 2)
    F["imom_day"] = lambda: rule_intraday_momentum(B, 0, 14, 14.25, 6)
    F["squeeze_M15"] = lambda: rule_squeeze(B, "M15", 20, 0.1, 8)
    F["squeeze_H1"] = lambda: rule_squeeze(B, "H1", 20, 0.1, 24)
    F["shock_fade_M15"] = lambda: rule_shock_fade(B, "M15", 3.0, 4)
    F["shock_fade_H1"] = lambda: rule_shock_fade(B, "H1", 2.5, 12)
    F["rsi2_trend"] = lambda: rule_rsi2_trend(B, 5, 48)
    # tanda 2
    F["drift_asia_long"] = lambda: rule_session_drift(B, 1, 10, 1)
    F["drift_asia3_long"] = lambda: rule_session_drift(B, 3, 10, 1)
    F["drift_ny_short"] = lambda: rule_session_drift(B, 16, 23, -1)
    F["drift_asia_long_0115"] = lambda: rule_session_drift(B, 1, 10, 1, 15)
    F["drift_asia_long_0200"] = lambda: rule_session_drift(B, 2, 10, 1)
    F["drift_asia_long_0100_0600"] = lambda: rule_session_drift(B, 1, 6, 1)
    F["drift_ny_short_1500"] = lambda: rule_session_drift(B, 15, 23, -1)
    # tanda 3 (fijadas de antemano): horario + momentum diario
    F["asia_long_if_up"] = lambda: rule_drift_regime(B, 1, 10, 1, 2)
    F["asia_long_if_up_0115"] = lambda: rule_drift_regime(B, 1, 10, 1, 2, 15)
    F["asia_long_if_up_0200"] = lambda: rule_drift_regime(B, 2, 10, 1, 2)
    # tanda 4
    F["noise_band"] = lambda: rule_noise_band(B)
    F["noise_band_15"] = lambda: rule_noise_band(B, mult=1.5)
    for kinds, nm in ((["FOMC"], "fomc"), (["NFP", "CPI"], "nfpcpi")):
        F[f"event_{nm}_follow"] = lambda kinds=kinds: rule_event(B, kinds, 1.0, 4)
        F[f"event_{nm}_fade"] = lambda kinds=kinds: rule_event(B, kinds, 1.0, 4, follow=False)
    for name, sign in (("xag", 1), ("eurusd", 1), ("dxy", -1), ("ustbond", 1)):
        if os.path.exists(os.path.join(DATA, f"cross_{name}.pkl")):
            F[f"leadlag_{name}"] = lambda name=name, sign=sign: rule_leadlag(B, name, sign)
    if os.path.exists(os.path.join(DATA, "cross_xau.pkl")):
        F["volume_spike_follow"] = lambda: rule_volume_spike(B)
        F["volume_spike_fade"] = lambda: rule_volume_spike(B, follow=False)
        F["vwap_fade"] = lambda: rule_vwap_fade(B)
    if os.path.exists(os.path.join(DATA, "ml_dir_events.pkl")):
        F["ml_dir"] = lambda: pd.read_pickle(os.path.join(DATA, "ml_dir_events.pkl"))
    F["ny_short_if_notup"] = lambda: rule_drift_regime(B, 16, 23, -1, "<=0")
    F["ny_short_if_down"] = lambda: rule_drift_regime(B, 16, 23, -1, -2)
    for hd in (1, 3, 5):
        F[f"tsmom_{hd}d"] = lambda hd=hd: rule_tsmom(B, hd)
    F["rod_momentum"] = lambda: rule_rod_momentum(B)
    F["fade_extreme_day"] = lambda: rule_fade_extreme_day(B)
    return F


# ----------------------------------------------------------------------------- evaluacion
class Evaluator:
    def __init__(self, B):
        m5 = B["M5"]
        self.T, self.H, self.L, self.C = m5.time.values, m5.high.values, m5.low.values, m5.close.values
        self.O = m5.open.values
        m15 = B["M15"]
        self.t15 = m15.time.values + 900
        self.a15 = atr(m15)

    def outcome(self, t, side, scale, hz):
        """{(tp, sl): pnl $/oz} de una entrada en t: a la APERTURA de la primera vela M5 que
        empieza en/tras t (no al cierre de la anterior: tras la pausa diaria habria un salto)."""
        k = np.searchsorted(self.T, t)
        if k <= 0 or k >= len(self.T):
            return None
        px0 = self.O[k]
        n = min(int(hz * 12), len(self.T) - k)
        if n < 6:
            return None
        H, L, C = self.H[k:k + n], self.L[k:k + n], self.C[k:k + n]
        if side == 1:
            px = px0 + SPREAD
            fav, adv, last = np.maximum.accumulate((H) - px), np.maximum.accumulate(px - L), C[-1] - px
        else:
            px = px0
            fav, adv, last = np.maximum.accumulate(px - (L + SPREAD)), np.maximum.accumulate((H + SPREAD) - px), \
                px - (C[-1] + SPREAD)
        res = {}
        t_in = self.T[k]
        for tp in TPS:
            i_tp = np.searchsorted(fav, tp * scale) if tp else n
            for sl in SLS:
                i_sl = np.searchsorted(adv, sl * scale) if sl else n
                if i_sl < n and i_sl <= i_tp:
                    r, i_out = -sl * scale, i_sl
                elif i_tp < n:
                    r, i_out = tp * scale, i_tp
                else:
                    r, i_out = last, n - 1
                res[(tp, sl)] = r - COMM + swap_cost(t_in, self.T[k + i_out] + 300, side)
        return res

    def evaluate(self, E, rng, reps=3):
        rows = []
        day_s = 86400
        t_min, t_max = self.T[0] + 30 * day_s, self.T[-1] - 10 * day_s
        for e in E.itertuples():
            o = self.outcome(e.t, e.side, e.scale, e.hz)
            if o is None:
                continue
            # azar emparejado: misma hora del dia, mismo lado, otro dia del mismo tramo (IS/OOS)
            lo, hi = (t_min, IS_END) if e.t < IS_END else (IS_END, t_max)
            base = {k: [] for k in o}
            for _ in range(reps):
                for _try in range(10):
                    shift = int(rng.integers(1, 400)) * day_s * (1 if rng.random() < 0.5 else -1)
                    if e.base == "anytime":
                        shift += int(rng.integers(0, 96)) * 900
                    tr = e.t + shift
                    if lo <= tr <= hi and pd.Timestamp(tr, unit="s").dayofweek < 5:
                        break
                else:
                    continue
                j = np.searchsorted(self.t15, tr) - 1
                sc = self.a15[j] if j >= 0 and not np.isnan(self.a15[j]) else e.scale
                if e.scale and sc:
                    sc = e.scale * (sc / max(1e-9, self.a15[np.searchsorted(self.t15, e.t) - 1]))
                ob = self.outcome(tr, e.side, sc, e.hz)
                if ob:
                    for k in o:
                        base[k].append(ob[k])
            for k, v in o.items():
                b = np.mean(base[k]) if base[k] else np.nan
                rows.append((e.t, e.side, k[0] or 0, k[1] or 0, v, b))
        R = pd.DataFrame(rows, columns=["t", "side", "tp", "sl", "pnl", "rnd"])
        R["day"] = R.t // day_s
        R["is"] = R.t < IS_END
        R["year"] = pd.to_datetime(R.t, unit="s").dt.year
        return R


def summarize(name, R):
    out = []
    for (tp, sl), g in R.groupby(["tp", "sl"]):
        row = dict(rule=name, tp=tp, sl=sl)
        for part, gg in (("is", g[g["is"]]), ("oos", g[~g["is"]])):
            gg = gg.dropna(subset=["rnd"])
            d = gg.assign(edge=gg.pnl - gg.rnd).groupby("day").agg(edge=("edge", "mean"), pnl=("pnl", "mean"))
            n = len(gg)
            row[f"n_{part}"] = n
            row[f"pnl_{part}"] = gg.pnl.mean() if n else np.nan
            row[f"edge_{part}"] = d.edge.mean() if len(d) else np.nan
            row[f"t_{part}"] = d.edge.mean() / (d.edge.std(ddof=1) / np.sqrt(len(d))) if len(d) > 5 else np.nan
        yrs = g.dropna(subset=["rnd"]).assign(edge=lambda x: x.pnl - x.rnd).groupby("year").edge.mean()
        row["years_pos"] = f"{int((yrs > 0).sum())}/{len(yrs)}"
        out.append(row)
    return pd.DataFrame(out)


def run(names=None):
    B = pd.read_pickle(os.path.join(DATA, "bars_all.pkl"))
    F = families(B)
    ev_ = Evaluator(B)
    rng = np.random.default_rng(11)
    os.makedirs(RESULTS, exist_ok=True)
    allsum = []
    for name, fn in F.items():
        if names and name not in names:
            continue
        E = fn()
        R = ev_.evaluate(E, rng)
        R.to_pickle(os.path.join(RESULTS, f"entry_{name}.pkl"))
        S = summarize(name, R)
        if S.empty:
            print(f"{name:18s} eventos {len(E):5d} | sin resultados", flush=True)
            continue
        allsum.append(S)
        best = S.sort_values("t_is", ascending=False).iloc[0]
        print(f"{name:18s} eventos {len(E):5d} | mejor IS: tp {best.tp} sl {best.sl} "
              f"pnl_is {best.pnl_is:+.2f} ventaja_is {best.edge_is:+.2f} (t {best.t_is:+.1f}) | "
              f"OOS pnl {best.pnl_oos:+.2f} ventaja {best.edge_oos:+.2f} (t {best.t_oos:+.1f}) anos+ {best.years_pos}",
              flush=True)
    A = pd.concat(allsum, ignore_index=True)
    A.to_pickle(os.path.join(RESULTS, "entry_summary.pkl"))
    return A


if __name__ == "__main__":
    if sys.argv[1] == "build":
        build()
    else:
        run(sys.argv[2:] or None)
