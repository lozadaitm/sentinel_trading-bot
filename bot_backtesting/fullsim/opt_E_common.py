"""Linea E (patas nuevas poco correlacionadas / cartera) - piezas comunes. Solo simulacion, sin MT5, 2026 fuera.

Que hay aqui:
  * Sym(sym): velas M15 DEL BROKER de otro simbolo (data/broker_multi/<sym>.pkl) con ATR15 (14 velas cerradas,
    desplazado), ATR_D (media del rango de los 14 dias anteriores), tendencia s (signo C-C21 + signo C-C63 del
    dia anterior) y el costo por orden.
  * sim(sym, t_in, t_out, side): la gestion e2 (tercios hora / TP 2 / TP 3 ATR15 del simbolo, candado a
    -1 ATR_D del simbolo, cierre a la hora) sobre velas M15 con el lado en contra primero dentro de cada vela
    (no hay M5 de otros simbolos). Devuelve R = pnl / ATR_D (1 R = distancia del candado = riesgo de la pata).
    Las TP son limite fijo desde la entrada (no dependen del max/min de la misma vela).
  * gold_rows(...) + opt_base.run_trades: patas nuevas del ORO con el camino fino (M5/M1) de opt_base.
  * evaluate_mix / compare_mix: cartera e2 + patas nuevas con interes compuesto.
      - filas del oro (columna gold=True): igual que opt_base.evaluate (lotes reales: tercio = floor(lote/3; 0,01)).
      - filas de otros simbolos (gold=False): pnl = R y atrd = 1 -> ganancia = balance_al_entrar x 8 % x w x R
        (lote continuo: con 10 000 de cuenta y w>=0,25 el lote de indices/divisas es >= 0,1 por tercio, el
        redondeo es menor que en el oro; se dice en el informe).
    Comprobado: evaluate_mix(base) == opt_base.evaluate(base) (ver _selfcheck).
Costos de otros simbolos (conservadores; _info.csv no trae spread tipico):
  * spread = 1,25 x max(spread de la vela, mediana de los 60 dias previos a esa hora)  [en el oro el spread
    de las velas es ~1/1,2 del de los ticks: se calibro asi];
  * deslizamiento = 0,5 x ese spread por orden a mercado (entrada, salida por hora, candado; TP limite no);
  * comision: divisas y metales 0,006 % del nominal ida y vuelta (3 $/lote/lado RAW); indices, petroleo y
    demas CFD +0,002 % ida y vuelta de colchon (la cuenta RAW no cobra comision en CFD, se pone por las dudas);
  * swap por noche (si cruza las 00:00): divisas y metales con los puntos del broker (_info.csv), un credito
    cuenta como 0; resto de CFD: largo -6 %/360 del precio, corto -2 %/360 (sin creditos). Triple: miercoles
    en divisas/metales, viernes en CFD.
  * piso de spread de 2 puntos en divisas (las velas RAW traen spread 0 muchas veces);
  * nada entra entre 00:00 y 01:05 servidor (artefacto del rollover).
Uso: libreria. Autocomprobacion:  .venv/Scripts/python -m bot_backtesting.fullsim.opt_E_common
"""
import os

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.opt_base import (BAL, RISK, SEL, VAL, base_trades, boot_compare, daily_R, evaluate,
                                              low_priority, lots_of, m15, period, register, spread_at, swap_cost,
                                              bigger_lot, SLIP, BO_DELAY, RESULTS)

MDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "broker_multi")
INFO = pd.read_csv(os.path.join(MDIR, "_info.csv")).set_index("simbolo")
END = VAL[1].timestamp()          # nada de 2026
FXM = lambda s: s.endswith("+") or s.startswith(("XAG", "XPT"))   # noqa: E731  divisas y metales


class Sym:
    _cache = {}

    def __new__(cls, sym):
        if sym in cls._cache:
            return cls._cache[sym]
        o = super().__new__(cls)
        o._init(sym)
        cls._cache[sym] = o
        return o

    def _init(self, sym):
        self.sym = sym
        X = pd.read_pickle(os.path.join(MDIR, f"{sym}.pkl")).sort_values("time").reset_index(drop=True)
        X = X[X.time < END].reset_index(drop=True)
        pt = INFO.at[sym, "point"]
        self.T = X.time.values.astype(np.int64)
        self.O, self.H, self.L, self.C = (X[c].values.astype(float) for c in ("open", "high", "low", "close"))
        h, l, c = self.H, self.L, self.C
        tr = np.r_[h[0] - l[0], np.maximum(h[1:] - l[1:], np.maximum(abs(h[1:] - c[:-1]), abs(l[1:] - c[:-1])))]
        self.atr15 = pd.Series(tr).rolling(14).mean().shift(1).values
        sp = X.spread.values * pt
        slot = (self.T % 86400) // 900
        # mediana movil (60 dias habiles ~ 60 observaciones) del spread de esa franja, con datos ANTERIORES
        med = pd.Series(sp).groupby(slot).transform(lambda s: s.shift(1).rolling(60, min_periods=10).median()).values
        self.sp = 1.25 * np.fmax(sp, np.nan_to_num(med, nan=0.0))
        if FXM(sym):                                   # piso: 2 puntos (0,2 pip) en divisas, por las dudas
            self.sp = np.fmax(self.sp, 2 * pt)
        self.d = self.T // 86400
        D = X.assign(d=self.d).groupby("d").agg(O=("open", "first"), H=("high", "max"), L=("low", "min"),
                                                C=("close", "last"), n=("open", "size"))
        D["atrd"] = (D.H - D.L).rolling(14).mean().shift(1)
        D["s"] = (np.sign(D.C - D.C.shift(21)) + np.sign(D.C - D.C.shift(63))).shift(1)
        self.D = D
        self.idx = pd.Series(np.arange(len(self.T)), index=self.T)
        self.comm_pct = 0.006 if FXM(sym) else 0.002
        self.fx = FXM(sym)
        self.pt = pt

    def k_at(self, t):
        return self.idx.get(int(t))

    def swap_unit(self, side, px):
        """Swap por noche en unidades de precio por unidad de contrato (negativo = costo). Creditos = 0."""
        if self.fx:
            v = INFO.at[self.sym, "swap_l" if side == 1 else "swap_s"] * self.pt
            return min(v, 0.0)
        return -(0.06 if side == 1 else 0.02) / 360 * px

    def nights(self, t0, t1):
        tri = 2 if self.fx else 4
        n = 0
        for d in range(int(t0 // 86400), int(t1 // 86400)):
            dow = (d + 3) % 7
            if dow >= 5:
                continue
            n += 3 if dow == tri else 1
        return n


def sim(S, t_in, t_out, side, tps=(None, 2.0, 3.0), lock_k=1.0, fracs=None, atrd=None):
    """Gestion e2 sobre velas M15 de S (Sym) para una operacion que entra al open de la vela t_in y sale al cierre
    de la ultima vela antes de t_out. Devuelve dict(R, pnl, locked, atrd, n_bars) o None si faltan datos."""
    k0 = S.k_at(t_in)
    if k0 is None:
        return None
    k1 = int(np.searchsorted(S.T, t_out))           # velas [k0, k1)
    if k1 <= k0 or (t_in % 86400) < 3900:          # nada entra entre 00:00 y 01:05 servidor
        return None
    d = int(t_in // 86400)
    if d not in S.D.index:
        return None
    atrd = S.D.at[d, "atrd"] if atrd is None else atrd
    a15 = S.atr15[k0]
    if not (np.isfinite(atrd) and np.isfinite(a15)) or atrd <= 0:
        return None
    if S.T[k1 - 1] - S.T[k0] > (k1 - 1 - k0) * 900 + 3 * 86400 or k1 - k0 < 1:
        return None
    o, h, l, c = S.O[k0:k1], S.H[k0:k1], S.L[k0:k1], S.C[k0:k1]
    sp_in, sp_out = S.sp[k0], S.sp[k1 - 1]
    slip_in, slip_out = 0.5 * sp_in, 0.5 * sp_out
    mid = o[0]
    comm = S.comm_pct / 100 * mid
    if side == 1:
        px = mid + sp_in + slip_in
        fav, adv, opn, cls = h - px, l - px, o - px, c - px
    else:
        px = mid - slip_in
        fav, adv, opn, cls = px - (l + sp_out), px - (h + sp_out), px - (o + sp_out), px - (c + sp_out)
    n = len(fav)
    fracs = fracs or [1 / len(tps)] * len(tps)
    lockd = lock_k * atrd
    lk = np.nonzero(adv <= -lockd)[0]
    i_lock = lk[0] if len(lk) else n
    lock_px = min(opn[i_lock], -lockd) if i_lock < n else None
    pnls = []
    for tp in tps:
        if tp is not None:
            hit = np.nonzero(fav[:i_lock] >= tp * a15)[0]
            if len(hit):
                pnls.append(tp * a15 - comm)
                continue
        if i_lock < n:
            pnls.append(lock_px - comm - (sp_out + comm + slip_out))
        else:
            pnls.append(cls[-1] - comm - slip_out)
    t_end = S.T[k1 - 1] + 900
    sw = S.nights(t_in, t_end) * S.swap_unit(side, mid)
    pnl = float(np.dot(fracs, pnls)) + sw
    return dict(R=pnl / atrd, pnl=pnl, locked=i_lock < n, atrd=atrd, n_bars=n, t_end=t_end)


def leg_frame(S, plan, leg, tps=(None, 2.0, 3.0), lock_k=1.0, both=True):
    """plan: lista de (t_in, t_out, side_signal) ; side_signal = +1/-1 (lado de la regla).
    Devuelve DataFrame con R del lado de la regla y (si both) R_long / R_short para el nulo de lado al azar."""
    rows = []
    for t_in, t_out, side in plan:
        if t_in >= END:
            continue
        rl = sim(S, t_in, t_out, 1, tps, lock_k) if (both or side == 1) else None
        rs = sim(S, t_in, t_out, -1, tps, lock_k) if (both or side == -1) else None
        r = rl if side == 1 else rs
        if r is None or (both and (rl is None or rs is None)):
            continue
        rows.append(dict(leg=leg, sym=S.sym, t=int(t_in), t_out=int(r["t_end"]), side=int(side), R=r["R"],
                         R_long=rl["R"] if rl else np.nan, R_short=rs["R"] if rs else np.nan, locked=r["locked"]))
    F = pd.DataFrame(rows)
    if F.empty:
        return F
    F["day"] = pd.to_datetime(F.t, unit="s").dt.normalize()
    return F


# ------------------------------------------------------------------ oro: filas tipo entries()
def gold_rows(leg, plan, w=1.0):
    """plan: lista de (t_in, t_out, side). Filas con el esquema de opt_base.entries() (para run_trades)."""
    X, D = m15()
    T, O = X.time.values, X.open.values
    idx = pd.Series(np.arange(len(T)), index=T)
    rows = []
    for t_in, t_out, side in plan:
        k = idx.get(int(t_in)); d = int(t_in // 86400)
        if k is None or d not in D.index or not np.isfinite(D.at[d, "atrd"]) or not np.isfinite(X.atr15.iat[k]):
            continue
        if t_in >= END or (t_in % 86400) < 3900:
            continue
        rows.append((leg, int(t_in), int(t_in), int(t_out), int(side), w, D.at[d, "s"], 0, D.at[d, "atrd"],
                     X.atr15.iat[k], O[k], k))
    E = pd.DataFrame(rows, columns=["leg", "t", "t_in", "t_out", "side", "w", "state", "ev", "atrd", "atr15",
                                    "mid0", "k15"])
    if E.empty:
        return E
    E["spr_in"] = spread_at(E.t_in.values)
    E["spr_out"] = spread_at(E.t_out.values - 60)
    E["px"] = np.where(E.side == 1, E.mid0 + E.spr_in + SLIP, E.mid0 - SLIP)
    E["swap"] = [swap_cost(a, b, s) for a, b, s in zip(E.t_in, E.t_out, E.side)]
    E["day"] = pd.to_datetime(E.t, unit="s").dt.normalize()
    return E.sort_values("t").reset_index(drop=True)


# ------------------------------------------------------------------ cartera mixta
def base():
    B = base_trades().copy()
    B["gold"] = True
    B = B[B.t < END].reset_index(drop=True)
    return B


def as_rows(F, w, Rcol="R"):
    """Operaciones de otro simbolo -> filas de cartera (pnl=R, atrd=1, gold=False)."""
    G = pd.DataFrame(dict(leg=F.leg.values, t=F.t.values, t_out=F.t_out.values, w=float(w) if np.isscalar(w) else w,
                          pnl=F[Rcol].values, atrd=1.0, day=F.day.values, gold=False))
    G["R"] = G.pnl
    return G


def gold_as_rows(G, w):
    """Operaciones del oro ya simuladas (run_trades) -> filas de cartera con peso w (lotes reales)."""
    H = G[["leg", "t", "t_out", "pnl", "atrd", "day"]].copy()
    H["w"] = w; H["gold"] = True; H["R"] = H.pnl / H.atrd
    return H


def combine(B, *legs):
    cols = ["leg", "t", "t_out", "w", "pnl", "atrd", "day", "gold", "R"]
    return pd.concat([B[cols]] + [L[cols] for L in legs if L is not None and len(L)], ignore_index=True)


def evaluate_mix(T, per="sel", f=RISK, bal0=BAL):
    a, b = period(per) if isinstance(per, str) else per
    T = T[(T.t >= a.timestamp()) & (T.t < b.timestamp()) & (T.w > 0)].sort_values("t", kind="stable")
    ti, to, pnl, w, atr, gold = (T[c].values for c in ("t", "t_out", "pnl", "w", "atrd", "gold"))
    n = len(T)
    if n == 0:
        return dict(cagr=0, dd=0, mar=0, peor_dia=0, peor_mes=0, n=0, sharpe_d=0, x=1)
    ev = sorted([(ti[i], 0, i) for i in range(n)] + [(to[i], 1, i) for i in range(n)])
    eq, L, rows = bal0, np.zeros(n), []
    for t, kind, i in ev:
        if kind == 0:
            L[i] = lots_of(eq, f, w[i], atr[i]) * 100 if gold[i] else eq * f * w[i] / atr[i]
        else:
            eq += pnl[i] * L[i]
            rows.append((t, eq))
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
    cagr = x ** (1 / yrs) - 1 if x > 0 else -1.0
    return dict(cagr=cagr, dd=dd, mar=cagr / dd if dd > 0 else np.inf, peor_dia=float(dret.min()),
                peor_mes=float(mret.min()), n=n, sharpe_d=float(dret.mean() / dret.std() * np.sqrt(252)), x=x)


def daily(T, per):
    """sum(w x R) por dia de entrada (dias habiles del periodo)."""
    a, b = period(per) if isinstance(per, str) else per
    T = T[(T.t >= a.timestamp()) & (T.t < b.timestamp())]
    s = (T.w * T.pnl / T.atrd).groupby(T.day).sum()
    return s.reindex(pd.bdate_range(a, b - pd.Timedelta(days=1))).fillna(0.0)


_MB = {}


def compare_mix(C, B, per, label="", boot=True, f=RISK):
    """Como opt_base.compare pero para la cartera mixta. Nulo 'lote mayor' = base con el riesgo de la misma caida."""
    mc = evaluate_mix(C, per, f=f)
    if per not in _MB:
        _MB[per] = evaluate(B, per, f=f)
    mb = _MB[per]
    big = bigger_lot(B, mc["dd"], per)
    out = dict(label=label, per=per, mar_c=mc["mar"], mar_b=mb["mar"], mar_ratio=mc["mar"] / mb["mar"],
               cagr_c=mc["cagr"], cagr_b=mb["cagr"], dd_c=mc["dd"], dd_b=mb["dd"], cagr_lote_mayor=big["cagr"],
               f_lote_mayor=big["f"], mar_lote_mayor=big["cagr"] / mc["dd"] if mc["dd"] > 0 else np.nan,
               peor_dia_c=mc["peor_dia"], peor_dia_b=mb["peor_dia"], peor_mes_c=mc["peor_mes"],
               peor_mes_b=mb["peor_mes"], n_c=mc["n"], n_b=mb["n"], sharpe_c=mc["sharpe_d"], sharpe_b=mb["sharpe_d"])
    if boot:
        out.update(boot_compare(daily(C, per).values, daily_R(B, per).values, f=f))
    out["pasa"] = bool(out["mar_ratio"] >= 1.25 and mc["peor_dia"] >= mb["peor_dia"] - 1e-3
                       and mc["peor_mes"] >= mb["peor_mes"] - 1e-3)
    return out


def corr_daily(L, B, per):
    """Correlacion diaria (dias habiles) entre la pata nueva y e2 base."""
    a = daily(L, per); b = daily_R(B, per)
    if a.std() == 0:
        return np.nan
    return float(np.corrcoef(a.values, b.values)[0, 1])


def year_R(F, Rcol="R"):
    y = pd.to_datetime(F.t, unit="s").dt.year
    return F[Rcol].groupby(y).mean()


# ------------------------------------------------------------------ horas
def london_fix_server(day_ts, hh=16, mm=0):
    """Hora servidor (segundos epoch 'servidor') del fix de Londres hh:mm de ese dia. Servidor = NY + 7 h."""
    d = pd.Timestamp(day_ts, unit="s").normalize()
    lon = pd.Timestamp(d.year, d.month, d.day, hh, mm).tz_localize("Europe/London")
    ny = lon.tz_convert("America/New_York").tz_localize(None)
    srv = ny + pd.Timedelta(hours=7)
    return int(srv.value // 10 ** 9)


def tokyo_server(day_ts, hh=9, mm=55):
    d = pd.Timestamp(day_ts, unit="s").normalize()
    tk = pd.Timestamp(d.year, d.month, d.day, hh, mm).tz_localize("Asia/Tokyo")
    ny = tk.tz_convert("America/New_York").tz_localize(None)
    return int((ny + pd.Timedelta(hours=7)).value // 10 ** 9)


def floor15(t):
    return int(t - t % 900)


def weekdays(S, a=None, b=None):
    """Dias habiles (enteros, dias epoch servidor) con datos en S, dentro de [a,b)."""
    d = np.array(sorted(S.D.index))
    d = d[((d + 3) % 7) < 5]
    if a is not None:
        d = d[(d * 86400 >= a.timestamp()) & (d * 86400 < b.timestamp())]
    return d


def _selfcheck():
    low_priority()
    B = base()
    for p in ("sel", "val"):
        e1 = evaluate(B, p); e2 = evaluate_mix(B, p)
        print(p, "opt_base.evaluate MAR %.4f  evaluate_mix MAR %.4f | dd %.4f %.4f" % (e1["mar"], e2["mar"], e1["dd"], e2["dd"]))
    S = Sym("SP500")
    d0 = weekdays(S, *SEL)[100]
    print("SP500 dia", pd.Timestamp(d0, unit="D").date(), sim(S, d0 * 86400 + 16 * 3600 + 1800, d0 * 86400 + 23 * 3600, 1))
    print("fix Londres servidor:", [pd.Timestamp(london_fix_server(x), unit="s") for x in
                                    (pd.Timestamp("2024-01-10").timestamp(), pd.Timestamp("2024-03-20").timestamp(),
                                     pd.Timestamp("2024-07-10").timestamp())])


if __name__ == "__main__":
    _selfcheck()
